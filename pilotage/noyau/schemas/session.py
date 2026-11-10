"""Validateur de l'état d'une session principale : `attente/etat/<projet>/<pc>/<session>.json`.

Type de schéma nommé `session` (décision L1 de la story 2.2) pour ne pas le confondre avec le
module `noyau.etat`. Liste blanche de `stockage.md` : tout autre champ est refusé à l'écriture.
"""

import re
from datetime import datetime

from pilotage.noyau import ids, texte
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
OBLIGATOIRES = frozenset(
    {"schema", "projet", "pc", "session", "pid", "pid_cree", "dossier", "branche", "debut",
     "statut"}
)
FACULTATIFS = frozenset({"dernier_tour", "dernier_prompt", "fin", "attente", "reprise"})
CHAMPS = OBLIGATOIRES | FACULTATIFS
STATUTS = frozenset({"active", "attente", "finie"})
CHAMPS_ATTENTE = frozenset({"type", "quoi", "depuis", "source"})
# `source` facultative (absente : `marqueur`, attentes de 2.3) ; priorités : `heuristique`.
SOURCES_ATTENTE = frozenset({"marqueur", "askuserquestion", "permission", "question"})
OBLIGATOIRES_ATTENTE = frozenset({"quoi", "depuis"})
BORNE_BRANCHE = 255
_HORODATAGE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_FILETIME = re.compile(r"[1-9][0-9]{0,19}")
_TYPE_ATTENTE = re.compile(r"[a-z_]{1,40}")


def _refus(message: str) -> ErreurValidation:
    return ErreurValidation(f"session : {message}")


def _entier_positif(valeur: object, nom: str) -> None:
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur <= 0:
        raise _refus(f"{nom} : entier positif attendu")


def _pid_cree(valeur: object) -> None:
    """FILETIME décimal en chaîne, comme `procStart` de `~/.claude/sessions/`, ou `null`."""
    if valeur is not None and (not isinstance(valeur, str) or not _FILETIME.fullmatch(valeur)):
        raise _refus("pid_cree : FILETIME décimal (chaîne) ou null attendu")


def _horodatage(valeur: object, nom: str) -> None:
    if not isinstance(valeur, str) or not _HORODATAGE.fullmatch(valeur):
        raise _refus(f"{nom} : horodatage AAAA-MM-JJTHH:MM:SSZ attendu")
    try:
        datetime.strptime(valeur, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise _refus(f"{nom} : date impossible") from None


def _dossier(valeur: object) -> None:
    if not isinstance(valeur, str) or not valeur:
        raise _refus("dossier : chaîne non vide attendue")
    segments = valeur.split("/")
    if (
        any(c in valeur for c in ("\\", ":", "\x00"))
        or any(not s or s in (".", "..") or ".." in s for s in segments)
        or ids.cle_dossier(valeur) != valeur
    ):
        raise _refus(f"dossier : relatif normalisé attendu ({len(valeur)} caractères)")


def _branche(valeur: object) -> None:
    if valeur is None:
        return
    if (
        not isinstance(valeur, str)
        or not valeur
        or len(valeur) > BORNE_BRANCHE
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in valeur)
        or texte.est_suspect(valeur)
    ):
        raise _refus("branche : nom de branche invalide")


def _attente(valeur: object) -> None:
    if valeur is None:
        return
    if (
        not isinstance(valeur, dict)
        or not OBLIGATOIRES_ATTENTE <= valeur.keys()
        or not valeur.keys() <= CHAMPS_ATTENTE
    ):
        raise _refus("attente : objet {type?, quoi, depuis, source?} attendu")
    if "type" in valeur and (
        not isinstance(valeur["type"], str) or not _TYPE_ATTENTE.fullmatch(valeur["type"])
    ):
        raise _refus("attente.type : [a-z_]{1,40} attendu")
    if "source" in valeur and (
        not isinstance(valeur["source"], str) or valeur["source"] not in SOURCES_ATTENTE
    ):
        raise _refus(f"attente.source : {', '.join(sorted(SOURCES_ATTENTE))} attendu")
    _horodatage(valeur["depuis"], "attente.depuis")
    try:
        texte.valider_quoi(valeur["quoi"])
    except texte.ErreurTexte as exc:
        raise _refus(f"attente.{exc}") from None


def valider(objet: object) -> None:
    """Refuse champ inconnu ou manquant, `schema` autre que 1, identifiant ou forme invalide."""
    if not isinstance(objet, dict):
        raise _refus("un objet est attendu")
    inconnus = sorted(str(cle) for cle in objet.keys() - CHAMPS)
    if inconnus:
        raise _refus(f"champ inconnu : {', '.join(inconnus)}")
    manquants = sorted(OBLIGATOIRES - objet.keys())
    if manquants:
        raise _refus(f"champ manquant : {', '.join(manquants)}")
    schema = objet["schema"]
    if isinstance(schema, bool) or schema != SCHEMA:
        raise _refus(f"schema {SCHEMA} attendu")
    try:
        ids.valider_projet(objet["projet"])
        ids.valider_pc(objet["pc"])
        ids.valider_session(objet["session"])
    except ids.ErreurId as exc:
        raise _refus(str(exc)) from None
    _entier_positif(objet["pid"], "pid")
    _pid_cree(objet["pid_cree"])
    _dossier(objet["dossier"])
    _branche(objet["branche"])
    _horodatage(objet["debut"], "debut")
    for nom in ("dernier_tour", "dernier_prompt", "fin"):
        if nom in objet:
            _horodatage(objet[nom], nom)
    statut = objet["statut"]
    if statut not in STATUTS:
        raise _refus(f"statut : {', '.join(sorted(STATUTS))} attendu")
    if statut == "finie" and "fin" not in objet:
        raise _refus("statut finie sans fin")
    if "attente" in objet:
        _attente(objet["attente"])
    if statut == "attente" and not objet.get("attente"):
        raise _refus("statut attente sans attente")
    if "reprise" in objet and objet["reprise"] is not None:
        try:
            texte.valider_note(objet["reprise"])
        except texte.ErreurTexte as exc:
            raise _refus(f"reprise : {exc}") from None
