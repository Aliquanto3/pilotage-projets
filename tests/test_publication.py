"""Garde de publication : l'arbre suivi ne contient ni identité ni chemin personnel.

Les motifs sont construits par concaténation pour que ce fichier ne se déclenche pas lui-même.
Chaque ligne est comparée sans marques combinantes (formes NFC et NFD) et sans tenir compte de
la casse.
"""

import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
SUFFIXES_BINAIRES = {".woff2", ".woff", ".ttf", ".otf", ".png", ".jpg", ".jpeg", ".gif", ".ico"}
PROPRIETAIRE_AUTORISE = {"README.md", "LICENSE", "pyproject.toml"}
# `_bmad-output/` (historique privé) n'est exempté que si ce marqueur existe : sans lui, la
# garde couvre aussi ce dossier.
MARQUEUR_ARCHIVE = "_bmad-output/.archive-privee"

MOTIF_CHEMIN = re.compile("users" + r"[\\/]+" + "utilis" + "ateur", re.IGNORECASE)
MOTIF_PROPRIETAIRE = re.compile("aliquan" + "to3", re.IGNORECASE)
MOTIF_PRENOM = re.compile("ana" + "el", re.IGNORECASE)
MOTIF_MAIL = re.compile("@gm" + "ail" + r"\.com", re.IGNORECASE)
ALIAS_PROTOCOLE = "attend-" + "ana" + "el"
_ALIAS = re.compile(re.escape(ALIAS_PROTOCOLE), re.IGNORECASE)


def _en_ci() -> bool:
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def _sauter_ou_echouer(raison: str) -> None:
    """Hors CI, saut ; en CI, l'absence de contrôle est un échec."""
    if _en_ci():
        pytest.fail(f"garde de publication impossible en CI : {raison}")
    pytest.skip(raison)


def _fichiers_suivis() -> list[str]:
    if shutil.which("git") is None:
        _sauter_ou_echouer("git absent")
    res = subprocess.run(
        ["git", "ls-files", "-z"], cwd=RACINE, capture_output=True, check=False
    )
    if res.returncode != 0:
        _sauter_ou_echouer("pas un dépôt git")
    return [n for n in res.stdout.decode("utf-8").split("\0") if n]


def _ignore(nom: str, racine: Path = RACINE) -> bool:
    if nom.startswith("_bmad-output/") and (racine / MARQUEUR_ARCHIVE).is_file():
        return True
    return Path(nom).suffix.lower() in SUFFIXES_BINAIRES or nom == "tests/test_publication.py"


def _forme_comparee(ligne: str) -> str:
    """Sans marques combinantes (« ë » en NFC ou en NFD devient « e »)."""
    decomposee = unicodedata.normalize("NFD", ligne)
    return "".join(c for c in decomposee if not unicodedata.combining(c))


def trouver(nom: str, texte: str) -> list[str]:
    """Constats `fichier:ligne : motif` d'un fichier suivi (fonction pure, testée)."""
    constats = []
    for numero, brute in enumerate(texte.splitlines(), start=1):
        ligne = _forme_comparee(brute)
        if MOTIF_CHEMIN.search(ligne):
            constats.append(f"{nom}:{numero} : chemin personnel")
        if nom not in PROPRIETAIRE_AUTORISE and MOTIF_PROPRIETAIRE.search(ligne):
            constats.append(f"{nom}:{numero} : propriétaire GitHub")
        if MOTIF_PRENOM.search(_ALIAS.sub("", ligne)):
            constats.append(f"{nom}:{numero} : prénom")
        if MOTIF_MAIL.search(ligne):
            constats.append(f"{nom}:{numero} : adresse e-mail")
    return constats


def test_arbre_suivi_sans_identite():
    constats: list[str] = []
    for nom in _fichiers_suivis():
        if _ignore(nom):
            continue
        chemin = RACINE / nom
        if not chemin.is_file():
            continue
        constats += trouver(nom, chemin.read_bytes().decode("utf-8", errors="replace"))
    assert not constats, "\n".join(constats)


def test_motifs_detectent_et_tolerent():
    prenom = "Ana" + "ël"
    assert trouver("x.py", f"nom = '{prenom}'") == ["x.py:1 : prénom"]
    nfd = unicodedata.normalize("NFD", prenom)
    assert nfd != prenom
    assert trouver("x.py", f"nom = '{nfd}'") == ["x.py:1 : prénom"]
    assert trouver("x.py", "a\nANA" + "EL") == ["x.py:2 : prénom"]
    assert trouver("x.py", f"ACTION = '{ALIAS_PROTOCOLE}'") == []
    assert trouver("x.py", "C:/Users/" + "Utilis" + "ateur/x") == ["x.py:1 : chemin personnel"]
    assert trouver("x.py", "c:/users/" + "utilis" + "ateur/x") == ["x.py:1 : chemin personnel"]
    assert trouver("x.py", "C:\\Users\\" + "Utilis" + "ateur") == ["x.py:1 : chemin personnel"]
    assert trouver("x.py", "Aliquan" + "to3/depot") == ["x.py:1 : propriétaire GitHub"]
    assert trouver("README.md", "Aliquan" + "to3/depot") == []
    assert trouver("x.py", "a@gm" + "ail.com") == ["x.py:1 : adresse e-mail"]
    assert trouver("x.py", "rien") == []


def test_archive_privee_exemptee_seulement_avec_son_marqueur(tmp_path):
    nom = "_bmad-output/specs/x.md"
    assert not _ignore(nom, tmp_path)
    marqueur = tmp_path / MARQUEUR_ARCHIVE
    marqueur.parent.mkdir(parents=True)
    marqueur.write_text("x\n", encoding="utf-8")
    assert _ignore(nom, tmp_path)
    assert not _ignore("docs/x.md", tmp_path)
    assert _ignore("pilotage/web/polices/a.woff2", tmp_path)


def test_garde_echoue_en_ci_sans_git(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _nom: None)
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception):
        _fichiers_suivis()
    monkeypatch.delenv("CI")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _fichiers_suivis()
