"""`GET /api/operations` : opérations en attente et état des messages (story 5.2, AD-14).

Lecture sans effet : aucune écriture, aucun mutex, aucun processus. Sources :
- `attente/operations/<id>.json` : opérations déposées par le serveur, pas encore appliquées ;
- `donnees/boite/<projet>/<id>.json` : messages déposés par `sync` ;
- `attente/boite/<projet>/<id>.lu.<pc>` et `donnees/boite/…` : acquittements (story 5.3), lus avec
  tolérance (champ `heure` ISO 8601 s'il est lisible).
Les liens et jonctions ne sont jamais suivis ; les noms de fichiers sont validés (AD-9).
"""

import json
import os
from datetime import datetime
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import ids, schemas
from pilotage.serveur.routes import Reponse

EN_ATTENTE, DEPOSE, LU = "en-attente", "depose", "lu"
LIBELLES = {EN_ATTENTE: "en attente de synchro", DEPOSE: "déposé"}
TAILLE_MAX = 64 * 1024  # octets : au-delà, un fichier n'est pas lu
CHAMPS_RENDUS = ("id", "verbe", "projet", "pc", "patch")


def _fichiers(dossier: Path) -> list[os.DirEntry]:
    """Fichiers ordinaires de `dossier` (ni lien, ni jonction), triés ; `[]` si illisible."""
    if os.path.islink(dossier) or os.path.isjunction(dossier):
        return []
    try:
        entrees = list(os.scandir(dossier))
    except OSError:
        return []
    return sorted(
        (e for e in entrees if e.is_file(follow_symlinks=False) and not e.is_junction()),
        key=lambda e: e.name,
    )


def _sous_dossiers(dossier: Path) -> list[str]:
    if os.path.islink(dossier) or os.path.isjunction(dossier):
        return []
    try:
        entrees = list(os.scandir(dossier))
    except OSError:
        return []
    noms = []
    for entree in entrees:
        if entree.is_dir(follow_symlinks=False) and not entree.is_junction():
            try:
                noms.append(ids.valider_projet(entree.name))
            except ids.ErreurId:
                continue
    return sorted(noms)


def _lire(entree: os.DirEntry) -> object:
    try:
        if entree.stat(follow_symlinks=False).st_size > TAILLE_MAX:
            return None
        with open(entree.path, encoding="utf-8") as fichier:
            return json.load(fichier)
    except (OSError, ValueError):
        return None


def _valide(nom_schema: str, objet: object) -> bool:
    try:
        schemas.valider(nom_schema, objet)
    except ValueError:
        return False
    return True


def operations_en_attente() -> list[dict]:
    """Opérations valides de `attente/operations/`, triées par id."""
    rendues = []
    for entree in _fichiers(chemins.operations()):
        if not entree.name.endswith(".json"):
            continue
        try:
            id_ = ids.valider_id(entree.name[: -len(".json")])
        except ids.ErreurId:
            continue
        objet = _lire(entree)
        if not _valide("operation", objet) or objet["id"] != id_:
            continue
        rendues.append(objet)
    return rendues


def _heure(valeur: object) -> str | None:
    if not isinstance(valeur, str):
        return None
    try:
        moment = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone().strftime("%H:%M")


def _lectures(racines: tuple[Path, ...], projet: str) -> dict[str, dict[str, str | None]]:
    """`{id: {pc: HH:MM ou None}}` des acquittements `<id>.lu.<pc>` du projet."""
    lectures: dict[str, dict[str, str | None]] = {}
    for racine in racines:
        dossier = racine / "boite" / projet
        for entree in _fichiers(dossier):
            id_brut, separateur, pc_brut = entree.name.partition(".lu.")
            if not separateur:
                continue
            try:
                id_, pc = ids.valider_id(id_brut), ids.valider_pc(pc_brut)
            except ids.ErreurId:
                continue
            objet = _lire(entree)
            heure = _heure(objet.get("heure")) if isinstance(objet, dict) else None
            par_pc = lectures.setdefault(id_, {})
            if par_pc.get(pc) is None:
                par_pc[pc] = heure
    return lectures


def _deposes(projet: str) -> dict[str, dict]:
    deposes = {}
    for entree in _fichiers(chemins.donnees() / "boite" / projet):
        if not entree.name.endswith(".json"):
            continue
        try:
            id_ = ids.valider_id(entree.name[: -len(".json")])
        except ids.ErreurId:
            continue
        objet = _lire(entree)
        if _valide("message", objet) and (objet["id"], objet["projet"]) == (id_, projet):
            deposes[id_] = objet
    return deposes


def _libelle(etat: str, lectures: list[dict]) -> str:
    if etat != LU:
        return LIBELLES[etat]
    return ", ".join(
        f"lu par {lu['pc']} à {lu['heure']}" if lu["heure"] else f"lu par {lu['pc']}"
        for lu in lectures
    )


def messages(operations: list[dict]) -> list[dict]:
    """Messages en attente et déposés, avec leur état, triés par id."""
    en_attente = {o["id"]: o for o in operations if o["verbe"] == "deposer_message"}
    projets = set(_sous_dossiers(chemins.donnees() / "boite"))
    projets |= set(_sous_dossiers(chemins.attente() / "boite"))
    projets |= {o["projet"] for o in en_attente.values()}
    rendus = []
    for projet in sorted(projets):
        deposes = _deposes(projet)
        lectures = _lectures((chemins.attente(), chemins.donnees()), projet)
        sources = {**{i: o for i, o in en_attente.items() if o["projet"] == projet}, **deposes}
        for id_, source in sources.items():
            lus = [{"pc": pc, "heure": h} for pc, h in sorted(lectures.get(id_, {}).items())]
            etat = LU if lus else DEPOSE if id_ in deposes else EN_ATTENTE
            rendus.append({
                "id": id_, "projet": projet, "pc": source.get("pc"), "texte": source["texte"],
                "etat": etat, "lectures": lus, "libelle": _libelle(etat, lus),
            })
    return sorted(rendus, key=lambda m: m["id"])


def operations(parametres: dict[str, str], corps: bytes) -> Reponse:
    del parametres, corps
    en_attente = operations_en_attente()
    rendues = [{c: o[c] for c in CHAMPS_RENDUS if c in o} for o in en_attente]
    return Reponse(200, donnees={"operations": rendues, "messages": messages(en_attente)})
