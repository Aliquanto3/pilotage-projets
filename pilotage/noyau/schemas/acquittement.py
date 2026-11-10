"""Validateur d'un acquittement `attente/boite/<projet>/<id>.lu.<pc>` (AD-13, story 5.3).

Champs : `schema` (1), `id` (message acquitté), `projet`, `pc`, `session` (session qui l'a reçu),
`heure` (`AAAA-MM-JJTHH:MM:SSZ`). Tout autre champ est refusé.
"""

import re
from datetime import datetime

from pilotage.noyau import ids
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
CHAMPS = frozenset({"schema", "id", "projet", "pc", "session", "heure"})
_HEURE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def valider(objet: object) -> None:
    """Lève `ErreurValidation` pour un champ inconnu ou manquant, un type ou une forme invalide."""
    if not isinstance(objet, dict):
        raise ErreurValidation("acquittement : un objet est attendu")
    inconnus = sorted(str(c) for c in objet.keys() - CHAMPS)
    if inconnus:
        raise ErreurValidation(f"acquittement : champ inconnu : {', '.join(inconnus)}")
    manquants = sorted(CHAMPS - objet.keys())
    if manquants:
        raise ErreurValidation(f"acquittement : champ manquant : {', '.join(manquants)}")
    if type(objet["schema"]) is not int or objet["schema"] != SCHEMA:
        raise ErreurValidation(f"acquittement : schema {SCHEMA} attendu")
    try:
        ids.valider_id(objet["id"])
        ids.valider_projet(objet["projet"])
        ids.valider_pc(objet["pc"])
        ids.valider_session(objet["session"])
    except ids.ErreurId as exc:
        raise ErreurValidation(f"acquittement : {exc}") from None
    heure = objet["heure"]
    if not isinstance(heure, str) or not _HEURE.fullmatch(heure):
        raise ErreurValidation("acquittement : heure AAAA-MM-JJTHH:MM:SSZ attendue")
    try:
        datetime.strptime(heure, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ErreurValidation("acquittement : heure impossible") from None
