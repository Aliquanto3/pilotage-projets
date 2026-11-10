"""Synchro demandée après une mutation, avec relance bornée si le cycle est occupé (story 5.2, M2).

`demander()` lance `sync` par `enfants.lancer`. Cycle occupé (`deja_en_cours` tout de suite, ou
enfant qui rend 3) : une seule relance est mise en file, reprogrammée au plus `len(DELAIS)` fois,
à intervalle croissant ; au-delà, l'opération reste dans `attente/operations/` pour le cycle
planifié. Un enfant fini (fait ou échec) ou un abandon clôt la série et remet le compteur à
zéro ; une mutation reçue pendant une série ne le remet jamais à zéro (borne tenue sous POST
répétés). `arreter()` annule la relance
en file et refuse les suivantes (arrêt du serveur).
"""

import threading

from pilotage.serveur import enfants

DELAIS = (2, 4, 8, 16, 30)  # s : 5 reprogrammations au plus, de 2 s à 30 s


def _minuteur_reel(delai: float, fonction):
    fil = threading.Timer(delai, fonction)
    fil.daemon = True
    return fil


# Frontière horloge : `minuteur(délai, fonction)` rend un objet `start()` / `cancel()`.
# Les tests le remplacent par un minuteur déclenché à la main.
minuteur = _minuteur_reel

_verrou = threading.Lock()
_en_file = None  # minuteur de la relance en file, ou None
_tentatives = 0  # reprogrammations de la série en cours (depuis le dernier enfant fini)
_arrete = False
abandons = 0  # relances abandonnées (journal, tests)


def reinitialiser() -> None:
    """Oublie relance en file, compteur et arrêt (tests)."""
    global _en_file, _tentatives, _arrete, abandons
    with _verrou:
        if _en_file is not None:
            _en_file.cancel()
        _en_file, _tentatives, _arrete, abandons = None, 0, False, 0


def etat() -> dict:
    """`{en_file, tentatives, arrete, abandons}` (lecture sans effet)."""
    return {"en_file": _en_file is not None, "tentatives": _tentatives, "arrete": _arrete,
            "abandons": abandons}


def arreter() -> None:
    """Annule la relance en file ; plus aucune relance ensuite."""
    global _en_file, _arrete
    with _verrou:
        _arrete = True
        if _en_file is not None:
            _en_file.cancel()
        _en_file = None


def noter(message: str) -> None:
    """Une ligne au journal des enfants (jamais d'exception)."""
    journal = enfants._ouvrir_journal()
    if journal is not None:
        try:
            enfants._journal(journal, message)
        finally:
            try:
                journal.close()
            except OSError:
                pass


def _programmer() -> str:
    """Met une relance en file (une seule) ; `"en_file"` ou `"abandon"`."""
    global _en_file, _tentatives, abandons
    with _verrou:
        if _arrete:
            return "abandon"
        if _en_file is not None:
            return "en_file"
        abandon = _tentatives >= len(DELAIS)
        if abandon:
            abandons += 1
            _tentatives = 0  # série close : une mutation suivante en ouvre une nouvelle
        else:
            _en_file = minuteur(DELAIS[_tentatives], _tirer)
            _tentatives += 1
            _en_file.start()
    if abandon:
        noter("relance de sync abandonnée : cycle occupé, opérations laissées au cycle planifié")
        return "abandon"
    return "en_file"


def _fin(dernier: dict | None) -> None:
    global _tentatives
    if dernier is not None and dernier.get("resultat") == "deja_en_cours":
        _programmer()
        return
    with _verrou:
        _tentatives = 0


def _lancer() -> str:
    try:
        issue = enfants.lancer("sync", a_la_fin=_fin)
    except Exception as exc:  # noqa: BLE001 - Popen ou config : l'opération attend le cycle planifié
        noter(f"sync non lancée ({type(exc).__name__}) : opérations laissées au cycle planifié")
        return "abandon"
    if issue == "lance":
        return "lance"
    return _programmer()


def _tirer() -> None:
    global _en_file
    with _verrou:
        if _arrete:
            return
        _en_file = None
    _lancer()


def demander() -> str:
    """Synchro demandée par une mutation : `"lance"`, `"en_file"` ou `"abandon"`."""
    with _verrou:
        if _arrete:
            return "abandon"
        if _en_file is not None:
            return "en_file"  # une seule relance en file : elle verra aussi cette opération
    return _lancer()  # le compteur n'est remis à zéro que par la fin de la série (`_fin`)
