"""Faits de dépôt : énumérations fermées et réductions pures (story 1.4, M6, AD-10).

Toute valeur hors énumération est ramenée à `autre`/`null`/ignorée, jamais recopiée : aucun texte
libre ne sort de ce module.
"""

import re

CI = ("verte", "rouge", "aucune", "en_cours")
RUN = ("aucun", "en_cours", "bloque", "termine")
TYPES_COMMIT = (
    "feat", "fix", "docs", "chore", "refactor", "test", "perf", "ci", "build", "style", "revert",
    "autre",
)
TOPICS = (
    "status-spec", "status-dev", "status-test", "status-bench", "status-refonte",
    "status-deployed", "ai-portfolio",
)
SPRINT_STATUS = ("present", "absent")
TAG = re.compile(r"v?[0-9]+\.[0-9]+\.[0-9]+")

_PREFIXE = re.compile(r"([A-Za-z]+)(?:\([^)\n]*\))?!?:")
_CLE_STORY = re.compile(r"[0-9]+-[0-9]+-")
_LIGNE_JOURNAL = re.compile(r"^\s*-\s\d{4}-\d{2}-\d{2}\b.*·.*$", re.MULTILINE)
_LIGNE_MENAGE = re.compile(r"^\s*-\s.*·\s*ménage\s*·", re.MULTILINE)
_STATUTS_CLOS = frozenset({"done"})
_CONCLUSIONS_ROUGES = frozenset({"failure", "timed_out", "startup_failure", "action_required"})


def tag_ou_none(valeur: object) -> str | None:
    """Tag de release `vX.Y.Z` (ou `X.Y.Z`), sinon None."""
    if isinstance(valeur, str) and TAG.fullmatch(valeur):
        return valeur
    return None


def type_commit(message: object) -> str:
    """Type d'un commit déduit du préfixe conventionnel de son message ; sinon `autre`."""
    trouve = _PREFIXE.match(message) if isinstance(message, str) else None
    type_ = trouve.group(1).lower() if trouve else ""
    return type_ if type_ in TYPES_COMMIT and type_ != "autre" else "autre"


def compter_types(messages: object) -> dict[str, int]:
    """Comptes par type (types à zéro omis, ordre de `TYPES_COMMIT`) ; les messages sont jetés."""
    comptes = dict.fromkeys(TYPES_COMMIT, 0)
    for message in messages if isinstance(messages, list) else []:
        comptes[type_commit(message)] += 1
    return {type_: n for type_, n in comptes.items() if n}


def ci_depuis(statut: object, conclusion: object) -> str:
    """Conclusion de la CI de `main` à partir du dernier run (`status`, `conclusion` de `gh`)."""
    if statut is None:
        return "aucune"
    if statut != "completed":
        return "en_cours"
    if conclusion == "success":
        return "verte"
    if conclusion in _CONCLUSIONS_ROUGES:
        return "rouge"
    return "aucune"


def topics_connus(noms: object) -> list[str]:
    """Topics de l'énumération, triés, sans doublon ; les autres sont écartés."""
    if not isinstance(noms, list):
        return []
    return sorted({n for n in noms if isinstance(n, str) and n in TOPICS})


def stories_ouvertes(statuts: object) -> int:
    """Nombre de stories (`N-M-…`) de `development_status` dont le statut n'est pas `done`."""
    if not isinstance(statuts, dict):
        return 0
    return sum(
        1
        for cle, statut in statuts.items()
        if isinstance(cle, str)
        and _CLE_STORY.match(cle)
        and not (isinstance(statut, str) and statut in _STATUTS_CLOS)
    )


def etat_run(texte: str | None) -> str:
    """État du run d'après `run-autonome.md` : absent ou sans journal `aucun`.

    Une ligne `ménage` : `termine` ; sinon dernière ligne de journal d'étape `blocked` : `bloque` ;
    sinon `en_cours`. Seule source du critère : `scan.inventaire.etat_run` (story 1.3) s'y réfère.
    """
    if texte is None:
        return "aucun"
    lignes = _LIGNE_JOURNAL.findall(texte)
    if not lignes:
        return "aucun"
    if _LIGNE_MENAGE.search(texte):
        return "termine"
    champs = [c.strip() for c in lignes[-1].split("·")]
    return "bloque" if len(champs) > 2 and champs[2] == "blocked" else "en_cours"
