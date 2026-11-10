"""Lecture de `donnees/` pour l'assemblage (story 3.4, AD-12, M5) : les autres PC.

Lecture seule. Ce PC se lit dans `attente/` (jamais ici). Un fichier d'un schéma inconnu ou plus
récent est ignoré : l'alerte « Fichiers de <pc> ignorés : version plus récente » (« version
inconnue » pour un schéma inférieur à 1) est calculée à chaque lecture et n'est jamais écrite
dans `alertes.json`. Un fichier illisible ou invalide est
ignoré avec une alerte au texte fixe.
"""

import json
import os
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import alertes as catalogue
from pilotage.noyau import ids, schemas

ALERTE_VERSION = "donnees-version-recente"
ALERTE_ILLISIBLE = "donnees-illisibles"
MESSAGE_ILLISIBLE = "Fichier de donnees/ illisible ignoré"


def _illisible(alertes: dict) -> None:
    alertes[(ALERTE_ILLISIBLE, "")] = {"code": ALERTE_ILLISIBLE, "message": MESSAGE_ILLISIBLE}


def _alerte_version(pc: str, version: int) -> dict:
    quelle = "plus récente" if version > 1 else "inconnue"
    params = {"pc": pc, "quelle": quelle}
    return {
        "code": ALERTE_VERSION,
        "message": catalogue.texte({"code": ALERTE_VERSION, "params": params}),
        "params": params,
    }


def _lire(chemin: Path, nom_schema: str, pc: str, alertes: dict) -> dict | None:
    """Objet validé, ou None avec une alerte (version plus récente ou illisible)."""
    try:
        objet = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _illisible(alertes)
        return None
    version = objet.get("schema") if isinstance(objet, dict) else None
    if type(version) is int and version != 1:
        alertes.setdefault((ALERTE_VERSION, pc), _alerte_version(pc, version))
        if version > 1:  # « plus récente » l'emporte sur « inconnue » pour un même PC
            alertes[(ALERTE_VERSION, pc)] = _alerte_version(pc, version)
        return None
    try:
        schemas.valider(nom_schema, objet)
    except ValueError:  # ErreurValidation
        _illisible(alertes)
        return None
    return objet


def _noms(dossier: Path, dirs: bool) -> list[str]:
    try:
        return sorted(
            e.name for e in os.scandir(dossier)
            if (e.is_dir() if dirs else e.name.endswith(".json"))
        )
    except OSError:
        return []


def _pc_valide(nom: str) -> str | None:
    try:
        return ids.valider_pc(nom)
    except ids.ErreurId:
        return None


def lire_autres_pcs(pc: str) -> tuple[dict[str, dict], dict[str, dict[str, list]], list[dict]]:
    """(instantanés `{pc: objet}`, états `{pc: {projet: [états]}}`, alertes de lecture).

    Tous les PC de `donnees/` sauf `pc`. Pour les états, le nom du dossier, de l'état et du
    fichier doivent concorder avec leur contenu (comme `sessions.lire_etats`).
    """
    racine = chemins.donnees()
    alertes: dict = {}
    instantanes: dict[str, dict] = {}
    for nom in _noms(racine / "instantanes", dirs=False):
        autre = _pc_valide(nom.removesuffix(".json"))
        if autre is None:
            _illisible(alertes)
            continue
        if autre == pc:
            continue
        objet = _lire(racine / "instantanes" / nom, "instantane", autre, alertes)
        if objet is not None:
            instantanes[autre] = objet
    etats: dict[str, dict[str, list]] = {}
    for projet in _noms(racine / "etat", dirs=True):
        for dossier_pc in _noms(racine / "etat" / projet, dirs=True):
            autre = _pc_valide(dossier_pc)
            if autre is None or autre == pc:
                continue
            for nom in _noms(racine / "etat" / projet / dossier_pc, dirs=False):
                chemin = racine / "etat" / projet / dossier_pc / nom
                objet = _lire(chemin, "session", autre, alertes)
                if objet is None:
                    continue
                if (objet["projet"], objet["pc"], f"{objet['session']}.json") != (
                    projet, autre, nom
                ):
                    _illisible(alertes)
                    continue
                etats.setdefault(autre, {}).setdefault(projet, []).append(objet)
    return instantanes, etats, [alertes[k] for k in sorted(alertes)]
