"""Catalogue unique des alertes (AD-5 §9, M8) : texte rédigé à la lecture, pur, sans E/S.

`attente/alertes.json` ne stocke que `source`, `code` et `params` ; le texte vient de ce
catalogue, à chaque lecture. Les codes de `sync` ont des paramètres exacts (`REGLES`), vérifiés
par le validateur `schemas.alertes` ; leur heure est stockée en UTC (`instant`) et rendue dans le
fuseau reçu. Une alerte écrite avant M8 porte encore un `message` : il est rendu tel quel quand
le code n'a pas de modèle ou que ses paramètres ne conviennent pas. `texte` ne lève jamais.
"""

import re
from collections.abc import Mapping
from datetime import UTC, datetime, tzinfo

DEPOT_PUBLIC = "depot-public"
DEPOT_NON_CONFIGURE = "depot-non-configure"
SYNC_ECHEC = "sync-echec"
FICHIERS_IGNORES = "fichiers-ignores"
SYNC_CONFLIT = "sync-conflit"
SYNC_PUSH_REFUSE = "sync-push-refuse"
PROJETS_NON_COMMITE = "projets-non-commite"

MOTIF_AUTOSTASH = "autostash"
MOTIF_REBASE = "rebase"
MOTIF_NON_FAST_FORWARD = "non-fast-forward"
MOTIFS = {
    MOTIF_AUTOSTASH: "modifications locales en conflit, gardées dans le stash",
    MOTIF_REBASE: "conflit de rebase",
    MOTIF_NON_FAST_FORWARD: "push refusé (non-fast-forward)",
}

_ETAPE = re.compile(r"[a-z0-9-]{1,64}")
_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_FORMAT_INSTANT = "%Y-%m-%dT%H:%M:%SZ"
_ABANDON = "Synchro abandonnée à {heure} : {motif}. Nouvel essai au prochain cycle."

# code -> modèle `str.format` ; les paramètres nommés par le modèle sont ceux de l'alerte.
MODELES: dict[str, str] = {
    "scan-echec": "Scan en échec",
    "alertes-illisibles": "alertes.json illisible : remplacé, alertes des autres sources perdues",
    "projets-illisible": "projets.yaml illisible",
    "projets-invalide": "projets.yaml ignoré : {detail}",
    "projets-version-recente": "PC en version plus récente : projets.yaml en lecture seule",
    "depot-ignore": "dépôt ignoré : nom de projet invalide",
    "dossier-doublon-casse": "deux dossiers ne diffèrent que par la casse : le second est ignoré",
    "sessions-illisibles": "Fichier d'état de session illisible ignoré",
    "sessions-claude-illisibles": "Fichier de ~/.claude/sessions illisible ignoré",
    "faits-github-non-relus": "Faits GitHub non relus : {projet}.",
    "donnees-version-recente": "Fichiers de {pc} ignorés : {suite}",
    "donnees-illisibles": "Fichier de donnees/ illisible ignoré",
    DEPOT_PUBLIC: "Envoi refusé : le dépôt de données n'est pas privé.",
    # Story 7.1 : `depot_donnees` absent ou invalide dans config.json, synchro arrêtée avant
    # tout accès réseau.
    DEPOT_NON_CONFIGURE: (
        "Synchro arrêtée : dépôt de données non configuré. Renseignez depot_donnees "
        "(propriétaire/nom) dans config.json ou relancez l'installation."
    ),
    FICHIERS_IGNORES: "Fichiers locaux illisibles ou invalides : non copiés",
    SYNC_ECHEC: "Synchro en échec à l'étape {etape}",
    SYNC_CONFLIT: _ABANDON,
    SYNC_PUSH_REFUSE: _ABANDON,
    # Story 5.1 : projets.yaml invalide ou d'un schema plus récent, gardé hors du commit (M7).
    PROJETS_NON_COMMITE: "projets.yaml invalide ou d'une version plus récente : non envoyé",
    # Story 5.1 : opérations rejetées (source `operation`), gardées dans `operations/rejetees/`.
    "operation-nom-invalide": "{nombre} fichier(s) d'opération au nom invalide ignoré(s)",
    "operation-invalide": "Opération {id} rejetée : fichier invalide",
    "operation-version-recente": "Opération {id} rejetée : écrite par une version plus récente",
    "operation-message-different": (
        "Opération {id} rejetée : un autre message de {projet} porte déjà cet identifiant"
    ),
    "operation-projets-invalide": (
        "Opération {id} rejetée : projets.yaml absent, illisible ou invalide"
    ),
    "operation-projets-version-recente": (
        "Opération {id} rejetée : PC en version plus récente, projets.yaml en lecture seule"
    ),
    "operation-valeur-differente": (
        "Modification refusée : projets.yaml a changé ailleurs (champ {champ} de {projet})."
    ),
    "operation-patch-impossible": (
        "Opération {id} rejetée : projets.yaml ne se modifie pas sans risque ({champ} de {projet})"
    ),
    "operation-deja-appliquee": (
        "Opération {id} rejetée : identifiant déjà appliqué avec un autre contenu"
    ),
    "operation-resultat-invalide": (
        "Opération {id} rejetée : projets.yaml modifié serait invalide ({projet})"
    ),
}

# Codes à paramètres exacts : {paramètre: motif ou ensemble des valeurs admises}.
REGLES: dict[str, dict[str, re.Pattern | frozenset]] = {
    DEPOT_PUBLIC: {},
    DEPOT_NON_CONFIGURE: {},
    FICHIERS_IGNORES: {},
    SYNC_ECHEC: {"etape": _ETAPE},
    SYNC_CONFLIT: {"instant": _INSTANT, "motif": frozenset({MOTIF_AUTOSTASH, MOTIF_REBASE})},
    SYNC_PUSH_REFUSE: {"instant": _INSTANT, "motif": frozenset({MOTIF_NON_FAST_FORWARD})},
    PROJETS_NON_COMMITE: {},
}


class AlerteInconnue(ValueError):
    """Paramètres différents de ceux qu'un code à paramètres exacts attend."""


def instant(moment: datetime) -> str:
    """Horodatage UTC à la seconde, avec `Z`, du paramètre `instant`."""
    return moment.astimezone(UTC).strftime(_FORMAT_INSTANT)


def verifier(code: str, params: object) -> None:
    """Lève `AlerteInconnue` si `code` a des paramètres exacts (`REGLES`) et que `params` n'a pas
    ces clés et des valeurs texte admises. Sans effet pour les autres codes."""
    attendus = REGLES.get(code)
    if attendus is None:
        return
    if not isinstance(params, dict) or params.keys() != attendus.keys():
        raise AlerteInconnue(f"{code} : paramètres {sorted(attendus)} attendus")
    for cle, regle in attendus.items():
        valeur = params[cle]
        valide = isinstance(valeur, str) and (
            valeur in regle if isinstance(regle, frozenset) else regle.fullmatch(valeur)
        )
        if not valide:
            raise AlerteInconnue(f"{code} : paramètre {cle} invalide")


_SUITE_VERSION = {
    "plus récente": "version plus récente. Mettez à jour pilotage-projets sur ce PC.",
    "inconnue": "version inconnue.",
}


def _valeurs(code: str, params: Mapping, fuseau: tzinfo | None) -> Mapping:
    if code == "donnees-version-recente":
        return {**params, "suite": _SUITE_VERSION[params["quelle"]]}
    if code not in REGLES:
        return params
    verifier(code, params)
    valeurs = dict(params)
    if "instant" in valeurs:
        moment = datetime.strptime(valeurs.pop("instant"), _FORMAT_INSTANT).replace(tzinfo=UTC)
        valeurs["heure"] = f"{moment.astimezone(fuseau):%H:%M}"
    if "motif" in valeurs:
        valeurs["motif"] = MOTIFS[valeurs["motif"]]
    return valeurs


def texte(alerte: Mapping, fuseau: tzinfo | None = None) -> str:
    """Texte d'une alerte `{code, params}` (ou `{code, message}` écrite avant M8).

    `fuseau` : celui de l'heure affichée (`None` : fuseau local). Ne lève jamais : modèle absent
    ou paramètres qui ne conviennent pas, le `message` puis le code sont rendus.
    """
    code = alerte.get("code", "")
    params = alerte.get("params")
    modele = MODELES.get(code) if isinstance(code, str) else None
    if modele is not None and isinstance(params, Mapping):
        try:
            return modele.format_map(_valeurs(code, params, fuseau))
        # AlerteInconnue est une ValueError ; OSError, OverflowError : instant hors de la plage
        # du fuseau (an 1, an 9999) ; TypeError : fuseau qui n'est pas un `tzinfo`.
        except (KeyError, IndexError, ValueError, TypeError, OSError, OverflowError):
            pass
    message = alerte.get("message")
    if isinstance(message, str) and message:
        return message
    return str(code)
