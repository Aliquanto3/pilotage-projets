"""Hooks SessionStart et SessionEnd en vrai sous-processus (`-I -S`), sous une racine isolée."""

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from pilotage.hooks import _commun
from pilotage.noyau import schemas

DEPOT = Path(__file__).resolve().parent.parent
HOOKS = DEPOT / "pilotage" / "hooks"
START = HOOKS / "session_start.py"
END = HOOKS / "session_end.py"
PAYLOADS = Path(__file__).parent / "fixtures" / "payloads"
# Interpréteur de base : le `python.exe` d'un venv Windows est un lanceur qui ajoute un processus
# entre le test et le hook (le pid parent serait le sien). Les hooks sont stdlib seule.
PYTHON = getattr(sys, "_base_executable", None) or sys.executable
PC = "pc-essai"
DOSSIER = "_sandbox/capture-payloads"  # cwd des fixtures sous {{RACINE_GITHUB}}
HORODATAGE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
CHAMPS_CREATION = [
    "schema", "projet", "pc", "session", "pid", "pid_cree", "dossier", "branche", "debut",
    "statut",
]


@pytest.fixture
def racine(racine_locale_isolee, monkeypatch):
    """Racine GitHub factice : un dépôt par dossier de la table, plus un worktree."""
    monkeypatch.setenv("COMPUTERNAME", PC.upper())
    github = racine_locale_isolee / "github"
    for relatif in (DOSSIER, "projet-b", "projet-c", "projet-d"):
        _depot(github / relatif, "main")
    principal = github / "projet-b"
    gitdir = principal / ".git" / "worktrees" / "projet-b-2"
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/story/2-2\n", encoding="utf-8")
    worktree = github / "_worktrees" / "projet-b-2"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    installation = racine_locale_isolee / "installation"
    installation.mkdir(parents=True)
    shutil.copyfile(DEPOT / "regle-marqueur.md", installation / "regle-marqueur.md")
    _table(racine_locale_isolee, {
        DOSSIER: "capture-payloads", "projet-b": "projet-b", "projet-c": "projet-c",
        "projet-d": "projet-d", "_worktrees/projet-b-2": "projet-b",
    })
    return racine_locale_isolee


def _depot(dossier: Path, branche: str) -> None:
    (dossier / ".git").mkdir(parents=True)
    (dossier / ".git" / "HEAD").write_text(f"ref: refs/heads/{branche}\n", encoding="utf-8")


def _table(racine: Path, dossiers: dict[str, str]) -> None:
    (racine / "table-dossiers.json").write_text(
        json.dumps({"schema": 1, "dossiers": dossiers}), encoding="utf-8"
    )


def _payload(nom: str, racine: Path, session: str | None = None, **champs) -> dict:
    objet = json.loads((PAYLOADS / f"{nom}.json").read_text(encoding="utf-8"))
    objet["cwd"] = objet["cwd"].replace("{{RACINE_GITHUB}}", str(racine / "github"))
    objet["session_id"] = session or str(uuid.uuid4())
    objet.update(champs)
    return objet


def _octets(payload: dict | bytes) -> bytes:
    return payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")


def _lancer(hook: Path, payload: dict | bytes, prelude: str | None = None):
    if prelude is None:
        commande = [PYTHON, "-I", "-S", str(hook)]
    else:
        code = f"{prelude}\nimport runpy\nrunpy.run_path({str(hook)!r}, run_name='__main__')\n"
        commande = [PYTHON, "-I", "-S", "-c", code]
    return subprocess.run(commande, input=_octets(payload), capture_output=True, timeout=30)


def sortie_regle() -> bytes:
    """Octets exacts émis par `SessionStart` quand la règle du dépôt est installée."""
    texte = (DEPOT / "regle-marqueur.md").read_text(encoding="utf-8")
    objet = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": texte}}
    return json.dumps(objet, ensure_ascii=False).encode("utf-8")


def _sans_sortie(resultat) -> None:
    """Rien sur stdout ni stderr ; seule la règle de `SessionStart` y est tolérée, et pour ce
    seul hook (story 2.5, contrôlée à part par `test_regle_marqueur.py`)."""
    assert resultat.returncode == 0
    tolere = (b"", sortie_regle()) if START.name in " ".join(map(str, resultat.args)) else (b"",)
    assert resultat.stdout in tolere
    assert resultat.stderr == b""


def _etat(racine: Path, session: str, projet: str = "capture-payloads") -> Path:
    return racine / "attente" / "etat" / projet / PC / f"{session}.json"


def _journal(racine: Path) -> list[str]:
    dossier = racine / "attente" / "journal"
    if not dossier.exists():
        return []
    lignes: list[str] = []
    for fichier in sorted(dossier.glob("hooks-*.log")):
        assert re.fullmatch(r"hooks-\d{4}-\d{2}\.log", fichier.name)
        lignes += fichier.read_text(encoding="utf-8").splitlines()
    return [ligne.split(" ", 1)[1] for ligne in lignes]


def _lire(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


# --- Création, reprise, fin ---------------------------------------------------------------


def test_startup_cree_l_etat(racine):
    payload = _payload("SessionStart-startup", racine)
    _sans_sortie(_lancer(START, payload))
    chemin = _etat(racine, payload["session_id"])
    brut = chemin.read_bytes()
    assert not brut.startswith(b"\xef\xbb\xbf") and b"\r\n" not in brut
    etat = json.loads(brut)
    assert list(etat) == CHAMPS_CREATION
    assert etat["schema"] == 1
    assert etat["projet"] == "capture-payloads"
    assert etat["pc"] == PC
    assert etat["session"] == payload["session_id"]
    assert etat["pid"] == os.getpid()  # parent du hook = ce processus de test
    assert etat["pid_cree"] == _commun.heure_creation(os.getpid())
    if sys.platform == "win32":
        assert re.fullmatch(r"[1-9]\d{16,19}", etat["pid_cree"])
    assert etat["dossier"] == DOSSIER
    assert etat["branche"] == "main"
    assert HORODATAGE.fullmatch(etat["debut"])
    assert etat["statut"] == "active"
    schemas.valider("session", etat)
    assert _journal(racine) == []
    assert not list((racine / "attente" / "verrous").iterdir())  # verrou rendu
    assert not list(chemin.parent.glob("*.tmp"))


def test_casse_du_cwd_ignoree(racine):
    payload = _payload("SessionStart-startup", racine)
    payload["cwd"] = payload["cwd"].upper()
    _sans_sortie(_lancer(START, payload))
    assert _lire(_etat(racine, payload["session_id"]))["dossier"] == DOSSIER


def _etat_existant(racine: Path, session: str) -> Path:
    chemin = _etat(racine, session)
    chemin.parent.mkdir(parents=True)
    ancien = {
        "schema": 1, "projet": "capture-payloads", "pc": PC, "session": session, "pid": 1,
        "pid_cree": "1", "dossier": DOSSIER, "branche": "ancienne",
        "debut": "2026-01-02T03:04:05Z", "statut": "finie", "fin": "2026-01-02T04:00:00Z",
    }
    chemin.write_text(json.dumps(ancien), encoding="utf-8")
    return chemin


# `clear` et `compact` : sources supposées (fixtures « à confirmer », story 2.1), même règle.
@pytest.mark.parametrize(
    "fixture",
    ["SessionStart-resume", "SessionStart-clear-a-confirmer", "SessionStart-compact-a-confirmer"],
)
def test_reprise_conserve_le_debut(racine, fixture):
    session = str(uuid.uuid4())
    chemin = _etat_existant(racine, session)
    _sans_sortie(_lancer(START, _payload(fixture, racine, session)))
    etat = _lire(chemin)
    assert etat["debut"] == "2026-01-02T03:04:05Z"
    assert etat["pid"] == os.getpid()
    assert etat["pid_cree"] == _commun.heure_creation(os.getpid())
    assert etat["statut"] == "active"
    assert etat["branche"] == "main"
    assert "fin" not in etat


def test_reprise_sans_etat_le_cree(racine):
    payload = _payload("SessionStart-resume", racine)
    _sans_sortie(_lancer(START, payload))
    assert _lire(_etat(racine, payload["session_id"]))["statut"] == "active"


def test_fin_de_session(racine):
    payload = _payload("SessionStart-startup", racine)
    _sans_sortie(_lancer(START, payload))
    debut = _lire(_etat(racine, payload["session_id"]))["debut"]
    _sans_sortie(_lancer(END, _payload("SessionEnd-other", racine, payload["session_id"])))
    etat = _lire(_etat(racine, payload["session_id"]))
    assert etat["statut"] == "finie"
    assert HORODATAGE.fullmatch(etat["fin"]) and etat["fin"] >= debut
    assert etat["debut"] == debut
    schemas.valider("session", etat)


@pytest.mark.parametrize("cwd", ["{github}/_sandbox/capture-payloads/sous-dossier", "{racine}"])
def test_fin_retrouve_l_etat_si_le_cwd_a_change(racine, cwd):
    payload = _payload("SessionStart-startup", racine)
    _sans_sortie(_lancer(START, payload))
    fin = _payload("SessionEnd-other", racine, payload["session_id"])
    fin["cwd"] = cwd.format(github=racine / "github", racine=racine)
    _sans_sortie(_lancer(END, fin))
    assert _lire(_etat(racine, payload["session_id"]))["statut"] == "finie"
    assert _journal(racine) == []


def test_fin_clot_la_session_dans_chaque_projet(racine):
    session = str(uuid.uuid4())
    _sans_sortie(_lancer(START, _payload("SessionStart-startup", racine, session)))
    ailleurs = _payload("SessionStart-resume", racine, session)
    ailleurs["cwd"] = str(racine / "github" / "projet-c")
    _sans_sortie(_lancer(START, ailleurs))
    _sans_sortie(_lancer(END, _payload("SessionEnd-other", racine, session)))
    for projet in ("capture-payloads", "projet-c"):
        assert _lire(_etat(racine, session, projet))["statut"] == "finie"


def test_fin_sans_etat_ne_cree_rien(racine):
    payload = _payload("SessionEnd-other", racine)
    _sans_sortie(_lancer(END, payload))
    assert not (racine / "attente" / "etat").exists()
    assert _journal(racine) == []


# --- Sans effet ---------------------------------------------------------------------------


@pytest.mark.parametrize("hook", [START, END])
def test_sous_agent_sans_effet(racine, hook):
    session = str(uuid.uuid4())
    chemin = _etat_existant(racine, session)
    avant = chemin.read_bytes()
    payload = _payload("SubagentStart-sousagent", racine, session)
    _sans_sortie(_lancer(hook, payload))
    assert chemin.read_bytes() == avant
    nouveau = _payload("SessionStart-startup", racine, agent_id="agent-0001")
    _sans_sortie(_lancer(hook, nouveau))
    assert not _etat(racine, nouveau["session_id"]).exists()
    assert not (racine / "attente" / "verrous").exists()
    assert _journal(racine) == []


@pytest.mark.parametrize(
    "cwd", ["{github}/inconnu", "{github}/projet-b/sous-dossier", "{github}", "{racine}/ailleurs",
            "{github}/../github/projet-b"],
)
def test_dossier_hors_table_sans_effet(racine, cwd):
    payload = _payload("SessionStart-startup", racine)
    payload["cwd"] = cwd.format(github=racine / "github", racine=racine)
    _sans_sortie(_lancer(START, payload))
    assert not (racine / "attente").exists()


# --- Erreurs : sortie 0, rien sur stdout, une ligne de journal ----------------------------


def _verrou(racine: Path, session: str, age: float = 0.0) -> Path:
    chemin = racine / "attente" / "verrous" / f"{session}.lock"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("999", encoding="utf-8")
    if age:
        ancien = chemin.stat().st_mtime - age
        os.utime(chemin, (ancien, ancien))
    return chemin


def test_verrou_tenu_start(racine):
    payload = _payload("SessionStart-startup", racine)
    verrou = _verrou(racine, payload["session_id"])
    _sans_sortie(_lancer(START, payload))
    assert not _etat(racine, payload["session_id"]).exists()
    assert verrou.exists()  # jamais volé tant qu'il est récent
    assert _journal(racine) == ["SessionStart VerrouOccupe"]


def test_verrou_tenu_end(racine):
    session = str(uuid.uuid4())
    chemin = _etat_existant(racine, session)
    avant = chemin.read_bytes()
    _verrou(racine, session)
    _sans_sortie(_lancer(END, _payload("SessionEnd-other", racine, session)))
    assert chemin.read_bytes() == avant
    assert _journal(racine) == ["SessionEnd VerrouOccupe"]


def test_verrou_perime_supprime(racine):
    payload = _payload("SessionStart-startup", racine)
    _verrou(racine, payload["session_id"], age=3.0)
    _sans_sortie(_lancer(START, payload))
    assert _lire(_etat(racine, payload["session_id"]))["statut"] == "active"
    assert not (racine / "attente" / "verrous" / f"{payload['session_id']}.lock").exists()


@pytest.mark.parametrize("hook", [START, END])
@pytest.mark.parametrize("brut", [b"{pas du json", b"\xff\xfe{}", b"[1, 2]", b""])
def test_payload_invalide(racine, hook, brut):
    _sans_sortie(_lancer(hook, brut))
    evenement = "SessionStart" if hook == START else "SessionEnd"
    assert _journal(racine) == [f"{evenement} PayloadInvalide"]
    assert not (racine / "attente" / "etat").exists()


def test_session_invalide(racine):
    payload = _payload("SessionStart-startup", racine, session="session-0001")
    _sans_sortie(_lancer(START, payload))
    assert _journal(racine) == ["SessionStart ErreurId"]
    assert not (racine / "attente" / "etat").exists()


def test_disque_plein_simule(racine):
    prelude = (
        "import errno, os\n"
        "def _plein(*a, **k):\n    raise OSError(errno.ENOSPC, 'plein')\n"
        "os.replace = _plein\n"
    )
    payload = _payload("SessionStart-startup", racine)
    _sans_sortie(_lancer(START, payload, prelude))
    chemin = _etat(racine, payload["session_id"])
    assert not chemin.exists()
    assert not list(chemin.parent.glob("*.tmp"))
    assert _journal(racine) == ["SessionStart OSError:ENOSPC"]
    assert not list((racine / "attente" / "verrous").iterdir())


def test_table_absente(racine):
    (racine / "table-dossiers.json").unlink()
    _sans_sortie(_lancer(START, _payload("SessionStart-startup", racine)))
    assert _journal(racine) == ["SessionStart TableAbsente"]
    assert not (racine / "attente" / "etat").exists()


@pytest.mark.parametrize("contenu", ["{", '{"schema": 2, "dossiers": {}}', '{"schema": 1}'])
def test_table_invalide(racine, contenu):
    (racine / "table-dossiers.json").write_text(contenu, encoding="utf-8")
    _sans_sortie(_lancer(START, _payload("SessionStart-startup", racine)))
    assert _journal(racine) == ["SessionStart TableIllisible"]


# --- Interrupteur ---------------------------------------------------------------------------


@pytest.mark.parametrize("hook", [START, END])
def test_desactive_ne_lit_ni_n_ecrit_rien(racine, hook):
    interrupteur = racine / "installation" / "desactive"
    interrupteur.parent.mkdir(parents=True, exist_ok=True)
    interrupteur.write_bytes(b"")
    _sans_sortie(_lancer(hook, _payload("SessionStart-startup", racine)))
    _sans_sortie(_lancer(hook, b"{pas du json"))
    assert not (racine / "attente").exists()
    interrupteur.unlink()  # rallumé : le hook agit de nouveau
    _sans_sortie(_lancer(hook, b"{pas du json"))
    assert len(_journal(racine)) == 1


@pytest.mark.parametrize("hook", [START, END])
@pytest.mark.parametrize("surcharge", [True, False])
def test_desactive_avant_tout_import_du_paquet(racine, hook, surcharge, monkeypatch):
    if surcharge:
        interrupteur = racine / "installation" / "desactive"
    else:
        monkeypatch.delenv("PILOTAGE_RACINE_LOCALE")
        interrupteur = Path(os.environ["USERPROFILE"]) / ".claude" / "pilotage" / "desactive"
    # Le calcul en ligne des points d'entrée suit celui de `chemins`.
    from pilotage import chemins

    assert chemins.fichier_desactive() == interrupteur
    interrupteur.parent.mkdir(parents=True, exist_ok=True)
    interrupteur.write_bytes(b"")
    resultat = subprocess.run(
        [PYTHON, "-I", "-S", "-X", "importtime", str(hook)],
        input=_octets(_payload("SessionStart-startup", racine)), capture_output=True, timeout=30,
    )
    assert (resultat.returncode, resultat.stdout) == (0, b"")
    assert b"pilotage" not in resultat.stderr  # aucun module du paquet importé
    assert not (racine / "attente").exists()


# --- Cinq sessions simultanées, dont une en worktree ----------------------------------------


def test_cinq_sessions_simultanees(racine):
    github = racine / "github"
    dossiers = {
        github / "_sandbox" / "capture-payloads": ("capture-payloads", "main"),
        github / "projet-b": ("projet-b", "main"),
        github / "projet-c": ("projet-c", "main"),
        github / "projet-d": ("projet-d", "main"),
        github / "_worktrees" / "projet-b-2": ("projet-b", "story/2-2"),
    }
    sessions = {str(uuid.uuid4()): dossier for dossier in dossiers}
    for hook, fixture in ((START, "SessionStart-startup"), (END, "SessionEnd-other")):
        processus = []
        for session, dossier in sessions.items():
            payload = _payload(fixture, racine, session, cwd=str(dossier))
            p = subprocess.Popen(
                [PYTHON, "-I", "-S", str(hook)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            processus.append((p, _octets(payload)))
        for p, octets in processus:
            sortie, erreur = p.communicate(octets, timeout=30)
            assert (p.returncode, erreur) == (0, b"")
            assert sortie == (sortie_regle() if hook == START else b"")
    fichiers = sorted((racine / "attente" / "etat").rglob("*.json"))
    assert len(fichiers) == 5
    for session, dossier in sessions.items():
        projet, branche = dossiers[dossier]
        etat = _lire(_etat(racine, session, projet))
        schemas.valider("session", etat)
        assert (etat["projet"], etat["branche"], etat["statut"]) == (projet, branche, "finie")
        assert etat["dossier"] == dossier.relative_to(github).as_posix().casefold()
    assert _journal(racine) == []
