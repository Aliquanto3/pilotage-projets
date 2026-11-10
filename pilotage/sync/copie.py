"""Copie `attente/` → `donnees/` des seuls fichiers de ce PC (story 3.1, AD-3, AD-5 §4).

- États de session `etat/<projet>/<pc>/<session>.json` : relus, filtre de secrets rejoué
  (`noyau.texte.nettoyer`, racine GitHub normalisée), validés par le schéma `session`. Un
  `reprise` suspect est supprimé ; un `attente.quoi` suspect devient `""` (l'objet `attente`
  reste exigé par le statut). Fichier illisible, invalide, d'un autre PC ou
  atteint par un lien symbolique ou une jonction : non copié.
- Instantané `instantanes/<pc>.json` : validé par le schéma `instantane`, copié tel quel.
- Acquittements `boite/<projet>/<id>.lu.<pc>` de ce PC (story 5.3) : validés par le schéma
  `acquittement` (`id`, `projet`, `pc` égaux au chemin), copiés tels quels.

Rend les chemins relatifs (`/`) des fichiers copiés, pour le `git add` par liste.
"""

import json
import os
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import ids, schemas, texte


def filtrer_session(objet: dict, racine_github: str) -> dict:
    """Rejoue le filtre de secrets sur les textes libres d'un état de session (copie modifiée)."""
    propre = dict(objet)
    attente = propre.get("attente")
    if isinstance(attente, dict) and isinstance(attente.get("quoi"), str):
        propre["attente"] = {
            **attente, "quoi": texte.nettoyer(attente["quoi"], texte.BORNE_QUOI, racine_github)
        }
    reprise = propre.get("reprise")
    if isinstance(reprise, str):
        nette = texte.nettoyer(reprise, texte.BORNE_NOTE, racine_github)
        if nette:
            propre["reprise"] = nette
        else:
            del propre["reprise"]
    return propre


def _ecrire_si_change(cible: Path, contenu: str) -> None:
    try:
        if cible.read_text(encoding="utf-8") == contenu:
            return
    except (OSError, UnicodeDecodeError):
        pass
    chemins.ecrire_atomique(cible, contenu)


def sans_lien(racine: Path, *segments: str) -> bool:
    """Vrai si aucun des chemins `racine/segments[0]`, … `racine/segments` n'est un lien
    symbolique ou une jonction : un lien ne fait jamais entrer un autre fichier dans la copie."""
    chemin = racine
    for segment in segments:
        chemin = chemin / segment
        if os.path.islink(chemin) or os.path.isjunction(chemin):
            return False
    return True


def _sous_dossiers(dossier: Path) -> list[str]:
    try:
        return sorted(
            e.name for e in os.scandir(dossier)
            if e.is_dir(follow_symlinks=False) and not e.is_junction()
        )
    except OSError:
        return []


def _fichiers(dossier: Path) -> list[str]:
    try:
        # Un lien de fichier est listé pour être refusé par `sans_lien` et compté comme ignoré.
        return sorted(
            e.name for e in os.scandir(dossier)
            if e.is_file(follow_symlinks=False) or e.is_symlink()
        )
    except OSError:
        return []


def copier_etats(pc: str, racine_github: str) -> tuple[list[str], int]:
    """Copie les états de session de `pc` ; rend (relatifs copiés, nombre de fichiers ignorés)."""
    attente, donnees = chemins.attente(), chemins.donnees()
    copies: list[str] = []
    ignores = 0
    for projet in _sous_dossiers(attente / "etat"):
        try:
            ids.valider_projet(projet)
            dossier_pc = chemins.joindre_sous(attente, "etat", projet, pc)
        except ids.ErreurId:
            ignores += 1
            continue
        for nom in _fichiers(dossier_pc):
            if not nom.endswith(".json"):
                continue  # `.tmp` d'une écriture en cours : jamais lu comme donnée (AD-3)
            try:
                session = ids.valider_session(nom.removesuffix(".json"))
                if not (sans_lien(attente, "etat", projet, pc, nom)
                        and sans_lien(donnees, "etat", projet, pc, nom)):
                    raise ValueError("lien symbolique ou jonction")
                source = chemins.joindre_sous(attente, "etat", projet, pc, nom)
                objet = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(objet, dict):
                    raise ValueError("objet attendu")
                objet = filtrer_session(objet, racine_github)
                schemas.valider("session", objet)
                if (objet["projet"], objet["pc"], objet["session"]) != (projet, pc, session):
                    raise ValueError("chemin et contenu divergent")
                cible = chemins.joindre_sous(donnees, "etat", projet, pc, nom)
            except (OSError, ValueError):  # ErreurId, ErreurValidation, JSON : ValueError
                ignores += 1
                continue
            _ecrire_si_change(cible, json.dumps(objet, ensure_ascii=False, indent=2) + "\n")
            copies.append(f"etat/{projet}/{pc}/{nom}")
    return copies, ignores


def copier_instantane(pc: str) -> tuple[list[str], int]:
    """Copie `attente/instantanes/<pc>.json` ; rend (relatifs copiés, nombre ignoré)."""
    nom = f"{pc}.json"
    source = chemins.instantanes() / nom
    if not source.is_file():
        return [], 0
    try:
        if not (sans_lien(chemins.attente(), "instantanes", nom)
                and sans_lien(chemins.donnees(), "instantanes", nom)):
            raise ValueError("lien symbolique ou jonction")
        contenu = source.read_text(encoding="utf-8")
        schemas.valider("instantane", json.loads(contenu))
        cible = chemins.joindre_sous(chemins.donnees(), "instantanes", nom)
    except (OSError, ValueError):
        return [], 1
    _ecrire_si_change(cible, contenu)
    return [f"instantanes/{nom}"], 0


def copier_acquittements(pc: str) -> tuple[list[str], int]:
    """Copie `attente/boite/<projet>/<id>.lu.<pc>` de `pc` ; rend (relatifs copiés, ignorés).

    Fichier d'un autre PC : non lu (pas compté). Illisible, invalide, divergent du chemin ou
    atteint par un lien : non copié, compté comme ignoré."""
    attente, donnees = chemins.attente(), chemins.donnees()
    suffixe = f".lu.{pc}"
    copies: list[str] = []
    ignores = 0
    for projet in _sous_dossiers(attente / "boite"):
        try:
            ids.valider_projet(projet)
            dossier = chemins.joindre_sous(attente, "boite", projet)
        except ids.ErreurId:
            ignores += 1
            continue
        for nom in _fichiers(dossier):
            if not nom.endswith(suffixe):
                continue  # autre PC, ou `.tmp` d'une écriture en cours
            try:
                identifiant = ids.valider_id(nom.removesuffix(suffixe))
                if not (sans_lien(attente, "boite", projet, nom)
                        and sans_lien(donnees, "boite", projet, nom)):
                    raise ValueError("lien symbolique ou jonction")
                contenu = (dossier / nom).read_text(encoding="utf-8")
                objet = json.loads(contenu)
                schemas.valider("acquittement", objet)
                if (objet["id"], objet["projet"], objet["pc"]) != (identifiant, projet, pc):
                    raise ValueError("chemin et contenu divergent")
                cible = chemins.joindre_sous(donnees, "boite", projet, nom)
            except (OSError, ValueError):  # ErreurId, ErreurValidation, JSON : ValueError
                ignores += 1
                continue
            _ecrire_si_change(cible, contenu)
            copies.append(f"boite/{projet}/{nom}")
    return copies, ignores
