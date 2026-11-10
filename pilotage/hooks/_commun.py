"""Socle commun des hooks (AD-1, AD-2, AD-3, AD-9, AD-10) : stdlib seule, aucun réseau.

API pour les hooks :
- `lire_payload(flux)` : stdin en octets, décodé UTF-8, objet JSON ;
- `emettre(octets)` : seule écriture sur stdout ;
- `journaliser(evenement, erreur)` : une ligne dans `attente/journal/hooks-AAAA-MM.log`
  (horodatage, événement, type d'erreur ; jamais de contenu) ;
- `verrou(session, essais)` : `attente/verrous/<session>.lock` par `O_CREAT|O_EXCL`, 20 ms par
  essai, verrou de plus de 2 s supprimé ; jeton (pid + aléa) écrit dedans, seul son porteur le
  rend ; lève `VerrouOccupe` ;
- `contexte(payload)` : projet, pc, session et dossier validés, ou `None` si le hook est sans
  effet (sous-agent, dossier hors de `table-dossiers.json`, `cwd` hors de la racine GitHub) ;
- `session_seule(payload)` : pc et session validés, sans `cwd` (fin ou mise à jour d'une session
  existante), `None` pour un sous-agent ; `etats_de_session(pc, session)` : ses états existants ;
- `chemin_etat`, `lire_etat`, `ecrire_etat` : état d'une session, validé par le schéma `session`
  puis écrit par `chemins.ecrire_atomique` ;
- `declencher_sync(evenement)` : crée `attente/sync-demande` puis lance `lancer.py sync` détaché
  (AD-6, M2), sans attendre ni jamais lever ;
- `executer(evenement, traitement)` : lit le payload, appelle `traitement`, journalise toute erreur.
"""

import errno
import json
import os
import re
import sys
import time
from collections import namedtuple
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import ids, schemas, texte

ATTENTE_VERROU_S = 0.020
PAUSE_VERROU_S = 0.002
VERROU_PERIME_S = 2.0
BORNE_BRANCHE = 255
_HEAD = re.compile(r"ref:\s*refs/heads/(.+?)\s*")
_GITDIR = re.compile(r"gitdir:\s*(.+?)\s*")
# Drapeaux de `CreateProcess` (AD-6), définis ici pour rester testables hors Windows.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
ERREUR_ACCES_REFUSE = 5  # ERROR_ACCESS_DENIED : breakaway refusé par le job de `claude.exe`
NOM_LANCEUR = "lancer.py"


class ErreurHook(Exception):
    """Abandon volontaire d'un hook (journalisé par son nom de classe)."""


class PayloadInvalide(ErreurHook):
    """stdin n'est pas un objet JSON UTF-8, ou un champ attendu manque."""


class TableAbsente(ErreurHook):
    """`table-dossiers.json` absent : le scan n'a pas encore tourné."""


class TableIllisible(ErreurHook):
    """`table-dossiers.json` illisible ou invalide."""


class VerrouOccupe(ErreurHook):
    """Verrou de session tenu par un autre hook au-delà du délai."""


# `namedtuple` plutôt que `dataclass` : `dataclasses` coûte ~10 ms d'import au démarrage du hook.
# `dossier` est la clé de `table-dossiers.json` (C5).
Contexte = namedtuple("Contexte", ["projet", "pc", "session", "dossier", "cwd"])


def maintenant() -> str:
    """Horodatage ISO 8601 UTC à la seconde, avec `Z`."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def emettre(octets: bytes) -> None:
    """Seule écriture sur stdout : octets bruts (UTF-8 sans BOM attendu), vidés aussitôt."""
    sys.stdout.buffer.write(octets)
    sys.stdout.buffer.flush()


def lire_payload(flux=None) -> dict:
    """Lit le flux (stdin par défaut) en octets, décode en UTF-8 strict, rend l'objet JSON."""
    brut = (flux if flux is not None else sys.stdin.buffer).read()
    try:
        objet = json.loads(brut.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise PayloadInvalide("payload illisible") from None
    if not isinstance(objet, dict):
        raise PayloadInvalide("payload : objet attendu")
    return objet


def type_erreur(erreur: BaseException | str) -> str:
    """Nom de classe (plus le code `errno` d'une `OSError`), jamais le message."""
    if isinstance(erreur, str):
        return erreur
    nom = type(erreur).__name__
    code = getattr(erreur, "errno", None) if isinstance(erreur, OSError) else None
    if isinstance(code, int) and code in errno.errorcode:
        nom = f"{nom}:{errno.errorcode[code]}"
    return nom


def journaliser(evenement: str, erreur: BaseException | str) -> None:
    """Ajoute `<horodatage> <evenement> <type>` à `attente/journal/hooks-AAAA-MM.log`.

    Ne lève jamais : un journal impossible à écrire (disque plein) est abandonné.
    """
    try:
        horodatage = maintenant()
        try:
            dossier = chemins.attente() / "journal"
        except chemins.ErreurConfiguration:  # config.json invalide : emplacement par défaut
            dossier = chemins.attente_de_secours() / "journal"
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"hooks-{horodatage[:7]}.log"
        ligne = f"{horodatage} {evenement} {type_erreur(erreur)}\n"
        with open(chemin, "a", encoding="utf-8", newline="") as fichier:
            fichier.write(ligne)
    except Exception:  # noqa: BLE001 - le journal ne doit jamais faire échouer le hook
        pass


def chemin_verrou(session: str) -> Path:
    """`attente/verrous/<session>.lock`, session validée avant la jointure."""
    nom = f"{ids.valider_session(session)}.lock"
    return chemins.joindre_sous(chemins.attente(), "verrous", nom)


def _prendre(chemin: Path) -> int | None:
    try:
        return os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            if time.time() - chemin.stat().st_mtime > VERROU_PERIME_S:
                chemin.unlink()
        except OSError:
            pass  # libéré entre-temps, ou Windows (ouvert, suppression en cours) : occupé
        return None
    except PermissionError:
        return None  # Windows : fichier en cours de suppression par un autre hook


@contextmanager
def verrou(session: str, essais: int = 1) -> Iterator[None]:
    """Verrou de session : `essais` fois 20 ms au plus, sinon `VerrouOccupe`.

    Un verrou de plus de 2 s (hook tué) est supprimé puis repris.
    """
    chemin = chemin_verrou(session)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    descripteur = None
    for _ in range(max(1, essais)):
        limite = time.monotonic() + ATTENTE_VERROU_S
        while True:
            descripteur = _prendre(chemin)
            if descripteur is not None or time.monotonic() >= limite:
                break
            time.sleep(PAUSE_VERROU_S)
        if descripteur is not None:
            break
    if descripteur is None:
        raise VerrouOccupe("verrou de session tenu")
    jeton = f"{os.getpid()} {os.urandom(8).hex()}".encode("ascii")
    try:
        os.write(descripteur, jeton)
        yield
    finally:
        os.close(descripteur)
        try:
            # Jugé périmé puis repris par un autre hook : ce n'est plus le nôtre, on n'y touche pas.
            with open(chemin, "rb") as fichier:
                notre = fichier.read() == jeton
            if notre:
                chemin.unlink()
        except OSError:
            pass


def relatif_sous(chemin: str, racine: str) -> str | None:
    """Chemin relatif de `chemin` sous `racine` (`/`, casse ignorée), ou `None` s'il n'y est pas."""
    parties = [p for p in re.split(r"[\\/]+", chemin) if p]
    base = [p for p in re.split(r"[\\/]+", racine) if p]
    if not base or len(parties) <= len(base) or any(p in (".", "..") for p in parties):
        return None
    if [p.casefold() for p in parties[: len(base)]] != [b.casefold() for b in base]:
        return None
    return "/".join(parties[len(base) :])


def lire_table() -> dict[str, str]:
    """`dossiers` de `table-dossiers.json`, validé ; lève `TableAbsente` ou `TableIllisible`."""
    chemin = chemins.table_dossiers()
    try:
        objet = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TableAbsente("table-dossiers absente") from None
    except (OSError, ValueError):
        raise TableIllisible("table-dossiers illisible") from None
    try:
        schemas.valider("table_dossiers", objet)
    except schemas.ErreurValidation:
        raise TableIllisible("table-dossiers invalide") from None
    return objet["dossiers"]


def nom_pc() -> str:
    """`COMPUTERNAME` (nom d'hôte court hors Windows), normalisé comme le scan
    (`ids.normaliser_pc`, partagé avec `scan.lecture.nom_pc`)."""
    nom = os.environ.get("COMPUTERNAME", "")
    if not nom and hasattr(os, "uname"):
        nom = os.uname().nodename.split(".")[0]
    return ids.normaliser_pc(nom)


def contexte(payload: dict) -> Contexte | None:
    """Contexte validé, ou `None` si le hook doit rester sans effet (AD-2, table des dossiers)."""
    if "agent_id" in payload:
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise PayloadInvalide("cwd absent")
    relatif = relatif_sous(cwd, str(chemins.racine_github()))
    if relatif is None:
        return None
    dossier = ids.cle_dossier(relatif)
    projet = lire_table().get(dossier)
    if projet is None:
        return None
    return Contexte(
        projet=ids.valider_projet(projet),
        pc=nom_pc(),
        session=ids.valider_session(payload.get("session_id")),
        dossier=dossier,
        cwd=cwd,
    )


def session_seule(payload: dict) -> tuple[str, str] | None:
    """`(pc, session)` validés, sans lire `cwd` ni la table ; `None` pour un sous-agent (AD-2).

    Fin ou mise à jour d'une session existante : le `cwd` a pu changer depuis `SessionStart`,
    l'id de session prime. La création reste réservée à `contexte` (dossier de la table).
    """
    if "agent_id" in payload:
        return None
    return nom_pc(), ids.valider_session(payload.get("session_id"))


def etats_de_session(pc: str, session: str) -> list[Path]:
    """États existants `attente/etat/*/<pc>/<session>.json`, segments validés, triés par projet."""
    nom = f"{ids.valider_session(session)}.json"
    attente = chemins.attente()
    trouves: list[Path] = []
    try:
        projets = sorted(e.name for e in os.scandir(attente / "etat") if e.is_dir())
    except OSError:
        return trouves
    for projet in projets:
        try:
            relatif = ids.joindre("etat", projet, pc, nom)  # lexical, sans E/S
            # Test d'existence bon marché d'abord : la résolution (liens, jonctions) ne coûte
            # que pour les états trouvés (budget p95 avec beaucoup de projets).
            if os.path.isfile(attente / relatif):
                trouves.append(chemins.joindre_sous(attente, "etat", projet, pc, nom))
        except ids.ErreurId:
            continue  # dossier hors convention ou lien qui sort de `attente/` : ignoré
    return trouves


def chemin_etat(ctx: Contexte) -> Path:
    """`attente/etat/<projet>/<pc>/<session>.json`, segments validés, sous `attente/`."""
    return chemins.joindre_sous(
        chemins.attente(), "etat", ctx.projet, ctx.pc, f"{ctx.session}.json"
    )


def lire_etat(chemin: Path) -> dict | None:
    """État existant et valide, sinon `None` (absent, illisible ou invalide)."""
    try:
        objet = json.loads(chemin.read_text(encoding="utf-8"))
        schemas.valider("session", objet)
    except (OSError, ValueError):
        return None
    return objet


def ecrire_etat(chemin: Path, etat: dict) -> None:
    """Valide l'état (champ hors liste refusé : `ErreurValidation`) puis l'écrit atomiquement."""
    schemas.valider("session", etat)
    contenu = json.dumps(etat, ensure_ascii=False, indent=2) + "\n"
    chemins.ecrire_atomique(chemin, contenu)


def _gitdir_plausible(gitdir: Path) -> bool:
    """`<...>.git/worktrees/<nom>` ou `<...>.git/modules/...` : jamais un dossier arbitraire."""
    parties = [p.casefold() for p in gitdir.parts[:-1]]
    for i, partie in enumerate(parties[:-1]):
        if partie.endswith(".git"):
            suite = parties[i + 1 :]
            if suite == ["worktrees"] or suite[0] == "modules":
                return True
    return False


def lire_branche(dossier: Path) -> str | None:
    """Branche courante lue dans `.git` (dossier ou fichier `gitdir:` d'un worktree), sinon `None`.

    Aucun sous-processus. Détachée, illisible, trop longue ou suspecte (filtre de secrets) : `None`.
    """
    try:
        git = dossier / ".git"
        if git.is_file():
            trouve = _GITDIR.fullmatch(git.read_text(encoding="utf-8"))
            if not trouve:
                return None
            gitdir = Path(trouve.group(1))
            git = (gitdir if gitdir.is_absolute() else dossier / gitdir).resolve()
            if not _gitdir_plausible(git):
                return None
        trouve = _HEAD.fullmatch((git / "HEAD").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    if not trouve:
        return None
    branche = trouve.group(1)
    if (
        len(branche) > BORNE_BRANCHE
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in branche)
        or texte.est_suspect(branche)
    ):
        return None
    return branche


def pid_parent() -> int:
    """Pid du parent du hook : `claude.exe` en forme exec (story 2.1)."""
    return os.getppid()


def heure_creation(pid: int) -> str | None:
    """FILETIME décimal de création du processus (format `procStart`), `None` si illisible.

    Windows seulement (`GetProcessTimes` par ctypes) ; ailleurs, ou en cas d'échec : `None`.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        noyau32 = ctypes.WinDLL("kernel32", use_last_error=True)
        noyau32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        noyau32.OpenProcess.restype = wintypes.HANDLE
        temps = ctypes.POINTER(wintypes.FILETIME)
        noyau32.GetProcessTimes.argtypes = (wintypes.HANDLE, temps, temps, temps, temps)
        noyau32.GetProcessTimes.restype = wintypes.BOOL
        noyau32.CloseHandle.argtypes = (wintypes.HANDLE,)
        poignee = noyau32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not poignee:
            return None
        try:
            cree, fin, noyau, user = (wintypes.FILETIME() for _ in range(4))
            if not noyau32.GetProcessTimes(
                poignee, ctypes.byref(cree), ctypes.byref(fin), ctypes.byref(noyau),
                ctypes.byref(user),
            ):
                return None
        finally:
            noyau32.CloseHandle(poignee)
        valeur = (cree.dwHighDateTime << 32) | cree.dwLowDateTime
        return str(valeur) if valeur > 0 else None
    except Exception:  # noqa: BLE001 - jamais bloquant : `pid_cree` vaut alors null
        return None


def _breakaway_refuse(erreur: OSError) -> bool:
    return isinstance(erreur, PermissionError) or (
        getattr(erreur, "winerror", None) == ERREUR_ACCES_REFUSE
    )


def _lancer_detache(arguments: list[str], racine: str, evenement: str) -> None:
    import subprocess  # import tardif : seuls les hooks qui lancent la synchro le paient

    options = {
        "cwd": racine,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name != "nt":
        subprocess.Popen(arguments, start_new_session=True, **options)
        return
    drapeaux = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            arguments, creationflags=drapeaux | CREATE_BREAKAWAY_FROM_JOB, **options
        )
    except OSError as erreur:
        if not _breakaway_refuse(erreur):
            raise
        subprocess.Popen(arguments, creationflags=drapeaux, **options)
        journaliser(evenement, "SyncSansBreakaway")


def declencher_sync(evenement: str) -> None:
    """Lance `<pythonw> -I <racine installée>/lancer.py sync` détaché, sans l'attendre (AD-6).

    Crée d'abord `attente/sync-demande` (M2) : si un cycle tient déjà le mutex, il la verra et
    refera un cycle. Interpréteur ou lanceur absent, ou chemin relatif dans `config.json` : rien
    lancé, journalisé (sauf sous
    `PILOTAGE_RACINE_LOCALE` sans `PILOTAGE_PYTHONW`). Ne lève jamais, n'écrit rien sur stdout.
    """
    try:
        pythonw = chemins.pythonw()
        if pythonw is None:
            if not chemins.racine_surchargee():
                journaliser(evenement, "SyncSansPythonw")
            return
        racine = chemins.racine_installation()
        lanceur = racine / NOM_LANCEUR
        if not os.path.isabs(pythonw) or not racine.is_absolute():
            journaliser(evenement, "SyncCheminRelatif")  # évalué depuis le cwd : ignoré
            return
        if not os.path.isfile(pythonw):
            journaliser(evenement, "SyncSansPythonw")
            return
        if not lanceur.is_file():
            journaliser(evenement, "SyncSansLanceur")
            return
        demande = chemins.sync_demande()
        demande.parent.mkdir(parents=True, exist_ok=True)
        with open(demande, "ab"):
            pass
        _lancer_detache([pythonw, "-I", str(lanceur), "sync"], str(racine), evenement)
    except BaseException as erreur:  # noqa: BLE001 - la session ne doit jamais en pâtir
        journaliser(evenement, erreur)


def executer(evenement: str, traitement: Callable[[dict], None], flux=None) -> None:
    """Lit le payload et appelle `traitement` ; toute erreur est journalisée, jamais propagée."""
    try:
        traitement(lire_payload(flux))
    except BaseException as erreur:  # noqa: BLE001 - un hook sort toujours avec 0
        journaliser(evenement, erreur)
