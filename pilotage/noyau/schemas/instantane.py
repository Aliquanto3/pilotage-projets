"""Validateur de l'instantané d'un PC : faits comptés ou énumérés, jamais de texte libre (AD-10)."""

import re
from datetime import datetime

from pilotage.noyau import faits, ids
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
CHAMPS = frozenset({"schema", "genere_a", "projets"})
CHAMPS_PROJET = frozenset({"faits_depot", "sessions_vivantes"})
CHAMPS_FAITS = frozenset(
    {"tag", "commits", "prs_ouvertes", "ci", "topics", "stories_ouvertes", "sprint_status", "run"}
)
_GENERE_A = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def _entier(valeur: object, nom: str) -> None:
    if type(valeur) is not int or valeur < 0:
        raise ErreurValidation(f"instantane : {nom} doit être un entier positif ou nul")


def _enum(valeur: object, nom: str, permis: tuple[str, ...]) -> None:
    if not isinstance(valeur, str) or valeur not in permis:
        raise ErreurValidation(f"instantane : {nom} hors de l'énumération")


def _champs(objet: dict, permis: frozenset[str], nom: str) -> None:
    inconnus = sorted(str(c) for c in objet.keys() - permis)
    if inconnus:
        raise ErreurValidation(f"instantane : {nom} : champ inconnu : {', '.join(inconnus)}")
    manquants = sorted(permis - objet.keys())
    if manquants:
        raise ErreurValidation(f"instantane : {nom} : champ manquant : {', '.join(manquants)}")


def _faits(objet: object) -> None:
    if not isinstance(objet, dict):
        raise ErreurValidation("instantane : faits_depot : un objet ou null est attendu")
    _champs(objet, CHAMPS_FAITS, "faits_depot")
    if objet["tag"] is not None and faits.tag_ou_none(objet["tag"]) is None:
        raise ErreurValidation("instantane : tag ni vX.Y.Z ni null")
    commits = objet["commits"]
    if not isinstance(commits, dict):
        raise ErreurValidation("instantane : commits doit être un objet")
    for type_, nombre in commits.items():
        _enum(type_, "type de commit", faits.TYPES_COMMIT)
        _entier(nombre, "commits")
    _entier(objet["prs_ouvertes"], "prs_ouvertes")
    _entier(objet["stories_ouvertes"], "stories_ouvertes")
    _enum(objet["ci"], "ci", faits.CI)
    _enum(objet["run"], "run", faits.RUN)
    _enum(objet["sprint_status"], "sprint_status", faits.SPRINT_STATUS)
    topics = objet["topics"]
    if not isinstance(topics, list):
        raise ErreurValidation("instantane : topics doit être une liste")
    for topic in topics:
        _enum(topic, "topic", faits.TOPICS)
    if topics != sorted(set(topics)):
        raise ErreurValidation("instantane : topics triés et sans doublon attendus")


def _projet(objet: object) -> None:
    if not isinstance(objet, dict):
        raise ErreurValidation("instantane : projet : un objet est attendu")
    _champs(objet, CHAMPS_PROJET, "projet")
    if objet["faits_depot"] is not None:
        _faits(objet["faits_depot"])
    sessions = objet["sessions_vivantes"]
    if not isinstance(sessions, list):
        raise ErreurValidation("instantane : sessions_vivantes doit être une liste")
    for session in sessions:
        ids.valider_session(session)


def valider(objet: object) -> None:
    """Refuse champ inconnu, `schema` autre que 1, valeur hors énumération et texte libre."""
    if not isinstance(objet, dict):
        raise ErreurValidation("instantane : un objet est attendu")
    _champs(objet, CHAMPS, "racine")
    schema = objet["schema"]
    if isinstance(schema, bool) or schema != SCHEMA:
        raise ErreurValidation(f"instantane : schema {SCHEMA} attendu")
    genere_a = objet["genere_a"]
    if not isinstance(genere_a, str) or not _GENERE_A.fullmatch(genere_a):
        raise ErreurValidation("instantane : genere_a au format AAAA-MM-JJTHH:MM:SSZ attendu")
    try:
        datetime.strptime(genere_a, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ErreurValidation("instantane : genere_a : date impossible") from None
    projets = objet["projets"]
    if not isinstance(projets, dict):
        raise ErreurValidation("instantane : projets doit être un objet")
    try:
        for nom, projet in projets.items():
            ids.valider_projet(nom)
            _projet(projet)
    except ids.ErreurId as exc:
        raise ErreurValidation(f"instantane : {exc}") from None
