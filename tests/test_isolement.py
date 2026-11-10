"""Garde de l'isolement des tests (incident du 2026-11-06, story 5.1)."""

import os
import subprocess
from pathlib import Path

from pilotage import chemins


def test_aucun_monkeypatch_undo_dans_les_tests():
    """L'appel `undo` du monkeypatch retire aussi l'isolement : interdit dans `tests/`."""
    motif = "monkeypatch" + ".undo("
    fautifs = [
        p.name for p in Path(__file__).parent.glob("*.py")
        if motif in p.read_text(encoding="utf-8")
    ]
    assert fautifs == []


def test_sans_isolement_de_fonction_l_isolement_de_session_tient(monkeypatch, tmp_path_factory):
    """Variables du test retirées : racine sous le dossier de pytest, GitHub injoignable."""
    for cle in ("PILOTAGE_RACINE_LOCALE", "LOCALAPPDATA"):
        monkeypatch.setenv(cle, os.environ[cle])
    monkeypatch.delenv("PILOTAGE_RACINE_LOCALE")
    base = tmp_path_factory.getbasetemp().resolve()
    assert base in chemins.racine_locale().resolve().parents
    sortie = subprocess.run(
        ["git", "ls-remote", "https://github.com/Proprio-Test/donnees-test.git"],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, timeout=30,
    )
    assert sortie.returncode != 0 and "reseau-interdit" in sortie.stderr


def test_aucun_retrait_direct_d_os_environ_dans_les_tests():
    """`os.environ` se change par monkeypatch seulement (rétabli à la fin du test)."""
    motifs = ["os.environ" + s for s in (".clear(", ".pop(", ".popitem(")] + [
        "del " + "os.environ"
    ]
    fautifs = [
        (p.name, m) for p in Path(__file__).parent.glob("*.py") if p.name != "conftest.py"
        for m in motifs if m in p.read_text(encoding="utf-8")
    ]
    assert fautifs == []


def test_profil_retire_la_racine_reste_sous_pytest(monkeypatch, tmp_path_factory):
    """`delenv` de la racine, de LOCALAPPDATA, USERPROFILE et HOME : HOMEDRIVE/HOMEPATH tiennent."""
    for cle in ("PILOTAGE_RACINE_LOCALE", "LOCALAPPDATA", "USERPROFILE", "HOME"):
        monkeypatch.delenv(cle)
    base = tmp_path_factory.getbasetemp().resolve()
    assert base in chemins.racine_locale().resolve().parents


def test_session_retablie_apres_retrait_hors_monkeypatch(retablir_session):
    """`os.environ.clear` ou `pop` direct : la garde de session rétablit et signale."""
    environ = os.environ
    avant = dict(environ)
    try:
        environ.pop("GIT_CONFIG_COUNT")
        environ["GH_TOKEN"] = "faux"
        assert sorted(retablir_session()) == ["GH_TOKEN", "GIT_CONFIG_COUNT"]
        assert environ["GIT_CONFIG_COUNT"] == "2" and "GH_TOKEN" not in environ
        environ.clear()
        changees = retablir_session()
        assert "GIT_CONFIG_KEY_0" in changees and "HTTPS_PROXY" in changees
        assert environ.get("GH_CONFIG_DIR") == avant["GH_CONFIG_DIR"]
    finally:
        environ.clear()
        environ.update(avant)


def test_github_injoignable_meme_avec_la_config_git_d_un_test(monkeypatch, tmp_path):
    """Un test qui pose son `GIT_CONFIG_GLOBAL` garde le détournement de github.com."""
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = Autre\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    sortie = subprocess.run(
        ["git", "ls-remote", "https://github.com/Proprio-Test/autre.git"],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, timeout=30,
    )
    assert sortie.returncode != 0 and "reseau-interdit" in sortie.stderr
