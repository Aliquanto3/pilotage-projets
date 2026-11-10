"""Validateur d'une opération `attente/operations/<id>.json` (AD-5 §7, AD-9, AD-10, story 5.1).

Commun : `schema` (1), `id`, `verbe`, `projet`. Verbes fermés :
- `deposer_message` : `texte` (2 048 octets UTF-8 au plus), `pc` facultatif ;
- `modifier_projets` : `patch`, objet non vide de champs `chantier` (nom ou `null`), `exclu`
  (booléen), `pause` (date `AAAA-MM-JJ` ou `null`), chacun `{attendu, voulu}`, différents.
Tout champ inconnu, ou propre à l'autre verbe, est refusé. Un `schema` plus récent est repéré par
le lecteur avant la validation (alerte de version), comme pour `donnees/`.
"""

import re
from datetime import date

from pilotage.noyau import ids
from pilotage.noyau.schemas import message
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
VERBES = ("deposer_message", "modifier_projets")
COMMUNS = frozenset({"schema", "id", "verbe", "projet"})
OBLIGATOIRES = {
    "deposer_message": COMMUNS | {"texte"},
    "modifier_projets": COMMUNS | {"patch"},
}
CHAMPS = {
    "deposer_message": OBLIGATOIRES["deposer_message"] | {"pc"},
    "modifier_projets": OBLIGATOIRES["modifier_projets"],
}
CHAMPS_PATCH = ("chantier", "exclu", "pause")
BORNE_CHANTIER = 100  # points de code, comme `schemas.projets`
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _chantier(valeur: object) -> None:
    if valeur is None:
        return
    if (
        not isinstance(valeur, str)
        or not valeur.strip()
        or valeur != valeur.strip()
        or len(valeur) > BORNE_CHANTIER
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in valeur)
    ):
        raise ErreurValidation(
            "operation : chantier = nom sans espace de bord ni caractère de contrôle "
            f"({BORNE_CHANTIER} caractères au plus) ou null"
        )


def _exclu(valeur: object) -> None:
    if type(valeur) is not bool:
        raise ErreurValidation("operation : exclu = booléen")


def _pause(valeur: object) -> None:
    if valeur is None:
        return
    if isinstance(valeur, str) and _DATE.fullmatch(valeur):
        try:
            date.fromisoformat(valeur)
            return
        except ValueError:
            pass
    raise ErreurValidation("operation : pause = date AAAA-MM-JJ ou null")


_VALEUR = {"chantier": _chantier, "exclu": _exclu, "pause": _pause}


def _patch(patch: object) -> None:
    if not isinstance(patch, dict) or not patch:
        raise ErreurValidation("operation : patch = objet non vide")
    inconnus = sorted(str(c) for c in patch.keys() - set(CHAMPS_PATCH))
    if inconnus:
        raise ErreurValidation(f"operation : champ de patch inconnu : {', '.join(inconnus)}")
    for champ, valeurs in patch.items():
        if not isinstance(valeurs, dict) or valeurs.keys() != {"attendu", "voulu"}:
            raise ErreurValidation(f"operation : patch.{champ} = {{attendu, voulu}}")
        _VALEUR[champ](valeurs["attendu"])
        _VALEUR[champ](valeurs["voulu"])
        if valeurs["attendu"] == valeurs["voulu"]:
            raise ErreurValidation(f"operation : patch.{champ} sans changement")


def valider(objet: object) -> None:
    """Lève `ErreurValidation` pour un verbe hors liste, un champ inconnu ou manquant, un
    identifiant hors d'AD-9, un message de plus de 2 048 octets ou un patch invalide."""
    if not isinstance(objet, dict):
        raise ErreurValidation("operation : un objet est attendu")
    verbe = objet.get("verbe")
    if not isinstance(verbe, str) or verbe not in VERBES:
        raise ErreurValidation("operation : verbe deposer_message ou modifier_projets attendu")
    inconnus = sorted(str(c) for c in objet.keys() - CHAMPS[verbe])
    if inconnus:
        raise ErreurValidation(f"operation : champ inconnu : {', '.join(inconnus)}")
    manquants = sorted(OBLIGATOIRES[verbe] - objet.keys())
    if manquants:
        raise ErreurValidation(f"operation : champ manquant : {', '.join(manquants)}")
    if type(objet["schema"]) is not int or objet["schema"] != SCHEMA:
        raise ErreurValidation(f"operation : schema {SCHEMA} attendu")
    if verbe == "deposer_message":
        message.valider_champs(objet, "operation")
        return
    try:
        ids.valider_id(objet["id"])
        ids.valider_projet(objet["projet"])
    except ids.ErreurId as exc:
        raise ErreurValidation(f"operation : {exc}") from None
    _patch(objet["patch"])
