"""Validateur `session` (L1) : liste blanche de l'état d'une session principale."""

import pytest

from pilotage.noyau import schemas
from pilotage.noyau.schemas import ErreurValidation, session

DEPUIS = "2026-11-06T10:30:00Z"
SESSION = "0123abcd-0000-4000-8000-00000000abcd"


def _etat(**champs) -> dict:
    etat = {
        "schema": 1, "projet": "pilotage-projets", "pc": "pc-1", "session": SESSION,
        "pid": 1234, "pid_cree": "134070000000000000", "dossier": "_worktrees/pilotage-2-2",
        "branche": "story/2-2", "debut": "2026-11-06T10:00:00Z", "statut": "active",
    }
    etat.update(champs)
    return etat


def test_registre():
    assert schemas.REGISTRE["session"] is session.valider


@pytest.mark.parametrize(
    "etat",
    [
        _etat(),
        _etat(pid_cree=None, branche=None),
        _etat(statut="finie", fin="2026-11-06T11:00:00Z", dernier_tour="2026-11-06T10:59:00Z"),
        _etat(statut="attente", attente={"type": "choix", "quoi": "é" * 200, "depuis": DEPUIS}),
        _etat(statut="attente", attente={"quoi": "", "depuis": DEPUIS}),
        *[
            _etat(statut="attente", attente={"quoi": "q", "depuis": DEPUIS, "source": s})
            for s in ("marqueur", "askuserquestion", "permission", "question")
        ],
        _etat(dernier_prompt="2026-11-06T10:31:00Z"),
        _etat(attente=None, reprise="r" * 300),
        _etat(reprise=None),
    ],
)
def test_etats_valides(etat):
    schemas.valider("session", etat)


def _sans(nom: str) -> dict:
    etat = _etat()
    del etat[nom]
    return etat


@pytest.mark.parametrize(
    ("etat", "motif"),
    [
        ([], "un objet est attendu"),
        (_etat(prompt="x"), "champ inconnu : prompt"),
        (_sans("branche"), "champ manquant : branche"),
        (_sans("pid_cree"), "champ manquant : pid_cree"),
        (_etat(schema=2), "schema 1 attendu"),
        (_etat(schema=True), "schema 1 attendu"),
        (_etat(projet="Pilotage"), "projet invalide"),
        (_etat(pc="PC1"), "pc invalide"),
        (_etat(session="session-0001"), "session invalide"),
        (_etat(pid=0), "pid : entier positif"),
        (_etat(pid=True), "pid : entier positif"),
        (_etat(pid="12"), "pid : entier positif"),
        (_etat(pid_cree=134070000000000000), "pid_cree : FILETIME"),
        (_etat(pid_cree="0"), "pid_cree : FILETIME"),
        (_etat(pid_cree="1" * 21), "pid_cree : FILETIME"),
        (_etat(dossier="C:/x"), "dossier : relatif"),
        (_etat(dossier="a/../b"), "dossier : relatif"),
        (_etat(dossier="A/b"), "dossier : relatif"),
        (_etat(dossier="a/"), "dossier : relatif"),
        (_etat(dossier=""), "dossier : chaîne non vide"),
        (_etat(branche=""), "branche : nom"),
        (_etat(branche="a\nb"), "branche : nom"),
        (_etat(branche="x" * 256), "branche : nom"),
        (_etat(branche="ghp_abc"), "branche : nom"),
        (_etat(debut="2026-11-06 10:00:00"), "debut : horodatage"),
        (_etat(debut="2026-02-30T10:00:00Z"), "debut : date impossible"),
        (_etat(fin="2026-11-06T10:00:00+01:00"), "fin : horodatage"),
        (_etat(statut="morte"), "statut : active, attente, finie"),
        (_etat(statut="finie"), "statut finie sans fin"),
        (_etat(statut="attente"), "statut attente sans attente"),
        (_etat(attente={"type": "x"}), r"attente : objet \{type\?, quoi, depuis, source\?\}"),
        (_etat(attente={"quoi": "q", "depuis": DEPUIS, "source": "llm"}), "attente.source"),
        (_etat(attente={"quoi": "q", "depuis": DEPUIS, "source": ["x"]}), "attente.source"),
        (_etat(attente={"quoi": "q"}), r"attente : objet"),
        (_etat(attente={"quoi": "q", "depuis": DEPUIS, "x": 1}), "attente : objet"),
        (_etat(attente={"quoi": "q", "depuis": "hier"}), "attente.depuis : horodatage"),
        (_etat(dernier_prompt="hier"), "dernier_prompt : horodatage"),
        (_etat(dernier_prompt="texte du prompt"), "dernier_prompt : horodatage"),
        (_etat(attente={"type": "X", "quoi": "", "depuis": DEPUIS}), "attente.type"),
        (
            _etat(attente={"type": "x", "quoi": "q" * 201, "depuis": DEPUIS}),
            "attente.quoi : 201 points de code",
        ),
        (_etat(reprise="r" * 301), "reprise : note : 301 points de code"),
    ],
)
def test_etats_refuses(etat, motif):
    with pytest.raises(ErreurValidation, match=f"^session : .*{motif}"):
        session.valider(etat)
