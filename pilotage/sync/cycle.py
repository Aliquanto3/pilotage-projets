"""Cycle `sync` en étapes nommées, sous le mutex tenu par l'appelant (story 3.1, AD-5 §4).

Ordre : contrôle `isPrivate`, clone ou pull, copie des états du PC, opérations (story 5.1,
AD-5 §7), scan, copie de l'instantané, commit par liste de chemins, nouveau
contrôle `isPrivate`, push. L'archivage (AD-5 §4.5, story 3.3) et la reprise sur erreur (story 3.2)
s'accrochent à `ETAPES`. Alertes de source `sync` remplacées à chaque cycle (AD-5 §9), en
`code` + `params` du catalogue `noyau.alertes` (M8) : jamais le texte d'une exception ni une
sortie git.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import alertes as catalogue
from pilotage.noyau import schemas
from pilotage.scan import api as scan_api
from pilotage.scan import inventaire
from pilotage.sync import archivage, copie, depot, operations

SOURCE = "sync"
ALERTE_PUBLIC = catalogue.DEPOT_PUBLIC
ALERTE_NON_CONFIGURE = catalogue.DEPOT_NON_CONFIGURE
ALERTE_ECHEC = catalogue.SYNC_ECHEC
ALERTE_IGNORES = catalogue.FICHIERS_IGNORES
ALERTE_CONFLIT = catalogue.SYNC_CONFLIT
ALERTE_PUSH = catalogue.SYNC_PUSH_REFUSE
ALERTE_PROJETS = catalogue.PROJETS_NON_COMMITE
CODE_FAIT, CODE_ECHEC = 0, 1

Alerte = tuple[str, dict[str, str]]  # (code, params)


def alerte_echec(etape: str) -> Alerte:
    return (ALERTE_ECHEC, {"etape": etape})


def alerte_abandon(code: str, motif: str) -> Alerte:
    return (code, {"instant": catalogue.instant(_maintenant()), "motif": motif})


@dataclass
class Contexte:
    pc: str
    racine_github: Path
    donnees: Path = field(default_factory=chemins.donnees)
    relatifs: list[str] = field(default_factory=list)  # chemins à `git add`
    ignores: int = 0
    commit: bool = False
    mutex_abandonne: bool = False  # `WAIT_ABANDONED` : le cycle précédent est mort en route
    operations: list = field(default_factory=list)  # identifiants figés à l'étape 4 (5.1)
    projets_exclu: bool = False  # projets.yaml modifié mais invalide ou plus récent : non commité
    # Dépôt de données lu une fois au premier contrôle (story 7.1) : clone, pull et push visent
    # la valeur contrôlée, même si `config.json` change pendant le cycle.
    depot_donnees: str | None = None


def _maintenant() -> datetime:
    return datetime.now().astimezone()  # heure locale du PC (substituable en test)


def message_commit(pc: str, instant: datetime) -> str:
    return f"etat({pc}): {instant:%Y-%m-%d %H:%M}"


def _controle_prive(ctx: Contexte) -> None:
    if ctx.depot_donnees is None:
        ctx.depot_donnees = depot.depot_attendu()
    depot.controler_prive(ctx.donnees, ctx.depot_donnees)


def _tirer(ctx: Contexte) -> None:
    if not depot.est_clone(ctx.donnees):
        depot.cloner(ctx.donnees, ctx.depot_donnees)
    depot.verifier_clone(ctx.donnees)
    depot.tirer(ctx.donnees)


def _copier_attente(ctx: Contexte) -> None:
    relatifs, ignores = copie.copier_etats(ctx.pc, str(ctx.racine_github))
    ctx.relatifs += relatifs
    ctx.ignores += ignores
    relatifs, ignores = copie.copier_acquittements(ctx.pc)  # story 5.3
    ctx.relatifs += relatifs
    ctx.ignores += ignores


def _scanner(ctx: Contexte) -> None:
    """Scan sous le mutex déjà tenu. Un échec du scan n'arrête pas la synchro : il est signalé
    par une alerte de source `scan`, et l'instantané précédent reste en place."""
    try:
        scan_api.ecrire_alertes_scan(scan_api.scanner(ctx.racine_github, ctx.pc))
    except Exception:  # noqa: BLE001 (même traitement que `lancer.py scan`)
        scan_api.ecrire_alertes_scan(
            [{"code": scan_api.ALERTE_ECHEC, "message": scan_api.MESSAGE_ECHEC}]
        )


def _copier_instantane(ctx: Contexte) -> None:
    relatifs, ignores = copie.copier_instantane(ctx.pc)
    ctx.relatifs += relatifs
    ctx.ignores += ignores


def _commiter(ctx: Contexte) -> None:
    relatifs = list(ctx.relatifs)
    projets = ctx.donnees / "projets.yaml"
    if projets.is_file() and copie.sans_lien(ctx.donnees, "projets.yaml"):
        config, recent, _ = inventaire.lire_projets(projets)
        if config is not None and not recent:
            relatifs.append("projets.yaml")  # édité à la main dans le clone (AD-3)
        elif depot.git(["diff", "--quiet", "HEAD", "--", "projets.yaml"], ctx.donnees).returncode:
            ctx.projets_exclu = True  # M7 : jamais commité invalide ni d'un schema plus récent
    ctx.commit = depot.commiter(ctx.donnees, relatifs, message_commit(ctx.pc, _maintenant()))


def _pousser(ctx: Contexte) -> None:
    depot.pousser(ctx.donnees)


def journaliser(texte: str) -> None:
    """Une ligne `AAAA-MM-JJ HH:MM texte` dans `attente/journal/sync-AAAA-MM.log` (texte fixe,
    jamais une sortie git). Un journal inécrivable n'arrête pas le cycle."""
    instant = _maintenant()
    chemin = chemins.journal_sync(f"{instant:%Y-%m}")
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"{instant:%Y-%m-%d %H:%M} {texte}\n")
    except OSError:
        pass


def _reprendre(ctx: Contexte) -> None:
    """Étape 0 (AD-5 §1, M3) : avant toute autre, à chaque acquisition du mutex, abandonne le
    rebase en cours, rétablit l'arbre propre sur `donnees`, journalise la reprise. Locale : aucun
    accès réseau. Sans clone, rien à rétablir."""
    actions = ["mutex abandonné"] if ctx.mutex_abandonne else []
    if depot.est_clone(ctx.donnees):
        depot.verifier_racine(ctx.donnees)
        actions += depot.reprendre(ctx.donnees)
    if actions:
        journaliser("reprise : " + ", ".join(actions))


def _archiver(ctx: Contexte) -> None:
    """Archivage des sessions de plus de 7 jours et rotation des journaux (AD-5 §4.5, story 3.3).
    Après le pull (le retrait de `donnees/` s'applique au clone à jour), avant la copie : une
    session archivée n'est pas recopiée. La suppression part avec le commit du cycle."""
    instant = _maintenant()
    retires, nombre = archivage.archiver_sessions(ctx.pc, instant.astimezone(UTC), journaliser)
    ctx.relatifs += retires
    supprimes = archivage.faire_tourner_journaux(instant)
    if nombre or supprimes:
        journaliser(
            f"archivage : {nombre} session(s) archivée(s), {supprimes} journal(aux) supprimé(s)"
        )


ETAPES: list[tuple[str, Callable[[Contexte], None]]] = [
    ("reprise", _reprendre),
    ("controle-prive", _controle_prive),
    ("pull", _tirer),
    ("archivage", _archiver),
    ("copie-attente", _copier_attente),
    ("operations", operations.appliquer),
    ("scan", _scanner),
    ("copie-instantane", _copier_instantane),
    ("commit", _commiter),
    ("controle-prive-envoi", _controle_prive),
    ("push", _pousser),
    ("operations-nettoyage", operations.nettoyer),
]


def _lire_alertes() -> list[dict]:
    chemin = chemins.alertes_json()
    try:
        objet = json.loads(chemin.read_text(encoding="utf-8"))
        schemas.valider("alertes", objet)
    except (OSError, ValueError):  # absent, illisible ou invalide : remplacé
        return []
    return objet["alertes"]


def ecrire_alertes(nouvelles: list[Alerte]) -> None:
    """Remplace les alertes de source `sync` ; celles des autres sources sont conservées."""
    gardees = [a for a in _lire_alertes() if a["source"] != SOURCE]
    ajout = [{"source": SOURCE, "code": c, "params": p} for c, p in nouvelles]
    objet = {"schema": 1, "alertes": gardees + ajout}
    schemas.valider("alertes", objet)
    chemins.ecrire_atomique(
        chemins.alertes_json(), json.dumps(objet, ensure_ascii=False, indent=2) + "\n"
    )


def _jouer(ctx: Contexte) -> tuple[list[Alerte], int, bool]:
    """Un passage sur `ETAPES` : (alertes, code, push refusé en non-fast-forward)."""
    for nom, etape in ETAPES:
        try:
            etape(ctx)
        except depot.DepotNonPrive:
            return [(ALERTE_PUBLIC, {})], CODE_ECHEC, False
        except chemins.ConfigurationGithubAbsente:  # `depot_donnees` : aucun accès réseau tenté
            return [(ALERTE_NON_CONFIGURE, {})], CODE_ECHEC, False
        except depot.ConflitAutostash as erreur:
            motif = catalogue.MOTIFS[catalogue.MOTIF_AUTOSTASH]
            journaliser(f"pull : {motif} {erreur.stash}".rstrip())
            alerte = alerte_abandon(ALERTE_CONFLIT, catalogue.MOTIF_AUTOSTASH)
            return [alerte], CODE_ECHEC, False
        except depot.ConflitRebase:
            return [alerte_abandon(ALERTE_CONFLIT, catalogue.MOTIF_REBASE)], CODE_ECHEC, False
        except depot.NonFastForward:
            return [], CODE_ECHEC, True
        except Exception:  # noqa: BLE001 (tout échec devient une alerte)
            return [alerte_echec(nom)], CODE_ECHEC, False
    return [], CODE_FAIT, False


def executer(ctx: Contexte) -> int:
    """Joue `ETAPES` dans l'ordre ; la première en échec arrête le cycle (code 1, alerte).

    Un push refusé en non-fast-forward rejoue une seule fois le cycle complet (contrôles
    `isPrivate` compris), puis abandonne avec une alerte (AD-5 §6).
    """
    alertes, code, refuse = _jouer(ctx)
    if refuse:
        journaliser("push refusé (non-fast-forward) : nouvel essai du cycle")
        ctx.relatifs, ctx.ignores, ctx.commit = [], 0, False
        ctx.projets_exclu = False
        alertes, code, refuse = _jouer(ctx)
        if refuse:
            alertes = [alerte_abandon(ALERTE_PUSH, catalogue.MOTIF_NON_FAST_FORWARD)]
    if ctx.ignores:
        alertes.append((ALERTE_IGNORES, {}))
    if ctx.projets_exclu:
        alertes.append((ALERTE_PROJETS, {}))
    ecrire_alertes(alertes)
    return code
