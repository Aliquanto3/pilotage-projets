"""Story 8.3 : schémas `etat_depot` et `decision` (C2)."""

import pytest

from pilotage.noyau import schemas
from pilotage.noyau.schemas import ErreurValidation, decision, etat_depot

SESSION = "11111111-1111-4111-8111-111111111111"


def _ligne(**champs):
    objet = {"date": "2026-11-14", "ecrit": "2026-11-14T10:00:00Z", "decision": "D",
             "session": SESSION}
    objet.update(champs)
    return {k: v for k, v in objet.items() if v is not None}


def _etat(**champs):
    objet = {"schema": 1, "projet": "projet-a", "pc": "pc-a", "session": SESSION,
             "ecrit": "2026-11-14T10:00:00Z", "etat": {"prochaine": "P"}, "decisions": []}
    objet.update(champs)
    return {k: v for k, v in objet.items() if v is not None}


def test_valides():
    schemas.valider("decision", _ligne(pourquoi="car"))
    schemas.valider("etat_depot", _etat())
    schemas.valider("etat_depot", _etat(etat=None, decisions=[_ligne()] * 5))
    pleine = {cle: "x" * borne for cle, borne in etat_depot.BORNES.items()}
    schemas.valider("etat_depot", _etat(etat=pleine))
    assert etat_depot.BORNES == {"prochaine": 300, "branche": 100, "blocages": 300,
                                 "explore": 300, "a_explorer": 300}
    assert (decision.BORNE_DECISION, etat_depot.MAX_DECISIONS) == (300, 5)


@pytest.mark.parametrize(
    ("champs", "motif"),
    [
        ({"autre": 1}, "champ inconnu : autre"),
        ({"session": None}, "champ manquant : session"),
        ({"date": "2026-11-13"}, "jour de `ecrit`"),
        ({"ecrit": "2026-11-14 10:00:00"}, "horodatage"),
        ({"ecrit": "2026-02-30T10:00:00Z", "date": "2026-02-30"}, "date impossible"),
        ({"decision": ""}, "decision : texte"),
        ({"decision": "a\nb"}, "decision : texte"),
        ({"decision": "a\rb"}, "decision : texte"),
        ({"decision": "a\x00b"}, "decision : texte"),
        ({"decision": " a"}, "decision : texte"),
        ({"decision": "x" * 301}, "decision : texte"),
        ({"pourquoi": "\x85"}, "pourquoi : texte"),
        ({"decision": 3}, "decision : texte"),
        ({"session": "../x"}, "session"),
    ],
)
def test_decision_refusee(champs, motif):
    with pytest.raises(ErreurValidation, match=motif):
        schemas.valider("decision", _ligne(**champs))


@pytest.mark.parametrize(
    ("champs", "motif"),
    [
        ({"x": 1}, "champ inconnu : x"),
        ({"decisions": None}, "champ manquant : decisions"),
        ({"schema": 2}, "schema 1"),
        ({"schema": True}, "schema 1"),
        ({"projet": "Projet A"}, "projet invalide"),
        ({"pc": "PC_A"}, "pc invalide"),
        ({"ecrit": "hier"}, "horodatage"),
        ({"etat": {"branche": "b"}}, "avec `prochaine`"),
        ({"etat": "P"}, "avec `prochaine`"),
        ({"etat": {"prochaine": "P", "autre": "x"}}, "etat : champ inconnu : autre"),
        ({"etat": {"prochaine": "P", "branche": "b" * 101}}, "etat.branche"),
        ({"etat": {"prochaine": "a\nb"}}, "etat.prochaine"),
        ({"decisions": [_ligne()] * 6}, "5 au plus"),
        ({"decisions": {}}, "5 au plus"),
        ({"decisions": [_ligne(decision="")]}, "decision : decision"),
    ],
)
def test_etat_refuse(champs, motif):
    with pytest.raises(ErreurValidation, match=motif):
        schemas.valider("etat_depot", _etat(**champs))


def test_non_objets_refuses():
    for nom in ("etat_depot", "decision"):
        with pytest.raises(ErreurValidation, match="un objet est attendu"):
            schemas.valider(nom, [])


def test_filtrer_etat_et_decision():
    racine = "C:/GitHub"
    assert etat_depot.filtrer_etat({"prochaine": "P", "explore": "C:/GitHub/a/b.md",
                                    "blocages": "ghp_x", "a_explorer": "/etc"}, racine) == {
        "prochaine": "P", "explore": "{{RACINE_GITHUB}}/a/b.md"}
    assert etat_depot.filtrer_etat({"prochaine": "AKIA0", "branche": "b"}, racine) is None
    assert etat_depot.filtrer_etat("P", racine) is None
    assert etat_depot.filtrer_etat({"prochaine": "  p  "}) == {"prochaine": "p"}
    assert etat_depot.filtrer_decision(_ligne(decision="sk-1")) is None
    assert etat_depot.filtrer_decision(_ligne(pourquoi="Bearer x")) == _ligne()
    assert etat_depot.filtrer_decision(_ligne(pourquoi="car")) == _ligne(pourquoi="car")
    assert etat_depot.filtrer_decision(None) is None
