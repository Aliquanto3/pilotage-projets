"""Tour de conversation : `Stop` (écrivain de fin de tour, AD-3) et `UserPromptSubmit`."""

from pilotage import chemins
from pilotage.hooks import _commun
from pilotage.noyau import heuristique, marqueur, texte

ESSAIS_STOP = 1
ESSAIS_PROMPT = 3  # M1 : SessionEnd et UserPromptSubmit réessaient trois fois 20 ms
ESSAIS_NOTIFICATION = ESSAIS_PROMPT  # une permission perdue derrière un Stop ne revient pas
BLANCS_INITIAUX = " \t\r\n\ufeff"  # BOM ou blancs avant la balise
DEBUT_NOTIFICATION = "<task-notification>"  # fin d'un sous-agent, injectée comme un prompt (A1)


def fin_de_tour(payload: dict) -> None:
    """Pose ou efface l'attente et la note de reprise d'après `last_assistant_message` seul.

    Marqueur d'attente valide : `attente = {type?, quoi, depuis}` et `statut=attente` ; sinon une
    attente précédente est effacée (`statut=active`). Note de reprise : filtrée et bornée, ou
    supprimée si suspecte ; sans marqueur de reprise, la note précédente reste. `transcript_path`
    n'est jamais lu. Retrouvé par l'id de session ; un état `finie` n'est pas touché.
    """
    cle = _commun.session_seule(payload)
    if cle is None:
        return
    pc, session = cle
    etats = _commun.etats_de_session(pc, session)
    if not etats:
        return
    trouves = marqueur.lire(payload.get("last_assistant_message"))
    secours = None if trouves.attente else heuristique.depuis_stop(
        payload.get("last_assistant_message")
    )
    racine = str(chemins.racine_github())
    with _commun.verrou(session, ESSAIS_STOP):
        maintenant = _commun.maintenant()
        for chemin in etats:
            etat = _commun.lire_etat(chemin)
            if etat is None or etat["statut"] == "finie":
                continue
            etat["dernier_tour"] = maintenant
            if trouves.attente is None:
                attente = etat.get("attente")
                if heuristique.source_de(attente) in heuristique.MILIEU_DE_TOUR:
                    etat.pop("attente", None)  # dialogue de milieu de tour : résolu
                    etat["statut"] = "active"
                existante = _existante(etat)
                if existante is None:
                    etat.pop("attente", None)
                    etat["statut"] = "active"
                if secours is not None and heuristique.choisir(existante, secours) is secours:
                    _poser_secours(etat, secours, racine, maintenant)
            else:
                genre, quoi = trouves.attente
                attente = {} if genre is None else {"type": genre}
                attente["quoi"] = texte.nettoyer(quoi, texte.BORNE_QUOI, racine)
                precedente = etat.get("attente")
                meme = isinstance(precedente, dict) and all(
                    precedente.get(k) == attente.get(k) for k in ("type", "quoi")
                )
                # La même attente réémise garde son heure de départ (2.6 lit `depuis`).
                attente["depuis"] = precedente.get("depuis", maintenant) if meme else maintenant
                etat["attente"] = attente
                etat["statut"] = "attente"
            if trouves.reprise is not None:
                note = texte.nettoyer(trouves.reprise, texte.BORNE_NOTE, racine)
                if note:
                    etat["reprise"] = note
                else:
                    etat.pop("reprise", None)
            _commun.ecrire_etat(chemin, etat)


def _poser_secours(etat: dict, detection, racine: str, maintenant: str) -> None:
    """Attente de l'heuristique : sans type, avec sa `source`, *quoi* filtré et borné (vide si rien
    d'exploitable). L'appelant a vérifié (`heuristique.choisir`) qu'elle l'emporte sur l'existante.
    """
    quoi = texte.nettoyer(detection.quoi, texte.BORNE_QUOI, racine)
    etat["attente"] = {"quoi": quoi, "depuis": maintenant, "source": detection.source}
    etat["statut"] = "attente"


def notification(payload: dict) -> None:
    """`Notification` : permission native ou `AskUserQuestion` (heuristique, AD-2).

    Écrit une attente sans type seulement si aucune attente de priorité égale ou supérieure n'existe
    (`heuristique.choisir`, AD-3) : elle remplace une question finale ou une permission moins
    prioritaire ; n'efface rien d'autre. Les autres `notification_type`,
    un sous-agent (`agent_id`) et un état `finie` sont sans effet.
    """
    cle = _commun.session_seule(payload)
    if cle is None:
        return
    detection = heuristique.depuis_notification(
        payload.get("notification_type"), payload.get("message")
    )
    if detection is None:
        return
    pc, session = cle
    etats = _commun.etats_de_session(pc, session)
    if not etats:
        return
    racine = str(chemins.racine_github())
    with _commun.verrou(session, ESSAIS_NOTIFICATION):
        maintenant = _commun.maintenant()
        for chemin in etats:
            etat = _commun.lire_etat(chemin)
            if etat is None or etat["statut"] == "finie":
                continue
            if heuristique.choisir(_existante(etat), detection) is not detection:
                continue
            _poser_secours(etat, detection, racine, maintenant)
            _commun.ecrire_etat(chemin, etat)


def _existante(etat: dict) -> heuristique.Detection | None:
    """L'attente en cours comme détection (pour `heuristique.choisir`), ou `None` si elle ne compte
    plus (absente, ou l'utilisateur a répondu depuis : `_attente_gardee`)."""
    if not _attente_gardee(etat):
        return None
    attente = etat["attente"]
    return heuristique.Detection(heuristique.source_de(attente), attente.get("quoi", ""))


def _attente_gardee(etat: dict) -> bool:
    """Vrai si l'attente doit survivre à un tour sans marqueur : l'utilisateur n'a pas écrit
    depuis.

    Un tour sans prompt de l'utilisateur (fin d'un sous-agent, `<task-notification>`, ignorée par
    `prompt_utilisateur`, A1) ne doit pas effacer une question restée sans réponse.
    L'attente n'est effacée que si `dernier_prompt` est postérieur à `depuis`. À la même seconde,
    le prompt a précédé la question (sinon `prompt_utilisateur` l'aurait déjà effacée) : gardée.
    """
    attente = etat.get("attente")
    if not isinstance(attente, dict) or etat.get("statut") != "attente":
        return False
    dernier_prompt = etat.get("dernier_prompt")
    return not isinstance(dernier_prompt, str) or dernier_prompt <= attente.get("depuis", "")


def prompt_utilisateur(payload: dict) -> None:
    """Efface l'attente, remet `statut=active` et date `dernier_prompt` (jamais le texte).

    Sans effet pour un sous-agent (`agent_id`) et pour un prompt qui est la fin d'un sous-agent
    (`<task-notification>…`). Un état `finie` n'est pas touché.
    """
    cle = _commun.session_seule(payload)
    if cle is None:
        return
    prompt = payload.get("prompt")
    if isinstance(prompt, str) and prompt.lstrip(BLANCS_INITIAUX).startswith(DEBUT_NOTIFICATION):
        return
    pc, session = cle
    etats = _commun.etats_de_session(pc, session)
    if not etats:
        return
    with _commun.verrou(session, ESSAIS_PROMPT):
        maintenant = _commun.maintenant()
        for chemin in etats:
            etat = _commun.lire_etat(chemin)
            if etat is None or etat["statut"] == "finie":
                continue
            etat.pop("attente", None)
            etat.update(statut="active", dernier_prompt=maintenant)
            _commun.ecrire_etat(chemin, etat)
