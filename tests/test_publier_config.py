"""Story 2.8 : `outils/publier_config.py`, sur des dépôts git temporaires (tag créé dans tmp)."""

import subprocess
from pathlib import Path

import pytest

from outils import publier_config


def _git(depot: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(depot), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True,
    )


def _ecrire(racine: Path, relatif: str, texte: str) -> None:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(texte.encode("utf-8"))


@pytest.fixture
def depots(tmp_path):
    """(source avec tag v0.1.0, claude-config propre avec un runtime obsolète)."""
    source = tmp_path / "pilotage-projets"
    source.mkdir()
    _git(source, "init", "-q")
    fichiers = {
        "pilotage/__init__.py": "",
        "pilotage/hooks/stop.py": "# stop\n",
        "lancer.py": "# lancer\n",
        "pyproject.toml": "[project]\n",
        "uv.lock": "version = 1\n",
        "VERSION": "0.1.0\n",
        "hooks-pilotage.json": "{}\n",
        "regle-marqueur.md": "règle é\n",
        "README.md": "hors runtime\n",
        "tests/test_x.py": "hors runtime\n",
        "outils/publier_config.py": "hors runtime\n",
    }
    for relatif, texte in fichiers.items():
        _ecrire(source, relatif, texte)
    _git(source, "add", "-A")
    _git(source, "commit", "-q", "-m", "v0.1.0")
    _git(source, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
    config = tmp_path / "claude-config"
    config.mkdir()
    _git(config, "init", "-q")
    _ecrire(config, "sync.ps1", "# sync\n")
    _ecrire(config, "claude/settings.json", "{}\n")
    _ecrire(config, "claude/pilotage/pilotage/ancien.py", "# obsolète\n")
    _git(config, "add", "-A")
    _git(config, "commit", "-q", "-m", "init")
    return source, config


def _arbre(racine: Path) -> dict[str, bytes]:
    return {
        f.relative_to(racine).as_posix(): f.read_bytes() for f in racine.rglob("*") if f.is_file()
    }


def test_publie_le_tag_en_miroir(depots, capsys):
    source, config = depots
    # la copie de travail modifiée après le tag n'est pas lue : le tag fait foi
    _ecrire(source, "lancer.py", "# après le tag\n")
    _git(source, "commit", "-q", "-am", "après")
    (source / "pilotage" / "__pycache__").mkdir()
    (source / "pilotage" / "__pycache__" / "x.pyc").write_bytes(b"pyc")
    (source / ".venv").mkdir()
    (source / ".venv" / "pyvenv.cfg").write_bytes(b"")
    _ecrire(source, ".gitignore", "__pycache__/\n.venv/\n")
    _git(source, "add", ".gitignore")
    _git(source, "commit", "-q", "-m", "ignore")
    code = publier_config.main(["v0.1.0", "--vers", str(config), "--depot", str(source)])
    assert code == 0
    cible = config / "claude" / "pilotage"
    assert _arbre(cible) == {
        "pilotage/__init__.py": b"",
        "pilotage/hooks/stop.py": b"# stop\n",
        "lancer.py": b"# lancer\n",
        "pyproject.toml": b"[project]\n",
        "uv.lock": b"version = 1\n",
        "VERSION": b"0.1.0\n",
        "hooks-pilotage.json": b"{}\n",
        "regle-marqueur.md": "règle é\n".encode(),
    }
    assert capsys.readouterr().out == (
        f"v0.1.0 publié dans {cible} (8 fichiers) ; à commiter dans claude-config\n"
    )
    assert (config / "claude" / "settings.json").read_bytes() == b"{}\n"
    assert sorted(p.name for p in config.iterdir()) == [".git", "claude", "sync.ps1"]
    # deuxième publication sur la copie (désormais sale) : refusée
    assert publier_config.main(["v0.1.0", "--vers", str(config), "--depot", str(source)]) == 1


@pytest.mark.parametrize("tag", ["0.1.0", "v0.1", "v01.0.0", "v0.1.0-rc1", "main", ""])
def test_tag_non_semver_refuse(depots, tag, capsys):
    source, config = depots
    avant = _arbre(config / "claude")
    assert publier_config.main([tag, "--vers", str(config), "--depot", str(source)]) == 1
    assert "tag non SemVer" in capsys.readouterr().err
    assert _arbre(config / "claude") == avant


def test_tag_absent_refuse(depots, capsys):
    source, config = depots
    assert publier_config.main(["v9.9.9", "--vers", str(config), "--depot", str(source)]) == 1
    erreur = capsys.readouterr().err
    assert "tag absent" in erreur and erreur.endswith("rien n'a été écrit\n")
    assert (config / "claude" / "pilotage" / "pilotage" / "ancien.py").exists()


def test_version_differente_du_tag_refusee(depots, capsys):
    source, config = depots
    _git(source, "tag", "-a", "v0.2.0", "-m", "v0.2.0")
    assert publier_config.main(["v0.2.0", "--vers", str(config), "--depot", str(source)]) == 1
    assert "VERSION du tag ('0.1.0') différent du tag v0.2.0" in capsys.readouterr().err


def test_fichier_du_runtime_absent_du_tag_refuse(depots, capsys):
    source, config = depots
    _git(source, "rm", "-q", "regle-marqueur.md")
    _git(source, "commit", "-q", "-m", "sans règle")
    _git(source, "tag", "-a", "v0.1.1", "-m", "x")
    _ecrire(source, "VERSION", "0.1.1\n")
    _git(source, "commit", "-q", "-am", "version")
    assert publier_config.main(["v0.1.1", "--vers", str(config), "--depot", str(source)]) == 1
    assert "git archive v0.1.1 a échoué" in capsys.readouterr().err


@pytest.mark.parametrize("sale", ["source", "claude-config"])
def test_copie_de_travail_sale_refusee(depots, sale, capsys):
    source, config = depots
    _ecrire(source if sale == "source" else config, "nouveau.txt", "x\n")
    assert publier_config.main(["v0.1.0", "--vers", str(config), "--depot", str(source)]) == 1
    assert f"{sale} : copie de travail sale" in capsys.readouterr().err
    assert (config / "claude" / "pilotage" / "pilotage" / "ancien.py").exists()


def test_cible_sans_sync_ps1_refusee(depots, tmp_path, capsys):
    source, _ = depots
    autre = tmp_path / "autre"
    autre.mkdir()
    assert publier_config.main(["v0.1.0", "--vers", str(autre), "--depot", str(source)]) == 1
    assert "n'est pas un claude-config" in capsys.readouterr().err
    assert list(autre.iterdir()) == []


def test_cible_hors_git_refusee(depots, tmp_path, capsys):
    source, _ = depots
    autre = tmp_path / "autre"
    _ecrire(autre, "sync.ps1", "")
    assert publier_config.main(["v0.1.0", "--vers", str(autre), "--depot", str(source)]) == 1
    assert "n'est pas un dépôt git" in capsys.readouterr().err


def test_liste_du_runtime_conforme_a_ad8():
    assert publier_config.RUNTIME == (
        "pilotage", "lancer.py", "pyproject.toml", "uv.lock", "VERSION",
        "hooks-pilotage.json", "regle-marqueur.md",
    )


def test_republication_remplace_et_remet_l_ancienne_si_echec(depots, monkeypatch):
    source, config = depots
    cible = config / "claude" / "pilotage"
    original = Path.replace

    def remplacer(self, autre):
        # le déplacement de la préparation vers la cible échoue (fichier verrouillé)
        if Path(autre) == cible and self.name == "pilotage":
            raise PermissionError("verrouillé")
        return original(self, autre)

    monkeypatch.setattr(Path, "replace", remplacer)
    assert publier_config.main(["v0.1.0", "--vers", str(config), "--depot", str(source)]) == 1
    assert _arbre(cible) == {"pilotage/ancien.py": "# obsolète\n".encode()}
    assert sorted(p.name for p in config.iterdir()) == [".git", "claude", "sync.ps1"]


def test_vers_obligatoire(depots, capsys):
    source, _ = depots
    with pytest.raises(SystemExit) as sortie:
        publier_config.main(["v0.1.0", "--depot", str(source)])
    assert sortie.value.code == 2
