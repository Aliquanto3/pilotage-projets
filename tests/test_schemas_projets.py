from datetime import date

import pytest

from pilotage.noyau import schemas
from pilotage.noyau.schemas import ErreurValidation

VALIDE_PROJETS = {
    "schema": 1,
    "chantiers": {"c": {"projets": ["a", "b"]}},
    "dependances": ["a ← b"],
    "exclus": ["x"],
    "pauses": {"b": {"revue": date(2026, 12, 1)}},
}


def test_projets_valide():
    schemas.valider("projets", VALIDE_PROJETS)
    schemas.valider("projets", {"schema": 1, "pauses": {"b": {"revue": "2026-12-01"}}})
    vide = {"schema": 1, "chantiers": None, "exclus": None, "dependances": None, "pauses": None}
    schemas.valider("projets", vide)
    schemas.valider("projets", {"schema": 1, "chantiers": {"c": None, "d": {"projets": None}}})


@pytest.mark.parametrize(
    ("objet", "motif"),
    [
        ([], "un objet est attendu"),
        ({}, "champ manquant : schema"),
        ({"schema": 2}, "schema 1 attendu"),
        ({"schema": True}, "schema 1 attendu"),
        ({"schema": 1.0}, "schema 1 attendu"),
        ({"schema": 1, "zzz": 1}, "champ inconnu : zzz"),
        ({"schema": 1, "chantiers": {"c": {"projets": ["a"], "x": 1}}}, "champ inconnu : x"),
        ({"schema": 1, "chantiers": {"": {}}}, "nom de chantier"),
        ({"schema": 1, "chantiers": {"c": {"projets": ["A"]}}}, "projet invalide"),
        ({"schema": 1, "chantiers": {"c": {"projets": ["a"]}, "d": {"projets": ["a"]}}},
         "a déjà dans le chantier c"),
        ({"schema": 1, "chantiers": {"c": {"projets": ["a"]}}, "exclus": ["a"]},
         "a est aussi dans un chantier"),
        ({"schema": 1, "exclus": "a"}, "une liste est attendue"),
        ({"schema": 1, "dependances": ["a <- b"]}, "forme « A ← B »"),
        ({"schema": 1, "dependances": [3]}, "forme « A ← B »"),
        ({"schema": 1, "dependances": ["a ← a"]}, "a ne dépend pas de lui-même"),
        ({"schema": 1, "pauses": {"a": {}}}, "date de revue manquante"),
        ({"schema": 1, "pauses": {"a": {"revue": "2026-13-01"}}}, "date AAAA-MM-JJ"),
        ({"schema": 1, "pauses": {"a": {"revue": "demain"}}}, "date AAAA-MM-JJ"),
        ({"schema": 1, "pauses": {"a": {"revue": 5}}}, "date AAAA-MM-JJ"),
        ({"schema": 1, "pauses": {"a": {"revue": "2026-12-01", "x": 1}}}, "champ inconnu : x"),
    ],
)
def test_projets_refuse(objet, motif):
    with pytest.raises(ErreurValidation, match=motif):
        schemas.valider("projets", objet)


def test_table_dossiers_valide():
    schemas.valider("table_dossiers", {"schema": 1, "dossiers": {"a/b": "p", "c": "q"}})
    schemas.valider("table_dossiers", {"schema": 1, "dossiers": {}})


@pytest.mark.parametrize(
    ("objet", "motif"),
    [
        ([], "un objet est attendu"),
        ({"schema": 1, "dossiers": {}, "extra": 1}, "champ inconnu : extra"),
        ({"schema": 1}, "champ manquant : dossiers"),
        ({"schema": 2, "dossiers": {}}, "schema 1 attendu"),
        ({"schema": 1, "dossiers": []}, "dossiers doit être un objet"),
        ({"schema": 1, "dossiers": {"/abs": "p"}}, "dossier relatif invalide"),
        ({"schema": 1, "dossiers": {"a\\b": "p"}}, "dossier relatif invalide"),
        ({"schema": 1, "dossiers": {"C:/x": "p"}}, "dossier relatif invalide"),
        ({"schema": 1, "dossiers": {"../x": "p"}}, "dossier relatif invalide"),
        ({"schema": 1, "dossiers": {"a/": "p"}}, "dossier relatif invalide"),
        ({"schema": 1, "dossiers": {"": "p"}}, "clé de type chaîne"),
        ({"schema": 1, "dossiers": {"Mon-Depot": "p"}}, "clé non normalisée"),
        ({"schema": 1, "dossiers": {"a": "P"}}, "projet invalide"),
        ({"schema": 1, "dossiers": {"a": 3}}, "projet"),
    ],
)
def test_table_dossiers_refuse(objet, motif):
    with pytest.raises(ErreurValidation, match=motif):
        schemas.valider("table_dossiers", objet)
