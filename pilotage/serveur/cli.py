"""Sous-commande `lancer.py appli` : arrête l'instance précédente, sert l'appli en local."""

import argparse
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path

from pilotage import chemins
from pilotage.serveur import enfants, processus, relance
from pilotage.serveur.appli import ServeurPilotage


def main(
    argv: list[str],
    *,
    navigateur: Callable[[str], object] = webbrowser.open,
    pret: Callable[[ServeurPilotage], None] | None = None,
    racine_web: Path | None = None,
) -> int:
    """Point d'entrée appelé par `lancer.py` ; rend le code de sortie.

    `navigateur`, `pret` et `racine_web` ne servent qu'aux tests (navigateur factice, arrêt).
    """
    analyseur = argparse.ArgumentParser(prog="lancer.py appli", description=__doc__)
    analyseur.add_argument(
        "--port", type=int, help="port d'écoute (défaut : clé `port` de config.json)"
    )
    analyseur.add_argument(
        "--sans-sync", action="store_true", help="ne pas lancer de synchro au démarrage"
    )
    options = analyseur.parse_args(argv)
    try:
        port = options.port if options.port is not None else chemins.port_serveur()
    except chemins.ErreurConfiguration as exc:
        print(f"lancer.py appli : {exc}", file=sys.stderr)
        return 2
    if not 1 <= port <= 65535:
        print("lancer.py appli : port hors de 1 à 65535", file=sys.stderr)
        return 2
    try:
        # `appli_pid()` lit `config.json` (clé `attente`) même quand `--port` est donné.
        fichier_pid = chemins.appli_pid()
        processus.arreter_precedente(fichier_pid)
    except chemins.ErreurConfiguration as exc:
        print(f"lancer.py appli : {exc}", file=sys.stderr)
        return 2
    try:
        serveur = ServeurPilotage(port, racine_web or chemins.racine_web())
    except OSError as exc:
        print(
            f"lancer.py appli : port {port} indisponible ({exc.strerror or exc})", file=sys.stderr
        )
        return 1
    with serveur:
        try:
            processus.noter_instance(fichier_pid)
        except OSError as exc:
            print(
                f"lancer.py appli : impossible de noter l'instance ({exc.strerror or exc})",
                file=sys.stderr,
            )
            return 2
        try:
            # Le jeton ne part qu'au navigateur, dans le fragment ; jamais affiché ni journalisé.
            print(f"Appli : http://127.0.0.1:{serveur.port}/ (Ctrl+C pour arrêter)")
            if not options.sans_sync:
                try:  # comme le bouton Sync : « déjà en cours » n'est pas une erreur
                    enfants.lancer("sync")
                except Exception as exc:  # noqa: BLE001 - l'appli démarre quand même
                    cause = getattr(exc, "strerror", None) or type(exc).__name__
                    print(f"lancer.py appli : synchro non lancée ({cause})", file=sys.stderr)
            navigateur(serveur.url())
            if pret is not None:
                pret(serveur)
            serveur.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            relance.arreter()  # la relance en file (M2) ne survit pas au serveur
            processus.effacer_instance(fichier_pid)
    return 0
