"""`POST /api/rapport` (story 9.4) : génère la page de la semaine en cours et l'ouvre.

La génération tourne dans le fil de la requête (quelques secondes, sans réseau) : le serveur est
un `ThreadingHTTPServer`, les autres routes restent servies. Un verrou de module refuse une
seconde génération simultanée (409). L'URI `file:` est construite ici, depuis
`chemins.rapport_semaine()` : le client n'envoie rien, et aucune réponse ne porte de chemin.
"""

import re
import threading
import webbrowser
from collections.abc import Callable
from datetime import UTC, datetime

from pilotage.rapport import generation
from pilotage.serveur.routes import Reponse

_NOM_PAGE = re.compile(r"semaine-[0-9]{4}-W[0-9]{2}\.html")
_SEMAINE = re.compile(r"[0-9]{4}-W[0-9]{2}")

_verrou = threading.Lock()
_navigateur: Callable[[str], object] | None = None
_maintenant: Callable[[], datetime] | None = None


def configurer(
    navigateur: Callable[[str], object], maintenant: Callable[[], datetime] | None = None
) -> None:
    """Navigateur (défaut `webbrowser.open`) et horloge (aware) ; appelé par `serveur/cli`."""
    global _navigateur, _maintenant
    _navigateur = navigateur
    _maintenant = maintenant


def reinitialiser() -> None:
    """État initial du module (tests)."""
    global _navigateur, _maintenant
    _navigateur = None
    _maintenant = None


def _instant() -> datetime:
    return _maintenant() if _maintenant is not None else datetime.now(UTC)


def rapport(parametres: dict[str, str], corps: bytes) -> Reponse:
    del parametres
    if corps:
        return Reponse(400, erreur="corps refusé")
    if not _verrou.acquire(blocking=False):
        return Reponse(
            409, donnees={"type": "rapport", "etat": "deja_en_cours"}, erreur="déjà en cours"
        )
    try:
        return _generer_et_ouvrir()
    finally:
        _verrou.release()


def _generer_et_ouvrir() -> Reponse:
    try:
        instant = _instant()
        semaine = generation.semaine_courante(instant)
        chemin = generation.generer(semaine, instant)
        uri = chemin.resolve().as_uri()
    except Exception:  # noqa: BLE001 - ErreurConfiguration comprise : sa cause porte un chemin
        return Reponse(500, erreur="rapport impossible")
    if (
        not _SEMAINE.fullmatch(semaine)
        or not uri.startswith("file:")
        or not _NOM_PAGE.fullmatch(chemin.name)
        or chemin.name != f"semaine-{semaine}.html"
    ):
        return Reponse(500, erreur="rapport impossible")
    navigateur = _navigateur if _navigateur is not None else webbrowser.open
    try:
        ouvert = navigateur(uri)
    except Exception:  # noqa: BLE001 - navigateur introuvable ou en erreur : réponse fixe
        ouvert = False
    if ouvert is False:
        return Reponse(500, erreur="page générée, ouverture impossible")
    return Reponse(200, donnees={"type": "rapport", "etat": "ouvert", "semaine": semaine})
