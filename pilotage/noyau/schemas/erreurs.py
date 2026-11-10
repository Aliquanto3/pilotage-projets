"""Erreurs communes aux validateurs de schémas."""


class ErreurValidation(ValueError):
    """Objet refusé par un validateur (champ inconnu, type ou forme invalide)."""


class SchemaInconnu(LookupError):
    """Nom de schéma absent du registre."""
