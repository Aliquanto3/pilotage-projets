"""Heuristique de secours (AD-2, AD-3, AD-11) : pur, sans LLM, ne lève jamais.

Détecte une attente de l'utilisateur quand le modèle n'a pas émis de marqueur. Les règles sont
internes à ce module ; les hooks n'en décident aucune, ils appellent `depuis_stop` /
`depuis_notification`.
Le texte rendu est brut : `texte.nettoyer` (filtre et borne) s'applique à l'écriture.

Sources, de la plus à la moins prioritaire (le marqueur, lu par `marqueur`, passe avant toutes) :
- `askuserquestion` : `Notification` de type `elicitation_dialog`, *quoi* = texte de la question ;
- `permission` : `Notification` de type `permission_prompt`, *quoi* « permission demandée : X » ;
- `question` : `last_assistant_message` qui finit par `?`, *quoi* = dernière phrase.

HYPOTHÈSE a confirmer (AD-2, capture interactive de la story 2.1 pas encore faite) : le message de
`Notification` d'un `AskUserQuestion` est le texte de sa première question ; celui d'une permission
contient « ... permission to use <Outil> ». Un *quoi* vide signale qu'aucun texte n'est exploitable.
"""

import re
from collections import namedtuple

MARQUEUR = "marqueur"
ASKUSERQUESTION = "askuserquestion"
PERMISSION = "permission"
QUESTION_FINALE = "question"
PRIORITE = (MARQUEUR, ASKUSERQUESTION, PERMISSION, QUESTION_FINALE)  # valeurs de `attente.source`
# Sources de milieu de tour : le dialogue est résolu quand le tour se termine (`Stop`).
MILIEU_DE_TOUR = frozenset({ASKUSERQUESTION, PERMISSION})

# `notification_type` qui valent attente (AD-2 : décidé ici, pas par le matcher).
TYPES_NOTIFICATION = {"elicitation_dialog": ASKUSERQUESTION, "permission_prompt": PERMISSION}
LIBELLE_PERMISSION = "permission demandée : "
BORNE_ANALYSE = 2000  # derniers caractères examinés (coût linéaire borné)

# `source` parmi `PRIORITE` ; `quoi` brut (peut être vide).
Detection = namedtuple("Detection", ["source", "quoi"])

_COMMENTAIRE = re.compile(r"<!--.*?-->", re.DOTALL)
_FIN_QUESTION = re.compile(r"\?[\s*_`\"'»”)\]]*\Z")
_FIN_FERMANTS = re.compile(r"[\s*_`\"'»”)\]]+\Z")
_DEBUT_LIGNE = re.compile(r"^\s*(?:[>#*\-•]+\s*)*(?:\d+[.)]\s+)?")
_FRONTIERE = re.compile(r"[.!?…:;]\s+")
_OUTIL = re.compile(r"\buse\s+([A-Za-z0-9_.:-]{1,64})")
_URL = re.compile(r"(?:[a-z][a-z0-9+.-]*://|www\.)\S*\Z", re.IGNORECASE)
_FENCE = re.compile(r"^ {0,3}(?:```|~~~)", re.MULTILINE)


def priorite(source: str) -> int:
    """Rang d'une source (0 = marqueur, le plus prioritaire) ; inconnue : après toutes."""
    return PRIORITE.index(source) if source in PRIORITE else len(PRIORITE)


def source_de(attente: object) -> str:
    """Source d'une attente écrite ; `source` absente (posée par le marqueur) : `marqueur`."""
    source = attente.get("source", MARQUEUR) if isinstance(attente, dict) else MARQUEUR
    return source if source in PRIORITE else MARQUEUR


def choisir(*detections: Detection | None) -> Detection | None:
    """La détection la plus prioritaire (la première à égalité), ou `None`."""
    gardees = [d for d in detections if d is not None]
    return min(gardees, key=lambda d: priorite(d.source), default=None)


def question_finale(message: object) -> str | None:
    """Dernière phrase interrogative si le message finit par une question, sinon `None`.

    Les commentaires HTML (marqueurs) sont ignorés. La phrase commence après la dernière ponctuation
    forte suivie d'un blanc, dans la dernière ligne non vide.
    """
    if not isinstance(message, str):
        return None
    corps = _COMMENTAIRE.sub("", message[-BORNE_ANALYSE:]).rstrip()
    if corps.endswith("```") or not _FIN_QUESTION.search(corps):  # bloc de code : pas une question
        return None
    brute = corps.rsplit("\n", 1)[-1]
    if (
        len(_FENCE.findall(corps)) % 2  # bloc de code non fermé
        or brute.startswith(("    ", "\t"))  # code indenté
        or _URL.search(_FIN_FERMANTS.sub("", brute))  # `?` final d'une URL
    ):
        return None
    ligne = _DEBUT_LIGNE.sub("", brute, count=1).rstrip()
    coeur = len(_FIN_FERMANTS.sub("", ligne))  # position après le `?` final
    debut = 0
    for trouve in _FRONTIERE.finditer(ligne):
        if trouve.end() < coeur:
            debut = trouve.end()
    phrase = ligne[debut:coeur].strip()
    return "" if phrase.strip("?*_`\"'»”)] ") == "" else phrase


def depuis_stop(message: object) -> Detection | None:
    """Question finale d'un `last_assistant_message`, ou `None`."""
    phrase = question_finale(message)
    return None if phrase is None else Detection(QUESTION_FINALE, phrase)


def depuis_notification(notification_type: object, message: object) -> Detection | None:
    """Attente d'une `Notification` (`AskUserQuestion` ou permission native), ou `None`."""
    if not isinstance(notification_type, str):
        return None
    source = TYPES_NOTIFICATION.get(notification_type)
    if source is None:
        return None
    texte = message if isinstance(message, str) else ""
    if source == ASKUSERQUESTION:
        return Detection(source, texte.strip())
    trouve = _OUTIL.search(texte)
    return Detection(source, LIBELLE_PERMISSION + trouve.group(1) if trouve else "")


def detecter(payload: object) -> Detection | None:
    """Détection d'un payload `Stop` ou `Notification` (sans le marqueur) ; sinon `None`."""
    if not isinstance(payload, dict):
        return None
    evenement = payload.get("hook_event_name")
    if evenement == "Stop":
        return depuis_stop(payload.get("last_assistant_message"))
    if evenement == "Notification":
        return depuis_notification(payload.get("notification_type"), payload.get("message"))
    return None
