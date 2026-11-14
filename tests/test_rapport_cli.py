"""Story 9.2 : `lancer.py rapport` (`pilotage.rapport.cli`), sous `PILOTAGE_RACINE_LOCALE`."""

import ast
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

import lancer
from pilotage import chemins
from pilotage.rapport import cli

MAINTENANT = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
SOURCE_CLI = Path(cli.__file__).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def poste(monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "pc-local")
    chemins.racine_github().mkdir(parents=True, exist_ok=True)


def arbre() -> set[Path]:
    return set(chemins.racine_locale().rglob("*"))


def test_rapport_ecrit_et_chemin_relatif_affiche(capsys):
    assert lancer.main(["rapport", "--semaine", "2026-W46"]) == 0
    sortie = capsys.readouterr()
    assert sortie.out == "rapports/semaine-2026-W46.html\n"
    assert sortie.err == ""
    cible = chemins.racine_locale() / "rapports" / "semaine-2026-W46.html"
    contenu = cible.read_text(encoding="utf-8")
    assert contenu.startswith("<!doctype html>")
    assert "<title>Semaine 2026-W46</title>" in contenu
    assert list(cible.parent.glob("*.tmp")) == []
    assert all(p.is_relative_to(chemins.racine_locale()) for p in arbre())


def test_semaine_53_existante(capsys):
    assert cli.main(["--semaine", "2026-W53"], MAINTENANT) == 0
    assert capsys.readouterr().out == "rapports/semaine-2026-W53.html\n"


@pytest.mark.parametrize("semaine", ["2026-46", "2026-W54", "2026-W00", "2021-W53", "26-W01"])
def test_semaine_invalide_code_2_rien_ecrit(capsys, semaine):
    avant = arbre()
    assert cli.main(["--semaine", semaine], MAINTENANT) == 2
    sortie = capsys.readouterr()
    assert sortie.out == ""
    assert sortie.err == "rapport : semaine ISO AAAA-Www attendue (semaine existante)\n"
    assert arbre() == avant
    assert not chemins.rapports().exists()


@pytest.mark.parametrize(
    ("local", "attendue"),
    [
        (datetime(2026, 11, 15, 23, 30), "2026-W46"),  # dimanche soir local
        (datetime(2026, 11, 16, 0, 30), "2026-W47"),  # lundi matin local
        (datetime(2027, 1, 1, 12, 0), "2026-W53"),
    ],
)
def test_semaine_par_defaut_en_heure_locale(capsys, local, attendue):
    instant = local.astimezone().astimezone(UTC)  # même instant, vu en UTC
    assert cli.semaine_courante(instant) == attendue
    assert cli.main([], instant) == 0
    assert capsys.readouterr().out == f"rapports/semaine-{attendue}.html\n"


def test_erreur_d_ecriture_code_1_sans_tmp_ni_chemin(capsys):
    cible = chemins.rapport_semaine("2026-W46")
    cible.mkdir(parents=True)  # un dossier à la place de la page : `os.replace` échoue
    assert cli.main(["--semaine", "2026-W46"], MAINTENANT) == 1
    sortie = capsys.readouterr()
    assert sortie.out == ""
    assert sortie.err.startswith(f"{cli.ERREUR} (")
    assert sortie.err.rstrip().endswith("Error)")
    assert str(chemins.racine_locale()) not in sortie.err and "rapports" not in sortie.err
    assert list(chemins.rapports().glob("*.tmp")) == []
    assert cible.is_dir() and list(cible.iterdir()) == []


def test_rapports_est_un_fichier_code_1(capsys):
    chemins.racine_locale().mkdir(parents=True, exist_ok=True)
    chemins.rapports().write_text("x", encoding="utf-8")
    assert cli.main(["--semaine", "2026-W46"], MAINTENANT) == 1
    assert capsys.readouterr().err.startswith(cli.ERREUR)
    assert chemins.rapports().read_text(encoding="utf-8") == "x"


def test_charte_refusee_code_1_rien_ecrit(capsys, monkeypatch, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "charte.css").write_text("a{background:url(https://exemple.test/x)}",
                                    encoding="utf-8")
    monkeypatch.setattr(chemins, "racine_web", lambda: web)  # emplacement du fichier seulement
    assert cli.main(["--semaine", "2026-W46"], MAINTENANT) == 1
    sortie = capsys.readouterr()
    assert sortie.err == f"{cli.ERREUR} (ValueError)\n"
    assert "exemple" not in sortie.err
    assert not chemins.rapports().exists()


def test_alerte_ancienne_avec_chemin_masquee(capsys):
    racine = str(chemins.racine_github())
    message = f"échec dans {racine}{os.sep}projet"
    alerte = {"source": "scan", "code": "inconnue-a", "message": message}
    chemins.ecrire_atomique(chemins.alertes_json(), json.dumps({"schema": 1, "alertes": [alerte]}))
    assert cli.main(["--semaine", "2026-W46"], MAINTENANT) == 0
    capsys.readouterr()
    contenu = chemins.rapport_semaine("2026-W46").read_text(encoding="utf-8")
    assert "<li>échec dans {{RACINE_GITHUB}}" in contenu
    assert racine not in contenu


def test_aide_rend_0(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "--semaine" in capsys.readouterr().out


def test_cli_sans_reseau_et_git_par_lecture_seulement():
    arbre_ = ast.parse(SOURCE_CLI)
    modules = set()
    for noeud in ast.walk(arbre_):
        if isinstance(noeud, ast.Import):
            modules |= {a.name.split(".")[0] for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom):
            modules.add((noeud.module or "").split(".")[0])
    assert not modules & {"socket", "urllib", "http", "asyncio", "ssl"}
    usages = {n.attr for n in ast.walk(arbre_) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "subprocess"}
    assert usages == {"SubprocessError"}  # aucun lancement : `git` vient de `lecture`


def test_rapports_hors_attente_et_donnees():
    assert chemins.rapports().parent == chemins.racine_locale()
    assert not chemins.rapports().is_relative_to(chemins.attente())
    assert not chemins.rapports().is_relative_to(chemins.donnees())
