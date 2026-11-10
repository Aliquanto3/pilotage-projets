r"""Mutex nommé `Local\pilotage-projets-sync` (AD-5 §1, §3), partagé par `scan` et `sync`.

Le code vit dans `scan/` parce que le graphe des imports interdit `scan -> sync` ; la façade
publique est `pilotage.sync.verrou`. Le mutex est propre à la session Windows de l'utilisateur
(`Local\`) : une seule session interactive est supposée (L3).

Hors Windows (le projet cible Windows), il n'y a pas de mutex : `prendre` rend toujours acquis et
`occupe` rend faux ; les tests qui en dépendent sont sautés.
"""

import ctypes
import os
import sys
from ctypes import wintypes
from types import TracebackType

NOM = "Local\\pilotage-projets-sync"
VARIABLE_NOM = "PILOTAGE_NOM_MUTEX"  # tests : un nom propre, pour ne pas gêner un vrai scan
WAIT_OBJECT_0 = 0x0
WAIT_ABANDONED = 0x80
WAIT_TIMEOUT = 0x102
WAIT_FAILED = 0xFFFFFFFF
SYNCHRONIZE = 0x00100000
_WINDOWS = sys.platform == "win32"


def nom() -> str:
    """Nom du mutex : `NOM`, ou la valeur de `PILOTAGE_NOM_MUTEX` si elle est posée."""
    return os.environ.get(VARIABLE_NOM) or NOM


def _noyau():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    k.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenMutexW.restype = wintypes.HANDLE
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.ReleaseMutex.argtypes = [wintypes.HANDLE]
    k.ReleaseMutex.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    return k


class Verrou:
    """Prise du mutex sans attente. `acquis` dit si ce processus le tient ; libération sûre.

    À utiliser en `with Verrou() as verrou:` ; `verrou.abandonne` est vrai si le propriétaire
    précédent est mort sans le libérer (`WAIT_ABANDONED`, compté comme acquis).
    """

    def __init__(self) -> None:
        self.acquis = False
        self.abandonne = False
        self._handle = None
        self._k = None

    def __enter__(self) -> Verrou:
        if not _WINDOWS:
            self.acquis = True
            return self
        k = self._k = _noyau()
        handle = k.CreateMutexW(None, False, nom())
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW a échoué")
        # Occupé d'après l'attente (WAIT_TIMEOUT), jamais d'après ERROR_ALREADY_EXISTS.
        etat = k.WaitForSingleObject(handle, 0)
        if etat in (WAIT_OBJECT_0, WAIT_ABANDONED):
            self._handle = handle
            self.acquis = True
            self.abandonne = etat == WAIT_ABANDONED
        else:
            erreur = ctypes.get_last_error()
            k.CloseHandle(handle)
            if etat != WAIT_TIMEOUT:  # WAIT_FAILED : une erreur, pas un mutex occupé
                raise OSError(erreur, "WaitForSingleObject a échoué")
        return self

    def __exit__(
        self,
        type_: type[BaseException] | None,
        valeur: BaseException | None,
        pile: TracebackType | None,
    ) -> None:
        self.liberer()

    def liberer(self) -> None:
        """Rend le mutex puis ferme la poignée ; sans effet si rien n'est tenu."""
        handle, self._handle = self._handle, None
        if handle is not None and self._k is not None:
            try:
                self._k.ReleaseMutex(handle)
            finally:
                self._k.CloseHandle(handle)
        self.acquis = False


def occupe() -> bool:
    """Vrai si un cycle tient le mutex : `OpenMutexW(SYNCHRONIZE)`, sans jamais le prendre."""
    if not _WINDOWS:
        return False
    k = _noyau()
    handle = k.OpenMutexW(SYNCHRONIZE, False, nom())
    if not handle:
        return False
    k.CloseHandle(handle)
    return True
