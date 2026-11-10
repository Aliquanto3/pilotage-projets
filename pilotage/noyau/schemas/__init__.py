"""Validateurs des schémas JSON : un module par validateur, un registre commun.

Contrat (C2) : chaque story ajoute son module (`etat`, `instantane`, `message`,
`acquittement`, `operation`, `table_dossiers`, `alertes`, `projets`), qui expose
`valider(objet: object) -> None` et lève `ErreurValidation` sur un objet refusé,
puis une ligne dans `REGISTRE`, par exemple :

    from pilotage.noyau.schemas import etat
    REGISTRE["etat"] = etat.valider  # ou dans le littéral ci-dessous
"""

from collections.abc import Callable

from pilotage.noyau.schemas import (
    acquittement,
    alertes,
    instantane,
    message,
    operation,
    projets,
    session,
    table_dossiers,
)
from pilotage.noyau.schemas.erreurs import ErreurValidation, SchemaInconnu

Validateur = Callable[[object], None]

REGISTRE: dict[str, Validateur] = {
    "projets": projets.valider,
    "table_dossiers": table_dossiers.valider,
    "instantane": instantane.valider,
    "session": session.valider,
    "alertes": alertes.valider,
    "operation": operation.valider,
    "message": message.valider,
    "acquittement": acquittement.valider,
}


def valider(nom: str, objet: object) -> None:
    """Valide `objet` avec le validateur `nom` ; lève `SchemaInconnu` si `nom` est absent."""
    try:
        validateur = REGISTRE[nom]
    except KeyError:
        connus = ", ".join(sorted(REGISTRE)) or "aucun"
        raise SchemaInconnu(f"schéma inconnu : {nom!r} (connus : {connus})") from None
    validateur(objet)


__all__ = ["REGISTRE", "ErreurValidation", "SchemaInconnu", "Validateur", "valider"]
