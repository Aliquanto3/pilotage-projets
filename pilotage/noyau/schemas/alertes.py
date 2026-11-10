"""Validateur de `attente/alertes.json` : alertes rangées par source (AD-5 §9, M8).

Une alerte stocke `source`, `code` et `params` (valeurs texte ou entières) ; le texte est rédigé
à la lecture par le catalogue `noyau.alertes`, qui fixe aussi les paramètres exacts des codes de
`sync`. Forme transitoire tolérée : `message` à la place de `params` (alertes écrites avant M8),
rendu tel quel.
"""

import re

from pilotage.noyau import alertes as catalogue
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
SOURCES = ("sync", "scan", "operation")
BORNE_MESSAGE = 300  # points de code (message et valeur de paramètre)
CHAMPS = frozenset({"schema", "alertes"})
CHAMPS_ALERTE = frozenset({"source", "code", "params"})
CHAMPS_ALERTE_ANCIENNE = frozenset({"source", "code", "message"})
_CODE = re.compile(r"[a-z0-9-]{1,64}")
_NOM_PARAM = re.compile(r"[a-z_][a-z0-9_]{0,31}")


def _params(params: object) -> None:
    if not isinstance(params, dict):
        raise ErreurValidation("alertes : params doit être un objet")
    for nom, valeur in params.items():
        if not isinstance(nom, str) or not _NOM_PARAM.fullmatch(nom):
            raise ErreurValidation("alertes : nom de paramètre [a-z_][a-z0-9_]{0,31} attendu")
        if type(valeur) is int:
            continue
        if not isinstance(valeur, str) or len(valeur) > BORNE_MESSAGE:
            raise ErreurValidation(
                "alertes : paramètre entier ou texte de 300 caractères au plus"
            )


def valider(objet: object) -> None:
    """Lève `ErreurValidation` pour un champ inconnu, une source inconnue ou un type invalide."""
    if not isinstance(objet, dict) or objet.keys() != CHAMPS:
        raise ErreurValidation("alertes : un objet {schema, alertes} est attendu")
    if type(objet["schema"]) is not int or objet["schema"] != SCHEMA:
        raise ErreurValidation(f"alertes : schema {SCHEMA} attendu")
    if not isinstance(objet["alertes"], list):
        raise ErreurValidation("alertes : une liste est attendue")
    for alerte in objet["alertes"]:
        if not isinstance(alerte, dict) or alerte.keys() not in (
            CHAMPS_ALERTE, CHAMPS_ALERTE_ANCIENNE
        ):
            raise ErreurValidation("alertes : une alerte est {source, code, params}")
        if alerte["source"] not in SOURCES:
            raise ErreurValidation("alertes : source hors de sync, scan, operation")
        if not isinstance(alerte["code"], str) or not _CODE.fullmatch(alerte["code"]):
            raise ErreurValidation("alertes : code [a-z0-9-]{1,64} attendu")
        if "params" in alerte:
            _params(alerte["params"])
            try:
                catalogue.verifier(alerte["code"], alerte["params"])
            except catalogue.AlerteInconnue as erreur:
                raise ErreurValidation(f"alertes : {erreur}") from None
            continue
        message = alerte["message"]
        if not isinstance(message, str) or not message.strip() or len(message) > BORNE_MESSAGE:
            raise ErreurValidation("alertes : message non vide de 300 caractères au plus")
