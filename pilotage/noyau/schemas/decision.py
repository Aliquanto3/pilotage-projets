"""Validateur d'une ligne du journal de décisions d'un dépôt (story 8.3, AD-10).

`attente/depots/<projet>/<pc>.decisions.jsonl` (et sa copie dans `donnees/`), une ligne JSON par
décision : `date` (`AAAA-MM-JJ`, posée par le hook, jour de `ecrit`), `ecrit` (ISO Z),
`decision` (300 points de code au plus), `pourquoi` facultatif (300), `session`. Tout autre champ
est refusé. Les cinq dernières décisions du PC sont aussi rangées dans le fichier d'état
(`etat_depot`), au même format.
"""

import re
from datetime import datetime

from pilotage.noyau import ids
from pilotage.noyau.schemas.erreurs import ErreurValidation

BORNE_DECISION = 300  # points de code, `decision` comme `pourquoi`
OBLIGATOIRES = frozenset({"date", "ecrit", "decision", "session"})
CHAMPS = OBLIGATOIRES | {"pourquoi"}
_HORODATAGE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def horodatage(valeur: object, nom: str, schema: str) -> str:
    """`AAAA-MM-JJTHH:MM:SSZ` d'une date possible ; lève `ErreurValidation` sinon."""
    if not isinstance(valeur, str) or not _HORODATAGE.fullmatch(valeur):
        raise ErreurValidation(f"{schema} : {nom} : horodatage AAAA-MM-JJTHH:MM:SSZ attendu")
    try:
        datetime.strptime(valeur, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ErreurValidation(f"{schema} : {nom} : date impossible") from None
    return valeur


def champ_texte(valeur: object, borne: int, nom: str, schema: str) -> None:
    """Texte d'une ligne : chaîne non vide sans blanc au bord, `borne` points de code au plus,
    sans caractère de contrôle (`\n`, `\r` compris) ni substitut isolé."""
    if (
        not isinstance(valeur, str)
        or not valeur
        or valeur != valeur.strip()
        or len(valeur) > borne
        or any(
            ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F or 0xD800 <= ord(c) <= 0xDFFF for c in valeur
        )
    ):
        raise ErreurValidation(
            f"{schema} : {nom} : texte d'une ligne de 1 à {borne} points de code attendu"
        )


def valider(objet: object) -> None:
    """Lève `ErreurValidation` pour un champ inconnu ou manquant, un type ou une forme invalide."""
    if not isinstance(objet, dict):
        raise ErreurValidation("decision : un objet est attendu")
    inconnus = sorted(str(c) for c in objet.keys() - CHAMPS)
    if inconnus:
        raise ErreurValidation(f"decision : champ inconnu : {', '.join(inconnus)}")
    manquants = sorted(OBLIGATOIRES - objet.keys())
    if manquants:
        raise ErreurValidation(f"decision : champ manquant : {', '.join(manquants)}")
    ecrit = horodatage(objet["ecrit"], "ecrit", "decision")
    if objet["date"] != ecrit[:10]:
        raise ErreurValidation("decision : date : jour de `ecrit` attendu")
    champ_texte(objet["decision"], BORNE_DECISION, "decision", "decision")
    if "pourquoi" in objet:
        champ_texte(objet["pourquoi"], BORNE_DECISION, "pourquoi", "decision")
    try:
        ids.valider_session(objet["session"])
    except ValueError as exc:
        raise ErreurValidation(f"decision : {exc}") from None
