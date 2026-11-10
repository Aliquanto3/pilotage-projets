"""Schémas `operation` et `message` (story 5.1, AD-9, AD-10)."""

import pytest

from pilotage.noyau import schemas
from pilotage.noyau.schemas import ErreurValidation

ID = "20261106T090500Z-0123abcd"


def message_op(**champs):
    objet = {"schema": 1, "id": ID, "verbe": "deposer_message", "projet": "demo", "texte": "Salut"}
    objet.update(champs)
    return objet


def patch_op(patch=None, **champs):
    objet = {
        "schema": 1, "id": ID, "verbe": "modifier_projets", "projet": "demo",
        "patch": {"pause": {"attendu": None, "voulu": "2026-12-01"}} if patch is None else patch,
    }
    objet.update(champs)
    return objet


def test_operations_valides():
    schemas.valider("operation", message_op())
    schemas.valider("operation", message_op(pc="pc-bureau"))
    schemas.valider("operation", patch_op({
        "chantier": {"attendu": None, "voulu": "Pilotage"},
        "exclu": {"attendu": True, "voulu": False},
        "pause": {"attendu": "2026-11-01", "voulu": None},
    }))


@pytest.mark.parametrize("objet, motif", [
    (message_op(verbe="supprimer"), "verbe deposer_message ou modifier_projets attendu"),
    (message_op(verbe=None), "verbe deposer_message ou modifier_projets attendu"),
    (message_op(extra=1), "champ inconnu : extra"),
    (message_op(patch={}), "champ inconnu : patch"),
    (patch_op(texte="x"), "champ inconnu : texte"),
    (patch_op(pc="pc-a"), "champ inconnu : pc"),
    ({k: v for k, v in message_op().items() if k != "texte"}, "champ manquant : texte"),
    ({k: v for k, v in patch_op().items() if k != "id"}, "champ manquant : id"),
    (message_op(schema=2), "schema 1 attendu"),
    (message_op(schema=True), "schema 1 attendu"),
    (message_op(id="2026-11-06-0123abcd"), "id"),
    (message_op(id="20261340T090500Z-0123abcd"), "id"),
    (message_op(projet="Demo"), "projet"),
    (message_op(projet=".."), "projet"),
    (message_op(projet="a/b"), "projet"),
    (message_op(pc="PC BUREAU"), "pc"),
    (message_op(texte=3), "message"),
    (patch_op(projet="'; calc; '"), "projet"),
])
def test_operation_refusee(objet, motif):
    with pytest.raises(ErreurValidation, match=motif):
        schemas.valider("operation", objet)


def test_message_borne_en_octets_utf8():
    emoji = "\U0001f600"  # 4 octets
    schemas.valider("operation", message_op(texte=emoji * 512))  # 2 048 octets
    with pytest.raises(ErreurValidation, match="2049 octets, 2048 au plus"):
        schemas.valider("operation", message_op(texte=emoji * 512 + "a"))
    with pytest.raises(ErreurValidation, match="substitut"):
        schemas.valider("operation", message_op(texte="\ud800"))


@pytest.mark.parametrize("patch, motif", [
    ({}, "patch = objet non vide"),
    ([], "patch = objet non vide"),
    ({"categorie": {"attendu": 1, "voulu": 2}}, "champ de patch inconnu : categorie"),
    ({"pause": {"voulu": "2026-12-01"}}, r"patch.pause = \{attendu, voulu\}"),
    ({"pause": {"attendu": None, "voulu": "2026-12-01", "x": 1}}, r"\{attendu, voulu\}"),
    ({"pause": {"attendu": None, "voulu": "2026-13-01"}}, "pause = date"),
    ({"pause": {"attendu": None, "voulu": "2026-12-01T10:00"}}, "pause = date"),
    ({"exclu": {"attendu": 0, "voulu": 1}}, "exclu = booléen"),
    ({"chantier": {"attendu": None, "voulu": ""}}, "chantier = nom"),
    ({"chantier": {"attendu": None, "voulu": " a"}}, "chantier = nom"),
    ({"chantier": {"attendu": None, "voulu": "a\nb"}}, "chantier = nom"),
    ({"chantier": {"attendu": None, "voulu": "x" * 101}}, "chantier = nom"),
    ({"exclu": {"attendu": True, "voulu": True}}, "patch.exclu sans changement"),
])
def test_patch_refuse(patch, motif):
    with pytest.raises(ErreurValidation, match=motif):
        schemas.valider("operation", patch_op(patch))


def test_chantier_de_100_caracteres_accepte():
    schemas.valider("operation", patch_op({"chantier": {"attendu": None, "voulu": "x" * 100}}))


def test_message_valide_et_refuse():
    message = {"schema": 1, "id": ID, "projet": "demo", "texte": "Salut", "pc": "pc-a"}
    schemas.valider("message", message)
    del message["pc"]
    schemas.valider("message", message)
    for objet, motif in [
        ({**message, "verbe": "deposer_message"}, "champ inconnu : verbe"),
        ({k: v for k, v in message.items() if k != "projet"}, "champ manquant : projet"),
        ({**message, "schema": 2}, "schema 1 attendu"),
        ({**message, "texte": "é" * 1025}, "2050 octets"),
        ([], "un objet est attendu"),
    ]:
        with pytest.raises(ErreurValidation, match=motif):
            schemas.valider("message", objet)
