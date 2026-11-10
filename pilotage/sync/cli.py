"""Sous-commande `lancer.py sync` : cycle de synchro sous mutex (story 3.1, AD-5).

Codes de sortie : 0 cycle fait ; 3 mutex occupé, rien écrit ; 1 refus ou échec (alerte de
source `sync` dans `attente/alertes.json`, sauf mutex en panne : rien n'est écrit sans mutex).

Demande des hooks (M2, story 3.6) : le détenteur du mutex supprime `attente/sync-demande` avant
son cycle ; s'il la retrouve après un cycle réussi (créée pendant le sien par un hook dont le
`sync` a rendu 3), il la supprime et rejoue un seul cycle. Une demande apparue pendant ce cycle de
plus reste pour le `sync` suivant : jamais de boucle.
"""

import argparse
import sys
from pathlib import Path

from pilotage import chemins
from pilotage.scan import api as scan_api
from pilotage.sync import cycle
from pilotage.sync.verrou import Verrou

CODE_OCCUPE = 3


def _consommer_demande() -> bool:
    """Supprime `attente/sync-demande` ; rend `True` si elle existait et a été supprimée.

    Suppression impossible (fichier verrouillé, droits) : journalisée, `False`, le cycle continue
    (la demande restée en place sera vue par le `sync` suivant)."""
    try:
        chemins.sync_demande().unlink()
    except FileNotFoundError:
        return False
    except OSError as erreur:
        cycle.journaliser(f"sync-demande non supprimée : {type(erreur).__name__}")
        return False
    return True


def main(argv: list[str]) -> int:
    """Point d'entrée appelé par `lancer.py` ; rend le code de sortie."""
    parser = argparse.ArgumentParser(prog="lancer.py sync", description="Synchro de ce PC.")
    parser.add_argument("--racine-github", type=Path, help="défaut : chemins.racine_github()")
    parser.add_argument("--pc", help="nom du PC (défaut : nom de la machine)")
    ns = parser.parse_args(argv)
    verrou = Verrou()
    try:
        verrou.__enter__()  # une seule entrée : la sortie est dans le `finally`
    except OSError:
        print("lancer.py sync : échec du mutex", file=sys.stderr)
        return cycle.CODE_ECHEC
    try:
        if not verrou.acquis:
            print("lancer.py sync : déjà en cours", file=sys.stderr)
            return CODE_OCCUPE
        try:
            pc = scan_api.nom_pc(ns.pc)
            racine_github = ns.racine_github or chemins.racine_github()
        except Exception:  # noqa: BLE001 (nom de PC ou configuration invalide)
            cycle.ecrire_alertes([cycle.alerte_echec("configuration")])
            print("lancer.py sync : configuration invalide", file=sys.stderr)
            return cycle.CODE_ECHEC
        _consommer_demande()  # ce cycle couvre les demandes faites avant lui
        ctx = cycle.Contexte(pc=pc, racine_github=racine_github, mutex_abandonne=verrou.abandonne)
        code = cycle.executer(ctx)
        if code == cycle.CODE_FAIT and _consommer_demande():
            cycle.journaliser("demande pendant le cycle : nouveau cycle")
            code = cycle.executer(cycle.Contexte(pc=pc, racine_github=racine_github))
    finally:
        verrou.liberer()
    if code != cycle.CODE_FAIT:
        print("lancer.py sync : échec, voir les alertes", file=sys.stderr)
    return code
