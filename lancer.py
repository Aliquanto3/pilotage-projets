"""Point d'entrée : `lancer.py scan | sync | appli | installer-reglages [arguments]`.

Chaque sous-commande délègue à `main(argv) -> int` du `cli.py` de sa couche, importé
dans la fonction (import tardif) : une sous-commande ne charge que sa couche.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

# `python -I lancer.py` (tâche planifiée, story 3.5) n'ajoute pas le dossier du script à sys.path
_RACINE = str(Path(__file__).resolve().parent)
if _RACINE not in sys.path:
    sys.path.insert(0, _RACINE)


def _scan(argv: list[str]) -> int:
    from pilotage.scan.cli import main

    return main(argv)


def _sync(argv: list[str]) -> int:
    from pilotage.sync.cli import main

    return main(argv)


def _appli(argv: list[str]) -> int:
    from pilotage.serveur.cli import main

    return main(argv)


def _installer_reglages(argv: list[str]) -> int:
    from pilotage.installation.cli import main

    return main(argv)


SOUS_COMMANDES: dict[str, Callable[[list[str]], int]] = {
    "scan": _scan,
    "sync": _sync,
    "appli": _appli,
    "installer-reglages": _installer_reglages,
}


def main(argv: list[str] | None = None) -> int:
    """Analyse la sous-commande et rend le code de sortie de son `cli.main`."""
    parser = argparse.ArgumentParser(prog="lancer.py", description="Pilotage des projets.")
    parser.add_argument("commande", choices=list(SOUS_COMMANDES))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return SOUS_COMMANDES[ns.commande](list(ns.arguments))


if __name__ == "__main__":
    sys.exit(main())
