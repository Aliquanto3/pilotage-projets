"""Lancement de l'appli : instance précédente, fichier pid, navigateur (story 4.1, AD-14)."""

import http.client
import json
import os
import socket
import subprocess
import sys
import threading

import pytest

from pilotage import chemins
from pilotage.serveur import cli, enfants, processus


@pytest.fixture(autouse=True)
def pas_de_vraie_synchro(monkeypatch):
    """`lancer.py appli` lance une synchro au démarrage (4.3) : jamais de vrai processus ici."""
    monkeypatch.setattr(enfants, "popen", lambda commande, **options: type(
        "Faux", (), {"wait": lambda self, timeout=None: 0})())
    enfants.reinitialiser()
    yield
    enfants.reinitialiser()


WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="GetProcessTimes : Windows seulement")


@pytest.fixture
def dormeur():
    # Interpréteur de base : le `python.exe` d'un venv Windows est un lanceur intermédiaire.
    executable = getattr(sys, "_base_executable", sys.executable)
    enfant = subprocess.Popen([executable, "-c", "import time; time.sleep(60)"])
    yield enfant
    if enfant.poll() is None:
        enfant.kill()
        enfant.wait(5)


def _noter(pid, cree):
    chemins.ecrire_atomique(chemins.appli_pid(), json.dumps({"pid": pid, "cree": cree}))


@WINDOWS
def test_heure_creation_du_processus_courant():
    cree = processus.heure_creation(os.getpid())
    assert cree is not None and cree.isdigit()
    assert processus.heure_creation(os.getpid()) == cree


def test_heure_creation_pid_absent():
    assert processus.heure_creation(0x7FFFFFF0) is None


@WINDOWS
def test_instance_precedente_arretee_si_pid_et_heure_concordent(dormeur):
    _noter(dormeur.pid, processus.heure_creation(dormeur.pid))
    assert processus.arreter_precedente() is True
    assert dormeur.wait(5) is not None


@WINDOWS
def test_instance_epargnee_si_heure_differente(dormeur):
    cree = processus.heure_creation(dormeur.pid)
    _noter(dormeur.pid, str(int(cree) + 1))
    assert processus.arreter_precedente() is False
    assert dormeur.poll() is None


@pytest.mark.parametrize(
    "contenu",
    [None, "", "pas du json", "[]", '{"pid": 1}', '{"pid": true, "cree": "1"}',
     '{"pid": -4, "cree": "1"}', '{"pid": 4, "cree": 12}', '{"pid": 4, "cree": "x1"}'],
)
def test_fichier_pid_absent_ou_mal_forme(contenu):
    if contenu is not None:
        chemins.ecrire_atomique(chemins.appli_pid(), contenu)
    assert processus.lire_instance(chemins.appli_pid()) is None
    assert processus.arreter_precedente() is False


def test_processus_courant_jamais_arrete():
    _noter(os.getpid(), processus.heure_creation(os.getpid()) or "1")
    assert processus.arreter_precedente() is False


@WINDOWS
def test_processus_termine_non_arrete(dormeur):
    cree = processus.heure_creation(dormeur.pid)
    dormeur.kill()
    dormeur.wait(5)
    assert processus.arreter_si_meme(dormeur.pid, cree) is False


def test_noter_puis_effacer_instance():
    processus.noter_instance()
    objet = json.loads(chemins.appli_pid().read_text(encoding="utf-8"))
    assert objet["pid"] == os.getpid()
    assert objet["cree"] == processus.heure_creation(os.getpid())
    processus.effacer_instance()
    assert not chemins.appli_pid().exists()


def test_effacer_epargne_le_fichier_d_une_autre_instance():
    _noter(os.getpid() + 1, "1")
    processus.effacer_instance()
    assert chemins.appli_pid().exists()


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _lancer(web, ouvertes, pret, essais=3):
    """`cli.main` sur un port libre ; réessaie si le port a été repris entre-temps (course)."""
    for _ in range(essais):
        code = cli.main(["--port", str(_port_libre())], navigateur=ouvertes.append, pret=pret,
                        racine_web=web)
        if code != 1:
            break
    return code


def test_main_sert_ouvre_le_navigateur_et_note_l_instance(tmp_path, capsys):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    ouvertes, constats = [], {}

    def pret(serveur):
        def verifier():
            try:
                connexion = http.client.HTTPConnection("127.0.0.1", serveur.port, timeout=5)
                connexion.request("GET", "/api/etat",
                                  headers={"Authorization": f"Bearer {serveur.jeton}"})
                constats["api"] = connexion.getresponse().status
                connexion.close()
                constats["pid"] = json.loads(chemins.appli_pid().read_text(encoding="utf-8"))
            finally:
                constats["jeton"], constats["port"] = serveur.jeton, serveur.port
                serveur.shutdown()  # toujours : un échec ne laisse pas `serve_forever` bloqué

        threading.Thread(target=verifier, daemon=True).start()

    code = _lancer(web, ouvertes, pret)
    assert code == 0
    jeton, port = constats["jeton"], constats["port"]
    assert ouvertes == [f"http://127.0.0.1:{port}/#{jeton}"]
    assert constats["api"] == 200  # GET /api/etat livrée par 4.2
    assert constats["pid"]["pid"] == os.getpid()
    assert not chemins.appli_pid().exists()
    sortie = capsys.readouterr()
    assert jeton not in sortie.out + sortie.err
    assert f"http://127.0.0.1:{port}/" in sortie.out
    journal = "".join(
        f.read_text(encoding="utf-8") for f in (chemins.attente() / "journal").glob("*.log")
    )
    assert jeton not in journal


def test_main_config_invalide_avec_port_explicite_rend_2(tmp_path, monkeypatch, capsys):
    # `--port` évite la lecture du port, pas celle du dossier `attente` (fichier pid).
    monkeypatch.delenv("PILOTAGE_RACINE_LOCALE")
    config = tmp_path / "profil" / ".claude" / "pilotage" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text("{pas du json", encoding="utf-8")
    code = cli.main(["--port", "47615"], navigateur=lambda url: pytest.fail(url),
                    racine_web=tmp_path)
    assert code == 2
    assert "JSON invalide" in capsys.readouterr().err


def test_main_pid_non_inscriptible_rend_2(tmp_path, capsys):
    chemins.appli_pid().mkdir(parents=True)  # `os.replace` sur un dossier échoue
    code = _lancer(tmp_path, [], None)
    assert code == 2
    assert "impossible de noter l'instance" in capsys.readouterr().err


def test_main_port_occupe_rend_1(tmp_path, capsys):
    with socket.socket() as occupant:
        occupant.bind(("127.0.0.1", 0))
        occupant.listen()
        port = occupant.getsockname()[1]
        code = cli.main(["--port", str(port)], navigateur=lambda url: pytest.fail(url),
                        racine_web=tmp_path)
    assert code == 1
    assert f"port {port} indisponible" in capsys.readouterr().err


def test_main_port_hors_bornes_rend_2(capsys):
    assert cli.main(["--port", "70000"]) == 2
    assert "port hors de 1 à 65535" in capsys.readouterr().err
