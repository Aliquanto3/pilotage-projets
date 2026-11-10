"""Scan et synchro lancés par le serveur, et état `cycle` (story 4.3, AD-5 §3 et §10, AD-14, M2).

Le serveur lance `<python de config.json> -I <installation>/lancer.py scan|sync` par `Popen`
(tableau d'arguments, `shell=False`, sans fenêtre, stdin et stdout fermés, stderr vers
`attente/journal/enfants-AAAA-MM.log`) sans attendre dans la requête ; un fil lit le code de
sortie. Un enfant qui dépasse `DELAI_ENFANT` est tué avec son arbre (résultat `echec`, cause
`delai`) : la reprise de la story 3.2 traite le cycle interrompu au cycle suivant.

La place est réservée sous `_verrou`, `Popen` compris : deux POST simultanés ne lancent qu'un
enfant (M2). `lire_cycle()` ne prend pas ce verrou : il lit `_etat`, remplacé d'un bloc par les
écrivains. Le mutex d'un cycle externe est lu par `sync.verrou.occupe()`, jamais pris. L'état
reste en mémoire.
"""

import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

from pilotage import chemins
from pilotage.sync import verrou

TYPES = ("scan", "sync")
CODE_FAIT = 0
CODE_OCCUPE = 3  # code du mutex pris (`sync.cli.CODE_OCCUPE`, `scan.cli.CODE_OCCUPE`)
CREATE_NO_WINDOW = chemins.CREATE_NO_WINDOW
CREATE_NEW_PROCESS_GROUP = 0x00000200
DELAI_ENFANT = 600  # s : au-delà, l'enfant (réseau, gh, invite git bloqués) est tué
DELAI_ARRET = 10  # s : attente de la fin d'un enfant tué
TAILLE_MAX_JOURNAL = 1024 * 1024  # octets : au-delà, le journal du mois repart à zéro

# Seule frontière externe : les tests la remplacent par un faux `Popen`.
popen = subprocess.Popen

_verrou = threading.Lock()  # écrivains seulement
# (type de l'enfant en cours ou None, dernier résultat) : un seul objet, lu sans verrou.
_etat: tuple[str | None, dict | None] = (None, None)

CYCLE_NEUTRE = {"en_cours": False, "type": None, "origine": None, "dernier": None}


def reinitialiser() -> None:
    """Oublie enfant et dernier résultat (tests)."""
    global _etat
    with _verrou:
        _etat = (None, None)


def lire_cycle() -> dict:
    """État `cycle` : sans effet, sans attendre un lancement, la sonde ne prend pas le mutex."""
    type_, dernier = _etat
    if type_ is not None:
        return {"en_cours": True, "type": type_, "origine": "appli", "dernier": dernier}
    if verrou.occupe():
        return {"en_cours": True, "type": None, "origine": "externe", "dernier": dernier}
    return {"en_cours": False, "type": None, "origine": None, "dernier": dernier}


def _resultat(code: int) -> str:
    if code == CODE_FAIT:
        return "fait"
    return "deja_en_cours" if code == CODE_OCCUPE else "echec"


def _maintenant() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _journal(fichier, message: str) -> None:
    if fichier is not None:
        try:
            fichier.write(f"{_maintenant()} {message}\n".encode())
            fichier.flush()
        except OSError:
            pass


def _ouvrir_journal():
    """Journal binaire en ajout (repart à zéro au-delà de `TAILLE_MAX_JOURNAL`) ; `None` si
    impossible : l'enfant part alors sans sortie d'erreur."""
    try:
        chemin = chemins.journal_enfants(_maintenant()[:7])
        chemin.parent.mkdir(parents=True, exist_ok=True)
        try:
            trop_gros = chemin.stat().st_size > TAILLE_MAX_JOURNAL
        except FileNotFoundError:
            trop_gros = False
        return open(chemin, "wb" if trop_gros else "ab")  # noqa: SIM115 - fermé par l'appelant
    except (OSError, ValueError):
        return None


def tuer_arbre(processus) -> None:
    """Arrête l'enfant et ses descendants ; ne lève jamais."""
    try:
        if sys.platform == "win32":
            systeme = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
            taskkill = systeme / "taskkill.exe"
            subprocess.run(
                [str(taskkill), "/T", "/F", "/PID", str(processus.pid)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=DELAI_ARRET, check=False, **chemins.options_sans_fenetre(),
            )
        else:
            processus.terminate()
            try:
                processus.wait(timeout=DELAI_ARRET)
            except subprocess.TimeoutExpired:
                pass
    except Exception:  # noqa: BLE001, S110 - repli ci-dessous
        pass
    try:
        if processus.poll() is None:
            processus.kill()
        processus.wait(timeout=DELAI_ARRET)
    except Exception:  # noqa: BLE001, S110 - enfant déjà fini ou injoignable
        pass


def _surveiller(type_: str, processus, a_la_fin=None) -> None:
    global _etat
    cause = None
    try:
        code = processus.wait(timeout=DELAI_ENFANT)
    except subprocess.TimeoutExpired:
        tuer_arbre(processus)
        code, cause = -1, "delai"
    except Exception:  # noqa: BLE001 - un enfant illisible compte comme un échec
        tuer_arbre(processus)  # la place est libérée : l'enfant ne doit pas survivre
        code = -1
    dernier = {"type": type_, "resultat": _resultat(code), "fin": _maintenant(), "cause": cause}
    with _verrou:
        _etat = (None, dernier)
    if a_la_fin is not None:
        try:
            a_la_fin(dernier)
        except Exception as exc:  # noqa: BLE001 - le rappel (relance M2) ne tue pas le fil
            journal = _ouvrir_journal()
            _journal(journal, f"rappel de fin de {type_} en échec : {type(exc).__name__}")
            if journal is not None:
                try:
                    journal.close()
                except OSError:
                    pass


def _commande(type_: str) -> list[str]:
    # `lire_config` refuse tout chemin non absolu (`ErreurConfiguration`, remontée à l'appelant).
    python = chemins.lire_config().get("python")
    racine = chemins.racine_installation()
    return [str(python or sys.executable), "-I", str(racine / "lancer.py"), type_]


def lancer(type_: str, a_la_fin=None) -> str:
    """Lance l'enfant `type_` ; rend `"lance"` ou `"deja_en_cours"` (rien n'est lancé).

    `a_la_fin(dernier)`, s'il est donné, est appelé par le fil de surveillance une fois la place
    libérée, avec le dernier résultat (`resultat` `fait`, `deja_en_cours` ou `echec`).

    Toute exception (Popen impossible, config illisible, fil refusé) libère la place, tue
    l'enfant s'il est parti, puis remonte à l'appelant.
    """
    global _etat
    if type_ not in TYPES:
        raise ValueError(type_)
    with _verrou:
        if _etat[0] is not None or verrou.occupe():
            return "deja_en_cours"
        dernier = _etat[1]
        _etat = (type_, dernier)  # visible dès maintenant par `lire_cycle`
        processus = None
        journal = _ouvrir_journal()
        try:
            commande = _commande(type_)
            _journal(journal, f"{type_} lancé")
            options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                       "stderr": journal if journal is not None else subprocess.DEVNULL,
                       "shell": False, "cwd": str(Path(commande[2]).parent)}
            if sys.platform == "win32":
                options["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
            processus = popen(commande, **options)
            threading.Thread(target=_surveiller, args=(type_, processus, a_la_fin),
                             daemon=True).start()
        except BaseException:
            if processus is not None:
                tuer_arbre(processus)
            _etat = (None, dernier)
            raise
        finally:
            if journal is not None:
                journal.close()  # l'enfant garde sa copie du descripteur
    return "lance"
