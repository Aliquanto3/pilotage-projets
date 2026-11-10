"""Validateur de `projets.yaml` (objet déjà chargé par `yaml.safe_load` hors du noyau).

Champs : `schema` (1), `chantiers` (nom -> `{projets: [...]}`), `dependances` (`"A ← B"` : A
dépend de B), `exclus` (projets), `pauses` (projet -> `{revue: <date ISO>}`). Tout autre champ
est refusé.
"""

import re
from datetime import date, datetime

from pilotage.noyau import ids
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
CHAMPS = frozenset({"schema", "chantiers", "dependances", "exclus", "pauses"})
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _projet(valeur: object, contexte: str) -> str:
    try:
        return ids.valider_projet(valeur)
    except ids.ErreurId as exc:
        raise ErreurValidation(f"{contexte} : {exc}") from None


def _vide(valeur: object, defaut: object) -> object:
    """Une clé YAML sans valeur (`exclus:`) vaut `None` : elle se lit comme vide."""
    return defaut if valeur is None else valeur


def _liste(valeur: object, nom: str) -> list:
    if not isinstance(valeur, list):
        raise ErreurValidation(f"{nom} : une liste est attendue")
    return valeur


def _objet(valeur: object, nom: str, permis: frozenset[str]) -> dict:
    if not isinstance(valeur, dict):
        raise ErreurValidation(f"{nom} : un objet est attendu")
    inconnus = sorted(str(cle) for cle in valeur.keys() - permis)
    if inconnus:
        raise ErreurValidation(f"{nom} : champ inconnu : {', '.join(inconnus)}")
    return valeur


def _date(valeur: object, nom: str) -> None:
    if isinstance(valeur, datetime):
        raise ErreurValidation(f"{nom} : une date sans heure est attendue")
    if isinstance(valeur, date):
        return
    if isinstance(valeur, str) and _DATE.fullmatch(valeur):
        try:
            date.fromisoformat(valeur)
        except ValueError:
            pass
        else:
            return
    raise ErreurValidation(f"{nom} : date AAAA-MM-JJ attendue")


def valider(objet: object) -> None:
    """Lève `ErreurValidation` pour un champ inconnu, un type ou une forme invalide."""
    objet = _objet(objet, "projets", CHAMPS)
    if "schema" not in objet:
        raise ErreurValidation("projets : champ manquant : schema")
    if type(objet["schema"]) is not int or objet["schema"] != SCHEMA:
        raise ErreurValidation(f"projets : schema {SCHEMA} attendu")
    vus: dict[str, str] = {}
    chantiers = _vide(objet.get("chantiers"), {})
    if not isinstance(chantiers, dict):
        raise ErreurValidation("chantiers : un objet est attendu")
    for nom, chantier in chantiers.items():
        if not isinstance(nom, str) or not nom.strip() or len(nom) > 100:
            raise ErreurValidation("chantiers : nom de chantier non vide (100 caractères au plus)")
        chantier = _objet(_vide(chantier, {}), f"chantier {nom}", frozenset({"projets"}))
        for brut in _liste(_vide(chantier.get("projets"), []), f"chantier {nom} : projets"):
            projet = _projet(brut, f"chantier {nom}")
            if projet in vus:
                raise ErreurValidation(
                    f"chantier {nom} : {projet} déjà dans le chantier {vus[projet]}"
                )
            vus[projet] = nom
    exclus = [_projet(p, "exclus") for p in _liste(_vide(objet.get("exclus"), []), "exclus")]
    deja = sorted(set(exclus) & vus.keys())
    if deja:
        raise ErreurValidation(f"exclus : {deja[0]} est aussi dans un chantier")
    for brut in _liste(_vide(objet.get("dependances"), []), "dependances"):
        morceaux = brut.split(" ← ") if isinstance(brut, str) else []
        if len(morceaux) != 2:
            raise ErreurValidation("dependances : forme « A ← B » attendue")
        a, b = (_projet(m, "dependances") for m in morceaux)
        if a == b:
            raise ErreurValidation(f"dependances : {a} ne dépend pas de lui-même")
    pauses = _vide(objet.get("pauses"), {})
    if not isinstance(pauses, dict):
        raise ErreurValidation("pauses : un objet est attendu")
    for brut, pause in pauses.items():
        projet = _projet(brut, "pauses")
        pause = _objet(pause, f"pause {projet}", frozenset({"revue"}))
        if "revue" not in pause:
            raise ErreurValidation(f"pause {projet} : date de revue manquante")
        _date(pause["revue"], f"pause {projet} : revue")
