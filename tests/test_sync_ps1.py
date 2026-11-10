"""Story 2.8 : `claude-config/sync.ps1` joué sur une copie, toutes les cibles sous `tmp_path`.

Le script est lu dans `PILOTAGE_SYNC_PS1` ou dans `../claude-config/sync.ps1`, puis copié dans un
dépôt temporaire : jamais de git (`-SansGit`), jamais le vrai `~/.claude` (`-DossierClaude`).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from outils.publier_config import RUNTIME
from tests.test_imports import RACINE_DEPOT

SCRIPT = Path(
    os.environ.get("PILOTAGE_SYNC_PS1") or RACINE_DEPOT.parent / "claude-config" / "sync.ps1"
)

# porte locale (CLAUDE.md) : `PILOTAGE_EXIGER_SYNC_PS1=1` change le saut en échec
EXIGER = os.environ.get("PILOTAGE_EXIGER_SYNC_PS1") == "1"

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="sync.ps1 : Windows seulement"),
    pytest.mark.skipif(
        not EXIGER and not SCRIPT.is_file(), reason=f"sync.ps1 absent : {SCRIPT}"),
]


@pytest.fixture(autouse=True)
def _script_present():
    if not SCRIPT.is_file():
        pytest.fail(f"sync.ps1 introuvable : {SCRIPT} (PILOTAGE_EXIGER_SYNC_PS1=1)")

TIERS = {"type": "command", "command": "{{RACINE_GITHUB}}\\outils\\controle.exe"}
REGLAGES_DEPOT = {
    "model": "opus",
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [TIERS]}]},
    "théme": "é",
}


@pytest.fixture
def poste(tmp_path):
    """Dépôt claude-config avec runtime publié, racine GitHub et dossier Claude temporaires."""
    depot = tmp_path / "claude-config"
    (depot / "claude").mkdir(parents=True)
    shutil.copy2(SCRIPT, depot / "sync.ps1")
    (depot / "claude" / "CLAUDE.md").write_text("# global\n", encoding="utf-8")
    (depot / "claude" / "settings.json").write_text(
        json.dumps(REGLAGES_DEPOT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    runtime = depot / "claude" / "pilotage"
    runtime.mkdir()
    for nom in RUNTIME:
        source = RACINE_DEPOT / nom
        if source.is_dir():
            shutil.copytree(source, runtime / nom, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, runtime / nom)
    github = tmp_path / "GitHub"
    github.mkdir()
    claude = tmp_path / "claude"
    installe = claude / "pilotage"
    # `.venv` créé d'avance (-SansUv) : robocopy /MIR ne doit pas l'effacer
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(installe / ".venv")],
                   check=True, capture_output=True)
    (installe / "pilotage").mkdir()
    (installe / "pilotage" / "ancien.py").write_text("# obsolète\n", encoding="utf-8")
    (installe / "config.json").write_text('{"racine_locale": "D:/locale"}\n', encoding="utf-8")
    (installe / "desactive").write_bytes(b"")
    return depot, github, claude


# Valeurs neutres passées au script : sans elles, il écrirait celles de son auteur.
IDENTITE = ("-ProprietaireGitHub", "proprio-test", "-DepotDonnees", "proprio-test/donnees-test",
            "-Utilisateur", "Joël Test")


def _sync(depot: Path, sens: str, github: Path, claude: Path, *options: str, env=None):
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(depot / "sync.ps1"), sens, "-RacineGitHub", str(github),
         "-DossierClaude", str(claude), "-SansGit", "-SansTache", *IDENTITE, *options],
        capture_output=True, timeout=120, env=env,
    )


def _texte(resultat) -> str:
    return (resultat.stdout + resultat.stderr).decode("utf-8", "replace")


def _hash(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def test_restaurer_deux_fois_meme_hash_puis_sauver_sans_pilotage(poste):
    depot, github, claude = poste
    installe = claude / "pilotage"
    resultat = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert resultat.returncode == 0, _texte(resultat)
    assert "Pilotage install" in _texte(resultat)
    reglages = claude / "settings.json"
    contenu = json.loads(reglages.read_text(encoding="utf-8"))
    # autres clés du dépôt, jeton remplacé, hooks du pilotage ajoutés
    assert contenu["model"] == "opus" and contenu["théme"] == "é"
    assert contenu["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == (
        str(github) + "\\outils\\controle.exe")
    python = (installe / ".venv" / "Scripts" / "python.exe").as_posix()
    stop = contenu["hooks"]["Stop"][0]["hooks"][0]
    assert stop == {"type": "command", "command": python,
                    "args": ["-I", "-S", installe.as_posix() + "/pilotage/hooks/stop.py"]}
    # miroir : obsolète supprimé ; .venv, config.json et desactive gardés
    assert not (installe / "pilotage" / "ancien.py").exists()
    assert (installe / "desactive").exists()
    assert (installe / "regle-marqueur.md").read_bytes() == (
        RACINE_DEPOT / "regle-marqueur.md").read_bytes()
    assert json.loads((installe / "config.json").read_text(encoding="utf-8")) == {
        "racine_locale": "D:/locale",
        "python": python,
        "pythonw": python[: -len("python.exe")] + "pythonw.exe",
        "racine_github": github.as_posix(),
        "port": 47615,
        "proprietaire_github": "proprio-test",
        "depot_donnees": "proprio-test/donnees-test",
        "utilisateur": "Joël Test",
    }
    empreinte = _hash(reglages)
    resultat = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert resultat.returncode == 0, _texte(resultat)
    assert _hash(reglages) == empreinte

    # sauver : aucune entrée du pilotage versionnée, la racine GitHub redevient un jeton
    resultat = _sync(depot, "sauver", github, claude)
    assert resultat.returncode == 0, _texte(resultat)
    versionne = (depot / "claude" / "settings.json").read_text(encoding="utf-8")
    assert "pilotage" not in versionne.casefold()
    assert json.loads(versionne) == REGLAGES_DEPOT
    assert reglages.read_bytes() and _hash(reglages) == empreinte


def test_sauver_sans_runtime_refuse_si_hooks_du_pilotage(poste):
    depot, github, claude = poste
    assert _sync(depot, "restaurer", github, claude, "-SansUv").returncode == 0
    shutil.rmtree(claude / "pilotage")
    avant = (depot / "claude" / "settings.json").read_bytes()
    resultat = _sync(depot, "sauver", github, claude)
    assert resultat.returncode != 0
    assert "runtime install" in _texte(resultat)
    assert (depot / "claude" / "settings.json").read_bytes() == avant


@pytest.mark.parametrize("graphie", ["pilotage\\\\hooks", "Pilotage/Hooks", "pilotage//hooks"])
def test_sauver_sans_runtime_detecte_toute_graphie(poste, graphie):
    depot, github, claude = poste
    shutil.rmtree(claude / "pilotage")
    claude.mkdir(exist_ok=True)
    (claude / "CLAUDE.md").write_text("# x\n", encoding="utf-8")
    (claude / "settings.json").write_text(
        '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "C:\\\\py.exe", '
        f'"args": ["C:/x/{graphie}/stop.py"]}}]}}]}}}}\n', encoding="utf-8")
    resultat = _sync(depot, "sauver", github, claude)
    assert resultat.returncode != 0, _texte(resultat)
    assert "Rien n" in _texte(resultat)


def test_sauver_sans_runtime_ni_pilotage_comportement_actuel(poste):
    depot, github, claude = poste
    shutil.rmtree(claude / "pilotage")
    claude.mkdir(exist_ok=True)
    (claude / "CLAUDE.md").write_text("# x\n", encoding="utf-8")
    brut = '{"model":"opus","chemin":"' + str(github).replace("\\", "\\\\") + '\\\\a"}'
    (claude / "settings.json").write_text(brut, encoding="utf-8")
    resultat = _sync(depot, "sauver", github, claude)
    assert resultat.returncode == 0, _texte(resultat)
    assert (depot / "claude" / "settings.json").read_text(encoding="utf-8") == (
        '{"model":"opus","chemin":"{{RACINE_GITHUB}}\\\\a"}')


def test_restaurer_sans_runtime_publie(poste):
    depot, github, claude = poste
    shutil.rmtree(depot / "claude" / "pilotage")
    resultat = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert resultat.returncode == 0, _texte(resultat)
    assert "Aucun runtime" in _texte(resultat)
    contenu = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert list(contenu["hooks"]) == ["PreToolUse"]
    assert (claude / "pilotage" / "pilotage" / "ancien.py").exists()


def test_restaurer_uv_absent_laisse_settings_inchange(poste):
    depot, github, claude = poste
    (claude / "settings.json").write_bytes(b'{"model": "avant"}\n')
    systeme = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    env = dict(os.environ, PATH=os.pathsep.join([systeme, os.path.join(
        systeme, "WindowsPowerShell", "v1.0")]))
    resultat = _sync(depot, "restaurer", github, claude, env=env)
    assert resultat.returncode != 0
    assert "uv introuvable" in _texte(resultat)
    assert (claude / "settings.json").read_bytes() == b'{"model": "avant"}\n'
    assert (claude / "pilotage" / "pilotage" / "ancien.py").exists()


def _poser_hook(claude: Path, entree: dict) -> None:
    reglages = claude / "settings.json"
    contenu = json.loads(reglages.read_text(encoding="utf-8"))
    contenu["hooks"]["Stop"][0]["hooks"].append(entree)
    reglages.write_text(json.dumps(contenu, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")


def test_sauver_ne_versionne_jamais_le_hook_du_clone_de_dev(poste):
    depot, github, claude = poste
    assert _sync(depot, "restaurer", github, claude, "-SansUv").returncode == 0
    clone = str(github / "pilotage-projets" / "pilotage" / "hooks" / "stop.py")
    _poser_hook(claude, {"type": "command", "command": "C:/dev/python.exe",
                         "args": ["-I", "-S", clone]})
    resultat = _sync(depot, "sauver", github, claude)
    assert resultat.returncode == 0, _texte(resultat)
    versionne = (depot / "claude" / "settings.json").read_text(encoding="utf-8")
    assert "pilotage" not in versionne.casefold()
    assert json.loads(versionne) == REGLAGES_DEPOT


def test_sauver_refuse_un_hook_shell_non_reconnu(poste):
    depot, github, claude = poste
    assert _sync(depot, "restaurer", github, claude, "-SansUv").returncode == 0
    avant = (depot / "claude" / "settings.json").read_bytes()
    _poser_hook(claude, {"type": "command",
                         "command": "uv run python C:/dev/pilotage/hooks/stop.py"})
    resultat = _sync(depot, "sauver", github, claude)
    assert resultat.returncode != 0
    assert "Rien n" in _texte(resultat)
    assert (depot / "claude" / "settings.json").read_bytes() == avant


def test_restaurer_sans_runtime_publie_garde_les_hooks_installes(poste):
    depot, github, claude = poste
    assert _sync(depot, "restaurer", github, claude, "-SansUv").returncode == 0
    reglages = claude / "settings.json"
    empreinte = _hash(reglages)
    shutil.rmtree(depot / "claude" / "pilotage")
    resultat = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert resultat.returncode == 0, _texte(resultat)
    assert "refusionn" in _texte(resultat)
    assert _hash(reglages) == empreinte


def test_restaurer_sans_runtime_publie_echec_du_runtime_installe(poste):
    depot, github, claude = poste
    assert _sync(depot, "restaurer", github, claude, "-SansUv").returncode == 0
    shutil.rmtree(depot / "claude" / "pilotage")
    (claude / "pilotage" / "lancer.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
    reglages = claude / "settings.json"
    avant = reglages.read_bytes()
    config = (claude / "pilotage" / "config.json").read_bytes()
    resultat = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert resultat.returncode != 0
    assert "installer-reglages a " in _texte(resultat) and "(3)" in _texte(resultat)
    assert reglages.read_bytes() == avant
    assert (claude / "pilotage" / "config.json").read_bytes() == config


def test_restaurer_arrete_si_git_pull_echoue(poste, tmp_path):
    depot, github, claude = poste
    # dépôt sans git : `git pull` échoue ; le plafond empêche de remonter vers un vrai dépôt
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path))
    resultat = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(depot / "sync.ps1"), "restaurer", "-RacineGitHub", str(github),
         "-DossierClaude", str(claude), "-SansUv", "-SansTache"],
        capture_output=True, timeout=120, env=env,
    )
    assert resultat.returncode != 0
    assert "git pull --ff-only a " in _texte(resultat)
    assert not (claude / "settings.json").exists()
    assert not (claude / "CLAUDE.md").exists()


def _tache(sortie: str) -> dict:
    lignes = [ligne for ligne in sortie.splitlines() if ligne.startswith("TACHE-JSON: ")]
    assert len(lignes) == 1, sortie
    return json.loads(lignes[0][len("TACHE-JSON: "):])


def test_restaurer_construit_la_tache_planifiee_sans_l_enregistrer(poste):
    """Story 3.5 : `-SansTache` n'appelle jamais le planificateur, il décrit la tâche."""
    depot, github, claude = poste
    installe = claude / "pilotage"
    resultat = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert resultat.returncode == 0, _texte(resultat)
    tache = _tache(_texte(resultat))
    pythonw = str(installe / ".venv" / "Scripts" / "pythonw.exe")
    assert tache["nom"] == "pilotage-projets-sync"
    assert tache["execute"].casefold() == pythonw.casefold()
    assert tache["arguments"] == f'-I "{installe / "lancer.py"}" sync'
    assert tache["repertoire"] == str(installe)
    assert tache["intervalle"] == "PT15M"
    assert tache["duree"] == ""  # indéfiniment
    assert tache["ouverture"] == "Interactive"
    assert tache["elevation"] == "Limited"
    assert tache["instances"] == "IgnoreNew"
    assert tache["demarrage_sur_batterie"] is True  # portable pro sur batterie
    assert tache["arret_sur_batterie"] is False
    assert tache["rattrapage"] is True  # déclenchement manqué (veille) rattrapé
    assert tache["limite"] == "PT10M"  # instance bloquée arrêtée : IgnoreNew ne bloque pas 72 h
    assert tache["utilisateur"].casefold().endswith(os.environ["USERNAME"].casefold())
    assert "enregistr" not in _texte(resultat)


def test_restaurer_deux_fois_decrit_la_meme_tache_unique(poste):
    depot, github, claude = poste
    premiere = _sync(depot, "restaurer", github, claude, "-SansUv")
    seconde = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert premiere.returncode == 0 and seconde.returncode == 0, _texte(seconde)
    assert _tache(_texte(premiere)) == _tache(_texte(seconde))


def test_restaurer_sans_runtime_publie_ne_cree_pas_de_tache(poste):
    depot, github, claude = poste
    shutil.rmtree(depot / "claude" / "pilotage")
    resultat = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert resultat.returncode == 0, _texte(resultat)
    assert "TACHE-JSON" not in _texte(resultat)


def test_restaurer_fusion_en_echec_ne_cree_pas_de_tache(poste):
    depot, github, claude = poste
    (depot / "claude" / "pilotage" / "lancer.py").write_text(
        "raise SystemExit(3)\n", encoding="utf-8")
    resultat = _sync(depot, "restaurer", github, claude, "-SansUv")
    assert resultat.returncode != 0
    assert "TACHE-JSON" not in _texte(resultat)



def _sync_journal(depot: Path, github: Path, claude: Path, journal: Path):
    """Branche d'enregistrement sans -SansTache, mais `-JournalTache` : le script valide les objets
    par New-ScheduledTask et journalise. Jamais d'espion par fonction : le module CDXML
    ScheduledTasks, chargé à la volée, écraserait l'espion (vrai planificateur appelé)."""
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(depot / "sync.ps1"), "restaurer", "-RacineGitHub", str(github),
         "-DossierClaude", str(claude), "-SansGit", "-SansUv", "-JournalTache", str(journal)],
        capture_output=True, timeout=120,
    )


def test_restaurer_branche_d_enregistrement_journalisee(poste, tmp_path):
    """Deux restaurer : Unregister puis Register à chaque fois, objets acceptés par
    New-ScheduledTask."""
    depot, github, claude = poste
    journal = tmp_path / "planificateur.txt"
    for _ in range(2):
        resultat = _sync_journal(depot, github, claude, journal)
        assert resultat.returncode == 0, _texte(resultat)
    pythonw = str(claude / "pilotage" / ".venv" / "Scripts" / "pythonw.exe")
    lignes = journal.read_text(encoding="utf-8-sig").splitlines()
    assert [ligne.split(" ")[:2] for ligne in lignes] == [
        ["UNREGISTER", "pilotage-projets-sync"], ["REGISTER", "pilotage-projets-sync"]] * 2
    assert lignes[1].split(" ", 2)[2].casefold() == pythonw.casefold()
    assert "TACHE-JSON" not in _texte(resultat)


def test_restaurer_enregistrement_en_echec_rend_un_code_non_nul_et_une_consigne(poste, tmp_path):
    depot, github, claude = poste
    journal = tmp_path / "absent" / "planificateur.txt"  # écriture impossible : échec simulé
    resultat = _sync_journal(depot, github, claude, journal)
    assert resultat.returncode != 0
    texte = _texte(resultat)
    assert "pilotage-projets-sync non enregistr" in texte
    assert "relancer .\sync.ps1 restaurer" in texte
