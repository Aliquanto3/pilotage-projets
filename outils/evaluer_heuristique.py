"""Rappel et précision de l'heuristique de secours sur un jeu étiqueté (story 2.4).

Usage : `uv run python outils/evaluer_heuristique.py JEU.jsonl`.
Le jeu reste hors dépôt (story 6.1). Une ligne JSON par cas :
    {"payload": {"hook_event_name": "Stop", "last_assistant_message": "..."}, "attente": true}
`payload` est celui d'un `Stop` ou d'une `Notification` (`notification_type`, `message`) ;
`attente` dit si l'utilisateur était réellement attendu. Lignes vides ignorées ; une ligne invalide
arrête l'évaluation (code 1). Seule l'heuristique est jugée : le marqueur n'entre pas en compte.
Lignes non étiquetées (`attente` absent ou `null`, cas du `a-etiqueter.jsonl` de `extraire_jeu.py`)
ignorées et comptées. Sortie : vrais/faux positifs et négatifs, rappel = VP/(VP+FN), précision =
VP/(VP+FP) (`n/a` si le dénominateur est nul). Code retour : 0 seuils atteints (rappel >= 90 %,
précision >= 80 %), 2 sinon, 1 jeu illisible.
"""

import argparse
import json
import sys
from pathlib import Path

SEUIL_RAPPEL = 0.90
SEUIL_PRECISION = 0.80

DEPOT = Path(__file__).resolve().parent.parent
if str(DEPOT) not in sys.path:
    sys.path.insert(0, str(DEPOT))

from pilotage.noyau import heuristique  # noqa: E402


def lire_jeu(chemin: Path) -> list[tuple[dict, bool]]:
    """Cas étiquetés `(payload, attente)` ; `ValueError` (avec le numéro de ligne) si invalide."""
    return lire_jeu_complet(chemin)[0]


def lire_jeu_complet(chemin: Path) -> tuple[list[tuple[dict, bool]], int]:
    """Cas étiquetés et nombre de lignes non étiquetées (`attente` absent ou `null`)."""
    cas = []
    non_etiquetes = 0
    with open(chemin, encoding="utf-8") as fichier:
        for numero, ligne in enumerate(fichier, 1):
            if not ligne.strip():
                continue
            try:
                objet = json.loads(ligne)
            except ValueError:
                raise ValueError(f"ligne {numero} : JSON invalide") from None
            if (
                not isinstance(objet, dict)
                or not isinstance(objet.get("payload"), dict)
                or not (objet.get("attente") is None or isinstance(objet["attente"], bool))
            ):
                raise ValueError(f"ligne {numero} : `payload` (objet) et `attente` (bool) requis")
            if objet.get("attente") is None:
                non_etiquetes += 1
                continue
            cas.append((objet["payload"], objet["attente"]))
    return cas, non_etiquetes


def evaluer(cas: list[tuple[dict, bool]]) -> dict:
    """Comptes `vp`, `fp`, `fn`, `vn` puis `rappel` et `precision` (`None` si indéfinis)."""
    vp = fp = fn = vn = 0
    for payload, attendu in cas:
        trouve = heuristique.detecter(payload) is not None
        if trouve and attendu:
            vp += 1
        elif trouve:
            fp += 1
        elif attendu:
            fn += 1
        else:
            vn += 1
    return {
        "vp": vp, "fp": fp, "fn": fn, "vn": vn,
        "rappel": vp / (vp + fn) if vp + fn else None,
        "precision": vp / (vp + fp) if vp + fp else None,
    }


def _pourcent(valeur: float | None) -> str:
    return "n/a" if valeur is None else f"{valeur * 100:.1f} %"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("jeu", type=Path, help="fichier JSONL étiqueté")
    args = parser.parse_args(argv)
    try:
        cas, non_etiquetes = lire_jeu_complet(args.jeu)
    except (OSError, ValueError) as erreur:
        print(f"jeu illisible : {erreur}")
        return 1
    bilan = evaluer(cas)
    detail = f"VP {bilan['vp']}, FP {bilan['fp']}, FN {bilan['fn']}, VN {bilan['vn']}"
    print(f"{len(cas)} cas : {detail}")
    if non_etiquetes:
        print(f"{non_etiquetes} ligne(s) non étiquetée(s) ignorée(s)")
    print(f"rappel {_pourcent(bilan['rappel'])}, précision {_pourcent(bilan['precision'])}")
    atteints = (
        bilan["rappel"] is not None
        and bilan["precision"] is not None
        and bilan["rappel"] >= SEUIL_RAPPEL
        and bilan["precision"] >= SEUIL_PRECISION
    )
    seuils = "rappel >= 90 %, précision >= 80 %"
    print("seuils atteints" if atteints else f"seuils NON atteints ({seuils})")
    return 0 if atteints else 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
