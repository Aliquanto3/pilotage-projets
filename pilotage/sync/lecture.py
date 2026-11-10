"""Façade de la lecture de l'état pour le serveur (AD-14) : `serveur -> scan` est hors du graphe.

L'implémentation est dans `pilotage.scan.lecture` (comme `sync/verrou.py` pour le mutex).
"""

from pilotage.scan.lecture import lire_etat, nom_pc

__all__ = ["lire_etat", "nom_pc"]
