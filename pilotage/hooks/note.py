"""Dernière note de reprise du projet, relue par `SessionStart` (story 8.1, FR40, FR41, AD-13).

Candidats : les états de ce PC dans `attente/etat/<projet>/<pc>/`, puis ceux des autres PC dans
`donnees/etat/<projet>/<autre>/` (M5 : ce PC ne se lit que dans `attente/`) ; la session
courante en fait partie (`resume`, `clear`, `compact`). `MAX_ETATS_LUS` fichiers ouverts au
plus, les plus récents par `mtime` (NFR1). Un état n'est retenu que valide (schéma `session`),
à sa place (`projet`, `pc`, nom du fichier) et avec une note ; la note est repassée au filtre
de secrets (`texte.nettoyer`, comme `sync`) : suspecte, on passe à la suivante.

Ne lève jamais : toute erreur imprévue est journalisée (type seul, jamais la note) et rend
`None`. Les archives (`attente/archive/`) ne sont pas lues.
"""

import json
import os
from collections import namedtuple

from pilotage import chemins
from pilotage.hooks import _commun
from pilotage.noyau import ids, schemas, texte

EVENEMENT = "SessionStart"
MAX_ETATS_LUS = 20
BORNE_ETAT_OCTETS = 64 * 1024

# `namedtuple` plutôt que `dataclass` : import plus léger au démarrage du hook (NFR1).
NoteRetenue = namedtuple("NoteRetenue", ["pc", "session", "dernier_tour", "texte"])


def _fichiers(dossier, pc: str) -> list[tuple[int, str, str, str]]:
    """`(mtime_ns, pc, chemin, nom)` des `*.json` du dossier ; absent ou illisible : `[]`.

    Sous Windows, `DirEntry.stat()` sert les dates lues par `os.scandir`, sans appel de plus.
    """
    trouves = []
    try:
        with os.scandir(dossier) as entrees:
            for entree in entrees:
                try:
                    if entree.name.endswith(".json") and entree.is_file(follow_symlinks=False):
                        mtime = entree.stat(follow_symlinks=False).st_mtime_ns
                        trouves.append((mtime, pc, entree.path, entree.name))
                except OSError:
                    continue  # supprimé entre-temps
    except OSError:
        pass
    return trouves


def _sous_dossiers(dossier) -> list[str]:
    try:
        with os.scandir(dossier) as entrees:
            return [e.name for e in entrees if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def _candidats(ctx) -> list[tuple[int, str, str, str]]:
    trouves = []
    try:
        ici = chemins.joindre_sous(chemins.attente(), "etat", ctx.projet, ctx.pc)
        trouves += _fichiers(ici, ctx.pc)
    except ids.ErreurId:
        pass  # lien qui sort de `attente/` : ignoré
    racine = chemins.donnees()
    try:
        projet = chemins.joindre_sous(racine, "etat", ctx.projet)
    except ids.ErreurId:
        return trouves
    for autre in _sous_dossiers(projet):
        try:
            if ids.valider_pc(autre) == ctx.pc:
                continue  # M5 : ce PC se lit dans `attente/`
            trouves += _fichiers(chemins.joindre_sous(racine, "etat", ctx.projet, autre), autre)
        except ids.ErreurId:
            continue  # nom de PC invalide, ou lien qui sort de `donnees/`
    return trouves


def _lire(chemin: str, projet: str, pc: str, nom: str) -> dict | None:
    """État valide, à sa place, avec une note non vide ; sinon `None`."""
    try:
        with open(chemin, "rb") as fichier:
            brut = fichier.read(BORNE_ETAT_OCTETS + 1)
        if len(brut) > BORNE_ETAT_OCTETS:
            return None
        objet = json.loads(brut.decode("utf-8"))  # BOM : refusé par `json.loads`
        schemas.valider("session", objet)
    except (OSError, ValueError, RecursionError):
        return None
    if (objet["projet"], objet["pc"], f"{objet['session']}.json") != (projet, pc, nom):
        return None
    reprise = objet.get("reprise")
    if not isinstance(reprise, str) or not reprise.strip():
        return None
    return objet


def _choisir(ctx) -> NoteRetenue | None:
    candidats = sorted(_candidats(ctx), key=lambda c: c[0], reverse=True)[:MAX_ETATS_LUS]
    etats = []
    for _mtime, pc, chemin, nom in candidats:
        objet = _lire(chemin, ctx.projet, pc, nom)
        if objet is not None:
            etats.append(objet)
    etats.sort(key=lambda e: e["session"])
    etats.sort(key=lambda e: e.get("dernier_tour") or e["debut"], reverse=True)
    racine_github = str(chemins.racine_github())
    for etat in etats:
        note = texte.nettoyer(etat["reprise"], texte.BORNE_NOTE, racine_github)
        if note.strip():
            activite = etat.get("dernier_tour") or etat["debut"]
            return NoteRetenue(etat["pc"], etat["session"], activite, note)
    return None


def derniere_note(ctx) -> NoteRetenue | None:
    """Note la plus récente du projet (tous PC, session courante comprise), ou `None`."""
    try:
        return _choisir(ctx)
    except BaseException as erreur:  # noqa: BLE001 - la session ne doit jamais être bloquée
        _commun.journaliser(EVENEMENT, erreur)
        return None
