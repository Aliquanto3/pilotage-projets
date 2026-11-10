"""Gestionnaire de `GET /api/etat` (story 4.2, AD-5 §9, AD-11, AD-14).

Rend tel quel l'assemblage du noyau (`sync.lecture.lire_etat`, version sans effet du scan) plus
l'état `cycle` et `utilisateur` (nom affiché de `config.json`, `""` si absent : le web
montre alors « Vous attend »). Lecture sans effet : aucun mutex, aucun processus, aucune écriture.
"""

from pilotage import chemins
from pilotage.noyau import ids
from pilotage.serveur import enfants
from pilotage.serveur.routes import Reponse
from pilotage.sync import lecture

# État du cycle (en_cours, type, origine, dernier résultat) : voir `serveur.enfants`.
CYCLE_NEUTRE = enfants.CYCLE_NEUTRE


def lire_cycle() -> dict:
    """État `cycle`, lu sans effet (la sonde du mutex ne le prend jamais)."""
    return enfants.lire_cycle()


def etat(parametres: dict[str, str], corps: bytes) -> Reponse:
    del parametres, corps
    try:
        pc = lecture.nom_pc(None)
    except ids.ErreurId:  # nom de machine sans caractère [a-z0-9-] : alerte de lecture, pas 500
        pc = None
    donnees = lecture.lire_etat(chemins.racine_github(), pc)
    return Reponse(
        200, donnees={**donnees, "cycle": lire_cycle(), "utilisateur": chemins.utilisateur()}
    )
