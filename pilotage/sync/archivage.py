"""Archivage des sessions anciennes et rotation des journaux (story 3.3, AD-3, AD-5 §8).

- Session de ce PC dont `dernier_tour` (à défaut `debut`) a plus de `JOURS_ARCHIVAGE` jours :
  `attente/etat/<projet>/<pc>/<s>.json` passe à `attente/archive/etat/<projet>/<pc>/<s>.json`
  (même arborescence), puis le fichier est retiré de `donnees/` ; le commit du cycle enregistre
  la suppression. Laissée au cycle suivant si son verrou de session est tenu ou si son pid est
  présent, quelle que soit son heure de création (examen refait sous le verrou). Fichier
  illisible, invalide ou à date illisible : jamais archivé. Une session reprise après archivage
  repart d'un état neuf (le hook ne lit pas `archive/`).
- Journaux `attente/journal/<nom>-AAAA-MM.log` de plus de `MOIS_JOURNAUX` mois : supprimés ; un
  nom sans date n'est jamais touché.

Le verrou de session est celui des hooks (`attente/verrous/<session>.lock`, `O_CREAT|O_EXCL`,
périmé après 2 s, supprimé par le seul porteur du jeton) : `hooks` n'est pas importable depuis
`sync`, et aucune couche commune ne peut le porter (`noyau` sans E/S, `chemins` voué aux chemins,
module racine interdit aux hooks par `tests/test_imports.py`) : le protocole est répété ici.
"""

import json
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import ids, schemas
from pilotage.scan import processus
from pilotage.sync import copie, depot

JOURS_ARCHIVAGE = 7
MOIS_JOURNAUX = 12
VERROU_PERIME_S = 2.0  # même valeur que `hooks._commun.VERROU_PERIME_S`
_JOURNAL = re.compile(r"[a-z]+-([0-9]{4})-([0-9]{2})\.log")


def dossier_archive() -> Path:
    """`attente/archive/` : états de sessions archivés (jamais copiés vers `donnees/`)."""
    return chemins.attente() / "archive"


def _prendre_verrou(session: str) -> tuple[Path, bytes] | None:
    """Pose le verrou de session des hooks avec un jeton (pid + aléa) ; None s'il est tenu.

    Même protocole que `hooks._commun.verrou` : `O_CREAT|O_EXCL`, verrou de plus de 2 s supprimé
    puis repris, et seul le porteur du jeton le supprime (`_rendre_verrou`).
    """
    chemin = chemins.joindre_sous(chemins.attente(), "verrous", f"{session}.lock")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descripteur = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                if time.time() - chemin.stat().st_mtime <= VERROU_PERIME_S:
                    return None
                chemin.unlink()  # hook tué : verrou périmé, repris
            except OSError:
                return None
            continue
        except OSError:
            return None
        jeton = f"{os.getpid()} {os.urandom(8).hex()}".encode("ascii")
        try:
            os.write(descripteur, jeton)
        finally:
            os.close(descripteur)
        return chemin, jeton
    return None


def _rendre_verrou(chemin: Path, jeton: bytes) -> None:
    """Supprime le verrou s'il porte encore notre jeton (jugé périmé et repris : pas touché)."""
    try:
        with open(chemin, "rb") as fichier:
            notre = fichier.read() == jeton
        if notre:
            chemin.unlink()
    except OSError:
        pass


def _date(objet: dict) -> datetime | None:
    texte = objet.get("dernier_tour") or objet.get("debut")
    try:
        return datetime.strptime(texte, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _a_archiver(source: Path, cle: tuple[str, str, str], maintenant: datetime) -> bool:
    """État lisible, valide, conforme à son chemin, daté de plus de 7 jours et sans pid présent.

    Tout pid présent garde la session, même sans `pid_cree` ou avec une autre heure de création
    (prudence : l'inverse de la règle « tourne » de 2.6, voulu).
    """
    try:
        objet = json.loads(source.read_text(encoding="utf-8"))
        schemas.valider("session", objet)
    except (OSError, ValueError):
        return False
    if (objet["projet"], objet["pc"], objet["session"]) != cle:
        return False
    date = _date(objet)
    if date is None or maintenant - date <= timedelta(days=JOURS_ARCHIVAGE):
        return False
    return not processus.pid_present(objet["pid"])


def _suivi(donnees: Path, relatif: str) -> bool:
    """Relatif suivi par git dans `donnees/` (sinon `git add` de son retrait ferait échouer le
    commit du cycle : pathspec sans correspondance)."""
    try:
        resultat = depot.git(["ls-files", "--error-unmatch", "--", relatif], donnees)
    except depot.ErreurGit:
        return False
    return resultat.returncode == 0


def _archiver(
    projet: str, pc: str, nom: str, maintenant: datetime, journal: Callable[[str], None]
) -> str | None:
    """Archive un état s'il y a lieu ; rend le relatif retiré de `donnees/` (ou `""` s'il n'y
    était pas suivi), None s'il est laissé en place.

    Premier examen sans verrou (rien à faire le plus souvent), puis relecture et nouvel examen sous
    le verrou de session, juste avant le déplacement : un hook qui a écrit entre-temps l'emporte.
    """
    attente = chemins.attente()
    if not copie.sans_lien(attente, "etat", projet, pc, nom):
        return None
    try:
        session = ids.valider_session(nom.removesuffix(".json"))
        source = chemins.joindre_sous(attente, "etat", projet, pc, nom)
        cible = chemins.joindre_sous(dossier_archive(), "etat", projet, pc, nom)
    except ValueError:
        return None
    cle = (projet, pc, session)
    if not _a_archiver(source, cle, maintenant):
        return None
    relatif = f"etat/{projet}/{pc}/{nom}"
    donnees = chemins.donnees()
    publiee = copie.sans_lien(donnees, "etat", projet, pc, nom)
    # `git ls-files` hors verrou : un sous-processus lent (jusqu'à 120 s) rendrait le verrou
    # périmé (2 s) et laisserait un hook le reprendre pendant le déplacement.
    suivi = publiee and _suivi(donnees, relatif)
    verrou = _prendre_verrou(session)
    if verrou is None:
        return None
    try:
        if not _a_archiver(source, cle, maintenant):
            return None
        try:
            cible.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, cible)
        except OSError:
            return None
        if not publiee:
            return ""
        try:
            (donnees / relatif).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # Copie publiée non supprimable : l'état revient dans `attente/` (nouvel essai au cycle
            # suivant) plutôt qu'une copie orpheline dans `donnees/` que plus rien ne retirerait.
            journal("archivage : retrait de donnees/ impossible, session laissée au cycle suivant")
            try:
                # Sans écraser : un état recréé entre-temps par un hook (verrou jugé périmé)
                # l'emporte ; `os.link` échoue si `source` existe.
                os.link(cible, source)
            except OSError:
                journal("archivage : état resté dans archive/, copie orpheline dans donnees/")
                return ""
            try:
                cible.unlink()
            except OSError:
                pass  # doublon dans archive/, écrasé au prochain archivage
            return None
        return relatif if suivi else ""
    finally:
        _rendre_verrou(*verrou)


def archiver_sessions(
    pc: str, maintenant: datetime, journal: Callable[[str], None] = lambda texte: None
) -> tuple[list[str], int]:
    """Archive les sessions de `pc` ; rend (relatifs retirés de `donnees/` pour `git add`,
    nombre de sessions archivées). `journal` reçoit les échecs de retrait (messages fixes)."""
    attente = chemins.attente()
    retires: list[str] = []
    nombre = 0
    for projet in copie._sous_dossiers(attente / "etat"):
        try:
            ids.valider_projet(projet)
            dossier_pc = chemins.joindre_sous(attente, "etat", projet, pc)
        except ids.ErreurId:
            continue
        for nom in copie._fichiers(dossier_pc):
            if not nom.endswith(".json"):
                continue
            resultat = _archiver(projet, pc, nom, maintenant, journal)
            if resultat is not None:
                nombre += 1
                if resultat:
                    retires.append(resultat)
    return retires, nombre


def faire_tourner_journaux(maintenant: datetime) -> int:
    """Supprime les journaux datés de plus de `MOIS_JOURNAUX` mois ; rend leur nombre."""
    courant = maintenant.year * 12 + maintenant.month
    supprimes = 0
    try:
        entrees = [e for e in os.scandir(chemins.attente() / "journal") if e.is_file()]
    except OSError:
        return 0
    for entree in entrees:
        trouve = _JOURNAL.fullmatch(entree.name)
        if not trouve or not 1 <= int(trouve[2]) <= 12:
            continue  # sans date : jamais supprimé
        if courant - (int(trouve[1]) * 12 + int(trouve[2])) > MOIS_JOURNAUX:
            try:
                os.unlink(entree.path)
                supprimes += 1
            except OSError:
                pass
    return supprimes
