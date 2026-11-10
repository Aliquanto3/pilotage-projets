"""Faits de dépôt lus par `gh` et instantané sans texte libre (story 1.4, AD-10, AD-12).

`gh` est lancé en sous-processus, tableau d'arguments, sans shell, avec un délai par appel. Aucun
titre de PR, message de commit ni nom de branche libre n'est gardé : le type d'un commit se déduit
du préfixe de son message, puis le message est jeté. Aucun client de modèle n'est importé.
"""

import base64
import binascii
import json
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime

import yaml

from pilotage import chemins
from pilotage.noyau import faits, ids, schemas
from pilotage.scan.inventaire import Inventaire

DELAI_S = 30.0
ALERTE_NON_RELUS = "faits-github-non-relus"
MESSAGE_NON_RELUS = "Faits GitHub non relus"
CHEMIN_SPRINT = "_bmad-output/implementation-artifacts/sprint-status.yaml"
CHEMIN_RUN = "_bmad-output/implementation-artifacts/run-autonome.md"
_BRANCHE = re.compile(r"[A-Za-z0-9._/][A-Za-z0-9._/-]{0,99}")
# Première ligne du message de chaque commit : le reste est écarté par `jq` avant d'arriver ici.
# `compare` : une chaîne JSON par ligne, pour concaténer les pages de `--paginate` (sans
# pagination, l'API plafonne à 250 commits).
_JQ_MESSAGES = ".commits[].commit.message | split(\"\\n\")[0] | @json"
_JQ_MESSAGES_LISTE = "[.[].commit.message | split(\"\\n\")[0]]"

Executeur = Callable[[list[str], float], subprocess.CompletedProcess]


class ErreurGh(Exception):
    """Lecture `gh` impossible (réseau, quota, dépôt inaccessible, sortie inattendue)."""


class _Absent(ErreurGh):
    """Réponse 404 : le fichier demandé n'existe pas sur la branche par défaut."""


def executeur_gh(args: list[str], delai: float) -> subprocess.CompletedProcess:
    """Lance `gh <args>` sans shell ; `ErreurGh` si `gh` manque ou dépasse le délai."""
    try:
        return subprocess.run(  # noqa: S603 (tableau d'arguments, pas de shell)
            ["gh", *args],  # noqa: S607
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=delai,
            check=False,
            stdin=subprocess.DEVNULL,
            **chemins.options_sans_fenetre(),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ErreurGh("gh indisponible ou trop lent") from None


def _sortie(executeur: Executeur, args: list[str]) -> str:
    resultat = executeur(args, DELAI_S)
    if resultat.returncode != 0:
        if "HTTP 404" in (resultat.stderr or ""):
            raise _Absent("introuvable")
        raise ErreurGh("gh a échoué")
    return resultat.stdout or ""


def _json(executeur: Executeur, args: list[str]) -> object:
    try:
        return json.loads(_sortie(executeur, args))
    except ValueError:
        raise ErreurGh("sortie gh illisible") from None


def _fichier(executeur: Executeur, depot: str, branche: str, chemin: str) -> str | None:
    """Contenu d'un fichier de la branche par défaut (`gh api`, base64), None si 404."""
    try:
        reponse = _json(
            executeur,
            ["api", f"repos/{depot}/contents/{chemin}?ref={branche}", "--jq",
             "[.encoding, .content]"],
        )
    except _Absent:
        return None
    # Au-delà de 1 Mo, l'API rend `encoding: "none"` et un contenu vide : échec, pas « vide ».
    if not (isinstance(reponse, list) and len(reponse) == 2 and reponse[0] == "base64"
            and isinstance(reponse[1], str)):
        raise ErreurGh("contenu gh inattendu")
    try:
        return base64.b64decode(reponse[1], validate=False).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        raise ErreurGh("contenu gh illisible") from None


def _messages_compare(executeur: Executeur, args: list[str]) -> list:
    lignes = _sortie(executeur, args).splitlines()
    try:
        return [json.loads(ligne) for ligne in lignes if ligne.strip()]
    except ValueError:
        raise ErreurGh("sortie gh illisible") from None


def _stories(texte: str | None) -> tuple[int, str]:
    if texte is None:
        return 0, "absent"
    try:
        objet = yaml.safe_load(texte)
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        raise ErreurGh("sprint-status.yaml illisible") from None
    statuts = objet.get("development_status") if isinstance(objet, dict) else None
    return faits.stories_ouvertes(statuts), "present"


def lire_faits_depot(
    projet: str, executeur: Executeur = executeur_gh, proprietaire: str | None = None
) -> dict:
    """Faits de dépôt d'un projet (`<propriétaire>/<projet>`) ; `ErreurGh` si une lecture échoue.

    `proprietaire` absent : `chemins.proprietaire_github()` (`ConfigurationGithubAbsente` s'il
    n'est pas configuré).
    """
    proprietaire = proprietaire or chemins.proprietaire_github()
    depot = f"{proprietaire}/{ids.valider_projet(projet)}"
    infos = _json(executeur, ["repo", "view", depot, "--json", "defaultBranchRef,repositoryTopics"])
    if not isinstance(infos, dict):
        raise ErreurGh("réponse gh inattendue")
    branche = (infos.get("defaultBranchRef") or {}).get("name")
    if not isinstance(branche, str) or not _BRANCHE.fullmatch(branche) or ".." in branche:
        raise ErreurGh("branche par défaut inattendue")
    topics = faits.topics_connus(
        [t.get("name") for t in infos.get("repositoryTopics") or [] if isinstance(t, dict)]
    )
    releases = _json(
        executeur, ["release", "list", "--repo", depot, "--limit", "1", "--json", "tagName"]
    )
    if not isinstance(releases, list):
        raise ErreurGh("réponse gh inattendue")
    brut = releases[0].get("tagName") if releases and isinstance(releases[0], dict) else None
    tag = faits.tag_ou_none(brut)
    if tag is not None:
        messages = _messages_compare(
            executeur,
            ["api", f"repos/{depot}/compare/{tag}...{branche}?per_page=100", "--paginate",
             "--jq", _JQ_MESSAGES],
        )
    else:
        messages = _json(
            executeur,
            ["api", f"repos/{depot}/commits?sha={branche}&per_page=100", "--jq",
             _JQ_MESSAGES_LISTE],
        )
    if not isinstance(messages, list):
        raise ErreurGh("réponse gh inattendue")
    commits = faits.compter_types(messages)
    del messages
    prs = _json(
        executeur,
        ["pr", "list", "--repo", depot, "--state", "open", "--limit", "1000", "--json", "number"],
    )
    runs = _json(
        executeur,
        ["run", "list", "--repo", depot, "--branch", branche, "--limit", "1",
         "--json", "status,conclusion"],
    )
    if not isinstance(prs, list) or not isinstance(runs, list):
        raise ErreurGh("réponse gh inattendue")
    dernier = runs[0] if runs and isinstance(runs[0], dict) else {}
    ci = faits.ci_depuis(dernier.get("status") if runs else None, dernier.get("conclusion"))
    stories, sprint = _stories(_fichier(executeur, depot, branche, CHEMIN_SPRINT))
    run = faits.etat_run(_fichier(executeur, depot, branche, CHEMIN_RUN))
    return {
        "tag": tag,
        "commits": commits,
        "prs_ouvertes": len(prs),
        "ci": ci,
        "topics": topics,
        "stories_ouvertes": stories,
        "sprint_status": sprint,
        "run": run,
    }


def alerte_non_relus(projet: str) -> dict:
    """Alerte d'un projet dont les faits GitHub n'ont pas été relus (texte du catalogue)."""
    return {"code": ALERTE_NON_RELUS, "message": f"{MESSAGE_NON_RELUS} : {projet}.",
            "params": {"projet": projet}}


def construire_instantane(
    inventaire: Inventaire,
    executeur: Executeur = executeur_gh,
    maintenant: datetime | None = None,
) -> dict:
    """Instantané validé de ce PC ; une alerte par projet dont les faits n'ont pas été relus.

    Propriétaire GitHub non configuré : `chemins.ConfigurationGithubAbsente`, le scan échoue.
    """
    maintenant = maintenant or datetime.now(UTC)
    proprietaire = chemins.proprietaire_github()
    projets: dict[str, dict] = {}
    for entree in inventaire.projets:
        projet = entree["projet"]
        try:
            depot = lire_faits_depot(projet, executeur, proprietaire)
        except Exception:  # noqa: BLE001 (un projet illisible ne doit pas arrêter le scan)
            depot = None
            inventaire.alertes.append(alerte_non_relus(projet))
        projets[projet] = {"faits_depot": depot, "sessions_vivantes": []}
    instantane = {
        "schema": 1,
        "genere_a": maintenant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "projets": projets,
    }
    schemas.valider("instantane", instantane)
    return instantane


__all__ = ["ErreurGh", "construire_instantane", "executeur_gh", "lire_faits_depot"]
