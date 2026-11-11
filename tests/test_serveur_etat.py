"""`GET /api/etat` : état assemblé par le noyau, sans effet (story 4.2, AD-5 §9, AD-14, M8, M15)."""

import hashlib
import json
import os
import subprocess
from dataclasses import replace

import pytest

from pilotage import chemins
from pilotage.noyau import etat as noyau_etat
from pilotage.scan import cli as scan_cli
from pilotage.scan import faits_gh, processus
from pilotage.scan import verrou as impl
from pilotage.serveur import enfants, routes
from pilotage.serveur import etat as serveur_etat
from pilotage.serveur.routes import Reponse
from tests.test_faits_gh import faux_gh
from tests.test_inventaire import faux_depot
from tests.test_serveur import _demarrer, _json, requete

SESSION = "11111111-2222-3333-4444-555555555555"
QUOI = "é😀日本" * 50  # 200 points de code, de 2, 4, 3 et 3 octets UTF-8
ID = "20261106T101500Z-0a1b2c3d"


@pytest.fixture(autouse=True)
def pc_et_mutex(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPUTERNAME", "PC-Test")
    enfants.reinitialiser()  # état mémoire des enfants : un fil d'un autre test a pu le remplir
    monkeypatch.setenv(impl.VARIABLE_NOM, f"Local\\pilotage-test-etat-{abs(hash(str(tmp_path)))}")


@pytest.fixture
def racine_web(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return web


@pytest.fixture
def scanne(monkeypatch):
    """Un dépôt `demo` scanné par le vrai scan (gh simulé) : instantané et alertes en place."""
    github = chemins.racine_github()
    faux_depot(github / "demo", url="https://github.com/Proprio-Test/demo.git")
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    assert scan_cli.main(["--racine-github", str(github), "--pc", "pc-test"]) == 0
    return github


@pytest.fixture
def serveur(racine_web):
    serveur = _demarrer(racine_web, routes.TABLE)
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def lire(serveur, cible="/api/etat"):
    return requete(serveur, "GET", cible, jeton=serveur.jeton)


def ecrire_session(quoi):
    dossier = chemins.attente() / "etat" / "demo" / "pc-test"
    dossier.mkdir(parents=True)
    objet = {
        "schema": 1, "projet": "demo", "pc": "pc-test", "session": SESSION, "pid": os.getpid(),
        "pid_cree": str(processus.heure_creation(os.getpid())), "dossier": "demo",
        "branche": "main", "debut": "2026-11-06T08:00:00Z", "statut": "attente",
        "attente": {"quoi": quoi, "depuis": "2026-11-06T09:00:00Z", "type": "choix"},
    }
    (dossier / f"{SESSION}.json").write_text(json.dumps(objet, ensure_ascii=False), "utf-8")


def test_sans_jeton_401(serveur):
    reponse, _ = requete(serveur, "GET", "/api/etat")
    assert reponse.status == 401


def test_etat_assemble_complet(scanne, serveur):
    reponse, contenu = lire(serveur)
    assert reponse.status == 200
    donnees = _json(contenu)["donnees"]
    assert list(donnees) == [
        "cartes", "colonnes", "chantiers", "comptes", "details", "dependances", "fraicheur",
        "alertes", "cycle", "utilisateur",
    ]
    assert list(donnees["colonnes"]) == list(noyau_etat.ACTIONS)
    assert donnees["chantiers"] == []
    assert donnees["comptes"] == {  # comptes étendus (4.8), renvoyés tels quels
        "actions": {"attend-utilisateur": 0, "a-relancer": 1, "tourne": 0, "rien-a-faire": 0},
        "types": {}, "familles": {"sans-session": 1}, "pcs_tourne": {}, "suivis": 1,
        "stables": 0,
    }
    (carte,) = donnees["colonnes"]["a-relancer"]
    assert carte["nom"] == "demo" and carte["genre"] == "projet"
    assert carte["raison"]["code"] == "run-en-cours"  # run non terminé du faux gh
    assert carte["phase"] == ["status-dev"]
    assert carte["etiquettes"] == ["ai-portfolio"]  # « secret » n'est pas dans l'énumération
    assert (carte["chantier"], carte["quoi"], carte["type"]) == (None, "", None)
    assert (carte["clone_ici"], carte["pcs"], carte["depot_de"]) == (True, ["pc-test"], None)
    assert (carte["pc"], carte["depuis"]) == (None, None)  # hors Attend
    assert (carte["famille"], carte["vieillissante"], carte["dernier_tour"]) == (
        "sans-session", False, None,
    )
    assert donnees["dependances"] == []
    assert [f["pc"] for f in donnees["fraicheur"]] == ["pc-test"]
    assert donnees["alertes"] == []
    # détail du tiroir (4.7) : à part des cartes, faits du dépôt et critères du noyau
    assert list(donnees["details"]) == ["demo"]
    detail = donnees["details"]["demo"]
    assert list(detail) == ["sessions", "depot", "depot_de", "criteres"]
    assert (detail["sessions"], detail["depot_de"]) == ([], None)
    assert set(detail["depot"]) == {
        "tag", "commits", "prs_ouvertes", "stories_ouvertes", "ci", "sprint_status"}
    assert [c["code"] for c in detail["criteres"]] == ["release", "commits", "stories", "prs", "ci"]
    assert "phase" not in detail and "etiquettes" not in detail
    assert donnees["cycle"] == serveur_etat.CYCLE_NEUTRE
    assert donnees["utilisateur"] == "Personne Test"  # nom affiché (story 7.2)


@pytest.mark.parametrize("brut", [None, "", "   ", "a" * 65, "nom\navec saut"])
def test_etat_utilisateur_absent_ou_invalide_vide(serveur, monkeypatch, brut):
    if brut is None:
        monkeypatch.delenv(chemins.VARIABLE_UTILISATEUR)
    else:
        monkeypatch.setenv(chemins.VARIABLE_UTILISATEUR, brut)
    donnees = _json(lire(serveur)[1])["donnees"]
    assert donnees["utilisateur"] == ""


def test_etat_utilisateur_configure_rendu_tel_quel(serveur, monkeypatch):
    monkeypatch.setenv(chemins.VARIABLE_UTILISATEUR, "  Zoe\u0308   O'Neil  ")  # NFD
    assert _json(lire(serveur)[1])["donnees"]["utilisateur"] == "Zoë O'Neil"  # NFC, resserré


def test_etat_sans_scan_prealable_alerte_de_lecture(serveur):
    donnees = _json(lire(serveur)[1])["donnees"]
    assert donnees["cartes"] == []
    assert donnees["alertes"] == [{
        "source": "lecture", "code": "instantane-absent", "params": {},
        "texte": "Aucun instantané de ce PC : lancer un scan",
    }]


def test_quoi_de_200_points_identique_a_l_octet(scanne, serveur):
    ecrire_session(QUOI)
    assert len(QUOI) == 200
    _, contenu = lire(serveur)
    carte = _json(contenu)["donnees"]["colonnes"]["attend-utilisateur"][0]
    assert carte["quoi"] == QUOI
    assert carte["type"] == "choix"
    assert (carte["pc"], carte["depuis"]) == ("pc-test", "2026-11-06T09:00:00Z")  # méta (4.5)
    assert QUOI.encode("utf-8") in contenu  # octets UTF-8 bruts
    assert b"\\u" not in contenu  # ni échappement ASCII ni paire de substitution


def test_alertes_ecrites_avec_texte_du_noyau_puis_alertes_de_lecture(scanne, serveur):
    detail = "é😀日本" * 75  # 300 points de code
    ecrites = {"schema": 1, "alertes": [
        {"source": "scan", "code": "faits-github-non-relus", "params": {"projet": "demo"}},
        {"source": "scan", "code": "projets-invalide", "params": {"detail": detail}},
        {"source": "sync", "code": "sync-conflit", "message": "Synchro abandonnée à 10:00 : x"},
        {"source": "scan", "code": "inconnu-du-catalogue", "params": {"n": 3}},
    ]}
    chemins.ecrire_atomique(chemins.alertes_json(), json.dumps(ecrites, ensure_ascii=False))
    dossier = chemins.donnees() / "instantanes"
    dossier.mkdir(parents=True)
    (dossier / "pc-autre.json").write_text('{"schema": 2}', "utf-8")
    avant = chemins.alertes_json().read_bytes()
    _, contenu = lire(serveur)
    alertes = _json(contenu)["donnees"]["alertes"]
    assert [(a["source"], a["code"], a["texte"]) for a in alertes] == [
        ("scan", "faits-github-non-relus", "Faits GitHub non relus : demo."),
        ("scan", "projets-invalide", f"projets.yaml ignoré : {detail}"),
        ("sync", "sync-conflit", "Synchro abandonnée à 10:00 : x"),
        ("scan", "inconnu-du-catalogue", "inconnu-du-catalogue"),
        ("lecture", "donnees-version-recente",
         "Fichiers de pc-autre ignorés : version plus récente. "
         "Mettez à jour pilotage-projets sur ce PC."),
    ]
    assert alertes[0]["params"] == {"projet": "demo"}
    assert detail.encode("utf-8") in contenu
    assert chemins.alertes_json().read_bytes() == avant  # alertes de lecture jamais écrites


def test_alertes_json_illisible_alerte_de_lecture(scanne, serveur):
    chemins.ecrire_atomique(chemins.alertes_json(), "{pas du json")
    alertes = _json(lire(serveur)[1])["donnees"]["alertes"]
    assert [(a["source"], a["code"]) for a in alertes] == [("lecture", "alertes-illisibles")]
    assert alertes[0]["texte"].startswith("alertes.json illisible")


def test_nom_de_pc_invalide_alerte_de_lecture_pas_500(scanne, serveur, monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "日本")  # aucun caractère [a-z0-9-]
    reponse, contenu = lire(serveur)
    assert reponse.status == 200
    donnees = _json(contenu)["donnees"]
    assert donnees["cartes"] == [] and donnees["fraicheur"] == []
    assert [(a["source"], a["code"]) for a in donnees["alertes"]] == [("lecture", "pc-invalide")]


def test_parametre_trop_long_tronque_le_scan_reste_vivant():
    """Clé YAML inconnue de 400 caractères citée dans le `detail` : borné à 300, scan à 0."""
    chemins.donnees().mkdir(parents=True, exist_ok=True)
    yaml = "schema: 1" + chr(10) + "z" * 400 + ": 1" + chr(10)
    (chemins.donnees() / "projets.yaml").write_text(yaml, "utf-8")
    github = chemins.racine_github()
    github.mkdir(parents=True, exist_ok=True)
    assert scan_cli.main(["--racine-github", str(github), "--pc", "pc-test"]) == 0
    (alerte,) = json.loads(chemins.alertes_json().read_text("utf-8"))["alertes"]
    assert alerte["code"] == "projets-invalide"
    assert len(alerte["params"]["detail"]) == 300


# --- M15, AD-14 : les lectures n'ont aucun effet --------------------------------------------


def empreinte():
    """Empreinte d'`attente/` hors journal, de `donnees/`, de la table et du tableau."""
    resultat = {}
    for nom, racine in (("attente", chemins.attente()), ("donnees", chemins.donnees())):
        for dossier, sous, fichiers in os.walk(racine):
            if nom == "attente" and dossier == str(racine) and "journal" in sous:
                sous.remove("journal")
            for fichier in fichiers:
                chemin = os.path.join(dossier, fichier)
                with open(chemin, "rb") as f:
                    resultat[(nom, os.path.relpath(chemin, racine))] = (
                        hashlib.sha256(f.read()).hexdigest()
                    )
            for rep in sous:
                resultat[(nom, os.path.relpath(os.path.join(dossier, rep), racine))] = "dossier"
    for fichier in (chemins.table_dossiers(), chemins.tableau()):
        resultat[("fichier", str(fichier))] = (
            hashlib.sha256(fichier.read_bytes()).hexdigest() if fichier.exists() else None
        )
    return resultat


def cible(route):
    valeurs = {"<id>": ID, "<projet>": "demo"}
    return "/" + "/".join(valeurs.get(s, s) for s in route.segments)


@pytest.mark.parametrize(
    "route", [r for r in routes.TABLE if r.methode == "GET"], ids=lambda r: r.motif
)
def test_route_get_sans_effet(route, scanne, racine_web, monkeypatch):
    ecrire_session("a faire")
    (chemins.donnees() / "etat").mkdir(parents=True)
    (chemins.donnees() / "projets.yaml").write_text("schema: 1\n", "utf-8")
    chemins.briefs().mkdir(parents=True)  # brief servi par `GET /api/brief/<id>` (5.4)
    (chemins.briefs() / f"{ID}.md").write_text("# Brief\n", "utf-8")
    # une route non encore livrée reçoit un gestionnaire neutre : le test couvre toute la table
    table = tuple(
        r if r.gestionnaire else replace(r, gestionnaire=lambda p, c: Reponse(200, donnees=p))
        for r in routes.TABLE
    )
    serveur = _demarrer(racine_web, table)
    avant = empreinte()
    assert chemins.table_dossiers().exists() and chemins.tableau().exists()  # écrits par le scan
    prises, lancees = [], []

    def interdit(liste):
        def espion(*args, **kwargs):
            liste.append(args)
            raise AssertionError("effet interdit pendant une lecture")
        return espion

    monkeypatch.setattr(impl.Verrou, "__init__", interdit(prises))
    monkeypatch.setattr(impl.Verrou, "__enter__", interdit(prises))
    for nom in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, nom, interdit(lancees))
    monkeypatch.setattr(os, "system", interdit(lancees))
    try:
        reponse, _ = requete(serveur, "GET", cible(route), jeton=serveur.jeton)
    finally:
        serveur.shutdown()
        serveur.server_close()
    assert reponse.status == 200
    assert empreinte() == avant
    assert prises == [] and lancees == []


# --- Identifiants des chemins (report de 4.1, AD-9) -----------------------------------------


@pytest.mark.parametrize("motif,mauvais", [
    ("/api/brief/<id>",
     ["x", "20261106T101500Z-0A1B2C3D", "20261340T101500Z-0a1b2c3d", "..", "a%2Fb"]),
    ("/api/sessions/<projet>", ["Demo", "..", "a..b", "nul", "con.txt", "x.", "a%5Cb"]),
])
def test_identifiants_du_chemin_valides_selon_ad9(racine_web, motif, mauvais):
    appels = []

    def espion(parametres, corps):
        appels.append(parametres)
        return Reponse(200, donnees=parametres)

    table = tuple(replace(r, gestionnaire=espion) for r in routes.TABLE)
    serveur = _demarrer(racine_web, table)
    try:
        route = next(r for r in routes.TABLE if r.motif == motif)
        valide = cible(route)
        debut = valide.rsplit("/", 1)[0]
        for brut in mauvais:
            reponse, contenu = requete(serveur, "GET", f"{debut}/{brut}", jeton=serveur.jeton)
            assert reponse.status == 400, brut
            assert _json(contenu)["ok"] is False
        assert appels == []
        assert requete(serveur, "GET", valide, jeton=serveur.jeton)[0].status == 200
        assert len(appels) == 1
        assert requete(serveur, "GET", f"{debut}/..")[0].status == 401  # le jeton passe avant
    finally:
        serveur.shutdown()
        serveur.server_close()
