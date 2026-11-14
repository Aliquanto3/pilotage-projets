"""`lancer.py rapport [--semaine AAAA-Www]` (story 9.2, FR45) : page HTML de la semaine.

Lit les données (`lecture.lire_entree`), calcule la synthèse (`semaine`), rend la page (`page`)
et l'écrit de façon atomique sous `chemins.rapports()`. Sans réseau ni modèle ; le seul
sous-processus est le `git` de `lecture`. Les messages d'erreur ne portent que le type de
l'erreur : jamais de contenu de données ni de chemin absolu.
"""

import argparse
import dataclasses
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import texte as noyau_texte
from pilotage.rapport import lecture, page, semaine

ERREUR = "rapport : échec de la lecture, du rendu ou de l'écriture"
_ERREURS = (OSError, chemins.ErreurConfiguration, ValueError, UnicodeError,
            subprocess.SubprocessError)


def semaine_courante(maintenant: datetime) -> str:
    """Semaine ISO `AAAA-Www` de `maintenant` (aware) en heure locale."""
    annee, numero, _ = maintenant.astimezone(lecture.FuseauLocal()).isocalendar()
    return f"{annee}-W{numero:02d}"


def _alertes_nettoyees(synthese: semaine.Synthese) -> semaine.Synthese:
    """Une alerte ancienne peut porter un chemin : racine GitHub masquée, secret retiré."""
    racine = str(chemins.racine_github())
    alertes = tuple(noyau_texte.nettoyer(a, page.BORNE_TEXTE, racine) for a in synthese.alertes)
    return dataclasses.replace(synthese, alertes=alertes)


def _relatif(chemin: Path) -> str:
    return chemin.relative_to(chemins.racine_locale()).as_posix()


def main(arguments: list[str], maintenant: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lancer.py rapport", description="Rapport de la semaine, en page HTML locale."
    )
    parser.add_argument("--semaine", help="semaine ISO AAAA-Www (défaut : la semaine courante)")
    ns = parser.parse_args(arguments)
    maintenant = maintenant or datetime.now(UTC)
    voulue = ns.semaine or semaine_courante(maintenant)
    try:
        semaine.bornes_semaine(voulue, lecture.FuseauLocal())
    except ValueError:
        print("rapport : semaine ISO AAAA-Www attendue (semaine existante)", file=sys.stderr)
        return 2
    try:
        cible = chemins.rapport_semaine(voulue)
        affiche = _relatif(cible)
        entree = lecture.lire_entree(voulue, maintenant)
        synthese = _alertes_nettoyees(semaine.synthese_semaine(entree, voulue, maintenant))
        css = (chemins.racine_web() / "charte.css").read_text(encoding="utf-8")
        contenu = page.rendre_page(
            synthese, css=css, genere=maintenant.astimezone(lecture.FuseauLocal())
        )
        chemins.ecrire_atomique(cible, contenu)
    except _ERREURS as exc:
        print(f"{ERREUR} ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(affiche)
    return 0
