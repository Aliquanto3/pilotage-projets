"""Action calculée à partir des faits (AD-11, `etats-action.md`) : seul code qui l'applique.

Pur, sans E/S. `calculer_action` rend le verdict d'un projet ; `assembler` rend une carte par
projet, les colonnes triées, les cartes de chantier à part, tous les comptes de l'accueil et le
détail de chaque projet pour le tiroir (`detail`, `criteres`, story 4.7).

Forme des faits d'un projet (un seul jeu par projet ; `noyau.assemblage` les produit pour tous
les PC) :
    categorie : "classé" | "découvert, à classer" (défaut "classé")
    chantier  : nom du chantier ou None (utilisé par `assembler`)
    pause     : {"revue": "AAAA-MM-JJ"} ou None
    depot     : `faits_depot` de l'instantané (None : faits non relus)
    attente   : {"origine": "marqueur"|"heuristique", "type": str|None, "quoi": str} ou None
    clone_ici : projet cloné sur ce PC (défaut True) ; pcs : PC dont l'instantané le cite
    depot_de  : {"pc", "genere_a"} si `depot` vient de l'instantané d'un autre PC, sinon None
    sessions  : sessions de tous les PC (liste de dicts ; autre PC : `distante`, `nouvelles`) :
                champs de l'état de session
                (`session`, `pc`, `debut`, `dernier_tour`, `dernier_prompt`, `fin`, `attente`
                `{quoi, depuis, type?, source?}`) plus `vivante` (bool fourni par l'adaptateur du
                scan : le noyau ne lit ni pid ni heure de création).
Un projet exclu n'est jamais passé à ce module.
"""

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import NamedTuple

from pilotage.noyau import faits as noyau_faits
from pilotage.noyau import heuristique
from pilotage.noyau import texte as noyau_texte

CATEGORIE_A_CLASSER = "découvert, à classer"  # = scan.inventaire.CATEGORIE_A_CLASSER (testé)

# Actions, de la plus urgente à la moins urgente (ordre de priorité de `etats-action.md`).
ATTEND = "attend-utilisateur"
A_RELANCER = "a-relancer"
TOURNE = "tourne"
RIEN = "rien-a-faire"
ACTIONS = (ATTEND, A_RELANCER, TOURNE, RIEN)
LIBELLES_ACTION = {
    ATTEND: "Vous attend",  # nom configuré : `libelle_action`
    A_RELANCER: "À relancer",
    TOURNE: "Tourne",
    RIEN: "Rien à faire",
}


def libelle_action(action: str, utilisateur: str = "") -> str:
    """Libellé d'une action ; « Attend <nom> » si l'appelant passe un nom affiché non vide."""
    nom = noyau_texte.nom_affiche(utilisateur)  # défense en profondeur : règle de chemins
    if action == ATTEND and nom:
        return f"Attend {nom}"
    return LIBELLES_ACTION[action]


TYPES_ATTENTE = ("choix", "test", "donnees", "acces")
A_QUALIFIER = "a-qualifier"

# Raisons : liste fermée des codes.
CODES = (
    "attend-utilisateur", "session-arretee", "tourne", "run-bloque", "run-en-cours",
    "story-ouverte", "pause-a-revoir",
    "a-stabiliser", "faits-absents", "pause", "a-classer", "stable",
)
# Critères d'« à stabiliser », dans l'ordre de `etats-action.md` (`ci-en-cours` : M6).
CRITERES = (
    "pas-de-release", "commits-depuis-release", "story-ouverte", "pr-ouverte", "ci-rouge",
    "pas-de-ci", "ci-en-cours",
)
_TEXTES_CRITERE = {
    "pas-de-release": "pas de release",
    "commits-depuis-release": "commits hors docs/chore depuis {tag}",
    "story-ouverte": "story ouverte",
    "pr-ouverte": "PR ouverte",
    "ci-rouge": "CI de main rouge",
    "pas-de-ci": "pas de CI",
    "ci-en-cours": "CI de main en cours",
}
# Familles (`etats-action.md` § Champs d'affichage) : ordre fixe, À relancer puis Rien à faire.
FAMILLES_A_RELANCER = (
    "arretee", "sans-nouvelles", "run-bloque", "sans-session", "pause-a-revoir", "non-relu",
    "a-stabiliser",
)
FAMILLES_RIEN = ("stable", "pause", "a-classer")
FAMILLES = FAMILLES_A_RELANCER + FAMILLES_RIEN
# Famille de chaque code de 🟠 et de ⚪ ; session arrêtée distante : `sans-nouvelles` (`_arretee`).
_FAMILLE_DU_CODE = {
    "session-arretee": "arretee", "run-bloque": "run-bloque", "run-en-cours": "sans-session",
    "story-ouverte": "sans-session", "pause-a-revoir": "pause-a-revoir",
    "faits-absents": "non-relu", "a-stabiliser": "a-stabiliser",
    "stable": "stable", "pause": "pause", "a-classer": "a-classer",
}
SEUIL_VIEILLISSANTE = timedelta(hours=8)
_COMMITS_NEUTRES = ("docs", "chore")
_CHAMPS_DEPOT = frozenset({"tag", "commits", "prs_ouvertes", "ci", "stories_ouvertes", "run"})


class Action(NamedTuple):
    action: str
    raison: dict
    quoi: str
    type: str | None
    famille: str | None = None  # 🟠 et ⚪ seulement (`FAMILLES`)
    vieillissante: bool = False  # 🔴 commencée depuis plus de `SEUIL_VIEILLISSANTE`


def _jj_mm(jour: date) -> str:
    return f"{jour.day:02d}/{jour.month:02d}"


def _raison(code: str, texte: str, critere: str | None = None, **params: object) -> dict:
    raison: dict = {"code": code}
    if critere is not None:
        raison["critere"] = critere
    raison["params"] = params
    raison["texte"] = texte
    return raison


def critere_manquant(depot: Mapping) -> str | None:
    """Premier critère de stabilité non rempli (ordre de `CRITERES`), None si stable."""
    if depot.get("tag") is None:
        return "pas-de-release"
    commits = depot.get("commits") or {}
    if any(n for type_, n in commits.items() if type_ not in _COMMITS_NEUTRES):
        return "commits-depuis-release"
    if depot.get("stories_ouvertes", 0) > 0:
        return "story-ouverte"
    if depot.get("prs_ouvertes", 0) > 0:
        return "pr-ouverte"
    ci = depot.get("ci", "aucune")
    if ci == "rouge":
        return "ci-rouge"
    if ci == "verte":
        return None
    return "ci-en-cours" if ci == "en_cours" else "pas-de-ci"


def _a_stabiliser(depot: Mapping, critere: str) -> Action:
    tag = depot.get("tag")
    texte = "à stabiliser : " + _TEXTES_CRITERE[critere].format(tag=tag)
    params = {"tag": tag} if critere == "commits-depuis-release" else {}
    return Action(A_RELANCER, _raison("a-stabiliser", texte, critere, **params), "", None)


def _travail_en_cours(depot: Mapping) -> Action | None:
    run = depot.get("run", "aucun")
    stories = depot.get("stories_ouvertes", 0)
    if run == "bloque":
        return Action(A_RELANCER, _raison("run-bloque", "run bloqué"), "", None)
    if run == "en_cours":
        return Action(A_RELANCER, _raison("run-en-cours", "run non terminé"), "", None)
    if stories > 0:
        texte = "1 story ouverte" if stories == 1 else f"{stories} stories ouvertes"
        return Action(A_RELANCER, _raison("story-ouverte", texte, n=stories), "", None)
    return None


def _origine(attente: Mapping) -> str:
    """`origine` fournie, sinon dérivée de `source` (absente : marqueur ; autre : heuristique)."""
    if "origine" in attente:
        return attente["origine"]
    source = attente.get("source", heuristique.MARQUEUR)
    return "marqueur" if source == heuristique.MARQUEUR else "heuristique"


def _vieillissante(attente: Mapping, maintenant: datetime) -> bool:
    """Attente commencée depuis strictement plus de 8 h ; faux si `depuis` absent ou illisible.

    `depuis` : ISO 8601 avec fuseau (`Z` ou `+HH:MM`) ; une date sans fuseau est illisible.
    """
    depuis = attente.get("depuis")
    if not isinstance(depuis, str):
        return False
    try:
        debut = datetime.fromisoformat(depuis)
    except ValueError:
        return False
    return debut.tzinfo is not None and maintenant - debut > SEUIL_VIEILLISSANTE


def _attente(attente: Mapping, maintenant: datetime) -> Action:
    type_ = attente.get("type")
    if _origine(attente) != "marqueur" or type_ not in TYPES_ATTENTE:
        type_ = A_QUALIFIER
    quoi = attente.get("quoi") or ""
    texte = f"vous attend : {quoi}" if quoi else "vous attend"
    return Action(
        ATTEND, _raison(ATTEND, texte, type=type_), quoi, type_,
        vieillissante=_vieillissante(attente, maintenant),
    )


def _finie(session: Mapping) -> bool:
    """M4 : une session qui porte `fin` ou `statut=finie` n'est jamais « Tourne »."""
    return bool(session.get("fin")) or session.get("statut") == "finie"


def _attente_valide(session: Mapping) -> Mapping | None:
    """Attente d'une session vivante sans `fin`, si aucun prompt ne l'a suivie (M1)."""
    attente = session.get("attente")
    if _finie(session) or not session.get("vivante") or not isinstance(attente, Mapping):
        return None
    depuis = attente.get("depuis")
    prompt = session.get("dernier_prompt")
    if not isinstance(depuis, str) or (isinstance(prompt, str) and prompt > depuis):
        return None
    return attente


def _session_en_attente(sessions: list[Mapping]) -> tuple[Mapping, Mapping] | None:
    """(session, attente) la plus prioritaire (marqueur d'abord), puis la plus récente."""
    valides = [(s, a) for s in sessions if (a := _attente_valide(s)) is not None]
    valides.sort(key=lambda p: p[1]["depuis"], reverse=True)  # tri stable : récente d'abord
    # source inconnue : après toutes (`priorite`), jamais au rang du marqueur
    valides.sort(key=lambda p: heuristique.priorite(p[1].get("source", heuristique.MARQUEUR)))
    return valides[0] if valides else None


def _attente_des_sessions(sessions: list[Mapping]) -> Mapping | None:
    retenue = _session_en_attente(sessions)
    return retenue[1] if retenue else None


def _dernier_etat(session: Mapping, fuseau: tzinfo) -> str:
    """`JJ/MM HH:MM` du plus récent de `debut`, `dernier_tour`, `dernier_prompt` ; sinon vide."""
    dates = [
        v for c in ("debut", "dernier_tour", "dernier_prompt")
        if isinstance(v := session.get(c), str)
    ]
    try:
        instant = datetime.strptime(max(dates), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:  # aucune date, ou illisible
        return ""
    return instant.astimezone(fuseau).strftime("%d/%m %H:%M")


def _heure_locale(horodatage: object, fuseau: tzinfo) -> str:
    """`JJ/MM HH:MM` d'un horodatage ISO UTC, sinon vide."""
    if not isinstance(horodatage, str):
        return ""
    try:
        instant = datetime.strptime(horodatage, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return ""
    return instant.astimezone(fuseau).strftime("%d/%m %H:%M")


def _plus_recent(session: Mapping) -> str:
    """Plus récente des dates `debut`, `dernier_tour`, `dernier_prompt` (chaînes ISO), ou ""."""
    return max(
        (v for c in ("debut", "dernier_tour", "dernier_prompt")
         if isinstance(v := session.get(c), str)),
        default="",
    )


def _identite(session: Mapping) -> tuple[str, str]:
    return session.get("pc") or "?", str(session.get("session") or "")[:8]


def _tourne(session: Mapping, fuseau: tzinfo) -> Action:
    pc, id_ = _identite(session)
    heure = _dernier_etat(session, fuseau)
    texte = f"tourne sur {pc}, session {id_}" + (f", état du {heure}" if heure else "")
    return Action(
        TOURNE, _raison("tourne", texte, pc=pc, session=id_, dernier_etat=heure), "", None,
    )


def _arretee(session: Mapping, fuseau: tzinfo) -> Action:
    pc, id_ = _identite(session)
    texte = f"session {id_} arrêtée sans fin propre ({pc})"
    famille = "arretee"
    if session.get("distante"):  # session d'un autre PC (3.4) : pas d'instantané récent la citant
        famille = "sans-nouvelles"
        depuis = _heure_locale(session.get("nouvelles"), fuseau) or _dernier_etat(session, fuseau)
        texte = f"session {id_} : sans nouvelles de {pc}" + (f" depuis {depuis}" if depuis else "")
    raison = _raison("session-arretee", texte, pc=pc, session=id_)
    return Action(A_RELANCER, raison, "", None, famille)


def _date_revue(pause: object) -> date | None:
    """Date de revue d'une pause ; None si elle est absente ou illisible (pause à revoir)."""
    revue = pause.get("revue") if isinstance(pause, Mapping) else None
    if isinstance(revue, datetime):
        return revue.date()
    if isinstance(revue, date):
        return revue
    try:
        return date.fromisoformat(revue) if isinstance(revue, str) else None
    except ValueError:
        return None


def _depot_lisible(depot: object) -> bool:
    """Faits de dépôt complets et typés (comme `schemas.instantane`) ; sinon tenus pour absents."""
    if not isinstance(depot, Mapping) or not _CHAMPS_DEPOT <= depot.keys():
        return False
    entiers = (depot["prs_ouvertes"], depot["stories_ouvertes"])
    if any(type(n) is not int or n < 0 for n in entiers):
        return False
    commits = depot["commits"]
    return isinstance(commits, Mapping) and all(type(n) is int for n in commits.values())


def calculer_action(faits: Mapping, maintenant: datetime, fuseau: tzinfo) -> Action:
    """Verdict d'un projet : `Action(action, raison, quoi, type, famille, vieillissante)`.

    `famille` suit `etats-action.md` § Champs d'affichage pour 🟠 et ⚪ (None pour 🔴 et 🟢) ;
    `vieillissante` n'est vrai que pour une attente 🔴 commencée depuis plus de 8 h.

    `maintenant` est aware ; `fuseau` situe « aujourd'hui » (échéance de pause) et les dates
    rendues (`JJ/MM`). Priorité : attente, session arrêtée, run bloqué, session vivante
    (« Tourne »), travail en cours, pause, à classer, faits non relus, à stabiliser, stable.
    """
    if maintenant.tzinfo is None:
        raise ValueError("calculer_action : `maintenant` doit porter un fuseau")
    if not isinstance(fuseau, tzinfo):
        raise ValueError("calculer_action : `fuseau` doit être un tzinfo")
    verdict = _verdict(faits, maintenant, fuseau)
    if verdict.action in (A_RELANCER, RIEN) and verdict.famille is None:
        return verdict._replace(famille=_FAMILLE_DU_CODE[verdict.raison["code"]])
    return verdict


def _verdict(faits: Mapping, maintenant: datetime, fuseau: tzinfo) -> Action:
    sessions = [s for s in faits.get("sessions") or [] if isinstance(s, Mapping)]
    ouvertes = sorted(
        (s for s in sessions if not _finie(s)), key=lambda s: str(s.get("session"))
    )
    vivantes = sorted(  # « Tourne » montre la session vivante la plus récente
        (s for s in ouvertes if s.get("vivante")), key=_plus_recent, reverse=True
    )
    attente = faits.get("attente") or _attente_des_sessions(sessions)
    if attente:
        return _attente(attente, maintenant)
    if ouvertes and not vivantes:  # M16 : pid mort ou heure de création différente
        # session de ce PC d'abord, la plus récente ; puis celles des autres PC (3.4)
        recentes = sorted(ouvertes, key=_plus_recent, reverse=True)
        return _arretee(min(recentes, key=lambda s: bool(s.get("distante"))), fuseau)
    depot = faits.get("depot")
    if not _depot_lisible(depot):
        depot = None  # faits incomplets ou mal typés : jamais « stable » (🟠 faits-absents)
    travail = _travail_en_cours(depot) if depot is not None else None
    if travail and travail.raison["code"] == "run-bloque":
        return travail
    if vivantes:
        return _tourne(vivantes[0], fuseau)
    if travail:
        return travail
    if faits.get("pause"):
        revue = _date_revue(faits["pause"])
        if revue is None or maintenant.astimezone(fuseau).date() > revue:
            iso = revue.isoformat() if revue else None
            return Action(
                A_RELANCER, _raison("pause-a-revoir", "pause à revoir", revue=iso), "", None,
            )
        texte = f"pause jusqu'au {_jj_mm(revue)}"
        return Action(RIEN, _raison("pause", texte, revue=revue.isoformat()), "", None)
    if faits.get("categorie") == CATEGORIE_A_CLASSER:
        return Action(RIEN, _raison("a-classer", "à classer"), "", None)
    if depot is None:
        return Action(A_RELANCER, _raison("faits-absents", "faits du dépôt non relus"), "", None)
    critere = critere_manquant(depot)
    if critere is not None:
        return _a_stabiliser(depot, critere)
    return Action(RIEN, _raison("stable", "stable"), "", None)


def _sessions(faits: Mapping) -> list[Mapping]:
    return [s for s in faits.get("sessions") or [] if isinstance(s, Mapping)]


def _texte_ou_none(valeur: object) -> str | None:
    return valeur if isinstance(valeur, str) and valeur else None


def _attente_retenue(faits: Mapping) -> tuple[str | None, str | None]:
    """(PC, `depuis`) de l'attente que retient `calculer_action` ; None quand ils manquent."""
    attente = faits.get("attente")
    if attente:
        if not isinstance(attente, Mapping):
            return None, None
        return _texte_ou_none(attente.get("pc")), _texte_ou_none(attente.get("depuis"))
    retenue = _session_en_attente(_sessions(faits))
    if retenue is None:
        return None, None
    session, attente = retenue
    return _texte_ou_none(session.get("pc")), _texte_ou_none(attente.get("depuis"))


def _cle_colonne(verdict: Action, faits: Mapping, depuis: str | None) -> tuple[bool, str]:
    """Clé de tri dans la colonne (EXPERIENCE.md, « Ordre dans les colonnes », UX-DR6).

    Attend : plus ancienne attente d'abord ; À relancer : plus ancien dernier tour d'abord ;
    Tourne : dernier état le plus récent d'abord ; Rien à faire : pauses par date de revue, puis
    les autres. Rend `(date absente, date ISO)` : une date absente passe après les dates connues ;
    le nom départage (`assembler`).
    """
    if verdict.action == ATTEND:
        return (depuis is None, depuis or "")
    sessions = _sessions(faits)
    if verdict.action == A_RELANCER:
        tour = max((_plus_recent(s) for s in sessions), default="")
        return (tour == "", tour)
    if verdict.action == TOURNE:
        vivantes = [_plus_recent(s) for s in sessions if s.get("vivante") and not _finie(s)]
        recent = max(vivantes, default="")
        return (recent == "", recent)  # décroissant : voir `_trier`
    revue = verdict.raison["params"].get("revue") if verdict.raison["code"] == "pause" else None
    return (revue is None, revue or "")


def _dernier_tour(faits: Mapping) -> tuple[str | None, str | None]:
    """(PC, date ISO) de la session la plus récente, celle de la clé de tri d'À relancer."""
    sessions = [(_plus_recent(s), str(s.get("pc") or "?")) for s in _sessions(faits)]
    date_, pc = max(sessions, default=("", None))
    return (pc, date_) if date_ else (None, None)


# --- Détail du tiroir (story 4.7) -------------------------------------------------------------

# Cinq critères de stabilité, dans l'ordre de `etats-action.md` : (code, libellé).
LIBELLES_CRITERE = (
    ("release", "une release publiée"),
    ("commits", "aucun commit hors docs/chore depuis la release"),
    ("stories", "aucune story ouverte"),
    ("prs", "aucune PR ouverte"),
    ("ci", "CI de main verte"),
)
# Code de `CRITERES` (rendu par `critere_manquant`) -> code du critère non rempli.
CRITERE_DU_CODE = {
    "pas-de-release": "release", "commits-depuis-release": "commits",
    "story-ouverte": "stories", "pr-ouverte": "prs",
    "ci-rouge": "ci", "pas-de-ci": "ci", "ci-en-cours": "ci",
}
_PRECISIONS_CI = {"rouge": "rouge", "en_cours": "en cours"}
SANS_SPRINT_STATUS = "pas de sprint-status.yaml"
# Statuts de session affichés au tiroir : code -> texte (`sans-nouvelles` : texte avec le PC).
TEXTES_STATUT = {
    "attend": "en attente", "active": "active", "finie": "finie",
    "arretee": "arrêtée sans fin propre",
}


def _pluriel(n: int, un: str, plusieurs: str) -> str:
    return f"{n} {un if n == 1 else plusieurs}"


def criteres(depot: Mapping) -> list[dict]:
    """Les cinq critères de stabilité : `{code, libelle, rempli, precision}` (`LIBELLES_CRITERE`).

    Mêmes règles que `critere_manquant` : le premier critère non rempli est celui qu'il rend.
    `precision` : le tag (release publiée), « 4 commits », « 1 story ouverte », « rouge »,
    « en cours », « aucune CI », « pas de sprint-status.yaml » (critère des stories rempli faute
    de fichier) ; None sinon.
    """
    tag = depot.get("tag")
    commits = depot.get("commits") or {}
    comptes = [n for t, n in commits.items() if t not in _COMMITS_NEUTRES]
    commits_restants = any(comptes)  # même test que `critere_manquant`
    hors_neutres = sum(n for n in comptes if n > 0)
    stories = depot.get("stories_ouvertes", 0)
    ci = depot.get("ci", "aucune")
    precision_stories = None
    if stories > 0:
        precision_stories = _pluriel(stories, "story ouverte", "stories ouvertes")
    elif depot.get("sprint_status") == "absent":
        precision_stories = SANS_SPRINT_STATUS
    precision_commits = _pluriel(hors_neutres, "commit", "commits") if hors_neutres > 0 else None
    etats = {
        "release": (tag is not None, tag),
        "commits": (not commits_restants, precision_commits),
        "stories": (stories <= 0, precision_stories),
        "prs": (depot.get("prs_ouvertes", 0) <= 0, None),
        "ci": (ci == "verte", None if ci == "verte" else _PRECISIONS_CI.get(ci, "aucune CI")),
    }
    return [
        {"code": code, "libelle": libelle, "rempli": etats[code][0], "precision": etats[code][1]}
        for code, libelle in LIBELLES_CRITERE
    ]


def _statut_session(session: Mapping) -> dict:
    """Statut affiché d'une session, par les mêmes aides que `calculer_action`."""
    if _attente_valide(session) is not None:
        code = "attend"
    elif _finie(session):
        code = "finie"
    elif session.get("vivante"):
        code = "active"
    elif session.get("distante"):
        pc = session.get("pc") or "?"
        return {"code": "sans-nouvelles", "texte": f"sans nouvelles de {pc}"}
    else:
        code = "arretee"
    return {"code": code, "texte": TEXTES_STATUT[code]}


def _session_affichee(session: Mapping) -> dict:
    """Liste blanche : ni identifiant de session, ni dossier, ni pid (la reprise a sa route)."""
    return {
        "pc": session.get("pc") or "?",
        "statut": _statut_session(session),
        "debut": _texte_ou_none(session.get("debut")),
        "dernier_tour": _texte_ou_none(session.get("dernier_tour")),
        "fin": _texte_ou_none(session.get("fin")),
        "branche": _texte_ou_none(session.get("branche")),
        "note": _texte_ou_none(session.get("reprise")),
    }


def _depot_affiche(depot: Mapping) -> dict:
    """Liste blanche des faits du dépôt ; commits dans l'ordre de `TYPES_COMMIT`, zéros omis."""
    commits = depot["commits"]
    return {
        "tag": depot.get("tag"),
        "commits": {t: commits[t] for t in noyau_faits.TYPES_COMMIT if commits.get(t)},
        "prs_ouvertes": depot["prs_ouvertes"],
        "stories_ouvertes": depot["stories_ouvertes"],
        "ci": depot.get("ci"),
        "sprint_status": depot.get("sprint_status"),
    }


def detail(faits: Mapping, fuseau: tzinfo) -> dict:
    """Détail d'un projet pour le tiroir : `{sessions, depot, depot_de, criteres, pause}`.

    `sessions` : liste blanche (`_session_affichee`), triées par PC (casefold) puis la plus
    récente d'abord ; `depot` : faits du dépôt lisibles (`_depot_affiche`) ou None ; `criteres` :
    `criteres(depot)`, None sans faits de dépôt lisibles ; `pause` : `{"revue": …}` tiré de
    `faits["pause"]` (liste blanche, valeur telle quelle : attendu exact d'un réglage de pause,
    story 5.6) ou None. Les heures restent en ISO UTC : le web les rend dans le fuseau du
    navigateur. `fuseau` est vérifié comme dans `calculer_action`.
    """
    if not isinstance(fuseau, tzinfo):
        raise ValueError("detail : `fuseau` doit être un tzinfo")
    sessions = sorted(_sessions(faits), key=_plus_recent, reverse=True)
    sessions.sort(key=lambda s: str(s.get("pc") or "?").casefold())  # stable : PC, puis récente
    depot = faits.get("depot")
    lisible = _depot_lisible(depot)
    pause = faits.get("pause")
    return {
        "sessions": [_session_affichee(s) for s in sessions],
        "depot": _depot_affiche(depot) if lisible else None,
        "depot_de": faits.get("depot_de"),
        "criteres": criteres(depot) if lisible else None,
        "pause": {"revue": pause.get("revue")} if isinstance(pause, Mapping) else None,
    }


def _carte(nom: str, genre: str, verdict: Action, **en_plus: object) -> dict:
    return {
        "nom": nom, "genre": genre, "action": verdict.action, "raison": verdict.raison,
        "quoi": verdict.quoi, "type": verdict.type, "famille": verdict.famille,
        "vieillissante": verdict.vieillissante, **en_plus,
    }


def _par_nom(carte: Mapping) -> tuple[str, str]:
    return carte["nom"].casefold(), carte["nom"]


def _comptes(colonnes: Mapping[str, list[dict]], projets: list[dict]) -> dict:
    """Comptes de l'accueil, par projet (AD-11) : le web ne compte rien."""
    familles = Counter(p["famille"] for p in projets)
    pcs = Counter(str(p["raison"]["params"].get("pc") or "?") for p in colonnes[TOURNE])
    return {
        "actions": {a: len(colonnes[a]) for a in ACTIONS},
        "types": dict(sorted(Counter(c["type"] for c in colonnes[ATTEND]).items())),
        "familles": {f: familles[f] for f in FAMILLES if familles[f]},
        "pcs_tourne": dict(sorted(pcs.items())),
        "suivis": len(projets),
        "stables": familles["stable"],
    }


def assembler(
    faits_par_projet: Mapping[str, Mapping], maintenant: datetime, fuseau: tzinfo
) -> dict:
    """Cartes de projet, colonnes triées, chantiers et comptes (AD-11 amendé, story 4.8).

    Retourne `{"cartes", "colonnes", "chantiers", "comptes", "details"}` :
    - `cartes` : une carte par projet, triée par nom (casefold, puis nom brut) ;
    - `colonnes` : `{action: [cartes de projet]}` dans l'ordre de `ACTIONS` (toutes présentes),
      triées par `_cle_colonne` puis par nom ;
    - `chantiers` : une carte par chantier non vide, triée par action (ordre de `ACTIONS`) puis
      par nom (AD-11 : le tri est au noyau, story 4.7) ; elle porte l'action, la
      raison, le *quoi*, le type et la famille de son dépôt le plus urgent (à égalité, premier
      par nom) et la liste `projets` de ses dépôts ;
    - `comptes` : `actions`, `types` (cartes Attend), `familles` (ordre de `FAMILLES`, zéros
      omis), `pcs_tourne` (`{pc: n}`), `suivis` (projets) et `stables` ;
    - `details` : `{nom: detail(faits)}` par projet, à part des cartes (leur empreinte ne bouge
      pas quand seules les heures d'une session changent).
    `pc` et `depuis` : PC et horodatage de l'attente retenue (Attend) ; `pc` et `dernier_tour` :
    PC et date de la session la plus récente (À relancer, la clé de tri) ; None ailleurs.
    """
    projets: list[dict] = []
    cles: dict[int, tuple] = {}  # id(carte de projet) -> clé de colonne (hors rendu)
    for nom, faits in sorted(faits_par_projet.items(), key=lambda p: (p[0].casefold(), p[0])):
        verdict = calculer_action(faits, maintenant, fuseau)
        pc, depuis, tour = None, None, None
        if verdict.action == ATTEND:
            pc, depuis = _attente_retenue(faits)
        elif verdict.action == A_RELANCER:
            pc, tour = _dernier_tour(faits)
        carte = _carte(nom, "projet", verdict,
                       chantier=faits.get("chantier"), categorie=faits.get("categorie", "classé"),
                       clone_ici=faits.get("clone_ici", True), pcs=list(faits.get("pcs") or []),
                       depot_de=faits.get("depot_de"), pc=pc, depuis=depuis, dernier_tour=tour)
        cles[id(carte)] = _cle_colonne(verdict, faits, depuis)
        projets.append(carte)
    membres: dict[str, list[dict]] = {}
    for p in projets:
        if p["chantier"] is not None:
            membres.setdefault(p["chantier"], []).append(p)
    chantiers = []
    for nom, liste in membres.items():
        tete = min(liste, key=lambda p: ACTIONS.index(p["action"]))
        chantiers.append(
            {**tete, "nom": nom, "genre": "chantier", "chantier": nom, "projets": liste}
        )
    chantiers.sort(key=_par_nom)
    chantiers.sort(key=lambda c: ACTIONS.index(c["action"]))  # stable : action, puis nom

    def trier(action: str) -> list[dict]:
        # tris stables sur des cartes déjà rangées par nom : date (décroissante pour Tourne),
        # puis date absente en dernier
        dans = [c for c in projets if c["action"] == action]
        dans.sort(key=lambda c: cles[id(c)][1], reverse=action == TOURNE)
        return sorted(dans, key=lambda c: cles[id(c)][0])

    colonnes = {a: trier(a) for a in ACTIONS}
    return {
        "cartes": projets,
        "colonnes": colonnes,
        "chantiers": chantiers,
        "comptes": _comptes(colonnes, projets),
        "details": {
            c["nom"]: detail(faits_par_projet[c["nom"]], fuseau) for c in projets
        },
    }
