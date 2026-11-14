"""Lecture des données du rapport (story 9.1) : seule couche du rapport qui touche aux fichiers.

Fin de semaine : l'état courant (comme le scan) tant que la semaine n'est pas finie, sinon le
dernier commit de `donnees/` avant le lundi suivant. Début de semaine : le dernier commit de
`donnees/` strictement avant le lundi 00:00 (heure locale), `instantanes/` et `etat/` lus par
`git show` (lecture seule, jamais dans un hook). Sans dépôt, sans commit avant le lundi ou si git
échoue : `debut` vaut None, donc aucune comparaison. Les catégories, chantiers et pauses du
début de semaine sont ceux d'aujourd'hui (l'historique n'a pas `projets.yaml` par projet).
"""

import json
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import assemblage, schemas
from pilotage.rapport.semaine import bornes_semaine
from pilotage.scan import donnees, inventaire, sessions
from pilotage.scan import lecture as lecture_scan

DELAI_GIT_S = 30.0


def _git(args: list[str], cwd: Path) -> str | None:
    """Sortie de `git <args>` dans `cwd`, ou None (git absent, délai, code de sortie non nul)."""
    try:
        sortie = subprocess.run(  # noqa: S603 (tableau d'arguments, pas de shell)
            ["git", *args],  # noqa: S607
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=DELAI_GIT_S, check=False, stdin=subprocess.DEVNULL,
            **chemins.options_sans_fenetre(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return sortie.stdout if sortie.returncode == 0 else None


def _json_valide(texte: str | None, nom_schema: str) -> dict | None:
    try:
        objet = json.loads(texte or "")
        schemas.valider(nom_schema, objet)
    except ValueError:
        return None
    return objet


def commit_avant(depot: Path, limite: datetime) -> str | None:
    """Dernier commit de `depot` strictement avant `limite` (aware), ou None."""
    if not depot.is_dir():
        return None
    jusque = (limite - timedelta(seconds=1)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sortie = _git(["log", "-1", "--format=%H", f"--until={jusque}"], depot)
    sha = (sortie or "").strip()
    return sha or None


def etat_au_commit(depot: Path, sha: str) -> tuple[dict, dict] | None:
    """(instantanés `{pc: objet}`, états `{pc: {projet: [états]}}`) valides à ce commit."""
    noms = _git(["ls-tree", "-r", "--name-only", sha, "--", "instantanes", "etat"], depot)
    if noms is None:
        return None
    instantanes: dict[str, dict] = {}
    etats: dict[str, dict[str, list]] = {}
    for chemin in sorted(n for n in noms.splitlines() if n.endswith(".json")):
        parties = chemin.split("/")
        if parties[0] == "instantanes" and len(parties) == 2:
            objet = _json_valide(_git(["show", f"{sha}:{chemin}"], depot), "instantane")
            if objet is not None:
                instantanes[parties[1].removesuffix(".json")] = objet
        elif parties[0] == "etat" and len(parties) == 4:
            objet = _json_valide(_git(["show", f"{sha}:{chemin}"], depot), "session")
            if objet is not None and (objet["projet"], objet["pc"], f"{objet['session']}.json") \
                    == (parties[1], parties[2], parties[3]):
                etats.setdefault(objet["pc"], {}).setdefault(objet["projet"], []).append(objet)
    return instantanes, etats


def etat_historique(
    depot: Path, limite: datetime, base: Mapping[str, Mapping], exclus: frozenset
) -> dict | None:
    """Faits par projet au dernier commit avant `limite`, ou None (aucun point de comparaison).

    `base` donne la catégorie, le chantier et la pause de chaque projet (ceux d'aujourd'hui).
    """
    sha = commit_avant(depot, limite)
    lu = etat_au_commit(depot, sha) if sha else None
    if lu is None or not lu[0]:
        return None
    defauts = {
        nom: {cle: f.get(cle) for cle in ("categorie", "chantier", "pause") if cle in f}
        for nom, f in base.items()
    }
    return assemblage.assembler_faits(
        {}, lu[0], lu[1], "", limite.astimezone(UTC), defauts, exclus
    )


def _instantane_local(pc: str) -> dict | None:
    try:
        objet = json.loads((chemins.instantanes() / f"{pc}.json").read_text(encoding="utf-8"))
        schemas.valider("instantane", objet)
    except (OSError, ValueError):
        return None
    return objet


def faits_courants(maintenant: datetime) -> tuple[dict, frozenset]:
    """(faits par projet tous PC, projets exclus) : mêmes sources que `lire_etat`, sans effet."""
    pc = lecture_scan.nom_pc(None)
    inv = inventaire.inventorier(chemins.racine_github())
    config, _, _ = inventaire.lire_projets(chemins.donnees() / "projets.yaml")
    config = config or {}
    claude, _ = sessions.vivantes_claude()
    etats, _ = sessions.lire_etats(pc, claude=claude)
    locaux = {
        p["projet"]: {
            "categorie": p["categorie"], "chantier": p["chantier"], "pause": p["pause"],
            "attente": None, "sessions": etats.get(p["projet"], []),
        }
        for p in inv.projets
    }
    autres, etats_distants, _ = donnees.lire_autres_pcs(pc)
    instantanes = {**autres, pc: _instantane_local(pc) or {"schema": 1, "genere_a": None,
                                                             "projets": {}}}
    chantier_de, pauses = inventaire.rattachements(config)
    defauts = {
        nom: {
            "categorie": inventaire.CATEGORIE_CLASSE if nom in chantier_de
            else inventaire.CATEGORIE_A_CLASSER,
            "chantier": chantier_de.get(nom), "pause": pauses.get(nom),
        }
        for i in autres.values() for nom in i["projets"]
    }
    exclus = frozenset(config.get("exclus") or [])
    faits = assemblage.assembler_faits(
        locaux, instantanes, etats_distants, pc, maintenant, defauts, exclus
    )
    return faits, exclus


def _archives() -> list[dict]:
    """États de session archivés de ce PC (`attente/archive/etat/`), valides seulement."""
    trouves = []
    for chemin in sorted((chemins.attente() / "archive" / "etat").glob("*/*/*.json")):
        try:
            objet = json.loads(chemin.read_text(encoding="utf-8"))
            schemas.valider("session", objet)
        except (OSError, ValueError):
            continue
        trouves.append(objet)
    return trouves


def _sessions_des(faits: Mapping[str, Mapping]) -> list[dict]:
    return [s for f in faits.values() for s in f.get("sessions") or []]


def lire_entree(semaine: str, maintenant: datetime | None = None) -> dict:
    """Entrée de `synthese_semaine` pour la semaine ISO `AAAA-Www` (voir `rapport.semaine`)."""
    maintenant = maintenant or datetime.now(UTC)
    debut_naif = bornes_semaine(semaine, UTC)[0].replace(tzinfo=None)
    fuseau: tzinfo = debut_naif.astimezone().tzinfo  # type: ignore[assignment]
    debut, fin = bornes_semaine(semaine, fuseau)
    faits, exclus = faits_courants(maintenant)
    depot = chemins.donnees()
    base = faits
    if fin <= maintenant:  # semaine finie : l'état de fin est celui du dernier commit avant elle
        faits = etat_historique(depot, fin, base, exclus) or faits
    avant = etat_historique(depot, debut, base, exclus)
    ecrites, _ = lecture_scan.lire_alertes_ecrites()
    toutes = _sessions_des(faits) + _sessions_des(avant or {}) + _sessions_des(base) + _archives()
    return {
        "faits": faits, "debut": avant, "sessions": toutes, "exclus": sorted(exclus),
        "alertes": [{k: a[k] for k in ("code", "params", "message") if k in a} for a in ecrites],
        "fuseau": fuseau,
    }

