"""`GET /api/operations` : opérations en attente et état des messages (story 5.2, AD-14)."""

import json
import os
import subprocess
from datetime import UTC, datetime

import pytest

from pilotage import chemins
from pilotage.serveur import routes, suivi
from tests.test_serveur import _demarrer, _json, requete
from tests.test_serveur_etat import empreinte

ID1 = "20261106T101500Z-0a1b2c3d"
ID2 = "20261106T101600Z-0a1b2c3e"
ID3 = "20261106T101700Z-0a1b2c3f"


def heure_locale(iso):
    return datetime.fromisoformat(iso).astimezone().strftime("%H:%M")


def ecrire(chemin, objet):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet, ensure_ascii=False), "utf-8")


def operation_message(id_, projet="demo", texte="bonjour", **en_plus):
    objet = {"schema": 1, "id": id_, "verbe": "deposer_message", "projet": projet,
             "texte": texte, **en_plus}
    ecrire(chemins.operations() / f"{id_}.json", objet)
    return objet


def message_depose(id_, projet="demo", texte="bonjour"):
    ecrire(chemins.donnees() / "boite" / projet / f"{id_}.json",
           {"schema": 1, "id": id_, "projet": projet, "texte": texte})


def acquitter(racine, id_, pc, heure, projet="demo"):
    ecrire(racine / "boite" / projet / f"{id_}.lu.{pc}",
           {"schema": 1, "session": "11111111-2222-3333-4444-555555555555", "pc": pc,
            "heure": heure})


def lire():
    return suivi.operations({}, b"").donnees


def test_rien_en_attente():
    assert lire() == {"operations": [], "messages": []}


def test_trois_etats_des_messages():
    operation_message(ID1, texte="en attente", pc="pc-autre")
    message_depose(ID2, texte="déposé")
    message_depose(ID3, texte="lu")
    acquitter(chemins.donnees(), ID3, "pc-b", "2026-11-06T13:05:00Z")
    acquitter(chemins.attente(), ID3, "pc-a", "2026-11-06T12:30:00+00:00")
    donnees = lire()
    assert donnees["operations"] == [
        {"id": ID1, "verbe": "deposer_message", "projet": "demo", "pc": "pc-autre"},
    ]
    a, b = heure_locale("2026-11-06T12:30:00+00:00"), heure_locale("2026-11-06T13:05:00+00:00")
    assert donnees["messages"] == [
        {"id": ID1, "projet": "demo", "pc": "pc-autre", "texte": "en attente",
         "etat": "en-attente", "lectures": [], "libelle": "en attente de synchro"},
        {"id": ID2, "projet": "demo", "pc": None, "texte": "déposé", "etat": "depose",
         "lectures": [], "libelle": "déposé"},
        {"id": ID3, "projet": "demo", "pc": None, "texte": "lu", "etat": "lu",
         "lectures": [{"pc": "pc-a", "heure": a}, {"pc": "pc-b", "heure": b}],
         "libelle": f"lu par pc-a à {a}, lu par pc-b à {b}"},
    ]


def test_operation_appliquee_mais_pas_encore_nettoyee_compte_comme_deposee():
    operation_message(ID1)
    message_depose(ID1)
    (message,) = lire()["messages"]
    assert (message["etat"], message["libelle"]) == ("depose", "déposé")


def test_message_en_attente_lu_localement():
    operation_message(ID1)
    acquitter(chemins.attente(), ID1, "pc-test", "pas une heure")
    (message,) = lire()["messages"]
    assert message["etat"] == "lu" and message["libelle"] == "lu par pc-test"


def test_patch_rendu_avec_son_projet():
    patch = {"exclu": {"attendu": False, "voulu": True}}
    ecrire(chemins.operations() / f"{ID1}.json", {"schema": 1, "id": ID1,
           "verbe": "modifier_projets", "projet": "outil", "patch": patch})
    assert lire() == {"operations": [{"id": ID1, "verbe": "modifier_projets",
                                      "projet": "outil", "patch": patch}], "messages": []}


def test_fichiers_invalides_ignores():
    operation_message(ID1)
    ecrire(chemins.operations() / f"{ID2}.json", {"schema": 1, "id": ID3, "verbe": "x"})
    ecrire(chemins.operations() / "pas-un-id.json", {"schema": 1})
    (chemins.operations() / f"{ID3}.json").write_text("{", "utf-8")
    (chemins.operations() / f"{ID3}.json.123.ab.tmp").write_text("{}", "utf-8")
    message_depose(ID2, projet="autre")
    ecrire(chemins.donnees() / "boite" / "Mauvais" / f"{ID2}.json", {})
    ecrire(chemins.donnees() / "boite" / "demo" / f"{ID3}.json",
           {"schema": 1, "id": ID1, "projet": "demo", "texte": "id différent du nom"})
    acquitter(chemins.donnees(), ID1, "PC_MAUVAIS", "2026-11-06T13:05:00Z")
    donnees = lire()
    assert [o["id"] for o in donnees["operations"]] == [ID1]
    assert [(m["id"], m["projet"], m["etat"]) for m in donnees["messages"]] == [
        (ID1, "demo", "en-attente"), (ID2, "autre", "depose"),
    ]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="liens symboliques indisponibles")
def test_liens_jamais_suivis(tmp_path):
    ailleurs = tmp_path / "ailleurs"
    ecrire(ailleurs / f"{ID1}.json", {"schema": 1, "id": ID1, "projet": "demo", "texte": "x"})
    (chemins.donnees() / "boite").mkdir(parents=True)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(chemins.donnees() / "boite" / "demo"),
                        str(ailleurs)], check=True, capture_output=True)
    else:
        os.symlink(ailleurs, chemins.donnees() / "boite" / "demo")
    assert lire()["messages"] == []


def test_route_sans_effet_par_le_serveur(tmp_path):
    operation_message(ID1)
    message_depose(ID2)
    acquitter(chemins.donnees(), ID2, "pc-b", datetime(2026, 11, 6, 13, 5, tzinfo=UTC).isoformat())
    web = tmp_path / "web"
    web.mkdir()
    serveur = _demarrer(web, routes.TABLE)
    avant = empreinte()
    try:
        reponse, contenu = requete(serveur, "GET", "/api/operations", jeton=serveur.jeton)
    finally:
        serveur.shutdown()
        serveur.server_close()
    assert reponse.status == 200
    assert [m["etat"] for m in _json(contenu)["donnees"]["messages"]] == ["en-attente", "lu"]
    assert empreinte() == avant
