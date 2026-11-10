"""Texte des alertes rédigé par le noyau, `alertes.json` sans texte (M8, story 4.2)."""

import pytest

from pilotage.noyau import alertes, schemas
from pilotage.noyau.schemas import ErreurValidation
from pilotage.scan import cli as scan_cli
from pilotage.scan import donnees, faits_gh, inventaire, sessions


def test_texte_rempli_par_les_params():
    alerte = {"code": "faits-github-non-relus", "params": {"projet": "demo"}}
    assert alertes.texte(alerte) == "Faits GitHub non relus : demo."


def test_catalogue_egal_aux_messages_des_ecrivains():
    """Chaque code écrit par le scan est rédigé exactement comme avant M8."""
    emises = [
        {"code": scan_cli.ALERTE_ECHEC, "message": scan_cli.MESSAGE_ECHEC},
        {"code": scan_cli.ALERTE_ILLISIBLE, "message": scan_cli.MESSAGE_ILLISIBLE},
        {"code": sessions.ALERTE_ETATS, "message": sessions.MESSAGE_ETATS},
        {"code": sessions.ALERTE_CLAUDE, "message": sessions.MESSAGE_CLAUDE},
        {"code": donnees.ALERTE_ILLISIBLE, "message": donnees.MESSAGE_ILLISIBLE},
        inventaire._invalide("YAML invalide"),
        inventaire._alerte(inventaire.ALERTE_ILLISIBLE, "projets.yaml illisible"),
        inventaire._alerte(
            inventaire.ALERTE_VERSION_RECENTE,
            "PC en version plus récente : projets.yaml en lecture seule",
        ),
        inventaire._alerte(
            inventaire.ALERTE_DEPOT_IGNORE, "dépôt ignoré : nom de projet invalide"
        ),
        inventaire._alerte(
            inventaire.ALERTE_DOSSIER_CASSE,
            "deux dossiers ne diffèrent que par la casse : le second est ignoré",
        ),
        faits_gh.alerte_non_relus("p"),
        donnees._alerte_version("pc-a", 2),
        donnees._alerte_version("pc-a", 0),
    ]
    for alerte in emises:
        sans_message = {c: v for c, v in alerte.items() if c != "message"}
        sans_message.setdefault("params", {})
        assert alertes.texte(sans_message) == alerte["message"], alerte["code"]


@pytest.mark.parametrize("alerte,attendu", [
    ({"code": "projets-invalide", "message": "ancien"}, "ancien"),  # forme d'avant M8
    ({"code": "projets-invalide", "params": {}, "message": "ancien"}, "ancien"),  # param manquant
    ({"code": "inconnu", "params": {}}, "inconnu"),
    ({"code": "scan-echec", "params": {"inutile": 1}}, "Scan en échec"),
])
def test_repli_sur_le_message_puis_le_code(alerte, attendu):
    assert alertes.texte(alerte) == attendu


def test_schema_accepte_params_texte_et_entier_et_forme_ancienne():
    schemas.valider("alertes", {"schema": 1, "alertes": [
        {"source": "scan", "code": "a", "params": {}},
        {"source": "scan", "code": "a", "params": {"projet": "é" * 300, "n": 2}},
        {"source": "sync", "code": "a", "message": "m" * 300},
    ]})


@pytest.mark.parametrize("alerte", [
    {"source": "scan", "code": "a", "params": []},
    {"source": "scan", "code": "a", "params": {"X": "v"}},
    {"source": "scan", "code": "a", "params": {"p": "é" * 301}},
    {"source": "scan", "code": "a", "params": {"p": True}},
    {"source": "scan", "code": "a", "params": {"p": ["x"]}},
    {"source": "scan", "code": "a", "params": {}, "message": "m"},
    {"source": "scan", "code": "a"},
    {"source": "web", "code": "a", "params": {}},
])
def test_schema_refuse(alerte):
    with pytest.raises(ErreurValidation):
        schemas.valider("alertes", {"schema": 1, "alertes": [alerte]})
