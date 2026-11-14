"""État court du dépôt et journal de décisions (story 8.3, FR41, FR43, AD-10, AD-13).

Écriture par `Stop` (`enregistrer`) : la session déclare son état et ses décisions par marqueur
(`noyau.marqueur`) ; rien n'est écrit dans le dépôt du projet. Sous
`attente/depots/<projet>/` :
- `<pc>.json` (schéma `etat_depot`) : l'état courant, réécrit en entier, et les
  `MAX_DECISIONS` dernières décisions de ce PC ; seul fichier relu au démarrage ;
- `<pc>.decisions.jsonl` (schéma `decision`, une ligne par décision) : l'historique en ajout
  seul, date posée par le hook ; jamais relu par les hooks, borné par `sync`.
Chaque champ passe par `texte.nettoyer_champ` (secrets, bornes, contrôles, chemins absolus) ;
`prochaine` ou `decision` refusé : l'état ou la décision entière est ignorée. Verrou
`verrous/depot-<projet>.lock` (un essai de 20 ms) ; occupé, ou `os.replace` refusé : écriture
abandonnée, type d'erreur journalisé.

Lecture par `SessionStart` (`etat_du_depot`) : `attente/depots/<projet>/<ce pc>.json` et
`donnees/depots/<projet>/<autre pc>.json`, `MAX_FICHIERS_LUS` au plus par `mtime` décroissant,
`BORNE_FICHIER_OCTETS` chacun ; retenu : le plus récent par `ecrit` seul ; son état (date
`etat_ecrit`) et ses décisions de moins de `PEREMPTION_JOURS`, champs refiltrés.
Dépôt en run (`run-autonome.md` présent) : rien.
Ne lève jamais.
"""

import json
import os
from collections import namedtuple
from datetime import UTC, datetime, timedelta

from pilotage import chemins
from pilotage.hooks import _commun
from pilotage.noyau import ids, marqueur, schemas
from pilotage.noyau.schemas import etat_depot

ESSAIS_VERROU = 1
PEREMPTION_JOURS = 14
MAX_FICHIERS_LUS = 8
BORNE_FICHIER_OCTETS = 16 * 1024
RUN_AUTONOME = ("_bmad-output", "implementation-artifacts", "run-autonome.md")
SUFFIXE_JOURNAL = ".decisions.jsonl"

# `etat` : champs filtrés ou `None` ; `decisions` : lignes filtrées, la plus ancienne d'abord.
EtatRetenu = namedtuple("EtatRetenu", ["pc", "ecrit", "etat", "decisions"])


def chemin_etat(projet: str, pc: str):
    return chemins.joindre_sous(chemins.attente(), "depots", projet, f"{pc}.json")


def chemin_journal(projet: str, pc: str):
    return chemins.joindre_sous(chemins.attente(), "depots", projet, f"{pc}{SUFFIXE_JOURNAL}")


def chemin_verrou(projet: str):
    """`attente/verrous/depot-<projet>.lock`, partagé avec la rotation du journal par `sync`."""
    nom = f"depot-{ids.valider_projet(projet)}.lock"
    return chemins.joindre_sous(chemins.attente(), "verrous", nom)


# --- Écriture (Stop) ----------------------------------------------------------------------


def _projet(lus: list[dict], cwd: object) -> str | None:
    """Projet de la session : celui de son seul état, sinon celui dont `dossier` est le `cwd`."""
    projets = {etat["projet"] for etat in lus}
    if len(projets) == 1:
        return projets.pop()
    if not isinstance(cwd, str) or not cwd:
        return None
    relatif = _commun.relatif_sous(cwd, str(chemins.racine_github()))
    if relatif is None:
        return None
    dossier = ids.cle_dossier(relatif)
    trouves = {etat["projet"] for etat in lus if etat["dossier"] == dossier}
    return trouves.pop() if len(trouves) == 1 else None


def _lire_precedent(chemin, projet: str, pc: str) -> dict | None:
    try:
        with open(chemin, "rb") as fichier:
            brut = fichier.read(BORNE_FICHIER_OCTETS + 1)
        if len(brut) > BORNE_FICHIER_OCTETS:
            return None
        objet = json.loads(brut.decode("utf-8"))
        schemas.valider("etat_depot", objet)
    except (OSError, ValueError, RecursionError):
        return None
    return objet if (objet["projet"], objet["pc"]) == (projet, pc) else None


def _ajouter_au_journal(chemin, lignes: list[dict]) -> None:
    """Ajout seul ; une dernière ligne tronquée (écriture interrompue) est d'abord fermée.

    Sans `fsync` (~7 ms sous Windows, budget de `Stop`) : une coupure de courant peut perdre la
    ligne, les cinq dernières décisions restent dans `<pc>.json`, écrit par `ecrire_atomique`."""
    contenu = "".join(json.dumps(ligne, ensure_ascii=False) + "\n" for ligne in lignes)
    with open(chemin, "a+b") as fichier:
        fichier.seek(0, os.SEEK_END)
        if fichier.tell() > 0:
            fichier.seek(-1, os.SEEK_END)
            if fichier.read(1) != b"\n":
                contenu = "\n" + contenu
        fichier.write(contenu.encode("utf-8"))


def _ecrire(projet: str, pc: str, session: str, trouves, racine: str) -> None:
    maintenant = _commun.maintenant()
    nouvelles = []
    for decision, pourquoi in trouves.decisions:
        ligne = {"date": maintenant[:10], "ecrit": maintenant, "decision": decision}
        if pourquoi:
            ligne["pourquoi"] = pourquoi
        ligne["session"] = session
        ligne = etat_depot.filtrer_decision(ligne, racine)
        if ligne is not None:
            nouvelles.append(ligne)
    clos = trouves.etat == marqueur.ETAT_CLOS
    etat = etat_depot.filtrer_etat(trouves.etat, racine) if isinstance(trouves.etat, dict) else None
    if not clos and etat is None and not nouvelles:
        return  # rien d'exploitable : rien n'est changé
    chemin = chemin_etat(projet, pc)
    with _commun.verrou_fichier(chemin_verrou(projet), ESSAIS_VERROU):
        precedent = _lire_precedent(chemin, projet, pc)
        date_etat = maintenant
        if not clos and etat is None and precedent is not None and "etat" in precedent:
            # décision seule : l'état gardé garde sa date (la péremption porte sur lui)
            etat, date_etat = precedent["etat"], etat_depot.date_etat(precedent)
        decisions = ([] if precedent is None else precedent["decisions"]) + nouvelles
        objet = {"schema": etat_depot.SCHEMA, "projet": projet, "pc": pc, "session": session,
                 "ecrit": maintenant}
        if etat:
            objet["etat_ecrit"] = date_etat
            objet["etat"] = etat
        objet["decisions"] = decisions[-etat_depot.MAX_DECISIONS:]
        schemas.valider("etat_depot", objet)
        if nouvelles:
            chemin.parent.mkdir(parents=True, exist_ok=True)
            _ajouter_au_journal(chemin_journal(projet, pc), nouvelles)
        if "etat" not in objet and not objet["decisions"]:
            chemin.unlink(missing_ok=True)  # état vidé, aucune décision : plus rien à relire
            return
        chemins.ecrire_atomique(chemin, json.dumps(objet, ensure_ascii=False, indent=2) + "\n")


def enregistrer(pc: str, session: str, lus: list[dict], cwd: object, trouves, racine: str) -> None:
    """Écrit l'état et les décisions déclarés par `trouves` (`marqueur.lire`) pour la session
    `session` de `pc`, dont `lus` sont les états (non finis) ; sans marqueur, rien n'est lu.

    Ne lève jamais : toute erreur est journalisée (type seul, jamais le texte)."""
    if trouves.etat is None and not trouves.decisions:
        return
    try:
        projet = _projet(lus, cwd)
        if projet is not None:
            _ecrire(projet, pc, session, trouves, racine)
    except BaseException as erreur:  # noqa: BLE001 - `Stop` ne doit jamais en pâtir
        _commun.journaliser("Stop", erreur)


# --- Lecture (SessionStart) ---------------------------------------------------------------


def _candidats(ctx) -> list[tuple[int, str, str]]:
    """`(mtime_ns, pc, chemin)` : le fichier de ce PC dans `attente/`, ceux des autres PC dans
    `donnees/` (M5) ; un seul `scandir`, liens écartés."""
    trouves = []
    try:
        ici = chemin_etat(ctx.projet, ctx.pc)
        trouves.append((os.stat(ici).st_mtime_ns, ctx.pc, str(ici)))
    except (OSError, ids.ErreurId):
        pass
    try:
        dossier = chemins.joindre_sous(chemins.donnees(), "depots", ctx.projet)
        with os.scandir(dossier) as entrees:
            for entree in entrees:
                nom = entree.name
                if not nom.endswith(".json"):
                    continue  # journal `.decisions.jsonl`, `.tmp`
                try:
                    pc = ids.valider_pc(nom[:-5])
                    if pc == ctx.pc or not entree.is_file(follow_symlinks=False):
                        continue
                    trouves.append((entree.stat(follow_symlinks=False).st_mtime_ns, pc,
                                    entree.path))
                except (OSError, ids.ErreurId):
                    continue
    except (OSError, ids.ErreurId):
        pass
    return trouves


def _lire(chemin: str, projet: str, pc: str, limite: str) -> dict | None:
    objet = _lire_precedent(chemin, projet, pc)
    if objet is None or objet["ecrit"] < limite:
        return None  # invalide, hors de sa place, ou périmé
    return objet


def _choisir(ctx) -> EtatRetenu | None:
    """Le fichier le plus récent par `ecrit` seul : son état (s'il a moins de
    `PEREMPTION_JOURS`, date `etat_ecrit`) et ses décisions récentes, refiltrés ; rien
    d'exploitable : `None`, sans repli sur un fichier plus ancien (il serait pris pour l'actuel)."""
    if os.path.exists(os.path.join(ctx.cwd, *RUN_AUTONOME)):
        return None  # dépôt en run : `run-autonome.md` fait foi
    candidats = sorted(_candidats(ctx), key=lambda c: c[0], reverse=True)[:MAX_FICHIERS_LUS]
    if not candidats:
        return None
    limite = (datetime.now(UTC) - timedelta(days=PEREMPTION_JOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    objets = [o for _m, pc, chemin in candidats if (o := _lire(chemin, ctx.projet, pc, limite))]
    if not objets:
        return None
    objet = max(objets, key=lambda o: (o["ecrit"], o["pc"]))
    racine = str(chemins.racine_github())
    date_etat = etat_depot.date_etat(objet) if "etat" in objet else objet["ecrit"]
    etat = etat_depot.filtrer_etat(objet.get("etat"), racine) if date_etat >= limite else None
    decisions = [
        ligne for ligne in (
            etat_depot.filtrer_decision(d, racine) for d in objet["decisions"]
            if d["ecrit"] >= limite
        ) if ligne is not None
    ]
    if etat is None and not decisions:
        return None
    # En-tête : date de l'état montré, sinon de la dernière écriture (décisions seules).
    return EtatRetenu(objet["pc"], date_etat if etat is not None else objet["ecrit"], etat,
                      decisions)


def etat_du_depot(ctx) -> EtatRetenu | None:
    """État du dépôt le plus récent (tous PC), à injecter par `SessionStart`, ou `None`."""
    try:
        return _choisir(ctx)
    except BaseException as erreur:  # noqa: BLE001 - la session ne doit jamais être bloquée
        _commun.journaliser("SessionStart", erreur)
        return None
