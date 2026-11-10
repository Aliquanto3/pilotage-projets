"""Validateur de `table-dossiers.json` : dossier relatif à `{{RACINE_GITHUB}}` -> projet."""

from pilotage.noyau import ids
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
CHAMPS = frozenset({"schema", "dossiers"})


def _dossier(cle: object) -> str:
    if not isinstance(cle, str) or not cle:
        raise ErreurValidation("dossiers : clé de type chaîne non vide attendue")
    segments = cle.split("/")
    if "\\" in cle or ":" in cle or "\x00" in cle or any(
        not segment or segment in (".", "..") or ".." in segment for segment in segments
    ):
        raise ErreurValidation(f"dossiers : dossier relatif invalide ({len(cle)} caractères)")
    if ids.cle_dossier(cle) != cle:
        raise ErreurValidation(f"dossiers : clé non normalisée ({len(cle)} caractères)")
    return cle


def valider(objet: object) -> None:
    """Refuse champ inconnu, `schema` autre que 1, dossier non relatif et projet invalide."""
    if not isinstance(objet, dict):
        raise ErreurValidation("table_dossiers : un objet est attendu")
    inconnus = sorted(str(cle) for cle in objet.keys() - CHAMPS)
    if inconnus:
        raise ErreurValidation(f"table_dossiers : champ inconnu : {', '.join(inconnus)}")
    manquants = sorted(CHAMPS - objet.keys())
    if manquants:
        raise ErreurValidation(f"table_dossiers : champ manquant : {', '.join(manquants)}")
    schema = objet["schema"]
    if isinstance(schema, bool) or schema != SCHEMA:
        raise ErreurValidation(f"table_dossiers : schema {SCHEMA} attendu")
    dossiers = objet["dossiers"]
    if not isinstance(dossiers, dict):
        raise ErreurValidation("table_dossiers : dossiers doit être un objet")
    for cle, projet in dossiers.items():
        _dossier(cle)
        try:
            ids.valider_projet(projet)
        except ids.ErreurId as exc:
            raise ErreurValidation(f"table_dossiers : {exc}") from None
