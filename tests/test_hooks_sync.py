"""Synchro détachée lancée par SessionStart et SessionEnd (story 3.6, AD-6, M2).

Aucun vrai `sync` : le `Popen` est espionné, ou le lanceur est un `lancer.py` factice posé sous
l'installation de `PILOTAGE_RACINE_LOCALE`.
"""

import json
import os
import subprocess
import sys
import time
import uuid

import pytest

from pilotage import chemins
from pilotage.hooks import _commun, cycle
from tests.test_hooks_session import (
    END,
    PYTHON,
    START,
    _etat,
    _journal,
    _lancer,
    _payload,
    _sans_sortie,
    racine,  # noqa: F401 - fixture
)

windows = pytest.mark.skipif(sys.platform != "win32", reason="drapeaux CreateProcess")
DRAPEAUX = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
BREAKAWAY = 0x01000000


@pytest.fixture
def installe(racine_locale_isolee, monkeypatch, tmp_path):
    """Interpréteur (fichier réel) et `lancer.py` factice sous l'installation isolée."""
    installation = racine_locale_isolee / "installation"
    installation.mkdir(parents=True, exist_ok=True)
    (installation / "lancer.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    pythonw = tmp_path / "pythonw.exe"
    pythonw.write_bytes(b"")
    monkeypatch.setenv(chemins.VARIABLE_PYTHONW, str(pythonw))
    return installation, str(pythonw)


class Espion:
    """Double de `subprocess.Popen` (frontière système) : note chaque appel, peut refuser."""

    def __init__(self, refus: list[BaseException] | None = None):
        self.appels: list[tuple[list, dict]] = []
        self.refus = list(refus or [])

    def __call__(self, arguments, **options):
        self.appels.append((arguments, options))
        if self.refus:
            raise self.refus.pop(0)
        return object()


@pytest.fixture
def espion(monkeypatch):
    double = Espion()
    monkeypatch.setattr(subprocess, "Popen", double)
    return double


# --- Lancement ----------------------------------------------------------------------------


@windows
def test_popen_arguments_drapeaux_et_flux(installe, espion, racine_locale_isolee, capsys):
    installation, pythonw = installe
    _commun.declencher_sync("SessionStart")
    assert len(espion.appels) == 1
    arguments, options = espion.appels[0]
    assert arguments == [pythonw, "-I", str(installation / "lancer.py"), "sync"]
    assert options == {
        "cwd": str(installation),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "creationflags": DRAPEAUX | BREAKAWAY,
    }
    assert _commun.CREATE_BREAKAWAY_FROM_JOB == subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert _commun.DETACHED_PROCESS == subprocess.DETACHED_PROCESS
    assert _commun.CREATE_NEW_PROCESS_GROUP == subprocess.CREATE_NEW_PROCESS_GROUP
    assert (racine_locale_isolee / "attente" / "sync-demande").is_file()  # M2
    assert _journal(racine_locale_isolee) == []
    assert capsys.readouterr().out == ""


@pytest.mark.skipif(sys.platform == "win32", reason="branche hors Windows")
def test_popen_hors_windows_nouvelle_session(installe, espion):
    _commun.declencher_sync("SessionEnd")
    assert espion.appels[0][1]["start_new_session"] is True
    assert "creationflags" not in espion.appels[0][1]


@windows
@pytest.mark.parametrize(
    "refus",
    [PermissionError(13, "refusé"), OSError(22, "refusé", None, 5)],  # EACCES, ERROR_ACCESS_DENIED
)
def test_breakaway_refuse_nouvel_essai_sans_le_drapeau(
    installe, monkeypatch, racine_locale_isolee, refus
):
    double = Espion([refus])
    monkeypatch.setattr(subprocess, "Popen", double)
    _commun.declencher_sync("SessionEnd")
    assert [o["creationflags"] for _, o in double.appels] == [DRAPEAUX | BREAKAWAY, DRAPEAUX]
    assert double.appels[0][0] == double.appels[1][0]
    assert _journal(racine_locale_isolee) == ["SessionEnd SyncSansBreakaway"]


@windows
def test_second_refus_journalise_sans_lever(installe, monkeypatch, racine_locale_isolee):
    double = Espion([PermissionError(13, "refusé"), PermissionError(13, "refusé")])
    monkeypatch.setattr(subprocess, "Popen", double)
    _commun.declencher_sync("SessionStart")  # ne lève pas
    assert len(double.appels) == 2
    assert _journal(racine_locale_isolee) == ["SessionStart PermissionError:EACCES"]


@windows
def test_autre_echec_sans_nouvel_essai(installe, monkeypatch, racine_locale_isolee):
    double = Espion([FileNotFoundError(2, "absent")])
    monkeypatch.setattr(subprocess, "Popen", double)
    _commun.declencher_sync("SessionStart")
    assert len(double.appels) == 1
    assert _journal(racine_locale_isolee) == ["SessionStart FileNotFoundError:ENOENT"]


# --- Absences -----------------------------------------------------------------------------


def test_sans_pythonw_sous_racine_de_test_silence(espion, racine_locale_isolee):
    _commun.declencher_sync("SessionStart")
    assert espion.appels == []
    assert _journal(racine_locale_isolee) == []
    assert not (racine_locale_isolee / "attente" / "sync-demande").exists()


def test_sans_pythonw_configure_journalise(espion, monkeypatch, tmp_path):
    monkeypatch.delenv("PILOTAGE_RACINE_LOCALE")  # profil isolé par conftest : config absente
    _commun.declencher_sync("SessionEnd")
    assert espion.appels == []
    journal = chemins.attente() / "journal"
    assert str(journal).startswith(str(tmp_path))
    assert [ligne.split(" ", 1)[1] for f in journal.glob("hooks-*.log")
            for ligne in f.read_text("utf-8").splitlines()] == ["SessionEnd SyncSansPythonw"]


def test_pythonw_introuvable(installe, espion, monkeypatch, racine_locale_isolee, tmp_path):
    monkeypatch.setenv(chemins.VARIABLE_PYTHONW, str(tmp_path / "absent.exe"))
    _commun.declencher_sync("SessionStart")
    assert espion.appels == []
    assert _journal(racine_locale_isolee) == ["SessionStart SyncSansPythonw"]


def test_pythonw_relatif_ignore(installe, espion, monkeypatch, racine_locale_isolee):
    monkeypatch.setenv(chemins.VARIABLE_PYTHONW, "pythonw.exe")
    _commun.declencher_sync("SessionStart")
    assert espion.appels == []
    assert _journal(racine_locale_isolee) == ["SessionStart SyncCheminRelatif"]
    assert not (racine_locale_isolee / "attente" / "sync-demande").exists()


def test_vrai_lanceur_sous_une_racine_installee(tmp_path):
    """Le lanceur réel, copié avec `pilotage/` comme une installation, démarre sous `-I` depuis
    un autre dossier (la commande des hooks, sans lancer de cycle : `sync --help`)."""
    import shutil

    from tests.test_imports import RACINE_DEPOT

    installation = tmp_path / "installation"
    installation.mkdir()
    shutil.copy2(RACINE_DEPOT / "lancer.py", installation / "lancer.py")
    shutil.copytree(RACINE_DEPOT / "pilotage", installation / "pilotage",
                    ignore=shutil.ignore_patterns("__pycache__"))
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    resultat = subprocess.run(
        [sys.executable, "-I", str(installation / "lancer.py"), "sync", "--help"],
        capture_output=True, cwd=ailleurs, check=False,
    )
    assert resultat.returncode == 0, resultat.stderr.decode("utf-8", "replace")
    assert b"usage: lancer.py sync" in resultat.stdout


def test_lanceur_absent(installe, espion, racine_locale_isolee):
    (installe[0] / "lancer.py").unlink()
    _commun.declencher_sync("SessionEnd")
    assert espion.appels == []
    assert _journal(racine_locale_isolee) == ["SessionEnd SyncSansLanceur"]
    assert not (racine_locale_isolee / "attente" / "sync-demande").exists()


# --- Branchement dans le cycle de session -------------------------------------------------


def test_demarrer_et_terminer_lancent_la_synchro(racine, installe, espion):  # noqa: F811
    payload = _payload("SessionStart-startup", racine)
    cycle.demarrer(payload)
    assert _etat(racine, payload["session_id"]).is_file()
    assert len(espion.appels) == 1
    cycle.terminer(_payload("SessionEnd-other", racine, payload["session_id"]))
    assert len(espion.appels) == 2
    assert all(a[-1] == "sync" for a, _ in espion.appels)


def test_sous_agent_et_dossier_non_suivi_ne_lancent_rien(racine, installe, espion):  # noqa: F811
    cycle.demarrer(_payload("SessionStart-startup", racine, agent_id="a1"))
    cycle.demarrer(_payload("SessionStart-startup", racine, cwd=str(racine / "github" / "x")))
    cycle.terminer(_payload("SessionEnd-other", racine))  # session sans état : rien à clore
    cycle.terminer(_payload("SessionEnd-other", racine, agent_id="a1"))
    assert espion.appels == []
    assert not (racine / "attente" / "sync-demande").exists()


def test_etat_non_ecrit_pas_de_synchro(racine, installe, espion):  # noqa: F811
    payload = _payload("SessionStart-startup", racine)
    with _commun.verrou(payload["session_id"]), pytest.raises(_commun.VerrouOccupe):
        cycle.demarrer(payload)
    assert espion.appels == []


# --- Bout en bout : vrai hook, vrai lancement détaché d'un lanceur factice ----------------


def _attendre(chemin, delai=20.0):
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        if chemin.is_file() and chemin.stat().st_size:
            return json.loads(chemin.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise AssertionError(f"{chemin} jamais écrit")


@pytest.mark.parametrize("hook", [START, END])
def test_hook_reel_lance_le_lanceur_detache(racine, monkeypatch, hook):  # noqa: F811
    installation = racine / "installation"
    temoin = racine / f"temoin-{hook.stem}.json"
    (installation / "lancer.py").write_text(
        "import json, os, sys\n"
        f"open({str(temoin)!r} + '.tmp', 'w').write(json.dumps("
        "{'argv': sys.argv, 'cwd': os.getcwd(), 'isole': sys.flags.isolated}))\n"
        f"os.replace({str(temoin)!r} + '.tmp', {str(temoin)!r})\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(chemins.VARIABLE_PYTHONW, PYTHON)
    session = str(uuid.uuid4())
    debut = _payload("SessionStart-startup", racine, session)
    if hook == END:
        monkeypatch.delenv(chemins.VARIABLE_PYTHONW)  # SessionStart sans lancement
        _sans_sortie(_lancer(START, debut))
        assert _etat(racine, session).is_file()
        monkeypatch.setenv(chemins.VARIABLE_PYTHONW, PYTHON)
        debut = _payload("SessionEnd-other", racine, session)
    _sans_sortie(_lancer(hook, debut))
    vu = _attendre(temoin)
    assert vu["argv"] == [str(installation / "lancer.py"), "sync"]
    assert os.path.normcase(vu["cwd"]) == os.path.normcase(str(installation))
    assert vu["isole"] == 1
    assert (racine / "attente" / "sync-demande").is_file()
    # Un job Windows sans droit de breakaway (runner de CI) : le nouvel essai réussit et le note.
    assert [ligne for ligne in _journal(racine) if not ligne.endswith(" SyncSansBreakaway")] == []


def test_journal_de_secours_si_config_invalide(monkeypatch, tmp_path):
    monkeypatch.delenv("PILOTAGE_RACINE_LOCALE")
    config = chemins.chemin_config()
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"pythonw": "pythonw.exe"}), encoding="utf-8")
    _commun.declencher_sync("Stop")  # ne lève pas, rien lancé
    journal = chemins.attente_de_secours() / "journal"
    (fichier,) = journal.glob("hooks-*.log")
    assert fichier.read_text(encoding="utf-8").rstrip().endswith("Stop ErreurConfiguration")
