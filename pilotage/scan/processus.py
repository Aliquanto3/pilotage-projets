"""Pid vivant et heure de création du processus, en lecture seule (story 2.6, AD-11).

`vivante` : Windows seulement (ctypes `OpenProcess` + `GetProcessTimes` + `GetExitCodeProcess`) ;
ailleurs, ou au moindre échec, le processus est tenu pour absent. `pid_present` (archivage, 3.3) :
tous OS, prudent (au moindre échec, présent). Aucun signal ni `TerminateProcess` : ce module
ne fait jamais autre chose que lire.
"""

import sys

_QUERY_LIMITED = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
_STILL_ACTIVE = 259


def heure_creation(pid: int) -> int | None:
    """FILETIME de création du processus vivant `pid`, ou None (absent, terminé, inconnu).

    Toute erreur de l'adaptateur (ctypes, DLL, accès refusé) donne None : jamais d'exception.
    """
    if sys.platform != "win32" or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    try:
        return _heure_creation_windows(pid)
    except Exception:  # noqa: BLE001 - adaptateur jamais bloquant pour le scan
        return None


def _heure_creation_windows(pid: int) -> int | None:
    import ctypes
    from ctypes import wintypes

    noyau = ctypes.WinDLL("kernel32", use_last_error=True)
    noyau.OpenProcess.restype = wintypes.HANDLE
    noyau.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    noyau.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    noyau.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    noyau.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = noyau.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        creation, sortie, noyau_t, utilisateur = (wintypes.FILETIME() for _ in range(4))
        if not noyau.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != _STILL_ACTIVE:
            return None
        if not noyau.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(sortie),
            ctypes.byref(noyau_t), ctypes.byref(utilisateur),
        ):
            return None
        valeur = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return valeur or None
    finally:
        noyau.CloseHandle(handle)


def vivante(pid: int, pid_cree: object) -> bool:
    """Le pid tourne et sa date de création est celle notée (Windows réutilise les pid).

    `pid_cree` : FILETIME décimal (chaîne ou entier). `None` (heure non notée par le hook) : False,
    un pid vivant seul ne prouve rien (pid réutilisé).
    """
    if pid_cree is None or isinstance(pid_cree, bool):
        return False
    try:
        attendu = int(pid_cree)
    except (TypeError, ValueError):
        return False
    actuel = heure_creation(pid)
    return actuel is not None and actuel == attendu


def pid_present(pid: object) -> bool:
    """Un processus porte ce pid (quel qu'il soit), en lecture seule ; prudent pour l'archivage.

    Windows : `OpenProcess` puis `GetExitCodeProcess` (accès refusé : présent). Ailleurs :
    `os.getpgid(pid)`, simple lecture (`ProcessLookupError` : absent, `PermissionError` : présent).
    Pid invalide : False. Échec de l'adaptateur : True (dans le doute, pas d'archivage).
    """
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            return _pid_present_windows(pid)
        import os

        os.getpgid(pid)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:  # noqa: BLE001 - dans le doute, présent
        return True


def _pid_present_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    noyau = ctypes.WinDLL("kernel32", use_last_error=True)
    noyau.OpenProcess.restype = wintypes.HANDLE
    noyau.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    noyau.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    noyau.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = noyau.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER : aucun processus
    try:
        code = wintypes.DWORD()
        if not noyau.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        noyau.CloseHandle(handle)
