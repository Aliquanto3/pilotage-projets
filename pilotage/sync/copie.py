"""Copie `attente/` → `donnees/` des seuls fichiers de ce PC (story 3.1, AD-3, AD-5 §4).

- États de session `etat/<projet>/<pc>/<session>.json` : relus, filtre de secrets rejoué
  (`noyau.texte.nettoyer`, racine GitHub normalisée), validés par le schéma `session`. Un
  `reprise` suspect est supprimé ; un `attente.quoi` suspect devient `""` (l'objet `attente`
  reste exigé par le statut). Fichier illisible, invalide, d'un autre PC ou
  atteint par un lien symbolique ou une jonction : non copié.
- Instantané `instantanes/<pc>.json` : validé par le schéma `instantane`, copié tel quel.
- Acquittements `boite/<projet>/<id>.lu.<pc>` de ce PC (story 5.3) : validés par le schéma
  `acquittement` (`id`, `projet`, `pc` égaux au chemin), copiés tels quels.
- État du dépôt `depots/<projet>/<pc>.json` et journal `<pc>.decisions.jsonl` (story 8.3) :
  filtre rejoué, validés (`etat_depot`, `decision` ligne à ligne), journal borné à 200 lignes.

Rend les chemins relatifs (`/`) des fichiers copiés, pour le `git add` par liste.
"""

import json
import os
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import ids, schemas, texte
from pilotage.noyau.schemas import etat_depot


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


# --- État du dépôt et journal de décisions (story 8.3) ----------------------------------------

MAX_LIGNES_JOURNAL = 200
BORNE_ETAT_DEPOT_OCTETS = 16 * 1024
SUFFIXE_JOURNAL = ".decisions.jsonl"


def filtrer_etat_depot(objet: dict, racine_github: str) -> dict:
    """Rejoue le filtre sur l'état et les décisions d'un fichier `<pc>.json` (copie modifiée)."""
    propre = dict(objet)
    if "etat" in propre:
        etat = etat_depot.filtrer_etat(propre["etat"], racine_github)
        if etat is None:
            del propre["etat"]
            propre.pop("etat_ecrit", None)
        else:
            propre["etat"] = etat
    if isinstance(propre.get("decisions"), list):
        propre["decisions"] = [
            ligne for ligne in (
                etat_depot.filtrer_decision(d, racine_github) for d in propre["decisions"]
            ) if ligne is not None
        ]
    return propre


def lignes_du_journal(contenu: str, racine_github: str) -> list[dict]:
    """Lignes valides (schéma `decision`) et refiltrées du journal ; une ligne tronquée ou
    invalide est ignorée seule ; les `MAX_LIGNES_JOURNAL` dernières."""
    lignes = []
    for brute in contenu.split("\n"):
        if not brute.strip():
            continue
        try:
            ligne = etat_depot.filtrer_decision(json.loads(brute), racine_github)
            if ligne is None:
                continue
            schemas.valider("decision", ligne)
        except (ValueError, RecursionError):
            continue
        lignes.append(ligne)
    return lignes[-MAX_LIGNES_JOURNAL:]


def _borner_journal(attente: Path, projet: str, nom: str) -> None:
    """Rotation de `attente/depots/<projet>/<nom>` aux `MAX_LIGNES_JOURNAL` dernières lignes,
    sous le verrou `verrous/depot-<projet>.lock` que prend aussi `Stop` (un essai : occupé,
    la rotation attend le cycle suivant). Lignes gardées telles quelles."""
    verrou = chemins.joindre_sous(attente, "verrous", f"depot-{projet}.lock")
    verrou.parent.mkdir(parents=True, exist_ok=True)
    try:
        descripteur = os.open(verrou, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        return
    jeton = f"{os.getpid()} {os.urandom(8).hex()}".encode("ascii")
    try:
        os.write(descripteur, jeton)
        source = chemins.joindre_sous(attente, "depots", projet, nom)
        with open(source, "rb") as fichier:
            lignes = fichier.read().split(b"\n")
        if lignes and not lignes[-1]:
            lignes.pop()
        if len(lignes) > MAX_LIGNES_JOURNAL:
            gardees = b"\n".join(lignes[-MAX_LIGNES_JOURNAL:]) + b"\n"
            chemins.ecrire_atomique(source, gardees.decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        pass  # rotation au cycle suivant
    finally:
        os.close(descripteur)
        try:  # repris par `Stop` (plus de 2 s, jugé périmé) : son verrou n'est pas effacé
            with open(verrou, "rb") as fichier:
                notre = fichier.read(64) == jeton
            if notre:
                os.unlink(verrou)
        except OSError:
            pass


def copier_depots(pc: str, racine_github: str) -> tuple[list[str], int]:
    """Copie `attente/depots/<projet>/<pc>.json` et `<pc>.decisions.jsonl` de `pc` vers
    `donnees/depots/<projet>/` ; rend (relatifs copiés, nombre de fichiers ignorés).

    Filtre rejoué, validation par schéma (`etat_depot`, `decision` ligne à ligne), identité
    `(projet, pc)` égale au chemin ; journal borné à `MAX_LIGNES_JOURNAL` lignes (dans
    `attente/` aussi). Fichiers d'un autre PC : non lus. Lien symbolique ou jonction : ignoré."""
    attente, donnees = chemins.attente(), chemins.donnees()
    copies: list[str] = []
    ignores = 0
    for projet in _sous_dossiers(attente / "depots"):
        try:
            ids.valider_projet(projet)
            dossier = chemins.joindre_sous(attente, "depots", projet)
        except ids.ErreurId:
            ignores += 1
            continue
        for nom in _fichiers(dossier):
            if nom not in (f"{pc}.json", f"{pc}{SUFFIXE_JOURNAL}"):
                continue  # autre PC, ou `.tmp` d'une écriture en cours
            try:
                if not (sans_lien(attente, "depots", projet, nom)
                        and sans_lien(donnees, "depots", projet, nom)):
                    raise ValueError("lien symbolique ou jonction")
                if nom.endswith(SUFFIXE_JOURNAL):
                    _borner_journal(attente, projet, nom)
                    brut = (dossier / nom).read_text(encoding="utf-8", errors="replace")
                    lignes = lignes_du_journal(brut, racine_github)
                    if not lignes:
                        raise ValueError("journal sans ligne valide")
                    contenu = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lignes)
                else:
                    brut = (dossier / nom).read_bytes()
                    if len(brut) > BORNE_ETAT_DEPOT_OCTETS:
                        raise ValueError("état du dépôt trop long")
                    objet = json.loads(brut.decode("utf-8"))
                    if not isinstance(objet, dict):
                        raise ValueError("objet attendu")
                    objet = filtrer_etat_depot(objet, racine_github)
                    schemas.valider("etat_depot", objet)
                    if (objet["projet"], objet["pc"]) != (projet, pc):
                        raise ValueError("chemin et contenu divergent")
                    contenu = json.dumps(objet, ensure_ascii=False, indent=2) + "\n"
                cible = chemins.joindre_sous(donnees, "depots", projet, nom)
            except (OSError, ValueError, RecursionError):
                ignores += 1
                continue
            _ecrire_si_change(cible, contenu)
            copies.append(f"depots/{projet}/{nom}")
    return copies, ignores
