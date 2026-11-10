"""Hook `Stop` (AD-1) : lancé en `python -I -S`, sort toujours avec 0, rien sur stdout."""

EVENEMENT = "Stop"

try:
    import os

    # Interrupteur, avant tout import du paquet (rien lu ni écrit, pas même `__pycache__`) :
    # même calcul que `chemins.fichier_desactive()`, vérifié par `test_hooks_session.py`.
    _surcharge = os.environ.get("PILOTAGE_RACINE_LOCALE", "")
    if _surcharge:
        _desactive = os.path.join(os.path.abspath(_surcharge), "installation", "desactive")
    else:
        _desactive = os.path.join(os.path.expanduser("~"), ".claude", "pilotage", "desactive")
    if not os.path.exists(_desactive):
        import sys

        _racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if _racine not in sys.path:
            sys.path.insert(0, _racine)  # `-I` n'ajoute pas le dossier du script
        from pilotage.hooks import _commun, tour

        _commun.executer(EVENEMENT, tour.fin_de_tour)
except BaseException as _erreur:  # noqa: BLE001 - un hook sort toujours avec 0
    try:
        from pilotage.hooks import _commun

        _commun.journaliser(EVENEMENT, _erreur)
    except BaseException:  # noqa: BLE001
        pass

raise SystemExit(0)
