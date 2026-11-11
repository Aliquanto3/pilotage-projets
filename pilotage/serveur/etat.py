"""Gestionnaire de `GET /api/etat` (story 4.2, AD-5 §9, AD-11, AD-14).

Rend tel quel l'assemblage du noyau (`sync.lecture.lire_etat`, version sans effet du scan) plus
l'état `cycle` et `utilisateur` (nom affiché de `config.json`, `""` si absent : le web
montre alors « Vous attend »). Lecture sans effet : aucun mutex, aucun processus, aucune écriture.

Story 5.6 : chaque carte de projet porte `message_en_attente` (un message du projet n'est lu
par aucun PC) et l'état gagne `chantiers_connus` (chantiers de `projets.yaml`, vides compris,
proposés par les réglages du tiroir).
"""

from pilotage import chemins
from pilotage.noyau import ids
from pilotage.serveur import enfants, mutations, suivi
from pilotage.serveur.routes import Reponse
from pilotage.sync import lecture

# État du cycle (en_cours, type, origine, dernier résultat) : voir `serveur.enfants`.
CYCLE_NEUTRE = enfants.CYCLE_NEUTRE


def lire_cycle() -> dict:
    """État `cycle`, lu sans effet (la sonde du mutex ne le prend jamais)."""
    return enfants.lire_cycle()


def projets_avec_message_en_attente() -> set[str]:
    """Projets dont un message (en file ou déposé) n'est encore lu par aucun PC."""
    rendus = suivi.messages(suivi.operations_en_attente())
    return {m["projet"] for m in rendus if m["etat"] != suivi.LU}


def chantiers_connus() -> list[str]:
    """Chantiers de `projets.yaml`, vides compris, triés casefold ; `[]` sans fichier lisible."""
    return sorted(mutations.chantiers_de_projets_yaml(), key=lambda n: (n.casefold(), n))


def _marquer(donnees: dict, en_attente: set[str]) -> None:
    """Pose `message_en_attente` sur les cartes de projet de `cartes`, `colonnes` et `chantiers`."""
    listes = [donnees.get("cartes") or []]
    listes += list((donnees.get("colonnes") or {}).values())
    listes += [c.get("projets") or [] for c in donnees.get("chantiers") or []]
    for liste in listes:
        for carte in liste:
            if isinstance(carte, dict) and carte.get("genre") == "projet":
                carte["message_en_attente"] = carte.get("nom") in en_attente


def etat(parametres: dict[str, str], corps: bytes) -> Reponse:
    del parametres, corps
    try:
        pc = lecture.nom_pc(None)
    except ids.ErreurId:  # nom de machine sans caractère [a-z0-9-] : alerte de lecture, pas 500
        pc = None
    donnees = lecture.lire_etat(chemins.racine_github(), pc)
    _marquer(donnees, projets_avec_message_en_attente())
    return Reponse(200, donnees={
        **donnees, "cycle": lire_cycle(), "utilisateur": chemins.utilisateur(),
        "chantiers_connus": chantiers_connus(),
    })
