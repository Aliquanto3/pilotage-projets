r"""Façade du mutex `Local\pilotage-projets-sync` pour `sync` et le serveur (AD-5 §3).

L'implémentation est dans `pilotage.scan.verrou` (le graphe d'imports interdit `scan -> sync`).
`occupe()` est la seule sonde ; elle ne prend jamais le mutex.
"""

from pilotage.scan.verrou import NOM, Verrou, nom, occupe

__all__ = ["NOM", "Verrou", "nom", "occupe"]
