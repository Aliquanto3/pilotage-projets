"""Sous-commande `lancer.py scan` : scan seul sous mutex (story 1.6, AD-5 §5).

Mutex, inventaire, faits `gh`, instantané, `table-dossiers.json`, assemblage du noyau, puis
`TABLEAU.md`. Aucune commande git dans `donnees/`, ni `isPrivate`, pull, commit ou push.
Codes de sortie : 0 fait, 3 mutex occupé (rien écrit), 1 échec (alerte de source `scan`).
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import schemas
from pilotage.scan import faits_gh, inventaire, lecture, sessions, tableau
from pilotage.scan.verrou import Verrou

SOURCE = "scan"
ALERTE_ECHEC = "scan-echec"
MESSAGE_ECHEC = "Scan en échec"
ALERTE_ILLISIBLE = "alertes-illisibles"
MESSAGE_ILLISIBLE = "alertes.json illisible : remplacé, alertes des autres sources perdues"
CODE_FAIT, CODE_ECHEC, CODE_OCCUPE = 0, 1, 3


def _executeur(args: list[str], delai: float):
    return faits_gh.executeur_gh(args, delai)  # résolu à l'appel : substituable en test


_nom_pc = lecture.nom_pc  # nom public : `scan.lecture.nom_pc`


def _lire_alertes() -> tuple[list[dict], bool]:
    """(alertes en place, fichier présent mais illisible ou invalide)."""
    chemin = chemins.alertes_json()
    if not chemin.exists():
        return [], False
    try:
        objet = json.loads(chemin.read_text(encoding="utf-8"))
        schemas.valider("alertes", objet)
    except (OSError, ValueError):  # illisible ou invalide (ErreurValidation est ValueError)
        return [], True
    return objet["alertes"], False


def _bornes(params: dict) -> dict:
    """Valeurs texte tronquées à `BORNE_MESSAGE` points de code : un paramètre trop long (clé
    YAML de 400 caractères citée dans un `detail`) ne doit pas faire refuser `alertes.json`."""
    borne = schemas.alertes.BORNE_MESSAGE
    return {n: v[:borne] if isinstance(v, str) else v for n, v in params.items()}


def _ecrire_alertes_scan(nouvelles: list[dict]) -> None:
    """Remplace les alertes de source `scan` ; celles des autres sources sont conservées.

    Un `alertes.json` illisible est remplacé, avec une alerte qui le dit.
    """
    anciennes, illisible = _lire_alertes()
    gardees = [a for a in anciennes if a["source"] != SOURCE]
    # M8 : seuls `code` et `params` sont écrits ; le texte est rédigé à la lecture (noyau.alertes)
    propres = {
        (a["code"], json.dumps(_bornes(a.get("params") or {}), sort_keys=True,
                               ensure_ascii=False))
        for a in nouvelles
    }
    if illisible:
        propres.add((ALERTE_ILLISIBLE, "{}"))
    ajout = [
        {"source": SOURCE, "code": c, "params": json.loads(p)} for c, p in sorted(propres)
    ]
    objet = {"schema": 1, "alertes": gardees + ajout}
    schemas.valider("alertes", objet)
    chemins.ecrire_atomique(
        chemins.alertes_json(), json.dumps(objet, ensure_ascii=False, indent=2) + "\n"
    )


def _json(objet: object) -> str:
    return json.dumps(objet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _scanner(racine: Path, pc: str) -> list[dict]:
    """Écrit instantané, table et `TABLEAU.md` ; rend les alertes du scan."""
    inv = inventaire.inventorier(racine)
    instantane = faits_gh.construire_instantane(inv, _executeur)
    claude, alertes_claude = sessions.vivantes_claude()
    etats, alertes_sessions = sessions.lire_etats(pc, claude=claude)
    vivantes = set(claude.values())
    for nom, projet in instantane["projets"].items():
        projet["sessions_vivantes"] = sorted(
            {s["session"] for s in etats.get(nom, [])} & vivantes
        )
    schemas.valider("instantane", instantane)
    chemins.ecrire_atomique(chemins.instantanes() / f"{pc}.json", _json(instantane))
    inventaire.ecrire_table(inv)  # peut ajouter l'alerte de doublon de casse à `inv.alertes`
    config, _, _ = inventaire.lire_projets(chemins.donnees() / "projets.yaml")
    maintenant = datetime.now(UTC)
    fuseau = maintenant.astimezone().tzinfo
    tout = lecture.assembler_tout(
        inv, config or {}, instantane, etats, pc, maintenant, fuseau
    )
    chemins.ecrire_atomique(
        chemins.tableau(),
        tableau.rendre(
            tout["assemblee"], tout["depots"], tout["dependances"], maintenant,
            fraicheur=tout["fraicheur"], alertes_lecture=tout["alertes_lecture"],
            utilisateur=chemins.utilisateur(),
        ),
    )
    uniques = {
        (a["code"], a["message"]): a for a in alertes_sessions + alertes_claude
    }
    return inv.alertes + list(uniques.values())


def main(argv: list[str]) -> int:
    """Point d'entrée appelé par `lancer.py` ; rend le code de sortie."""
    parser = argparse.ArgumentParser(prog="lancer.py scan", description="Scan seul de ce PC.")
    parser.add_argument("--racine-github", type=Path, help="défaut : chemins.racine_github()")
    parser.add_argument("--pc", help="nom du PC (défaut : nom de la machine)")
    ns = parser.parse_args(argv)
    verrou = Verrou()
    try:
        verrou.__enter__()  # une seule entrée : la sortie est dans le `finally`
    except OSError:  # mutex non créé ou attente en échec : rien n'est écrit sans le mutex
        print("lancer.py scan : échec du mutex", file=sys.stderr)
        return CODE_ECHEC
    try:
        if not verrou.acquis:
            print("lancer.py scan : déjà en cours", file=sys.stderr)
            return CODE_OCCUPE
        try:
            alertes = _scanner(ns.racine_github or chemins.racine_github(), _nom_pc(ns.pc))
            _ecrire_alertes_scan(alertes)
        except Exception as exc:  # noqa: BLE001 (tout échec devient une alerte)
            # Configuration absente (story 7.1) : son message dit quoi faire, sans donnée privée.
            detail = exc if isinstance(exc, chemins.ConfigurationGithubAbsente) else type(
                exc
            ).__name__
            print(f"lancer.py scan : échec ({detail})", file=sys.stderr)
            try:
                _ecrire_alertes_scan([{"code": ALERTE_ECHEC, "message": MESSAGE_ECHEC}])
            except Exception:  # noqa: BLE001
                print("lancer.py scan : alerte non écrite", file=sys.stderr)
            return CODE_ECHEC
    finally:
        verrou.liberer()
    return CODE_FAIT
