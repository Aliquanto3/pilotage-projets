"""Sous-commande `lancer.py installer-reglages` : fusion ciblée de `settings.json` (AD-7).

Codes de sortie : 0 (écrit ou déjà à jour), 1 (refus : rien d'écrit), 2 (usage).
"""

import argparse
import os
import sys
from pathlib import Path

from pilotage import chemins
from pilotage.installation import fusion


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lancer.py installer-reglages",
        description="Installe les hooks du pilotage dans settings.json, sans toucher au reste.",
    )
    parser.add_argument("--settings", help="settings.json cible (défaut : ~/.claude/settings.json)")
    parser.add_argument("--racine", help="racine installée (défaut : racine_installation())")
    parser.add_argument(
        "--python",
        help="interpréteur des hooks (défaut : python de config.json, sinon <racine>/.venv)",
    )
    parser.add_argument("--modele", help="hooks-pilotage.json (défaut : celui du runtime)")
    parser.add_argument("--depuis", help="réglages de base à fusionner (défaut : --settings)")
    parser.add_argument("--config", help="config.json écrit après une fusion réussie (restaurer)")
    parser.add_argument("--racine-github", help="racine GitHub écrite dans --config")
    # Story 7.1 : facultatifs, avec --config ; absents, la valeur de config.json est gardée.
    parser.add_argument("--proprietaire", help="login GitHub des projets, écrit dans --config")
    parser.add_argument(
        "--depot-donnees", help="dépôt privé des données (propriétaire/nom), écrit dans --config"
    )
    parser.add_argument("--utilisateur", help="nom affiché, écrit dans --config")
    parser.add_argument(
        "--exporter-sans-pilotage",
        metavar="FICHIER",
        help="écrit --settings sans les entrées du pilotage dans FICHIER (sauver), sans fusion",
    )
    return parser


def main(argv: list[str]) -> int:
    """Point d'entrée appelé par `lancer.py` ; rend le code de sortie."""
    parser = _parser()
    ns = parser.parse_args(argv)
    if (ns.config is None) != (ns.racine_github is None):
        parser.error("--config et --racine-github vont ensemble")
    identite = (ns.proprietaire, ns.depot_donnees, ns.utilisateur)
    if ns.config is None and any(v is not None for v in identite):
        parser.error("--proprietaire, --depot-donnees et --utilisateur vont avec --config")
    if ns.exporter_sans_pilotage and (ns.config or ns.depuis):
        parser.error("--exporter-sans-pilotage exclut --config et --depuis")
    try:
        racine = Path(ns.racine) if ns.racine else chemins.racine_installation()
        cible = Path(ns.settings) if ns.settings else fusion.settings_par_defaut()
        if ns.exporter_sans_pilotage:
            fusion.exporter_sans_pilotage(cible, Path(ns.exporter_sans_pilotage), str(racine))
            print(f"{ns.exporter_sans_pilotage} : réglages sans le pilotage")
            return 0
        python = ns.python or str(chemins.lire_config().get("python") or "") or str(
            fusion.python_par_defaut(racine)
        )
        modele = Path(ns.modele) if ns.modele else None
        depuis = Path(ns.depuis) if ns.depuis else None
        config = None
        if ns.config:
            if not os.path.isfile(python):
                raise fusion.ErreurInstallation(f"python introuvable : {python!r}")
            # validé avant la fusion, écrit seulement après une fusion réussie
            config = fusion.preparer_config(
                Path(ns.config), python, ns.racine_github, *identite
            )
        ecrit, copie = fusion.installer(cible, python, str(racine), modele, depuis=depuis)
        if config is not None:
            chemins.ecrire_atomique(Path(ns.config), config.decode("utf-8"))
            print(f"{ns.config} : écrit")
    except (fusion.ErreurInstallation, chemins.ErreurConfiguration) as exc:
        print(f"lancer.py installer-reglages : {exc} ; rien n'a été écrit", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"lancer.py installer-reglages : écriture impossible ({exc})", file=sys.stderr)
        return 1
    if not ecrit:
        print(f"{cible} : déjà à jour")
    elif copie is None:
        print(f"{cible} : créé")
    else:
        print(f"{cible} : mis à jour (copie : {copie.name})")
    return 0
