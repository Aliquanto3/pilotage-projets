"""Génération de la page de la semaine (stories 9.2 et 9.3), partagée par `cli.py` et `sync`.

Lit les données, calcule la synthèse, rend la page et l'écrit de façon atomique sous
`chemins.rapports()`. Lève les erreurs de lecture, de rendu ou d'écriture : l'appelant décide.
"""

import dataclasses
import re
from datetime import datetime
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import texte as noyau_texte
from pilotage.rapport import lecture, page, semaine

CONSERVES = 12
_NOM_RAPPORT = re.compile(r"semaine-[0-9]{4}-W[0-9]{2}\.html")


def semaine_courante(maintenant: datetime) -> str:
    """Semaine ISO `AAAA-Www` de `maintenant` (aware) en heure locale."""
    annee, numero, _ = maintenant.astimezone(lecture.FuseauLocal()).isocalendar()
    return f"{annee}-W{numero:02d}"


def _alertes_nettoyees(synthese: semaine.Synthese) -> semaine.Synthese:
    """Une alerte ancienne peut porter un chemin : racine GitHub masquée, secret retiré."""
    racine = str(chemins.racine_github())
    alertes = tuple(noyau_texte.nettoyer(a, page.BORNE_TEXTE, racine) for a in synthese.alertes)
    return dataclasses.replace(synthese, alertes=alertes)


def generer(semaine_iso: str, maintenant: datetime) -> Path:
    """Écrit `rapports/semaine-<semaine_iso>.html` et renvoie son chemin."""
    cible = chemins.rapport_semaine(semaine_iso)
    entree = lecture.lire_entree(semaine_iso, maintenant)
    synthese = _alertes_nettoyees(semaine.synthese_semaine(entree, semaine_iso, maintenant))
    css = (chemins.racine_web() / "charte.css").read_text(encoding="utf-8")
    contenu = page.rendre_page(
        synthese, css=css, genere=maintenant.astimezone(lecture.FuseauLocal())
    )
    chemins.ecrire_atomique(cible, contenu)
    return cible


def appliquer_retention() -> None:
    """Ne garde que les `CONSERVES` rapports les plus récents (par nom de semaine). Seuls les
    fichiers `semaine-AAAA-Www.html` comptent et peuvent être supprimés."""
    noms = sorted(
        p.name for p in chemins.rapports().iterdir()
        if _NOM_RAPPORT.fullmatch(p.name) and p.is_file()
    )
    for nom in noms[:-CONSERVES]:
        (chemins.rapports() / nom).unlink()
