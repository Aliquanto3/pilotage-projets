"""Fixtures de payloads de hooks : assainies, valides, cas non observés marqués."""

import json
import os
import re
from pathlib import Path

import pytest

DOSSIER = Path(__file__).parent / "fixtures" / "payloads"
FICHIERS = sorted(c for c in DOSSIER.iterdir() if c.is_file() and c.name != "LISEZMOI.md")
FIXTURES = [c for c in FICHIERS if c.suffix == ".json"]
SUFFIXE = "-a-confirmer.json"
# Chemins personnels, quelle que soit la machine (seule garde active en CI) : lecteur + Users
# (`C:\Users`, `D:/Users`), Git Bash (`/c/Users`), segment `\Users\` sans lecteur, slug de
# projet Claude (`C--Users`).
CHEMIN_PERSONNEL = re.compile(
    r"[a-z]:[\\/]+users\b|/[a-z]/users\b|[\\/]users[\\/]|[a-z]--users\b",
    re.IGNORECASE,
)


def _texte(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def _chaines(objet):
    if isinstance(objet, str):
        yield objet
    elif isinstance(objet, dict):
        for cle, valeur in objet.items():
            yield cle
            yield from _chaines(valeur)
    elif isinstance(objet, list):
        for valeur in objet:
            yield from _chaines(valeur)


def test_des_fixtures_existent():
    assert len(FIXTURES) >= 15


def test_aucun_autre_format():
    assert FICHIERS == FIXTURES, "seuls des .json (et LISEZMOI.md) dans le dossier"


@pytest.mark.parametrize(
    "texte",
    [
        "C:\\Users\\x",
        "C:\\\\Users\\\\x",
        "D:/Users/x",
        "/c/Users/x",
        "\\\\Users\\\\x",
        "C--Users-x-projet",
    ],
)
def test_motif_chemin_personnel_detecte(texte):
    assert CHEMIN_PERSONNEL.search(texte)


@pytest.mark.parametrize("chemin", FICHIERS, ids=lambda c: c.name)
def test_aucun_nom_d_utilisateur_ni_chemin_personnel(chemin):
    texte = _texte(chemin).lower()
    assert not CHEMIN_PERSONNEL.search(texte)
    # Garde locale : en CI ces variables valent `runneradmin` et une machine jetable, seuls les
    # motifs ci-dessus tiennent. Le vrai nom n'est jamais écrit dans le dépôt (voir LISEZMOI.md).
    for variable in ("USERNAME", "USER", "COMPUTERNAME"):
        valeur = os.environ.get(variable, "")
        if len(valeur) >= 3:
            assert valeur.lower() not in texte, variable


@pytest.mark.parametrize("chemin", FIXTURES, ids=lambda c: c.name)
def test_aucun_caractere_de_controle(chemin):
    for chaine in _chaines(json.loads(_texte(chemin))):
        assert not any(ord(c) < 0x20 for c in chaine), repr(chaine)


@pytest.mark.parametrize("chemin", FIXTURES, ids=lambda c: c.name)
def test_json_valide_avec_evenement(chemin):
    objet = json.loads(_texte(chemin))
    assert isinstance(objet, dict)
    assert isinstance(objet.get("hook_event_name"), str) and objet["hook_event_name"]
    assert chemin.name.startswith(objet["hook_event_name"] + "-")


@pytest.mark.parametrize("chemin", FIXTURES, ids=lambda c: c.name)
def test_marquage_a_confirmer(chemin):
    objet = json.loads(_texte(chemin))
    suffixe = chemin.name.endswith(SUFFIXE)
    marque = objet.get("_statut") == "a_confirmer"
    assert suffixe == marque, "suffixe et champ _statut vont ensemble"
    if not marque:
        assert "_statut" not in objet


def test_cas_a_confirmer_attendus():
    noms = {c.name for c in FIXTURES if c.name.endswith(SUFFIXE)}
    assert noms == {
        "Notification-askuserquestion-a-confirmer.json",
        "Notification-permission-a-confirmer.json",
        "SessionStart-clear-a-confirmer.json",
        "SessionStart-compact-a-confirmer.json",
    }
    permission = json.loads(_texte(DOSSIER / "Notification-permission-a-confirmer.json"))
    assert permission["notification_type"] == "permission_prompt"
    for source in ("clear", "compact"):
        objet = json.loads(_texte(DOSSIER / f"SessionStart-{source}-a-confirmer.json"))
        assert objet["source"] == source
