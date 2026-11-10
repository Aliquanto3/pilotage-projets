"""Outil `outils/evaluer_heuristique.py` : rappel et précision sur un mini-jeu sous `tmp_path`."""

import importlib.util
import json
from pathlib import Path

import pytest

CHEMIN = Path(__file__).resolve().parent.parent / "outils" / "evaluer_heuristique.py"
_spec = importlib.util.spec_from_file_location("evaluer_heuristique", CHEMIN)
outil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(outil)


def _stop(message, attente):
    payload = {"hook_event_name": "Stop", "last_assistant_message": message}
    return {"payload": payload, "attente": attente}


def _jeu(tmp_path, lignes):
    chemin = tmp_path / "jeu.jsonl"
    texte = "\n".join(json.dumps(x) if isinstance(x, dict) else x for x in lignes)
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def test_rappel_et_precision(tmp_path, capsys):
    notif = {"hook_event_name": "Notification", "notification_type": "permission_prompt",
             "message": "permission to use Bash"}
    chemin = _jeu(tmp_path, [
        _stop("On continue ?", True),  # VP
        _stop("Je te laisse choisir ?", True),  # VP
        _stop("Que fait ce code ? Voici.", True),  # FN : question non finale
        _stop("Tu vois ce que je veux dire ?", False),  # FP
        _stop("Terminé.", False),  # VN
        {"payload": notif, "attente": True},  # VP
        "",
    ])
    assert outil.main([str(chemin)]) == 2
    sortie = capsys.readouterr().out
    assert "6 cas : VP 3, FP 1, FN 1, VN 1" in sortie
    assert "rappel 75.0 %, précision 75.0 %" in sortie


def test_denominateurs_nuls(tmp_path, capsys):
    chemin = _jeu(tmp_path, [_stop("Terminé.", False)])
    assert outil.main([str(chemin)]) == 2
    assert "rappel n/a, précision n/a" in capsys.readouterr().out


@pytest.mark.parametrize(("ligne", "message"), [
    ("pas du json", "ligne 1 : JSON invalide"),
    ('{"attente": true}', "ligne 1 : `payload` (objet) et `attente` (bool) requis"),
    ('{"payload": {}, "attente": "oui"}', "ligne 1 : `payload` (objet) et `attente` (bool)"),
    ("[1]", "ligne 1 : `payload` (objet) et `attente` (bool) requis"),
])
def test_jeu_invalide(tmp_path, capsys, ligne, message):
    assert outil.main([str(_jeu(tmp_path, [ligne]))]) == 1
    assert f"jeu illisible : {message}" in capsys.readouterr().out


def test_jeu_absent(tmp_path, capsys):
    assert outil.main([str(tmp_path / "absent.jsonl")]) == 1
    assert "jeu illisible" in capsys.readouterr().out


def test_seuils_atteints_et_non_etiquetes_ignores(tmp_path, capsys):
    lignes = [_stop("On continue ?", True)] * 10
    lignes += [_stop("Terminé.", True)]  # FN : rappel 10/11 = 90,9 %
    lignes += [_stop("Fini.", False)]
    lignes += [{"payload": {"hook_event_name": "Stop"}, "attente": None}, '{"payload": {}}']
    assert outil.main([str(_jeu(tmp_path, lignes))]) == 0
    sortie = capsys.readouterr().out
    assert "12 cas : VP 10, FP 0, FN 1, VN 1" in sortie
    assert "2 ligne(s) non étiquetée(s) ignorée(s)" in sortie
    assert "rappel 90.9 %, précision 100.0 %" in sortie
    assert "seuils atteints" in sortie


def test_seuil_de_precision_non_atteint(tmp_path, capsys):
    lignes = [_stop("On continue ?", True)] * 4 + [_stop("Tu vois ?", False)] * 2
    assert outil.main([str(_jeu(tmp_path, lignes))]) == 2
    assert "précision 66.7 %" in capsys.readouterr().out


def test_seuil_exact_precision_80(tmp_path):
    lignes = [_stop("On continue ?", True)] * 4 + [_stop("Tu vois ?", False)]
    assert outil.main([str(_jeu(tmp_path, lignes))]) == 0
