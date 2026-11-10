"""API du scan pour `sync` (story 3.1) : seul point d'appel hors de `pilotage/scan/`.

Les fonctions vivent dans `scan/cli.py` (contrat C1 : une story ne modifie que son `cli.py`) ;
cette façade fixe les noms dont `sync` dépend, comme `sync/verrou.py` le fait pour le mutex.
"""

from pilotage.scan.cli import ALERTE_ECHEC, MESSAGE_ECHEC
from pilotage.scan.cli import _ecrire_alertes_scan as ecrire_alertes_scan
from pilotage.scan.cli import _scanner as scanner
from pilotage.scan.lecture import nom_pc

__all__ = ["ALERTE_ECHEC", "MESSAGE_ECHEC", "ecrire_alertes_scan", "nom_pc", "scanner"]
