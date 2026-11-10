"""Extrait de vraies fins de tour des transcriptions Claude Code pour les étiqueter (story 6.1).

Usage : `uv run python outils/extraire_jeu.py [--depuis DOSSIER] [--max 300] [--graine 1]
[--force]`.
Lecture seule des transcriptions (`~/.claude/projects/*/*.jsonl` par défaut ; les sessions de
sous-agents, dossiers `subagents/` et entrées `isSidechain`, sont ignorées). Une fin de tour est le
dernier message texte de l'assistant avant le prochain message de l'utilisateur ; le contexte
est ce dernier message de l'utilisateur. Tout texte passe par `texte.nettoyer` (filtre de
secrets) ; une fin de tour dont le message assistant est filtré est écartée. Échantillon
déterministe (graine) de `--max` cas.

Écrit UNIQUEMENT sous `<racine locale>/jeu-etiquete/` : `a-etiqueter.jsonl` (champ `attente`
à remplir, `true` ou `false`) et `LISEZMOI.txt`. Refuse d'écrire sous la racine GitHub ou dans un
dépôt git, et d'écraser un `a-etiqueter.jsonl` existant sans `--force` (il peut contenir des
étiquettes) ; avec `--force`, l'ancien est d'abord copié en `a-etiqueter.<horodatage>.jsonl`.
"""

import argparse
import json
import random
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEPOT = Path(__file__).resolve().parent.parent
if str(DEPOT) not in sys.path:
    sys.path.insert(0, str(DEPOT))

from pilotage import chemins  # noqa: E402
from pilotage.noyau import texte  # noqa: E402

MAX_DEFAUT = 300
BORNE_ASSISTANT = 2000  # derniers caractères gardés (l'heuristique en examine autant)
BORNE_CONTEXTE = 600
NOM_DOSSIER = "jeu-etiquete"
NOM_JEU = "a-etiqueter.jsonl"
# Messages `user` écrits par Claude Code, pas par l'utilisateur : ils suivent une fin de tour
# (la clôturent) sans en être le contexte. Un prompt de l'utilisateur qui commence par une autre
# balise reste un prompt.
BALISES_SYSTEME = (
    "<command-name>", "<command-message>", "<command-args>", "<local-command-stdout>",
    "<local-command-stderr>", "<local-command-caveat>", "<task-notification>",
    "<system-reminder>", "<user-prompt-submit-hook>", "<bash-input>", "<bash-stdout>",
    "<bash-stderr>",
)
INTERRUPTION = "[Request interrupted by user"  # tour coupé par l'utilisateur : pas une fin de tour

LISEZMOI = """Jeu à étiqueter (story 6.1) - reste hors dépôt.

Fichier : a-etiqueter.jsonl, une fin de tour par ligne.
- `contexte` : ton dernier message avant la fin de tour (tronqué).
- `payload.last_assistant_message` : fin du dernier message de Claude.
- `attente` : à remplir. true = Claude t'attendait (question, choix, validation) ;
  false = rien à faire de ta part. Laisse null pour ignorer la ligne.
Ne change rien d'autre dans la ligne. Mets bien `true` ou `false` sans guillemets.

Mesure : uv run python outils/evaluer_heuristique.py <ce dossier>/a-etiqueter.jsonl
Cibles : rappel >= 90 %, précision >= 80 %. Code retour 0 si atteintes, 2 sinon.
"""


def _texte_du_message(contenu: object) -> str:
    """Texte brut d'un `message.content` (chaîne ou blocs `text`) ; `""` sinon."""
    if isinstance(contenu, str):
        return contenu
    if not isinstance(contenu, list):
        return ""
    parties = [
        b["text"] for b in contenu
        if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
    ]
    return "\n".join(parties)


def _nature_user(contenu: object) -> tuple[str, str]:
    """`("humain", texte)`, `("systeme", "")`, `("interruption", "")` ou `("outil", "")`."""
    brut = _texte_du_message(contenu).strip()
    if not brut:
        return "outil", ""  # résultat d'outil ou message vide : le tour continue
    if brut.startswith(INTERRUPTION):
        return "interruption", ""
    if brut.startswith(BALISES_SYSTEME):
        return "systeme", ""
    return "humain", brut


def fins_de_tour(chemin: Path) -> list[tuple[str, str]]:
    """Couples `(message assistant, dernier message de l'utilisateur)` d'une transcription."""
    fins: list[tuple[str, str]] = []
    prompt = ""
    assistant = ""
    try:
        with open(chemin, encoding="utf-8") as fichier:
            for ligne in fichier:  # en flux : une transcription peut peser des centaines de Mo
                try:
                    entree = json.loads(ligne)
                except ValueError:
                    continue
                if not isinstance(entree, dict) or entree.get("isSidechain"):
                    continue
                message = entree.get("message")
                if not isinstance(message, dict):
                    continue
                if entree.get("type") == "user":
                    nature, humain = _nature_user(message.get("content"))
                    if nature in ("humain", "systeme") and assistant:
                        fins.append((assistant, prompt))
                    if nature != "outil":
                        assistant = ""
                    if nature == "humain":
                        prompt = humain
                elif entree.get("type") == "assistant":
                    dit = _texte_du_message(message.get("content")).strip()
                    if dit:
                        assistant = dit
    except (OSError, UnicodeDecodeError):
        return []
    if assistant:
        fins.append((assistant, prompt))
    return fins


def transcriptions(depuis: Path) -> list[Path]:
    """`*/*.jsonl` sous `depuis`, hors sous-agents, triées (déterminisme)."""
    return sorted(
        p for p in depuis.glob("*/*.jsonl") if "subagents" not in p.relative_to(depuis).parts
    )


def construire_cas(assistant: str, prompt: str) -> dict | None:
    """Cas à étiqueter, ou `None` si le message assistant contient un secret."""
    racine = str(chemins.racine_github())
    complet = texte.normaliser_racine(assistant, racine)
    if texte.est_suspect(complet):  # avant troncature : un secret coupé au bord passerait
        return None
    message = texte.nettoyer(complet[-BORNE_ASSISTANT:], BORNE_ASSISTANT, racine)
    if not message:
        return None
    contexte = texte.nettoyer(prompt, BORNE_CONTEXTE, racine)
    return {
        "contexte": contexte,
        "payload": {"hook_event_name": "Stop", "last_assistant_message": message},
        "attente": None,
    }


def extraire(depuis: Path, maximum: int, graine: int) -> list[dict]:
    """Échantillon déterministe d'au plus `maximum` cas, dans l'ordre des transcriptions.

    Réservoir (algorithme R) : mémoire bornée par `maximum`, quel que soit le volume lu.
    """
    tirage = random.Random(graine)
    reservoir: list[tuple[int, dict]] = []
    vus = 0
    for chemin in transcriptions(depuis):
        for assistant, prompt in fins_de_tour(chemin):
            construit = construire_cas(assistant, prompt)
            if construit is None:
                continue
            if len(reservoir) < maximum:
                reservoir.append((vus, construit))
            else:
                place = tirage.randrange(vus + 1)
                if place < maximum:
                    reservoir[place] = (vus, construit)
            vus += 1
    return [c for _, c in sorted(reservoir, key=lambda paire: paire[0])]


def verifier_sortie(dossier: Path) -> None:
    """`ValueError` si `dossier` est sous la racine GitHub ou dans un dépôt git."""
    cible = dossier.resolve()
    racine = chemins.racine_github().resolve()
    if cible == racine or racine in cible.parents:
        raise ValueError(f"{cible} : sortie sous la racine GitHub refusée")
    for dossier_parent in (cible, *cible.parents):
        if (dossier_parent / ".git").exists():
            raise ValueError(f"{cible} : sortie dans un dépôt git refusée")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--depuis", type=Path, default=Path.home() / ".claude" / "projects",
                        help="dossier des transcriptions (défaut ~/.claude/projects)")
    parser.add_argument("--max", type=int, default=MAX_DEFAUT, dest="maximum")
    parser.add_argument("--graine", type=int, default=1)
    parser.add_argument("--force", action="store_true", help="écraser un jeu existant")
    args = parser.parse_args(argv)
    if args.maximum < 1:
        print("--max doit être >= 1")
        return 1
    dossier = chemins.racine_locale() / NOM_DOSSIER
    try:
        verifier_sortie(dossier)
    except ValueError as erreur:
        print(f"extraction refusée : {erreur}")
        return 1
    if not args.depuis.is_dir():
        print(f"dossier de transcriptions introuvable : {args.depuis}")
        return 1
    jeu = dossier / NOM_JEU
    if jeu.exists() and not args.force:
        print(f"{jeu} existe déjà (étiquettes possibles) : relancer avec --force pour l'écraser")
        return 1
    cas = extraire(args.depuis, args.maximum, args.graine)
    if jeu.exists():  # --force : copie de l'ancien jeu (étiquettes possibles), même dossier
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        copie = dossier / f"a-etiqueter.{horodatage}.jsonl"
        shutil.copyfile(jeu, copie)  # octets inchangés (BOM, encodage de l'éditeur)
        print(f"ancien jeu copié dans {copie}")
    contenu = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cas)
    chemins.ecrire_atomique(jeu, contenu)
    chemins.ecrire_atomique(dossier / "LISEZMOI.txt", LISEZMOI)
    print(f"{len(cas)} fin(s) de tour écrite(s) dans {jeu}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
