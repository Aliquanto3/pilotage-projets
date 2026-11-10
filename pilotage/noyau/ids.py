"""Identifiants sûrs (AD-9) : validation des formes et jointure lexicale de segments.

Chaque validateur rend la valeur reçue si elle passe, sinon lève `ErreurId`. Aucune normalisation
silencieuse : l'appelant met en minuscules (`projet`, `pc`) avant de valider.
Les expressions utilisent `fullmatch` (un `$` accepterait un retour à la ligne final) et des
classes ASCII explicites (`\\d` accepterait d'autres chiffres Unicode).
"""

import re
from datetime import datetime

_PROJET = re.compile(r"[a-z0-9._-]{1,100}")
_PC = re.compile(r"[a-z0-9-]{1,32}")
_NON_PC = re.compile(r"[^a-z0-9-]+")
_SESSION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_ID = re.compile(r"([0-9]{8}T[0-9]{6}Z)-[0-9a-f]{8}")
_INTERDITS_SEGMENT = ("/", "\\", ":", "..", "\x00")
# Noms de périphériques Windows : `nul`, `con.json`… désignent le périphérique, pas un fichier.
_RESERVES_WINDOWS = frozenset(
    ["con", "prn", "aux", "nul", "conin$", "conout$"]
    + [f"{base}{n}" for base in ("com", "lpt") for n in [*"0123456789", "¹", "²", "³"]]
)


class ErreurId(ValueError):
    """Identifiant ou segment de chemin refusé."""


def _texte(valeur: object, nom: str) -> str:
    if not isinstance(valeur, str):
        raise ErreurId(f"{nom} : une chaîne est attendue, pas {type(valeur).__name__}")
    return valeur


def _refus(nom: str, valeur: str, attendu: str) -> ErreurId:
    # La valeur n'est jamais recopiée (elle peut contenir un secret qui finirait dans un journal).
    return ErreurId(f"{nom} invalide ({len(valeur)} caractères ; attendu : {attendu})")


def _graphie_windows_ambigue(texte: str) -> bool:
    """Vrai si Windows lirait le nom autrement : point ou espace final, nom de périphérique."""
    if texte.endswith((".", " ")):
        return True
    return texte.split(".", 1)[0].rstrip(" ").lower() in _RESERVES_WINDOWS


def valider_projet(valeur: object) -> str:
    """Nom de dépôt en minuscules, `[a-z0-9._-]{1,100}`, ni `.` ni `..`.

    Option la plus sûre (AD-9, deux graphies) : refuse aussi `..` n'importe où, un point final
    (Windows lit `a.` comme `a`) et les noms de périphériques Windows (`nul`, `con.x`…).
    """
    texte = _texte(valeur, "projet")
    if not _PROJET.fullmatch(texte) or ".." in texte or _graphie_windows_ambigue(texte):
        raise _refus("projet", texte, "[a-z0-9._-]{1,100}, sans .., ni point final ni nom réservé")
    return texte


def valider_pc(valeur: object) -> str:
    """Nom de PC en minuscules, `[a-z0-9-]{1,32}`."""
    texte = _texte(valeur, "pc")
    if not _PC.fullmatch(texte) or _graphie_windows_ambigue(texte):
        raise _refus("pc", texte, "[a-z0-9-]{1,32}, hors nom réservé Windows")
    return texte


def normaliser_pc(brut: str) -> str:
    """Nom de PC normalisé puis validé : `casefold()`, `[^a-z0-9-]+` -> `-`, bords `-` retirés,
    32 caractères au plus. Seule normalisation, partagée par le scan et les hooks."""
    propre = _NON_PC.sub("-", brut.casefold()).strip("-")[:32].strip("-")
    return valider_pc(propre)


def valider_session(valeur: object) -> str:
    """UUID en forme canonique minuscule (8-4-4-4-12)."""
    texte = _texte(valeur, "session")
    if not _SESSION.fullmatch(texte):
        raise _refus("session", texte, "UUID canonique en minuscules")
    return texte


def valider_id(valeur: object) -> str:
    """`AAAAMMJJTHHMMSSZ-<8 hex minuscules>`, avec une date et une heure réelles."""
    texte = _texte(valeur, "id")
    trouve = _ID.fullmatch(texte)
    if trouve:
        try:
            datetime.strptime(trouve.group(1), "%Y%m%dT%H%M%SZ")
        except ValueError:
            trouve = None
    if not trouve:
        raise _refus("id", texte, "AAAAMMJJTHHMMSSZ-<8 hex>")
    return texte


def valider_segment(valeur: object) -> str:
    """Segment de chemin : non vide, sans `/`, `\\`, `:`, `..`, octet nul ; ni `.` ni absolu."""
    texte = _texte(valeur, "segment")
    if (
        not texte
        or any(interdit in texte for interdit in _INTERDITS_SEGMENT)
        or _graphie_windows_ambigue(texte)
    ):
        raise _refus("segment", texte, "non vide, sans / \\ : .. ni octet nul, ni point ou "
                     "espace final, ni nom réservé Windows")
    return texte


def joindre(*segments: object) -> str:
    """Jointure lexicale par `/` de segments validés (aucune E/S, aucune résolution).

    Un segment absolu (`/x`, `C:\\x`, `\\\\h\\s`), vide ou à `..` est refusé : le résultat est
    toujours relatif et ne remonte jamais. La vérification sous une racine est faite
    sur le disque par `chemins.joindre_sous`.
    """
    if not segments:
        raise ErreurId("jointure sans segment")
    return "/".join(valider_segment(segment) for segment in segments)


def cle_dossier(relatif: str) -> str:
    """Clé de `table-dossiers.json` (contrat C5) pour un dossier relatif à la racine GitHub.

    Séparateur `/`, sans `/` final, `casefold()`. Seule normalisation des clés : le scan
    l'applique à l'écriture, le validateur `table_dossiers` refuse toute autre graphie, les hooks
    l'appliquent au chemin relatif de leur `cwd`. Aucune validation ici (rôle du validateur).
    """
    return relatif.replace("\\", "/").rstrip("/").casefold()
