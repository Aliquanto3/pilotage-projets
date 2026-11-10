"""Marqueurs d'une session dans `last_assistant_message` (AD-2, AD-10) : pur, ne lève jamais.

Grammaire (une ligne, entre `<!--` et `-->`, champs séparés par `|`) :

    <!-- pilotage: action=attend-utilisateur | type=choix | quoi="…" -->
    <!-- pilotage: reprise="…" -->

- un champ vaut `cle=valeur` (valeur sans espace ni `|` ni `"`) ou `cle="texte"` (sans `"`
  interne) ; `cle` est `[a-z_]+` ; les champs inconnus sont ignorés ;
- marqueur d'attente : `action=attend-utilisateur` (ou l'ancienne valeur `attend-anael`, émise
  par les sessions ouvertes avant la story 7.2) et `quoi` non vide ; `type` n'est gardé que s'il
  vaut `choix`, `test`, `donnees` ou `acces`, sinon il est omis ;
- marqueur de reprise : `reprise` non vide ;
- un marqueur mal formé (guillemet non fermé, séparateur manquant, champ sans `=`, corps de plus
  de 2000 caractères, ou qui en contient un autre ouvert avant d'être fermé) est ignoré en entier ;
  un même marqueur peut porter les deux genres ;
- seuls comptent les marqueurs du bloc final : les dernières lignes non vides du message qui se
  terminent chacune par un marqueur (les lignes vides entre elles sont sautées) ; un marqueur
  suivi d'une ligne de texte (exemple cité, bloc de code) est ignoré ;
- dans ce bloc, deux marqueurs valides du même genre : le dernier l'emporte.

Les textes rendus sont bruts : `texte.nettoyer` s'applique à l'écriture, pas ici.
"""

import re
from collections import namedtuple

TYPES = frozenset({"choix", "test", "donnees", "acces"})
BORNE_CORPS = 2000
ACTION_ATTENTE = "attend-utilisateur"
# Alias d'entrée : ancienne valeur (avant la story 7.2), lue comme `ACTION_ATTENTE`, jamais écrite.
ACTION_ATTENTE_ANCIENNE = "attend-anael"
ACTIONS_ATTENTE = frozenset({ACTION_ATTENTE, ACTION_ATTENTE_ANCIENNE})

_MARQUEUR = re.compile(rf"<!--[ \t]*pilotage:((?:(?!<!--)[^\n]){{0,{BORNE_CORPS}}}?)-->")
_CHAMP = re.compile(r'[ \t]*([a-z_]+)=(?:"([^"]*)"|([^\s|"]+))[ \t]*(?:\||$)')
_SUBSTITUT = re.compile("[\ud800-\udfff]")

# `attente` : `(type ou None, quoi)` ou `None` ; `reprise` : texte ou `None`.
Marqueurs = namedtuple("Marqueurs", ["attente", "reprise"])
AUCUN = Marqueurs(None, None)


def _champs(corps: str) -> dict[str, str] | None:
    """Champs d'un marqueur, ou `None` s'il est mal formé (le dernier doublon l'emporte)."""
    champs: dict[str, str] = {}
    position = 0
    corps = corps.rstrip()
    if not corps.strip():
        return None
    while position < len(corps):
        trouve = _CHAMP.match(corps, position)
        if trouve is None:
            return None
        valeur = trouve.group(2) if trouve.group(2) is not None else trouve.group(3)
        champs[trouve.group(1)] = valeur
        position = trouve.end()
    return champs


def _bloc_final(message: str) -> list[re.Match]:
    """Marqueurs des dernières lignes non vides qui finissent par un marqueur, dans l'ordre."""
    lignes: list[list[re.Match]] = []
    for ligne in reversed(message.split("\n")):
        ligne = ligne.rstrip()
        if not ligne:
            continue
        trouves = list(_MARQUEUR.finditer(ligne))
        if not trouves or trouves[-1].end() != len(ligne):
            break
        lignes.append(trouves)
    return [trouve for trouves in reversed(lignes) for trouve in trouves]


def lire(message: object) -> Marqueurs:
    """Marqueurs valides du message ; rien d'exploitable (ou type inattendu) : `AUCUN`."""
    if not isinstance(message, str):
        return AUCUN
    attente = None
    reprise = None
    try:
        for trouve in _bloc_final(message):
            if _SUBSTITUT.search(trouve.group(1)):
                continue  # substitut UTF-16 isolé : refusé à l'écriture, marqueur ignoré
            champs = _champs(trouve.group(1))
            if champs is None:
                continue
            quoi = champs.get("quoi", "").strip()
            if champs.get("action") in ACTIONS_ATTENTE and quoi:
                genre = champs.get("type")
                attente = (genre if genre in TYPES else None, quoi)
            note = champs.get("reprise", "").strip()
            if note:
                reprise = note
    except Exception:  # noqa: BLE001 - garde-fou : une lecture ne doit jamais lever
        return AUCUN
    return Marqueurs(attente, reprise)
