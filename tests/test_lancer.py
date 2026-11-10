import subprocess
import sys

import pytest

import lancer
from tests.test_imports import RACINE_DEPOT


def test_quatre_sous_commandes():
    assert list(lancer.SOUS_COMMANDES) == ["scan", "sync", "appli", "installer-reglages"]


def test_appli_option_inconnue_rend_2(capsys):
    with pytest.raises(SystemExit) as exc:
        lancer.main(["appli", "--option", "x"])
    assert exc.value.code == 2
    assert "usage: lancer.py appli" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["inconnue"]])
def test_commande_absente_ou_inconnue(capsys, argv):
    with pytest.raises(SystemExit) as exc:
        lancer.main(argv)
    assert exc.value.code == 2
    assert "usage: lancer.py" in capsys.readouterr().err


def test_execution_en_script():
    resultat = subprocess.run(
        [sys.executable, str(RACINE_DEPOT / "lancer.py"), "sync", "--option-inconnue"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=RACINE_DEPOT,
        check=False,
    )
    assert resultat.returncode == 2  # erreur d'argparse : aucun cycle lancé
    assert "usage: lancer.py sync" in resultat.stderr


@pytest.mark.parametrize("argv", [["--help"], ["sync", "--help"], ["installer-reglages", "--help"]])
def test_execution_isolee_depuis_un_autre_dossier(tmp_path, argv):
    """Story 3.5 : la tâche planifiée lance `pythonw -I lancer.py sync` (pas de dossier du script
    dans sys.path sous -I) : `pilotage` doit rester importable, quel que soit le dossier courant."""
    resultat = subprocess.run(
        [sys.executable, "-I", str(RACINE_DEPOT / "lancer.py"), *argv],
        capture_output=True,
        cwd=tmp_path,
        check=False,
    )  # octets : sous -I, PYTHONIOENCODING est ignoré (page de code de la console)
    assert resultat.returncode == 0, resultat.stderr.decode("utf-8", "replace")
    assert b"usage: lancer.py" in resultat.stdout
