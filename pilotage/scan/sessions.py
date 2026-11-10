"""Sessions de ce PC pour le scan (story 2.6, AD-12) : états des hooks et `~/.claude/sessions/`.

Lecture seule. Le pid vivant et l'heure de création viennent de `processus` (injectable) et sont
rendus au noyau sous forme d'un booléen `vivante` par session. Un fichier illisible est ignoré avec
une alerte (texte fixe, sans chemin) : il ne fait jamais tomber le scan.
"""

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import ids, schemas
from pilotage.scan import processus

ALERTE_ETATS = "sessions-illisibles"
MESSAGE_ETATS = "Fichier d'état de session illisible ignoré"
ALERTE_CLAUDE = "sessions-claude-illisibles"
MESSAGE_CLAUDE = "Fichier de ~/.claude/sessions illisible ignoré"
Vivante = Callable[[int, object], bool]


def _alerte(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _json(chemin: Path) -> object:
    return json.loads(chemin.read_text(encoding="utf-8"))


def lire_etats(
    pc: str, vivante: Vivante | None = None, claude: Mapping[int, str] | None = None
) -> tuple[dict[str, list[dict]], list[dict]]:
    """États `attente/etat/<projet>/<pc>/*.json` de ce PC : ({projet: [session]}, alertes).

    Chaque session porte les champs de l'état plus `vivante` (False d'office si `fin`). `claude` :
    `{pid: session}` des fichiers vivants de `~/.claude/sessions/` (`vivantes_claude`). Un pid qui y
    figure fait foi (AD-11 : vivante si la session du fichier est la sienne, ce qui écarte l'ancien
    état d'un même processus après `/clear`) ; sinon (session `-p`, sans fichier), le pid doit vivre
    avec l'heure de création notée (`pid_cree` null : non vivante).
    """
    claude = claude or {}
    vivante = vivante or processus.vivante  # résolu à l'appel : substituable en test
    racine = chemins.attente() / "etat"
    par_projet: dict[str, list[dict]] = {}
    alertes: list[dict] = []
    try:
        projets = sorted(e.name for e in os.scandir(racine) if e.is_dir())
    except OSError:
        return par_projet, alertes
    for projet in projets:
        dossier = racine / projet / pc
        try:
            noms = sorted(e.name for e in os.scandir(dossier) if e.name.endswith(".json"))
        except OSError:
            continue
        for nom in noms:
            try:
                objet = _json(dossier / nom)
                schemas.valider("session", objet)
                if objet["projet"] != projet or f"{objet['session']}.json" != nom:
                    raise ValueError("état hors de sa place")
            except (OSError, ValueError):
                alertes.append(_alerte(ALERTE_ETATS, MESSAGE_ETATS))
                continue
            pid = objet["pid"]
            objet["vivante"] = not objet.get("fin") and (
                claude[pid] == objet["session"] if pid in claude
                else bool(vivante(pid, objet["pid_cree"]))
            )
            par_projet.setdefault(projet, []).append(objet)
    return par_projet, alertes


def vivantes_claude(vivante: Vivante | None = None) -> tuple[dict[int, str], list[dict]]:
    """`{pid: session}` des `sessions/<pid>.json` dont le pid vit avec le même `procStart`."""
    vivante = vivante or processus.vivante
    ids_vivants: dict[int, str] = {}
    alertes: list[dict] = []
    try:
        dossier = chemins.sessions_claude()
        noms = sorted(e.name for e in os.scandir(dossier) if e.name.endswith(".json"))
    except OSError:
        return ids_vivants, alertes
    for nom in noms:
        try:
            objet = _json(dossier / nom)
            pid, session = objet["pid"], ids.valider_session(objet["sessionId"])
            if isinstance(pid, bool) or not isinstance(pid, int):
                raise ValueError("pid")
            debut = objet["procStart"]
        except (OSError, ValueError, KeyError, TypeError, ids.ErreurId):
            alertes.append(_alerte(ALERTE_CLAUDE, MESSAGE_CLAUDE))
            continue
        if vivante(pid, str(debut)):
            ids_vivants[pid] = session
    return ids_vivants, alertes
