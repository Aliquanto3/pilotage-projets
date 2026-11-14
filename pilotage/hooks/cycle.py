"""Cycle de vie d'une session principale : `SessionStart` crée l'état, `SessionEnd` le close."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from pilotage import chemins
from pilotage.hooks import _commun, boite, note
from pilotage.noyau import cadrage

ESSAIS_SESSION_START = 1
ESSAIS_SESSION_END = 3  # M1 : SessionEnd (et UserPromptSubmit) réessaient trois fois 20 ms
NOM_REGLE = "regle-marqueur.md"
BORNE_REGLE = 8192  # octets ; la règle livrée en fait ~2 Ko
# Plafond de `additionalContext`, en unités UTF-16 (longueur mesurée par Claude Code), story 8.1.
BORNE_CONTEXTE = 10_000


def lire_regle() -> str | None:
    """Texte de `regle-marqueur.md` (racine installée), ou `None` (erreur journalisée).

    Lecture bornée à `BORNE_REGLE` octets, UTF-8 strict (BOM retiré) ; illisible, trop long, vide
    ou non UTF-8 : `None`, jamais d'exception (AD-8, AD-13). Absent : `None` sans journal, car
    tant que l'installation (story 2.7) ne copie pas la règle, chaque `SessionStart` l'écrirait.
    """
    try:
        with open(chemins.racine_installation() / NOM_REGLE, "rb") as fichier:
            brut = fichier.read(BORNE_REGLE + 1)
        if len(brut) > BORNE_REGLE:
            raise ValueError("règle trop longue")
        texte = brut.decode("utf-8-sig")
    except FileNotFoundError:
        return None
    except BaseException as erreur:  # noqa: BLE001 - la session ne doit jamais être bloquée
        _commun.journaliser("SessionStart", erreur)
        return None
    return texte if texte.strip() else None


def _nonce(interdit: str = "") -> str:
    """Nonce imprévisible tiré à chaque injection, distinct de `interdit`.

    `secrets.token_hex` lit aussi `os.urandom`, mais son import coûte ~7 ms à `SessionStart`
    (NFR1)."""
    while True:
        nonce = os.urandom(16).hex()
        if nonce != interdit:
            return nonce


def _bloc_note(ctx, nonce: str) -> str:
    """Bloc cadré de la dernière note de reprise (story 8.1) ; aucune ou erreur : `""`.

    Identifiant propre au bloc (`AAAAMMJJTHHMMSSZ-<8 hex>`, heure UTC courante) et nonce propre :
    ni l'un ni l'autre ne vient des messages."""
    try:
        retenue = note.derniere_note(ctx)
        if retenue is None:
            return ""
        identifiant = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{os.urandom(4).hex()}"
        return cadrage.cadrer_note(
            retenue.texte, nonce, pc=retenue.pc, session=retenue.session,
            dernier_tour=retenue.dernier_tour, identifiant=identifiant,
        )
    except BaseException as erreur:  # noqa: BLE001 - règle et messages émis malgré tout
        _commun.journaliser("SessionStart", erreur)
        return ""


def _bloc_messages(ctx, nonce: str, borne_unites: int) -> tuple[str, list[str]]:
    """Bloc cadré des messages à remettre et leurs ids ; erreur journalisée : aucun (AD-13)."""
    try:
        return cadrage.cadrer_messages(
            boite.a_injecter(ctx), nonce, chemins.utilisateur(), borne_unites=borne_unites
        )
    except BaseException as erreur:  # noqa: BLE001 - la règle doit être émise malgré tout
        _commun.journaliser("SessionStart", erreur)
        return "", []


def _assembler(blocs: list[str]) -> str:
    """Blocs séparés par une ligne vide ; un bloc seul est rendu tel quel (story 2.5)."""
    if len(blocs) == 1:
        return blocs[0]
    return "\n\n".join(bloc.rstrip("\n") for bloc in blocs)


def _unites_avec_suite(blocs: list[str]) -> int:
    """Unités UTF-16 occupées par `blocs` suivis d'un bloc de plus (séparateur compris)."""
    if not blocs:
        return 0
    return cadrage.unites_utf16("\n\n".join(bloc.rstrip("\n") for bloc in blocs) + "\n\n")


def injecter(ctx) -> None:
    """Seule écriture sur stdout des hooks : un objet `hookSpecificOutput.additionalContext`
    (AD-13), règle du marqueur, dernière note de reprise, puis messages ; acquittements après
    l'émission seulement.

    Plafond `BORNE_CONTEXTE` (unités UTF-16) ; priorité règle, note, messages : la note est omise
    si elle ne tient pas après la règle, les messages reçoivent le reste et ceux qui ne tiennent
    pas ne sont pas acquittés. Sans note : sortie de la story 5.3 ; sans note ni message : la
    règle seule, à l'octet près (story 2.5). Rien à dire : rien.
    """
    regle = lire_regle()
    blocs = [regle] if regle else []
    nonce_note = _nonce()
    bloc_note = _bloc_note(ctx, nonce_note)
    if bloc_note and _unites_avec_suite(blocs) + cadrage.unites_utf16(bloc_note) <= (
        BORNE_CONTEXTE
    ):
        blocs.append(bloc_note)
    reste = BORNE_CONTEXTE - _unites_avec_suite(blocs)
    messages, retenus = _bloc_messages(ctx, _nonce(nonce_note), reste)
    if messages:
        blocs.append(messages)
    if not blocs:
        return
    contexte = _assembler(blocs)
    sortie = {
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": contexte}
    }
    try:
        _commun.emettre(json.dumps(sortie, ensure_ascii=False).encode("utf-8"))
    except BaseException as erreur:  # noqa: BLE001 - émission ratée : rien acquitté, sync lancée
        _commun.journaliser("SessionStart", erreur)
        return
    try:
        boite.acquitter(ctx, retenus)
    except BaseException as erreur:  # noqa: BLE001 - non acquitté : remis à la session suivante
        _commun.journaliser("SessionStart", erreur)


def demarrer(payload: dict) -> None:
    """Crée `attente/etat/<projet>/<pc>/<session>.json` (ou le réactive), puis injecte la règle
    et les messages non acquittés de ce PC (story 5.3).

    État existant (`resume`, et `clear`/`compact` supposés) : `pid`, `pid_cree`, `branche` mis à
    jour, `statut=active`, `fin` retirée ; `debut` conservé. La règle est émise pour toute
    `source`, même si l'état n'a pu être écrit (l'erreur est alors journalisée) ; rien pour un
    sous-agent ni un dossier non suivi. État écrit : synchro détachée lancée (story 3.6).
    """
    ctx = _commun.contexte(payload)
    if ctx is None:
        return
    try:
        _ecrire_etat_de_demarrage(ctx)
    finally:
        injecter(ctx)
    _commun.declencher_sync("SessionStart")  # après l'état écrit et la règle émise (AD-6)


def _ecrire_etat_de_demarrage(ctx) -> None:
    pid = _commun.pid_parent()
    pid_cree = _commun.heure_creation(pid)
    branche = _commun.lire_branche(Path(ctx.cwd))
    chemin = _commun.chemin_etat(ctx)
    with _commun.verrou(ctx.session, ESSAIS_SESSION_START):
        etat = _commun.lire_etat(chemin)
        if etat is None:
            etat = {
                "schema": 1,
                "projet": ctx.projet,
                "pc": ctx.pc,
                "session": ctx.session,
                "pid": pid,
                "pid_cree": pid_cree,
                "dossier": ctx.dossier,
                "branche": branche,
                "debut": _commun.maintenant(),
                "statut": "active",
            }
        else:
            etat.pop("fin", None)
            etat.update(pid=pid, pid_cree=pid_cree, branche=branche, statut="active")
        _commun.ecrire_etat(chemin, etat)


def terminer(payload: dict) -> None:
    """Pose `fin` et `statut=finie` sur les états existants de la session ; sans état, rien.

    Retrouvés par l'id de session, pas par le `cwd` (il a pu changer depuis `SessionStart`) ;
    une session reprise sous un autre projet est close partout. Puis synchro détachée (3.6).
    """
    cle = _commun.session_seule(payload)
    if cle is None:
        return
    pc, session = cle
    etats = _commun.etats_de_session(pc, session)
    if not etats:
        return  # rien à clore : ni verrou ni écriture
    with _commun.verrou(session, ESSAIS_SESSION_END):
        fin = _commun.maintenant()
        for chemin in etats:  # relu sous verrou : un état supprimé entre-temps rend `None`
            etat = _commun.lire_etat(chemin)
            if etat is None:
                continue
            etat.update(fin=fin, statut="finie")
            _commun.ecrire_etat(chemin, etat)
    _commun.declencher_sync("SessionEnd")  # état final clos : la synchro le recopie (AD-6)
