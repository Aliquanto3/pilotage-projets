"""Tests de l'adaptateur `scan.processus`, de `scan.sessions` et du scan de bout en bout (2.6)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pilotage import chemins
from pilotage.noyau import schemas
from pilotage.scan import cli, faits_gh, processus, sessions
from pilotage.scan import verrou as impl
from tests.test_faits_gh import faux_gh
from tests.test_inventaire import faux_depot

SID = "0a1b2c3d-0000-4000-8000-000000000001"
SID2 = "0a1b2c3d-0000-4000-8000-000000000002"
windows = pytest.mark.skipif(sys.platform != "win32", reason="GetProcessTimes (Windows)")


def etat(session=SID, projet="demo", pc="pc-test", **champs):
    base = {
        "schema": 1, "projet": projet, "pc": pc, "session": session, "pid": 4242,
        "pid_cree": "133000000000000000", "dossier": projet, "branche": "main",
        "debut": "2026-11-06T08:00:00Z", "statut": "active",
    }
    objet = {**base, **champs}
    schemas.valider("session", objet)
    chemin = chemins.attente() / "etat" / projet / pc / f"{session}.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet), "utf-8")
    return objet


def fichier_claude(pid, session=SID, proc_start="133000000000000000"):
    dossier = chemins.sessions_claude()
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{pid}.json").write_text(
        json.dumps({"pid": pid, "sessionId": session, "procStart": proc_start}), "utf-8"
    )


# --- processus (adaptateur Windows) ---


@windows
def test_processus_vivant_avec_heure_de_creation_notee():
    cree = processus.heure_creation(os.getpid())
    assert isinstance(cree, int) and cree > 0
    assert processus.vivante(os.getpid(), str(cree)) is True
    assert processus.vivante(os.getpid(), cree) is True


@windows
def test_processus_heure_de_creation_differente_ou_illisible_donne_faux():
    cree = processus.heure_creation(os.getpid())
    assert processus.vivante(os.getpid(), str(cree + 1)) is False
    assert processus.vivante(os.getpid(), "pas-un-nombre") is False


@windows
def test_processus_heure_non_notee_ne_suffit_pas_meme_pid_vivant():
    assert processus.heure_creation(os.getpid()) is not None
    assert processus.vivante(os.getpid(), None) is False


def test_processus_erreur_ctypes_donne_inconnu_sans_exception(monkeypatch):
    def casse(_pid):
        raise OSError("kernel32 indisponible")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(processus, "_heure_creation_windows", casse)
    assert processus.heure_creation(1234) is None
    assert processus.vivante(1234, "133000000000000000") is False


@windows
def test_processus_termine_donne_faux():
    enfant = subprocess.Popen([sys.executable, "-c", "pass"])
    enfant.wait()
    assert processus.heure_creation(enfant.pid) is None
    assert processus.vivante(enfant.pid, None) is False


@pytest.mark.parametrize("pid", [0, -1, True, "12", None])
def test_processus_pid_invalide_donne_faux(pid):
    assert processus.heure_creation(pid) is None
    assert processus.vivante(pid, None) is False


def test_processus_hors_windows_tout_est_absent(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert processus.heure_creation(1) is None
    assert processus.vivante(1, None) is False


def test_processus_ne_depend_ni_du_serveur_ni_des_hooks_et_ne_tue_rien():
    source = Path(processus.__file__).read_text("utf-8")
    assert "pilotage.serveur" not in source and "pilotage.hooks" not in source
    assert "TerminateProcess(" not in source and "kill" not in source


# --- lecture des états et de ~/.claude/sessions ---


def test_lire_etats_ajoute_vivante_depuis_l_adaptateur():
    etat(SID)
    etat(SID2, pid=999, pid_cree=None)
    appels = []

    def vivante(pid, cree):
        appels.append((pid, cree))
        return pid == 4242

    par_projet, alertes = sessions.lire_etats("pc-test", vivante)
    assert alertes == []
    assert {s["session"]: s["vivante"] for s in par_projet["demo"]} == {SID: True, SID2: False}
    assert sorted(appels, key=lambda a: a[0]) == [(999, None), (4242, "133000000000000000")]


def test_lire_etats_session_finie_pas_de_controle_de_pid():
    etat(fin="2026-11-06T10:00:00Z", statut="finie")
    par_projet, _ = sessions.lire_etats("pc-test", lambda *_: pytest.fail("pid contrôlé"))
    assert par_projet["demo"][0]["vivante"] is False


def test_lire_etats_ignore_autres_pc_et_fichiers_illisibles_avec_alerte():
    etat(pc="pc-autre")
    etat(SID)
    mauvais = chemins.attente() / "etat" / "demo" / "pc-test" / f"{SID2}.json"
    mauvais.write_text("{pas du json", "utf-8")
    par_projet, alertes = sessions.lire_etats("pc-test", lambda *_: True)
    assert [s["session"] for s in par_projet["demo"]] == [SID]
    assert alertes == [{"code": sessions.ALERTE_ETATS, "message": sessions.MESSAGE_ETATS}]


def test_lire_etats_etat_range_sous_un_autre_projet_est_ignore():
    objet = etat(SID)
    faux = chemins.attente() / "etat" / "autre" / "pc-test"
    faux.mkdir(parents=True)
    (faux / f"{SID}.json").write_text(json.dumps(objet), "utf-8")
    par_projet, alertes = sessions.lire_etats("pc-test", lambda *_: True)
    assert "autre" not in par_projet and len(alertes) == 1


def test_lire_etats_fichier_claude_fait_foi_pour_son_pid():
    etat(SID, pid=111, pid_cree=None)  # heure non notée, mais fichier Claude vivant : vivante
    etat(SID2, pid=111)  # ancien état du même processus (après /clear) : plus la session du pid
    par_projet, _ = sessions.lire_etats(
        "pc-test", lambda *_: pytest.fail("pid du fichier Claude recontrôlé"), {111: SID}
    )
    assert {s["session"]: s["vivante"] for s in par_projet["demo"]} == {SID: True, SID2: False}


def test_lire_etats_sans_dossier_rien():
    assert sessions.lire_etats("pc-test") == ({}, [])


def test_vivantes_claude_pid_vivant_et_proc_start_egal():
    fichier_claude(111, SID)
    fichier_claude(222, SID2, proc_start="5")
    (chemins.sessions_claude() / "111.key").write_text("non lu", "utf-8")
    vus = []

    def vivante(pid, cree):
        vus.append((pid, cree))
        return pid == 111

    ids_vivants, alertes = sessions.vivantes_claude(vivante)
    assert (ids_vivants, alertes) == ({111: SID}, [])
    assert sorted(vus) == [(111, "133000000000000000"), (222, "5")]


def test_vivantes_claude_fichier_illisible_ignore_avec_alerte():
    fichier_claude(111, SID)
    (chemins.sessions_claude() / "9.json").write_text("[1]", "utf-8")
    (chemins.sessions_claude() / "8.json").write_text('{"pid": 8, "sessionId": "nope"}', "utf-8")
    ids_vivants, alertes = sessions.vivantes_claude(lambda *_: True)
    assert ids_vivants == {111: SID}
    assert alertes == [{"code": sessions.ALERTE_CLAUDE, "message": sessions.MESSAGE_CLAUDE}] * 2


def test_vivantes_claude_dossier_absent():
    assert sessions.vivantes_claude() == ({}, [])


def test_sessions_claude_sous_la_racine_de_test(racine_locale_isolee):
    assert chemins.sessions_claude() == racine_locale_isolee / "claude-sessions"


# --- scan de bout en bout ---


@pytest.fixture
def github(tmp_path):
    racine = tmp_path / "github"
    faux_depot(racine / "demo", url="https://github.com/Proprio-Test/demo.git")
    return racine


@pytest.fixture(autouse=True)
def mutex(monkeypatch, tmp_path):
    monkeypatch.setenv(impl.VARIABLE_NOM, f"Local\\pilotage-test-sess-{abs(hash(str(tmp_path)))}")


def scanner(github, monkeypatch, vivante=lambda pid, cree: True):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    monkeypatch.setattr(processus, "vivante", vivante)
    assert cli.main(["--racine-github", str(github), "--pc", "pc-test"]) == 0
    instantane = json.loads((chemins.instantanes() / "pc-test.json").read_text("utf-8"))
    return instantane, chemins.tableau().read_text("utf-8")


def test_scan_remplit_sessions_vivantes_et_valide_l_instantane(github, monkeypatch):
    etat(SID)
    etat(SID2)  # état sans fichier ~/.claude/sessions : pas dans l'instantané
    fichier_claude(111, SID)
    fichier_claude(222, "0a1b2c3d-0000-4000-8000-0000000000ff")  # session d'un projet inconnu
    instantane, _ = scanner(github, monkeypatch)
    assert instantane["projets"]["demo"]["sessions_vivantes"] == [SID]
    schemas.valider("instantane", instantane)


def test_scan_attente_montre_quoi_et_type_dans_tableau(github, monkeypatch):
    etat(attente={"quoi": "valider le plan", "depuis": "2026-11-06T09:00:00Z", "type": "choix"},
         statut="attente")
    _, tableau = scanner(github, monkeypatch)
    assert "## 🔴 Attend Personne Test (1)" in tableau
    assert "- **demo** : vous attend : valider le plan · type : choix · phase" in tableau


def test_scan_attente_heuristique_est_a_qualifier(github, monkeypatch):
    etat(attente={"quoi": "Voulez-vous ?", "depuis": "2026-11-06T09:00:00Z", "type": "choix",
                  "source": "question"}, statut="attente")
    _, tableau = scanner(github, monkeypatch)
    assert "vous attend : Voulez-vous ? · type : a-qualifier" in tableau


def test_scan_prompt_posterieur_pas_d_attente(github, monkeypatch):
    etat(attente={"quoi": "q", "depuis": "2026-11-06T09:00:00Z"},
         dernier_prompt="2026-11-06T09:00:01Z")
    _, tableau = scanner(github, monkeypatch)
    assert "## 🔴 Attend Personne Test (0)" in tableau
    assert "## 🟢 Tourne (1)" in tableau
    assert "- **demo** : tourne sur pc-test, session 0a1b2c3d" in tableau


def test_scan_session_arretee_meme_en_attente_est_a_relancer(github, monkeypatch):
    etat(attente={"quoi": "q", "depuis": "2026-11-06T09:00:00Z"}, statut="attente")
    _, tableau = scanner(github, monkeypatch, vivante=lambda pid, cree: False)
    assert "## 🔴 Attend Personne Test (0)" in tableau
    assert "## 🟠 À relancer (1)" in tableau
    assert "- **demo** : session 0a1b2c3d arrêtée sans fin propre (pc-test)" in tableau


def test_scan_session_sans_heure_notee_ni_fichier_claude_est_arretee(github, monkeypatch):
    etat(pid_cree=None)
    _, tableau = scanner(github, monkeypatch, vivante=processus.vivante)
    assert "## 🟢 Tourne (0)" in tableau and "## 🟠 À relancer (1)" in tableau


def test_scan_fichier_de_session_illisible_alerte_sans_echec(github, monkeypatch):
    etat(SID)
    (chemins.attente() / "etat" / "demo" / "pc-test" / f"{SID2}.json").write_text("x", "utf-8")
    chemins.sessions_claude().mkdir(parents=True)
    (chemins.sessions_claude() / "1.json").write_text("x", "utf-8")
    scanner(github, monkeypatch)
    alertes = json.loads(chemins.alertes_json().read_text("utf-8"))["alertes"]
    assert {sessions.ALERTE_ETATS, sessions.ALERTE_CLAUDE} <= {a["code"] for a in alertes}
