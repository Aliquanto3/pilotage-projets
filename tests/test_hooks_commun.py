"""Socle `pilotage/hooks/_commun.py` : verrou, journal, payload, état, branche, chemins."""

import errno
import io
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import pytest

from pilotage import chemins
from pilotage.hooks import _commun
from pilotage.noyau import ids
from pilotage.noyau.schemas import ErreurValidation

SESSION = "0123abcd-0000-4000-8000-00000000abcd"


# --- verrou -------------------------------------------------------------------------------


def test_verrou_pris_puis_rendu(racine_locale_isolee):
    chemin = racine_locale_isolee / "attente" / "verrous" / f"{SESSION}.lock"
    with _commun.verrou(SESSION):
        assert re.fullmatch(rf"{os.getpid()} [0-9a-f]{{16}}", chemin.read_text(encoding="ascii"))
    assert not chemin.exists()


def test_verrou_repris_par_un_autre_n_est_pas_supprime(racine_locale_isolee):
    chemin = racine_locale_isolee / "attente" / "verrous" / f"{SESSION}.lock"
    with _commun.verrou(SESSION):
        # Simule un autre hook qui a jugé le verrou périmé et l'a repris (Windows refuse
        # d'effacer un fichier ouvert : on remplace le contenu par un autre jeton).
        chemin.write_text("4242 autre", encoding="ascii")
    assert chemin.read_text(encoding="ascii") == "4242 autre"


def test_verrou_stat_refuse_vaut_occupe(racine_locale_isolee, monkeypatch):
    chemin = racine_locale_isolee / "attente" / "verrous" / f"{SESSION}.lock"
    chemin.parent.mkdir(parents=True)
    chemin.write_text("1", encoding="ascii")

    def _refus(self, *a, **k):
        raise PermissionError(13, "refus")

    monkeypatch.setattr(Path, "stat", _refus)
    with pytest.raises(_commun.VerrouOccupe), _commun.verrou(SESSION):
        pass


def test_verrou_rendu_sur_exception(racine_locale_isolee):
    with pytest.raises(RuntimeError), _commun.verrou(SESSION):
        raise RuntimeError
    assert not (racine_locale_isolee / "attente" / "verrous" / f"{SESSION}.lock").exists()


@pytest.mark.parametrize(("essais", "minimum"), [(1, 0.020), (3, 0.060)])
def test_verrou_tenu_attend_puis_abandonne(racine_locale_isolee, essais, minimum):
    with _commun.verrou(SESSION):
        debut = time.monotonic()
        with pytest.raises(_commun.VerrouOccupe), _commun.verrou(SESSION, essais):
            pass
        duree = time.monotonic() - debut
    assert minimum <= duree < minimum + 0.5


def test_verrou_perime_repris(racine_locale_isolee):
    chemin = racine_locale_isolee / "attente" / "verrous" / f"{SESSION}.lock"
    chemin.parent.mkdir(parents=True)
    chemin.write_text("1", encoding="ascii")
    ancien = time.time() - 2.5
    os.utime(chemin, (ancien, ancien))
    with _commun.verrou(SESSION):
        assert chemin.read_text(encoding="ascii").startswith(f"{os.getpid()} ")


def test_verrou_session_invalide_refuse(racine_locale_isolee):
    with pytest.raises(ids.ErreurId), _commun.verrou("../x"):
        pass
    assert not (racine_locale_isolee / "attente").exists()


def test_constantes_m1():
    assert _commun.ATTENTE_VERROU_S == 0.020
    assert _commun.VERROU_PERIME_S == 2.0


# --- journal ------------------------------------------------------------------------------


def test_journal_type_seulement(racine_locale_isolee):
    _commun.journaliser("Stop", ValueError("secret sk-abc dans le prompt"))
    _commun.journaliser("Stop", OSError(errno.ENOSPC, "plein"))
    _commun.journaliser("Stop", "VerrouOccupe")
    fichiers = list((racine_locale_isolee / "attente" / "journal").iterdir())
    assert len(fichiers) == 1
    assert fichiers[0].name == f"hooks-{_commun.maintenant()[:7]}.log"
    lignes = fichiers[0].read_text(encoding="utf-8").splitlines()
    assert [ligne.split(" ", 1)[1] for ligne in lignes] == [
        "Stop ValueError", "Stop OSError:ENOSPC", "Stop VerrouOccupe",
    ]
    assert "sk-" not in fichiers[0].read_text(encoding="utf-8")


def test_journal_ne_leve_jamais(racine_locale_isolee):
    racine_locale_isolee.mkdir(parents=True)
    (racine_locale_isolee / "attente").write_text("fichier, pas dossier", encoding="utf-8")
    _commun.journaliser("SessionStart", ValueError())  # aucune exception


def test_type_erreur_oserror_sans_errno():
    assert _commun.type_erreur(OSError("x")) == "OSError"
    assert _commun.type_erreur(FileNotFoundError(errno.ENOENT, "x")) == "FileNotFoundError:ENOENT"


# --- payload et sortie --------------------------------------------------------------------


def test_lire_payload_utf8():
    texte = json.dumps({"cwd": "é", "session_id": "x"}, ensure_ascii=False).encode("utf-8")
    assert _commun.lire_payload(io.BytesIO(texte)) == {"cwd": "é", "session_id": "x"}


@pytest.mark.parametrize("brut", [b"", b"null", b'"x"', "é".encode("cp1252"), b"{"])
def test_lire_payload_refuse(brut):
    with pytest.raises(_commun.PayloadInvalide):
        _commun.lire_payload(io.BytesIO(brut))


def test_emettre_octets_bruts(capfdbinary):
    _commun.emettre("bloc é\n".encode())
    assert capfdbinary.readouterr().out == "bloc é\n".encode()


def test_executer_journalise_et_ne_propage_pas(racine_locale_isolee):
    def traitement(payload):
        raise KeyError(payload["absent"])

    _commun.executer("Stop", traitement, io.BytesIO(b"{}"))
    texte = next((racine_locale_isolee / "attente" / "journal").iterdir()).read_text("utf-8")
    assert texte.endswith(" Stop KeyError\n")


# --- rattachement -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("chemin", "racine", "attendu"),
    [
        (r"C:\Gh\Projet", r"c:\gh", "Projet"),
        ("C:/GH/a/b/", r"C:\gh\\", "a/b"),
        (r"C:\gh", r"C:\gh", None),
        (r"C:\ghx\a", r"C:\gh", None),
        (r"D:\gh\a", r"C:\gh", None),
        (r"C:\gh\..\a", r"C:\gh", None),
        (r"C:\gh\.\a", r"C:\gh", None),
        ("/home/u/gh/a", "/home/u/gh", "a"),
        ("a", "", None),
    ],
)
def test_relatif_sous(chemin, racine, attendu):
    assert _commun.relatif_sous(chemin, racine) == attendu


def test_nom_pc(monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "PC-Moi")
    assert _commun.nom_pc() == "pc-moi"
    monkeypatch.setenv("COMPUTERNAME", "PC_X")
    assert _commun.nom_pc() == "pc-x"  # même normalisation que le scan (`ids.normaliser_pc`)
    monkeypatch.setenv("COMPUTERNAME", "__")
    with pytest.raises(ids.ErreurId):
        _commun.nom_pc()


@pytest.mark.parametrize("brut", ["PC_X", "Bureau Joël", "-" + "a" * 40, "CON"])
def test_nom_pc_aligne_sur_le_scan(monkeypatch, brut):
    from pilotage.scan import api as scan_api

    monkeypatch.setenv("COMPUTERNAME", brut)
    try:
        attendu = scan_api.nom_pc(None)
    except ids.ErreurId:
        with pytest.raises(ids.ErreurId):
            _commun.nom_pc()
    else:
        assert _commun.nom_pc() == attendu


def test_contexte_sans_agent(racine_locale_isolee, monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "PC1")
    github = chemins.racine_github()
    racine_locale_isolee.mkdir(parents=True)
    (racine_locale_isolee / "table-dossiers.json").write_text(
        json.dumps({"schema": 1, "dossiers": {"mon/depot": "depot"}}), encoding="utf-8"
    )
    session = str(uuid.uuid4())
    payload = {"cwd": str(github / "Mon" / "Depot"), "session_id": session}
    assert _commun.contexte(payload) == _commun.Contexte(
        projet="depot", pc="pc1", session=session, dossier="mon/depot", cwd=payload["cwd"]
    )
    assert _commun.contexte({**payload, "agent_id": "a"}) is None
    with pytest.raises(_commun.PayloadInvalide):
        _commun.contexte({"session_id": session})


def test_projet_invalide_dans_la_table_refuse(racine_locale_isolee):
    # La table est validée en bloc : un projet invalide la rend illisible.
    racine_locale_isolee.mkdir(parents=True)
    (racine_locale_isolee / "table-dossiers.json").write_text(
        json.dumps({"schema": 1, "dossiers": {"a": "NUL"}}), encoding="utf-8"
    )
    payload = {"cwd": str(chemins.racine_github() / "a"), "session_id": SESSION}
    with pytest.raises(_commun.TableIllisible):
        _commun.contexte(payload)


# --- état ---------------------------------------------------------------------------------


def _etat() -> dict:
    return {
        "schema": 1, "projet": "p", "pc": "pc1", "session": SESSION, "pid": 42,
        "pid_cree": None, "dossier": "p", "branche": None, "debut": "2026-11-06T10:00:00Z",
        "statut": "active",
    }


def test_ecrire_etat_refuse_champ_hors_liste(racine_locale_isolee):
    chemin = racine_locale_isolee / "attente" / "etat" / "p" / "pc1" / f"{SESSION}.json"
    with pytest.raises(ErreurValidation, match="champ inconnu : prompt"):
        _commun.ecrire_etat(chemin, {**_etat(), "prompt": "texte"})
    assert not chemin.parent.exists()
    _commun.ecrire_etat(chemin, _etat())
    assert _commun.lire_etat(chemin) == _etat()


def test_lire_etat_invalide_vaut_absent(racine_locale_isolee):
    chemin = racine_locale_isolee / "e.json"
    racine_locale_isolee.mkdir(parents=True)
    assert _commun.lire_etat(chemin) is None
    chemin.write_text("{", encoding="utf-8")
    assert _commun.lire_etat(chemin) is None
    chemin.write_text(json.dumps({**_etat(), "schema": 2}), encoding="utf-8")
    assert _commun.lire_etat(chemin) is None


def test_chemin_etat_sous_attente(racine_locale_isolee):
    ctx = _commun.Contexte("p", "pc1", SESSION, "p", "c")
    attendu = (racine_locale_isolee / "attente" / "etat" / "p" / "pc1" / f"{SESSION}.json")
    assert _commun.chemin_etat(ctx) == attendu.resolve()


# --- branche ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "attendu"),
    [
        ("ref: refs/heads/main\n", "main"),
        ("ref: refs/heads/story/2-2", "story/2-2"),
        ("0123456789abcdef0123456789abcdef01234567\n", None),  # détachée
        ("ref: refs/heads/ghp_secret\n", None),
        ("ref: refs/heads/" + "a" * 256 + "\n", None),
        ("ref: refs/heads/a\tb\n", None),
    ],
)
def test_lire_branche(tmp_path, head, attendu):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text(head, encoding="utf-8")
    assert _commun.lire_branche(tmp_path) == attendu


def test_lire_branche_worktree_relatif_et_absent(tmp_path):
    gitdir = tmp_path / "commun" / ".git" / "worktrees" / "w"
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/w\n", encoding="utf-8")
    wt = tmp_path / "w"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: ../commun/.git/worktrees/w\n", encoding="utf-8")
    assert _commun.lire_branche(wt) == "w"
    # `gitdir:` vers un dossier qui n'est pas un worktree ni un module git : refusé.
    arbitraire = tmp_path / "ailleurs"
    arbitraire.mkdir()
    (arbitraire / "HEAD").write_text("ref: refs/heads/fuite\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {arbitraire}\n", encoding="utf-8")
    assert _commun.lire_branche(wt) is None
    (wt / ".git").write_text("rien\n", encoding="utf-8")
    assert _commun.lire_branche(wt) is None
    assert _commun.lire_branche(tmp_path / "absent") is None


# --- processus ----------------------------------------------------------------------------


def test_pid_parent():
    assert _commun.pid_parent() == os.getppid()


@pytest.mark.skipif(sys.platform != "win32", reason="GetProcessTimes : Windows seulement")
def test_heure_creation_windows():
    valeur = _commun.heure_creation(os.getpid())
    assert valeur is not None and valeur.isdigit()
    # FILETIME : centaines de ns depuis 1601 ; ce processus est né il y a moins d'une heure.
    secondes = int(valeur) / 1e7 - 11644473600
    assert time.time() - 3600 < secondes <= time.time() + 1
    assert _commun.heure_creation(os.getpid()) == valeur  # stable


def test_heure_creation_pid_inexistant_vaut_none():
    assert _commun.heure_creation(0x7FFFFFF0) is None


@pytest.mark.skipif(sys.platform == "win32", reason="repli hors Windows")
def test_heure_creation_hors_windows_vaut_none():
    assert _commun.heure_creation(os.getpid()) is None


def test_nom_pc_hors_computername_meme_nom_court_que_le_scan(monkeypatch):
    """Sans `COMPUTERNAME` (Mac, Linux), hooks et scan gardent le nom d'hôte avant le premier
    `.` : le dossier d'état d'un PC existant ne change pas (story 3.6)."""
    import platform
    from types import SimpleNamespace

    from pilotage.scan import lecture

    monkeypatch.delenv("COMPUTERNAME", raising=False)
    monkeypatch.setattr(os, "uname", lambda: SimpleNamespace(nodename="Mac-Moi.local"),
                        raising=False)
    monkeypatch.setattr(platform, "node", lambda: "Mac-Moi.local")
    assert _commun.nom_pc() == lecture.nom_pc(None) == "mac-moi"
