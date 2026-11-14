"""`lancer.py rapport [--semaine AAAA-Www]` (story 9.2, FR45) : page HTML de la semaine.

Lit les données (`lecture.lire_entree`), calcule la synthèse (`semaine`), rend la page (`page`)
et l'écrit de façon atomique sous `chemins.rapports()`. Sans réseau ni modèle ; le seul
sous-processus est le `git` de `lecture`. Les messages d'erreur ne portent que le type de
l'erreur : jamais de contenu de données ni de chemin absolu.
"""

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pilotage import chemins
from pilotage.rapport import generation, lecture, semaine
from pilotage.rapport.generation import semaine_courante

ERREUR = "rapport : échec de la lecture, du rendu ou de l'écriture"
_ERREURS = (OSError, chemins.ErreurConfiguration, ValueError, UnicodeError,
            subprocess.SubprocessError)


def _relatif(chemin: Path) -> str:
    return chemin.relative_to(chemins.racine_locale()).as_posix()


def main(arguments: list[str], maintenant: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lancer.py rapport", description="Rapport de la semaine, en page HTML locale."
    )
    parser.add_argument("--semaine", help="semaine ISO AAAA-Www (défaut : la semaine courante)")
    ns = parser.parse_args(arguments)
    maintenant = maintenant or datetime.now(UTC)
    voulue = ns.semaine if ns.semaine is not None else semaine_courante(maintenant)
    try:
        semaine.bornes_semaine(voulue, lecture.FuseauLocal())
    except (ValueError, OverflowError):
        print("rapport : semaine ISO AAAA-Www attendue (semaine existante)", file=sys.stderr)
        return 2
    try:
        cible = generation.generer(voulue, maintenant)
        affiche = _relatif(cible)
    except _ERREURS as exc:
        print(f"{ERREUR} ({type(exc).__name__})", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 : filet, jamais de traceback (chemins absolus)
        print(f"{ERREUR} (inattendue : {type(exc).__name__})", file=sys.stderr)
        return 1
    print(affiche)
    return 0
