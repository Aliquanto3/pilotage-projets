"""Inventaire des dépôts `<propriétaire>/*` sous la racine GitHub et table des dossiers (story 1.3).

Lecture directe de `.git` (aucun sous-processus, aucun réseau) : `config` pour les remotes,
`HEAD` pour la branche. Un worktree a un fichier `.git` (`gitdir: <chemin>`) ; son `HEAD` est dans
ce `gitdir`, sa `config` dans le dossier indiqué par `commondir`. Le propriétaire est
`chemins.proprietaire_github()` (story 7.1) : absent ou invalide, l'inventaire lève
`chemins.ConfigurationGithubAbsente` et le scan échoue (alerte `scan-echec` côté synchro).
"""

import configparser
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from pilotage import chemins
from pilotage.noyau import faits, ids, schemas
from pilotage.noyau.schemas import ErreurValidation
from pilotage.noyau.schemas import projets as schema_projets

CATEGORIE_A_CLASSER = "découvert, à classer"
CATEGORIE_CLASSE = "classé"
ALERTE_VERSION_RECENTE = "projets-version-recente"
ALERTE_INVALIDE = "projets-invalide"
ALERTE_ILLISIBLE = "projets-illisible"
ALERTE_DEPOT_IGNORE = "depot-ignore"
ALERTE_DOSSIER_CASSE = "dossier-doublon-casse"
CHEMIN_RUN = ("_bmad-output", "implementation-artifacts", "run-autonome.md")
PROFONDEUR_MAX = 2
_URL = re.compile(
    r"(?:https?://(?:[^/@]+@)?github\.com/|ssh://(?:[^/@]+@)?github\.com(?::[0-9]+)?/"
    r"|[^/@\s]+@github\.com:)"
    r"(?P<proprio>[^/\s]+)/(?P<nom>[^/\s]+?)(?:\.git)?/?",
    re.IGNORECASE,
)


class _CleDupliquee(yaml.YAMLError):
    """Deux fois la même clé dans un objet YAML (`safe_load` garderait la dernière en silence)."""


class _ChargeurStrict(yaml.SafeLoader):
    """`SafeLoader` qui refuse les clés dupliquées."""


def _objet_sans_doublon(chargeur: _ChargeurStrict, noeud: yaml.MappingNode) -> dict:
    chargeur.flatten_mapping(noeud)
    vues = set()
    for noeud_cle, _ in noeud.value:
        cle = chargeur.construct_object(noeud_cle)
        try:
            doublon = cle in vues
            vues.add(cle)
        except TypeError:  # clé non hachable : `construct_mapping` la refusera
            continue
        if doublon:
            raise _CleDupliquee(f"clé dupliquée (ligne {noeud_cle.start_mark.line + 1})")
    return chargeur.construct_mapping(noeud)


_ChargeurStrict.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _objet_sans_doublon
)


@dataclass
class Inventaire:
    """Résultat du scan : projets triés, alertes, et indicateur de lecture seule (M7)."""

    projets: list[dict] = field(default_factory=list)
    alertes: list[dict] = field(default_factory=list)
    lecture_seule: bool = False


def _alerte(code: str, message: str, **params: str) -> dict:
    """`message` reste pour les appelants du scan ; seuls `code` et `params` sont écrits (M8)."""
    alerte = {"code": code, "message": message}
    return {**alerte, "params": params} if params else alerte


def _invalide(detail: str) -> dict:
    return _alerte(ALERTE_INVALIDE, f"projets.yaml ignoré : {detail}", detail=detail)


def _lire(chemin: Path) -> str | None:
    try:
        return chemin.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _dossier_git(dossier: Path) -> tuple[Path, Path, str] | None:
    """(dossier de HEAD, dossier de config, type) ou None si `dossier` n'est pas un dépôt."""
    git = dossier / ".git"
    if git.is_dir():
        return git, git, "dossier"
    texte = _lire(git) if git.is_file() else None
    trouve = re.match(r"gitdir:\s*(.+?)\s*$", texte or "")
    if not trouve:
        return None
    gitdir = Path(trouve.group(1))
    if not gitdir.is_absolute():
        gitdir = dossier / gitdir
    commun = _lire(gitdir / "commondir")
    config = gitdir / commun.strip() if commun and commun.strip() else gitdir
    return gitdir, config, "worktree"


def _nom_depot(config: Path, proprietaire: str) -> str | None:
    """Nom (minuscules) du dépôt `<proprietaire>/<nom>` si un remote y pointe, `origin` d'abord.

    Propriétaire comparé sans tenir compte de la casse.
    """
    texte = _lire(config / "config")
    if texte is None:
        return None
    analyseur = configparser.RawConfigParser(strict=False, interpolation=None)
    try:
        analyseur.read_string(texte)
    except configparser.Error:
        return None
    sections = sorted(
        (s for s in analyseur.sections() if s.startswith('remote "')),
        key=lambda s: s != 'remote "origin"',
    )
    for section in sections:
        trouve = _URL.fullmatch(analyseur.get(section, "url", fallback="").strip())
        if trouve and trouve["proprio"].casefold() == proprietaire.casefold():
            return trouve["nom"].lower()
    return None


def _branche(gitdir: Path) -> str | None:
    texte = _lire(gitdir / "HEAD") or ""
    trouve = re.match(r"ref:\s*refs/heads/(.+?)\s*$", texte)
    return trouve.group(1) if trouve else None


def etat_run(dossier: Path) -> dict | None:
    """Fait de poste sur `run-autonome.md` : None si absent, sinon `{present, termine}`.

    `termine` est faux s'il y a des lignes de journal datées et aucune ligne `ménage` (clôture du
    run). Une ligne `ETAT:` est un brief de reprise : elle ne dit rien de la fin.
    """
    texte = _lire(dossier.joinpath(*CHEMIN_RUN))
    if texte is None:
        return None
    return {"present": True, "termine": faits.etat_run(texte) not in ("en_cours", "bloque")}


def _depots(racine: Path) -> Iterator[Path]:
    """Dossiers contenant `.git`, jusqu'à `PROFONDEUR_MAX` niveaux, sans entrer dans un dépôt."""
    a_voir = [(racine, 0)]
    while a_voir:
        parent, niveau = a_voir.pop()
        try:
            enfants = sorted(parent.iterdir())
        except OSError:
            continue
        for enfant in enfants:
            if (
                enfant.name.startswith(".")
                or enfant.is_symlink()
                or enfant.is_junction()  # jonction Windows : `is_symlink()` ne la voit pas
                or not enfant.is_dir()
            ):
                continue
            if (enfant / ".git").exists():
                yield enfant
            elif niveau + 1 < PROFONDEUR_MAX:
                a_voir.append((enfant, niveau + 1))


def lire_projets(chemin: Path) -> tuple[dict | None, bool, list[dict]]:
    """Lit `projets.yaml` : (contenu validé ou None, lecture seule, alertes).

    Absent : `(None, False, [])`. Illisible ou invalide : ignoré avec alerte. `schema` plus récent
    que celui connu : les champs connus sont validés comme en schéma 1, les autres ignorés ; le
    fichier est en lecture seule pour ce PC, avec l'alerte « PC en version plus récente ».
    """
    if not chemin.exists():
        return None, False, []
    texte = _lire(chemin)
    if texte is None:
        return None, False, [_alerte(ALERTE_ILLISIBLE, "projets.yaml illisible")]
    return analyser_projets(texte)


def analyser_projets(texte: str) -> tuple[dict | None, bool, list[dict]]:
    """Comme `lire_projets`, sur le texte déjà lu (sync le revalide après un patch, story 5.1)."""
    try:
        objet = yaml.load(texte, Loader=_ChargeurStrict)  # noqa: S506 (dérivé de SafeLoader)
    except _CleDupliquee as exc:
        return None, False, [_invalide(str(exc))]
    except yaml.YAMLError:
        return None, False, [_invalide("YAML invalide")]
    recent = (
        isinstance(objet, dict)
        and type(objet.get("schema")) is int
        and objet["schema"] > schema_projets.SCHEMA
    )
    a_valider = objet
    if recent:
        a_valider = {c: objet[c] for c in schema_projets.CHAMPS if c in objet}
        a_valider["schema"] = schema_projets.SCHEMA
    try:
        schemas.valider("projets", a_valider)
    except ErreurValidation as exc:
        return None, False, [_invalide(str(exc))]
    if recent:
        message = "PC en version plus récente : projets.yaml en lecture seule"
        return a_valider, True, [_alerte(ALERTE_VERSION_RECENTE, message)]
    return a_valider, False, []


def rattachements(config: dict) -> tuple[dict[str, str], dict[str, dict]]:
    """(chantier de chaque projet, pause de chaque projet) d'après `projets.yaml`."""
    chantier_de = {
        projet: nom
        for nom, chantier in (config.get("chantiers") or {}).items()
        for projet in (chantier or {}).get("projets") or []
    }
    pauses = {p: {"revue": str(v["revue"])} for p, v in (config.get("pauses") or {}).items()}
    return chantier_de, pauses


def inventorier(racine: Path, fichier_projets: Path | None = None) -> Inventaire:
    """Recense les dépôts `<propriétaire>/*` sous `racine`, rattachés à `projets.yaml`.

    `chemins.ConfigurationGithubAbsente` si le propriétaire GitHub n'est pas configuré.
    """
    proprietaire = chemins.proprietaire_github()
    racine = Path(racine)
    if fichier_projets is None:
        fichier_projets = chemins.donnees() / "projets.yaml"
    config, lecture_seule, alertes = lire_projets(fichier_projets)
    config = config or {}
    # Validé : une clé sans valeur (`exclus:`) vaut None, lue comme vide.
    exclus = set(config.get("exclus") or [])
    chantier_de, pauses = rattachements(config)
    par_projet: dict[str, dict] = {}
    for dossier in _depots(racine):
        trouve = _dossier_git(dossier)
        nom = _nom_depot(trouve[1], proprietaire) if trouve else None
        if trouve is None or nom is None:
            continue
        try:
            projet = ids.valider_projet(nom)
        except ids.ErreurId:
            alertes.append(_alerte(ALERTE_DEPOT_IGNORE, "dépôt ignoré : nom de projet invalide"))
            continue
        if projet in exclus:
            continue
        entree = par_projet.setdefault(
            projet,
            {
                "projet": projet,
                "categorie": CATEGORIE_CLASSE if projet in chantier_de else CATEGORIE_A_CLASSER,
                "chantier": chantier_de.get(projet),
                "pause": pauses.get(projet),
                "postes": [],
            },
        )
        entree["postes"].append(
            {
                "dossier": dossier.relative_to(racine).as_posix(),
                "type": trouve[2],
                "branche": _branche(trouve[0]),
                "run": etat_run(dossier),
            }
        )
    return Inventaire(
        projets=[_trie(par_projet[p]) for p in sorted(par_projet)],
        alertes=alertes,
        lecture_seule=lecture_seule,
    )


def table_dossiers(inventaire: Inventaire) -> dict:
    """Objet `table-dossiers.json` : `ids.cle_dossier(dossier)` -> projet (contrat C5).

    Les exclus sont déjà absents. Deux dossiers qui ne diffèrent que par la casse donnent la même
    clé : le premier (ordre des projets puis des postes) est gardé, avec une alerte dans
    `inventaire.alertes`, jamais un écrasement silencieux.
    """
    dossiers: dict[str, str] = {}
    for projet in inventaire.projets:
        for poste in projet["postes"]:
            cle = ids.cle_dossier(poste["dossier"])
            if cle in dossiers:
                message = "deux dossiers ne diffèrent que par la casse : le second est ignoré"
                inventaire.alertes.append(_alerte(ALERTE_DOSSIER_CASSE, message))
                continue
            dossiers[cle] = projet["projet"]
    return {"schema": 1, "dossiers": dossiers}


def ecrire_table(inventaire: Inventaire, chemin: Path | None = None) -> Path:
    """Valide puis écrit la table par `ecrire_atomique` (défaut : `chemins.table_dossiers()`)."""
    objet = table_dossiers(inventaire)
    schemas.valider("table_dossiers", objet)
    chemin = chemin or chemins.table_dossiers()
    texte = json.dumps(objet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    chemins.ecrire_atomique(chemin, texte)
    return chemin


def _trie(entree: dict) -> dict:
    entree["postes"].sort(key=lambda poste: poste["dossier"])
    return entree
