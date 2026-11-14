"""Banc `outils/bench_hooks.py` : centiles et petit passage réel sous racine temporaire."""

import importlib.util
from pathlib import Path

import pytest

CHEMIN = Path(__file__).resolve().parent.parent / "outils" / "bench_hooks.py"
_spec = importlib.util.spec_from_file_location("bench_hooks", CHEMIN)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def test_centile():
    valeurs = [float(v) for v in range(1, 101)]
    assert bench.centile(valeurs, 50) == pytest.approx(50.5)
    assert bench.centile(valeurs, 95) == pytest.approx(95.05)
    assert bench.centile([7.0], 95) == 7.0
    with pytest.raises(ValueError, match="aucune mesure"):
        bench.centile([], 95)


def test_passage_reel(capsys):
    code = bench.main(["--appels", "3"])
    sortie = capsys.readouterr().out
    assert code in (0, 2)  # 2 : budget dépassé sur un poste chargé, pas une erreur du banc
    assert all(f"{h} : p50 " in sortie for h in bench.HOOKS)
    assert "(2 appels à chaud)" in sortie
    assert "erreurs journalisées" not in sortie


def test_appels_minimum():
    with pytest.raises(SystemExit):
        bench.main(["--appels", "1"])


def test_messages_negatif_refuse():
    with pytest.raises(SystemExit):
        bench.main(["--appels", "2", "--messages", "-1"])


@pytest.mark.parametrize("messages", [0, 4])
def test_passage_reel_avec_messages(capsys, messages):
    code = bench.main(["--appels", "2", "--messages", str(messages)])
    sortie = capsys.readouterr().out
    assert code in (0, 2)
    assert "session_start : p50 " in sortie
    assert "erreurs journalisées" not in sortie


def test_messages_du_banc_valides(tmp_path):
    from pilotage.noyau import schemas

    bench.deposer_messages(tmp_path, 3)
    fichiers = sorted((tmp_path / "donnees" / "boite" / "bench").iterdir())
    assert [f.stem for f in fichiers] == bench.ids_messages(3)
    for fichier in fichiers:
        schemas.valider("message", __import__("json").loads(fichier.read_text(encoding="utf-8")))


def test_passage_reel_avec_operations_d_autres_projets(capsys):
    code = bench.main(["--appels", "2", "--messages", "3", "--operations-autres", "50"])
    sortie = capsys.readouterr().out
    assert code in (0, 2)
    assert "erreurs journalisées" not in sortie


# --- Story 8.1 : scénario « 20 états et 3 messages » ------------------------------------------


def test_scenario_vingt_etats_et_trois_messages(capsys):
    """SessionStart relit les 20 états, injecte la note la plus récente et les 3 messages (le
    banc vérifie la note et les acquittements à chaque appel, sinon il lève)."""
    code = bench.main(["--appels", "2", "--etats", "20", "--messages", "3"])
    sortie = capsys.readouterr().out
    assert code in (0, 2)
    assert "session_start : p50 " in sortie
    assert "erreurs journalisées" not in sortie


def test_defaut_vingt_etats():
    assert bench.ETATS_PAR_DEFAUT == 20


@pytest.mark.parametrize("etats", ["-1", str(24 * 28 + 1)])
def test_etats_hors_bornes_refuses(etats):
    with pytest.raises(SystemExit):
        bench.main(["--appels", "2", "--etats", etats])


def test_etats_du_banc_valides_et_plus_recents(tmp_path):
    import json
    import os
    import time

    from pilotage.noyau import schemas

    bench.deposer_etats(tmp_path, 20)
    fichiers = sorted((tmp_path / "donnees" / "etat" / "bench").rglob("*.json"))
    assert len(fichiers) == 20
    assert {f.parent.name for f in fichiers} == set(bench.PCS_AUTRES)
    for fichier in fichiers:
        objet = json.loads(fichier.read_text(encoding="utf-8"))
        schemas.valider("session", objet)
        assert (objet["pc"], f"{objet['session']}.json") == (fichier.parent.name, fichier.name)
        assert objet["reprise"] and len(objet["reprise"]) <= 300
        assert os.stat(fichier).st_mtime > time.time()  # restent les plus récents
