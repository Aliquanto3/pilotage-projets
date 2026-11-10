"""Instance précédente de l'appli : `attente/appli.pid` (pid et heure de création, AD-14).

Une instance n'est arrêtée que si le pid noté désigne encore le processus noté : l'heure de
création est relue (`GetProcessTimes`) sur la poignée même qui sert à l'arrêt, ce qui écarte
la réutilisation du pid entre la vérification et `TerminateProcess`. Hors Windows, l'heure de
création est inconnue (`None`) et rien n'est jamais arrêté.

Ces utilitaires restent dans `serveur/` : le graphe des imports interdit `serveur → hooks`.
"""

import json
import os
import sys
from pathlib import Path

from pilotage import chemins

_QUERY_LIMITED = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
_TERMINATE = 0x0001  # PROCESS_TERMINATE
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0


def _noyau32():
    import ctypes
    from ctypes import wintypes

    noyau32 = ctypes.WinDLL("kernel32", use_last_error=True)
    noyau32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    noyau32.OpenProcess.restype = wintypes.HANDLE
    temps = ctypes.POINTER(wintypes.FILETIME)
    noyau32.GetProcessTimes.argtypes = (wintypes.HANDLE, temps, temps, temps, temps)
    noyau32.GetProcessTimes.restype = wintypes.BOOL
    noyau32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    noyau32.TerminateProcess.restype = wintypes.BOOL
    noyau32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    noyau32.WaitForSingleObject.restype = wintypes.DWORD
    noyau32.CloseHandle.argtypes = (wintypes.HANDLE,)
    return noyau32


def _creation(noyau32, poignee) -> str | None:
    import ctypes
    from ctypes import wintypes

    cree, fin, noyau, user = (wintypes.FILETIME() for _ in range(4))
    if not noyau32.GetProcessTimes(
        poignee, ctypes.byref(cree), ctypes.byref(fin), ctypes.byref(noyau), ctypes.byref(user)
    ):
        return None
    valeur = (cree.dwHighDateTime << 32) | cree.dwLowDateTime
    return str(valeur) if valeur > 0 else None


def heure_creation(pid: int) -> str | None:
    """FILETIME décimal de création de `pid` ; `None` s'il est illisible ou hors Windows."""
    if sys.platform != "win32":
        return None
    try:
        noyau32 = _noyau32()
        poignee = noyau32.OpenProcess(_QUERY_LIMITED, False, pid)
        if not poignee:
            return None
        try:
            return _creation(noyau32, poignee)
        finally:
            noyau32.CloseHandle(poignee)
    except Exception:  # noqa: BLE001 - illisible : rien ne sera arrêté
        return None


def arreter_si_meme(pid: int, cree: str, attente_ms: int = 5000) -> bool:
    """Arrête `pid` seulement s'il est vivant et créé à `cree` ; rend `True` s'il a été arrêté."""
    if sys.platform != "win32" or pid == os.getpid() or not cree:
        return False
    try:
        noyau32 = _noyau32()
        poignee = noyau32.OpenProcess(_QUERY_LIMITED | _TERMINATE | _SYNCHRONIZE, False, pid)
        if not poignee:
            return False
        try:
            if _creation(noyau32, poignee) != cree:
                return False
            if noyau32.WaitForSingleObject(poignee, 0) == _WAIT_OBJECT_0:
                return False  # déjà terminé
            if not noyau32.TerminateProcess(poignee, 1):
                return False
            noyau32.WaitForSingleObject(poignee, attente_ms)
            return True
        finally:
            noyau32.CloseHandle(poignee)
    except Exception:  # noqa: BLE001 - dans le doute, on n'arrête rien
        return False


def lire_instance(fichier: Path) -> tuple[int, str] | None:
    """`(pid, cree)` noté dans `fichier`, ou `None` s'il est absent ou mal formé."""
    try:
        objet = json.loads(Path(fichier).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(objet, dict):
        return None
    pid, cree = objet.get("pid"), objet.get("cree")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if not isinstance(cree, str) or not cree.isdigit():
        return None
    return pid, cree


def arreter_precedente(fichier: Path | None = None) -> bool:
    """Arrête l'instance notée dans `attente/appli.pid` si pid et heure de création concordent."""
    instance = lire_instance(fichier or chemins.appli_pid())
    return instance is not None and arreter_si_meme(*instance)


def noter_instance(fichier: Path | None = None) -> None:
    """Note le pid et l'heure de création du processus courant (écriture atomique)."""
    pid = os.getpid()
    contenu = json.dumps({"pid": pid, "cree": heure_creation(pid)}) + "\n"
    chemins.ecrire_atomique(fichier or chemins.appli_pid(), contenu)


def effacer_instance(fichier: Path | None = None) -> None:
    """Supprime le fichier pid s'il désigne encore le processus courant."""
    fichier = fichier or chemins.appli_pid()
    try:
        objet = json.loads(fichier.read_text(encoding="utf-8"))
        if isinstance(objet, dict) and objet.get("pid") == os.getpid():
            fichier.unlink()
    except (OSError, ValueError):
        pass
