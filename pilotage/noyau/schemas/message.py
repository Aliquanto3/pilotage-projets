"""Validateur d'un message `donnees/boite/<projet>/<id>.json` (AD-9, AD-10, story 5.1).

Champs : `schema` (1), `id` (celui de l'opération qui l'a déposé), `projet`, `texte`
(2 048 octets UTF-8 au plus), `pc` facultatif (PC visé). Tout autre champ est refusé.
"""

from pilotage.noyau import ids, texte
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
OBLIGATOIRES = frozenset({"schema", "id", "projet", "texte"})
CHAMPS = OBLIGATOIRES | {"pc"}


def valider_champs(objet: dict, nom: str) -> None:
    """`id`, `projet`, `texte` et `pc` facultatif (partagé avec le schéma `operation`)."""
    try:
        ids.valider_id(objet["id"])
        ids.valider_projet(objet["projet"])
        texte.valider_message(objet["texte"])
        if "pc" in objet:
            ids.valider_pc(objet["pc"])
    except ValueError as exc:  # ErreurId, ErreurTexte
        raise ErreurValidation(f"{nom} : {exc}") from None


def valider(objet: object) -> None:
    """Lève `ErreurValidation` pour un champ inconnu ou manquant, un type ou une forme invalide."""
    if not isinstance(objet, dict):
        raise ErreurValidation("message : un objet est attendu")
    inconnus = sorted(str(c) for c in objet.keys() - CHAMPS)
    if inconnus:
        raise ErreurValidation(f"message : champ inconnu : {', '.join(inconnus)}")
    manquants = sorted(OBLIGATOIRES - objet.keys())
    if manquants:
        raise ErreurValidation(f"message : champ manquant : {', '.join(manquants)}")
    if type(objet["schema"]) is not int or objet["schema"] != SCHEMA:
        raise ErreurValidation(f"message : schema {SCHEMA} attendu")
    valider_champs(objet, "message")
