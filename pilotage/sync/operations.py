"""Étape 4 du cycle `sync` : application de `attente/operations/` (story 5.1, AD-5 §7, M7).

Sous le mutex du cycle. `appliquer` fige les identifiants des opérations lues, crée les messages
`boite/<projet>/<id>.json` absents et patche `projets.yaml` par remplacement ciblé de texte
(`patch_projets`), revalidé avant l'écriture atomique. `nettoyer`, après un push réussi, supprime
les seules opérations figées appliquées et range les rejetées dans `operations/rejetees/` avec leur
raison. Une opération appliquée laisse une trace `donnees/operations/appliquees/<pc>/<id>.json`,
commitée avec son effet : au rejeu (cycle arrêté entre le push et le nettoyage), une opération dont
la trace existe est retirée sans être réappliquée, même si un autre PC a changé la valeur depuis.
Traces purgées après 30 jours. Rejouer une opération ne change rien ; une opération déposée pendant
le cycle attend le suivant. Aucune écriture hors de `donnees/` et `attente/operations/` (et
`alertes.json`).
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import ids, schemas
from pilotage.noyau.schemas import operation as schema_operation
from pilotage.scan import inventaire
from pilotage.sync import copie, depot, patch_projets

SOURCE = "operation"
REJETEES = "rejetees"
SUFFIXE_RAISON = ".raison.json"
MAX_ALERTES = 20
BORNE_OCTETS = 64 * 1024  # un fichier d'opération plus gros est invalide
TRACES = ("operations", "appliquees")  # sous `donnees/`, puis `<pc>/<id>.json`
DUREE_TRACE = timedelta(days=30)
DELAI_ECRITURE = 60  # secondes : un fichier illisible plus récent attend le cycle suivant
_BOM = "\ufeff"
RAISONS = (
    "invalide", "version-recente", "message-different", "projets-invalide",
    "projets-version-recente", "valeur-differente", "patch-impossible", "resultat-invalide",
    "deja-appliquee",
)


@dataclass
class Figee:
    """Opération lue à l'étape 4 : son sort est appliqué après le push."""

    id: str
    projet: str | None = None
    raison: str | None = None  # None : appliquée
    champ: str | None = None
    tracee: bool = False  # trace déjà dans `donnees/` : appliquée lors d'un cycle précédent


class _Attendre(Exception):
    """L'opération n'est pas figée : elle attend le cycle suivant."""


def _maintenant() -> datetime:
    return datetime.now(UTC)  # substituable en test


def _ids_figes() -> tuple[list[str], int]:
    """(identifiants des fichiers `<id>.json` de `attente/operations/`, triés ; noms invalides)."""
    try:
        entrees = list(os.scandir(chemins.operations()))
    except OSError:
        return [], 0
    figes, invalides = [], 0
    for entree in entrees:
        if not entree.name.endswith(".json") or entree.is_dir(follow_symlinks=False):
            continue  # `.tmp` du serveur en cours d'écriture, `rejetees/`
        try:
            figes.append(ids.valider_id(entree.name[: -len(".json")]))
        except ids.ErreurId:
            invalides += 1
    return sorted(figes), invalides


def _lire(id_: str) -> tuple[dict | None, str | None]:
    """(opération validée, None) ou (None, raison du rejet)."""
    if not copie.sans_lien(chemins.operations(), f"{id_}.json"):
        return None, "invalide"  # un lien ne fait jamais lire un autre fichier
    chemin = chemins.operations() / ids.joindre(f"{id_}.json")
    try:
        if chemin.stat().st_size > BORNE_OCTETS:
            return None, "invalide"
        objet = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        try:
            recent = time.time() - chemin.stat().st_mtime < DELAI_ECRITURE
        except OSError:
            recent = False
        if recent:
            raise _Attendre from None  # en cours d'écriture : jamais rejetée sur une lecture
        return None, "invalide"
    version = objet.get("schema") if isinstance(objet, dict) else None
    if type(version) is int and version > schema_operation.SCHEMA:
        return None, "version-recente"
    try:
        schemas.valider("operation", objet)
    except ValueError:
        return None, "invalide"
    if objet["id"] != id_:
        return None, "invalide"
    return objet, None


def _deposer(ctx, op: dict, figee: Figee) -> None:
    projet, id_ = op["projet"], op["id"]
    message = {c: op[c] for c in ("schema", "id", "projet", "texte", "pc") if c in op}
    try:
        schemas.valider("message", message)
    except ValueError:
        figee.raison = "invalide"
        return
    if not copie.sans_lien(ctx.donnees, "boite", projet, f"{id_}.json"):
        figee.raison = "message-different"
        return
    cible = chemins.joindre_sous(ctx.donnees, "boite", projet, f"{id_}.json")
    if cible.exists():
        try:
            present = json.loads(cible.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            present = None
        if present != message:
            figee.raison = "message-different"  # jamais d'écrasement
            return
    else:
        chemins.ecrire_atomique(cible, json.dumps(message, ensure_ascii=False, indent=2) + "\n")
    ctx.relatifs.append(f"boite/{projet}/{id_}.json")


class _Projets:
    """Texte de `projets.yaml` partagé par les opérations `modifier_projets` d'un cycle."""

    def __init__(self, donnees: Path) -> None:
        self.chemin = donnees / "projets.yaml"
        self.texte: str | None = None
        self.config: dict | None = None
        self.raison: str | None = None
        self.original: str | None = None
        self.brut: str | None = None  # texte lu, BOM compris
        self.bom = ""
        self.figees: list[Figee] = []  # opérations dont le sort dépend du texte lu
        if not self.chemin.is_file() or not copie.sans_lien(donnees, "projets.yaml"):
            self.raison = "projets-invalide"
            return
        try:
            with open(self.chemin, encoding="utf-8", newline="") as f:
                texte = f.read()
        except (OSError, UnicodeDecodeError):
            self.raison = "projets-invalide"
            return
        self.brut = texte
        if texte.startswith(_BOM):  # conservé tel quel à l'écriture
            self.bom, texte = _BOM, texte[1:]
        config, recent, _ = inventaire.analyser_projets(texte)
        if config is None:
            self.raison = "projets-invalide"
        elif recent:
            self.raison = "projets-version-recente"
        else:
            self.texte = self.original = texte
            self.config = config

    def modifier(self, op: dict, figee: Figee) -> None:
        if self.raison is not None:
            figee.raison = self.raison
            return
        self.figees.append(figee)
        projet, patch = op["projet"], op["patch"]
        courants = patch_projets.valeurs(self.config, projet)
        a_faire = []
        for champ in patch_projets.CHAMPS:
            if champ not in patch:
                continue
            attendu, voulu = patch[champ]["attendu"], patch[champ]["voulu"]
            if courants[champ] == voulu:
                continue  # déjà appliqué
            if courants[champ] != attendu:
                figee.raison, figee.champ = "valeur-differente", champ
                return
            a_faire.append((champ, voulu))
        if not a_faire:
            return
        texte = self.texte
        for champ, voulu in a_faire:
            try:
                texte = patch_projets.appliquer(texte, projet, champ, courants[champ], voulu)
            except patch_projets.PatchImpossible:
                figee.raison, figee.champ = "patch-impossible", champ
                return
        config, recent, _ = inventaire.analyser_projets(texte)
        attendue = patch_projets.projection(self.config)
        vues = {**courants, **dict(a_faire)}
        if vues == patch_projets.DEFAUT:
            attendue["projets"].pop(projet, None)
        else:
            attendue["projets"][projet] = vues
        if config is None or recent or patch_projets.projection(config) != attendue:
            figee.raison = "resultat-invalide"
            return
        self.texte, self.config = texte, config

    def ecrire(self) -> list[Figee]:
        """Écrit le texte patché ; rend les opérations à remettre au cycle suivant si
        `projets.yaml` a changé depuis sa lecture (édition à la main pendant l'étape 4)."""
        if self.texte is None:
            return []
        try:
            with open(self.chemin, encoding="utf-8", newline="") as f:
                actuel = f.read()
        except (OSError, UnicodeDecodeError):
            actuel = None
        if actuel != self.brut:
            return [f for f in self.figees if f.raison is None]
        if self.texte != self.original:
            chemins.ecrire_atomique(self.chemin, self.bom + self.texte)
        return []


def _alerte(figee: Figee) -> dict:
    params = {"id": figee.id}
    if figee.projet is not None:
        params["projet"] = figee.projet
    if figee.champ is not None:
        params["champ"] = figee.champ
    return {"source": SOURCE, "code": f"operation-{figee.raison}", "params": params}


def _lire_raison(chemin: Path) -> Figee | None:
    try:
        objet = json.loads(chemin.read_text(encoding="utf-8"))
        if not isinstance(objet, dict) or objet.get("schema") != 1:
            return None
        figee = Figee(ids.valider_id(objet.get("id")), raison=objet.get("raison"))
        if figee.raison not in RAISONS:
            return None
        if objet.get("projet") is not None:
            figee.projet = ids.valider_projet(objet["projet"])
        champ = objet.get("champ")
        if champ is not None and champ not in patch_projets.CHAMPS:
            return None
        figee.champ = champ
    except (OSError, ValueError, TypeError):
        return None
    return figee


def _rejetees() -> list[Figee]:
    racine = chemins.operations()
    dossier = racine / REJETEES
    if not copie.sans_lien(racine, REJETEES):
        return []  # un lien ne fait jamais lire hors d'`attente/operations/`
    try:
        noms = [
            e.name for e in os.scandir(dossier)
            if e.name.endswith(SUFFIXE_RAISON) and e.is_file(follow_symlinks=False)
            and not e.is_junction()
        ]
    except OSError:
        return []
    return [f for nom in noms if (f := _lire_raison(dossier / nom)) is not None]


def _ecrire_alertes(rejets: list[Figee], noms_invalides: int) -> None:
    """Remplace les alertes de source `operation` : rejets du cycle et rejets gardés."""
    chemin = chemins.alertes_json()
    try:
        objet = json.loads(chemin.read_text(encoding="utf-8"))
        schemas.valider("alertes", objet)
        gardees = [a for a in objet["alertes"] if a["source"] != SOURCE]
    except FileNotFoundError:
        gardees = []
    except (OSError, ValueError):
        return  # illisible : gardé tel quel (le scan le remplace avec `alertes-illisibles`)
    par_id = {f.id: f for f in _rejetees()}
    par_id.update({f.id: f for f in rejets})
    recents = sorted(par_id.values(), key=lambda f: f.id, reverse=True)[:MAX_ALERTES]
    ajout = [_alerte(f) for f in recents]
    if noms_invalides:
        ajout.append({
            "source": SOURCE, "code": "operation-nom-invalide",
            "params": {"nombre": noms_invalides},
        })
    objet = {"schema": 1, "alertes": gardees + ajout}
    schemas.valider("alertes", objet)
    chemins.ecrire_atomique(chemin, json.dumps(objet, ensure_ascii=False, indent=2) + "\n")


def _dossier_traces(ctx) -> Path:
    if not copie.sans_lien(ctx.donnees, *TRACES, ctx.pc):
        raise OSError("operations/appliquees est un lien")  # jamais d'écriture hors de donnees/
    return chemins.joindre_sous(ctx.donnees, *TRACES, ctx.pc)


def _purger_traces(ctx, figes: list[str]) -> None:
    """Retire les traces suivies de plus de `DUREE_TRACE` (jamais celle d'une opération en
    attente) ; la suppression part avec le commit du cycle."""
    prefixe = ids.joindre(*TRACES, ctx.pc) + "/"
    suivies = depot.git_ok(["ls-files", "-z", "--", prefixe], ctx.donnees).split("\0")
    limite = _maintenant() - DUREE_TRACE
    garder = set(figes)
    for relatif in suivies:
        nom = relatif[len(prefixe):] if relatif.startswith(prefixe) else ""
        if not nom.endswith(".json") or "/" in nom:
            continue
        try:
            id_ = ids.valider_id(nom[: -len(".json")])
        except ids.ErreurId:
            continue
        moment = datetime.strptime(id_[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if moment >= limite or id_ in garder:
            continue
        (_dossier_traces(ctx) / ids.joindre(nom)).unlink(missing_ok=True)
        ctx.relatifs.append(relatif)


def _empreinte(op: dict) -> str:
    return hashlib.sha256(json.dumps(op, sort_keys=True).encode("utf-8")).hexdigest()


def _tracee(traces: Path, op: dict) -> bool | None:
    """Vrai si une trace de cette opération existe, None si la trace porte une autre empreinte
    (autre contenu au même identifiant : rejetée, jamais un second effet). Trace illisible :
    comptée comme la sienne."""
    chemin = traces / ids.joindre(f"{op['id']}.json")
    if not chemin.is_file():
        return False
    try:
        empreinte = json.loads(chemin.read_text(encoding="utf-8")).get("empreinte")
    except (OSError, ValueError, AttributeError):
        return True
    return True if empreinte is None or empreinte == _empreinte(op) else None


def _tracer(ctx, figee: Figee, op: dict) -> None:
    """Trace commitée avec l'effet de l'opération (même commit) : jamais réappliquée."""
    chemin = _dossier_traces(ctx) / ids.joindre(f"{figee.id}.json")
    contenu = {"schema": 1, "id": figee.id, "empreinte": _empreinte(op)}
    chemins.ecrire_atomique(chemin, json.dumps(contenu) + "\n")
    ctx.relatifs.append(ids.joindre(*TRACES, ctx.pc, f"{figee.id}.json"))


def appliquer(ctx) -> None:
    """Étape 4 : fige les identifiants (`ctx.operations`) et applique les opérations lues."""
    figes, noms_invalides = _ids_figes()
    ctx.operations = []
    projets: _Projets | None = None
    traces = _dossier_traces(ctx)
    lues: dict[str, dict] = {}
    for id_ in figes:
        figee = Figee(id_)
        try:
            op, raison = _lire(id_)
        except _Attendre:
            continue
        ctx.operations.append(figee)
        if op is None:
            figee.raison = raison
            continue
        figee.projet = op["projet"]
        tracee = _tracee(traces, op)
        if tracee is None:
            # Même identifiant, autre contenu : jamais un second effet.
            message = op["verbe"] == "deposer_message"
            figee.raison = "message-different" if message else "deja-appliquee"
            continue
        if tracee:
            figee.tracee = True  # appliquée et commitée par un cycle précédent : retirée seule
            continue
        lues[id_] = op
        if op["verbe"] == "deposer_message":
            _deposer(ctx, op, figee)
        else:
            projets = projets or _Projets(ctx.donnees)
            projets.modifier(op, figee)
    if projets is not None:
        reportees = projets.ecrire()  # `_commiter` ajoute `projets.yaml` au commit
        ctx.operations = [f for f in ctx.operations if f not in reportees]
    for figee in ctx.operations:
        if figee.raison is None and not figee.tracee:
            _tracer(ctx, figee, lues[figee.id])
    _purger_traces(ctx, figes)
    _ecrire_alertes([f for f in ctx.operations if f.raison], noms_invalides)


def nettoyer(ctx) -> None:
    """Après un push réussi : seuls les identifiants figés sont retirés de `attente/operations/`.

    Appliquée : supprimée. Rejetée : raison écrite dans `rejetees/<id>.raison.json`, puis fichier
    déplacé vers `rejetees/<id>.json` (une coupure entre les deux la laisse en attente).
    """
    dossier = chemins.operations()
    if any(f.raison for f in ctx.operations) and not copie.sans_lien(dossier, REJETEES):
        raise OSError("operations/rejetees est un lien")  # jamais d'écriture hors d'attente/
    for figee in ctx.operations:
        # Chemin lexical (id validé) : un lien est supprimé ou déplacé, jamais sa cible.
        source = dossier / ids.joindre(f"{figee.id}.json")
        if figee.raison is None:
            source.unlink(missing_ok=True)
            continue
        raison = {"schema": 1, "id": figee.id, "raison": figee.raison}
        if figee.projet is not None:
            raison["projet"] = figee.projet
        if figee.champ is not None:
            raison["champ"] = figee.champ
        chemins.ecrire_atomique(
            chemins.joindre_sous(dossier, REJETEES, f"{figee.id}{SUFFIXE_RAISON}"),
            json.dumps(raison, ensure_ascii=False, indent=2) + "\n",
        )
        if os.path.lexists(source):
            os.replace(source, chemins.joindre_sous(dossier, REJETEES, f"{figee.id}.json"))
    ctx.operations = []
