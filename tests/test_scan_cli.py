"""`lancer.py scan` : mutex, fichiers écrits, alertes, TABLEAU.md (story 1.6)."""

import json
import os
import subprocess
import sys
import textwrap
import time
from datetime import UTC, datetime

import pytest

from pilotage import chemins
from pilotage.noyau import schemas
from pilotage.noyau.schemas import ErreurValidation
from pilotage.scan import cli, faits_gh, tableau
from pilotage.scan import verrou as impl
from tests.test_faits_gh import faux_gh
from tests.test_imports import RACINE_DEPOT
from tests.test_inventaire import faux_depot
from tests.test_verrou import ENFANT

windows = pytest.mark.skipif(sys.platform != "win32", reason="mutex nommé Windows")


@pytest.fixture(autouse=True)
def nom_propre(monkeypatch, tmp_path):
    monkeypatch.setenv(impl.VARIABLE_NOM, f"Local\\pilotage-test-scan-{abs(hash(str(tmp_path)))}")


@pytest.fixture
def github(tmp_path):
    racine = tmp_path / "github"
    faux_depot(racine / "demo", url="https://github.com/Proprio-Test/demo.git")
    return racine


def scanner(github):
    return cli.main(["--racine-github", str(github), "--pc", "pc-test"])


def test_scan_ecrit_instantane_table_tableau_et_alertes(github, monkeypatch):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    assert scanner(github) == 0
    instantane = json.loads((chemins.instantanes() / "pc-test.json").read_text("utf-8"))
    schemas.valider("instantane", instantane)
    assert instantane["projets"]["demo"]["faits_depot"]["tag"] == "v1.2.3"
    assert json.loads(chemins.table_dossiers().read_text("utf-8"))["dossiers"] == {"demo": "demo"}
    assert chemins.tableau().is_file()
    assert json.loads(chemins.alertes_json().read_text("utf-8")) == {"schema": 1, "alertes": []}
    assert not chemins.donnees().exists()  # rien dans donnees/


def test_aucune_commande_git_ni_isprivate(github, monkeypatch):
    vus = []
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh(appels=vus))
    lancees = []

    def espion(cmd, *a, **k):
        lancees.append((cmd, k.get("cwd")))
        raise AssertionError("aucun sous-processus attendu hors de gh simulé")

    monkeypatch.setattr(subprocess, "run", espion)
    monkeypatch.setattr(subprocess, "Popen", espion)
    assert scanner(github) == 0
    assert lancees == []
    plat = " ".join(a for args, _ in vus for a in args)
    assert "isPrivate" not in plat
    assert all(args[0] != "git" for args, _ in vus)


def test_projet_non_relu_alerte_scan_et_code_0(github, monkeypatch):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh(echec=("repo view",)))
    assert scanner(github) == 0
    alertes = json.loads(chemins.alertes_json().read_text("utf-8"))["alertes"]
    assert alertes == [
        {"source": "scan", "code": "faits-github-non-relus",
         "params": {"projet": "demo"}}
    ]


def test_echec_code_1_remplace_seulement_les_alertes_scan(github, monkeypatch, capsys):
    ancien = {"schema": 1, "alertes": [
        {"source": "sync", "code": "rebase", "message": "conflit"},
        {"source": "scan", "code": "vieux", "message": "à remplacer"},
    ]}
    chemins.ecrire_atomique(chemins.alertes_json(), json.dumps(ancien))

    def boom(*a, **k):
        raise RuntimeError("secret C:\\chemin")

    monkeypatch.setattr(cli.inventaire, "inventorier", boom)
    assert scanner(github) == 1
    alertes = json.loads(chemins.alertes_json().read_text("utf-8"))["alertes"]
    assert alertes == [
        {"source": "sync", "code": "rebase", "message": "conflit"},
        {"source": "scan", "code": "scan-echec", "params": {}},
    ]
    assert "secret" not in capsys.readouterr().err
    assert not chemins.tableau().exists()


@windows
def test_mutex_tenu_par_un_autre_processus_code_3_sans_rien_ecrire(github, monkeypatch):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    enfant = subprocess.Popen(
        [sys.executable, "-c", ENFANT], cwd=RACINE_DEPOT, stdout=subprocess.PIPE, text=True
    )
    try:
        assert enfant.stdout.readline().strip() == "acquis"
        assert scanner(github) == 3
    finally:
        enfant.kill()
        enfant.wait()
    assert not chemins.attente().exists()
    assert not chemins.tableau().exists()
    assert not chemins.table_dossiers().exists()


@windows
def test_deux_scans_simultanes_un_0_un_3(github, tmp_path):
    outils = tmp_path / "outils"
    outils.mkdir()
    dans_gh, libere = tmp_path / "dans-gh", tmp_path / "libere"
    # Double de `gh` dans les processus enfants : le premier appel signale qu'il tient le mutex
    # (fichier témoin) puis attend que le test le libère ; aucun délai fixe.
    (outils / "sitecustomize.py").write_text(textwrap.dedent(
        f"""
        import pathlib, subprocess, time
        _run = subprocess.run
        def run(cmd, *a, **k):
            if cmd and cmd[0] == "gh":
                pathlib.Path({str(dans_gh)!r}).touch()
                fin = time.monotonic() + 60
                while not pathlib.Path({str(libere)!r}).exists() and time.monotonic() < fin:
                    time.sleep(0.05)
                return subprocess.CompletedProcess(cmd, 1, "", "boom")
            return _run(cmd, *a, **k)
        subprocess.run = run
        """), "utf-8")
    env = {**os.environ, "PYTHONPATH": str(outils)}
    commande = [sys.executable, str(RACINE_DEPOT / "lancer.py"), "scan",
                "--racine-github", str(github), "--pc", "pc-test"]

    def lancer():
        return subprocess.Popen(commande, cwd=RACINE_DEPOT, env=env, stderr=subprocess.PIPE,
                                text=True)

    premier = lancer()
    try:
        fin = time.monotonic() + 60
        while not dans_gh.exists() and premier.poll() is None and time.monotonic() < fin:
            time.sleep(0.05)
        assert dans_gh.exists(), premier.stderr.read() if premier.poll() is not None else ""
        second = lancer()
        assert second.wait(timeout=60) == 3, second.stderr.read()
        assert "déjà en cours" in second.stderr.read()
    finally:
        libere.touch()
    assert premier.wait(timeout=60) == 0, premier.stderr.read()
    assert (chemins.instantanes() / "pc-test.json").is_file()


@windows
@pytest.mark.parametrize("panne", ["creation", "attente"])
def test_mutex_en_panne_code_1_sans_rien_ecrire(github, monkeypatch, panne):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    vrai = impl._noyau

    def noyau_en_panne():
        k = vrai()

        class Panne:
            def __getattr__(self, nom):
                return getattr(k, nom)

            def CreateMutexW(self, *a):  # noqa: N802 (nom de l'API Windows)
                return None if panne == "creation" else k.CreateMutexW(*a)

            def WaitForSingleObject(self, *a):  # noqa: N802
                return impl.WAIT_FAILED if panne == "attente" else k.WaitForSingleObject(*a)

        return Panne()

    monkeypatch.setattr(impl, "_noyau", noyau_en_panne)
    assert scanner(github) == 1
    assert not chemins.attente().exists()
    assert not chemins.tableau().exists()


def test_alertes_illisibles_remplacees_avec_alerte(github, monkeypatch):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    chemins.ecrire_atomique(chemins.alertes_json(), "{pas du json")
    assert scanner(github) == 0
    alertes = json.loads(chemins.alertes_json().read_text("utf-8"))["alertes"]
    assert [a["code"] for a in alertes] == [cli.ALERTE_ILLISIBLE]


def test_dependance_d_un_projet_exclu_absente_du_tableau(github, monkeypatch):
    faux_depot(github / "autre", url="https://github.com/Proprio-Test/autre.git")
    faux_depot(github / "cache", url="https://github.com/Proprio-Test/cache.git")
    donnees = chemins.donnees()
    donnees.mkdir(parents=True)
    (donnees / "projets.yaml").write_text(
        "schema: 1\nexclus: [cache]\n"
        "dependances:\n  - demo ← autre\n  - demo ← cache\n", "utf-8")
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    assert scanner(github) == 0
    texte = chemins.tableau().read_text("utf-8")
    assert "- demo ← autre" in texte
    assert "cache" not in texte


def test_tableau_date_et_phases_dans_l_ordre_du_noyau():
    carte = {"nom": "p", "genre": "projet", "action": "rien-a-faire",
             "raison": {"code": "x", "params": {}, "texte": "rien"}, "quoi": None,
             "type": None, "chantier": None, "categorie": "classé"}
    depot = {"topics": ["status-test", "ai-portfolio", "status-dev"]}
    genere = datetime(2026, 11, 6, 8, 30, tzinfo=UTC)
    texte = tableau.rendre({"cartes": [carte]}, {"p": depot}, [], genere)
    assert f"_Généré le {genere.astimezone().strftime('%Y-%m-%d %H:%M')}._" in texte
    assert "phase : status-dev, status-test ·" in texte


def test_tableau_quatre_sections_et_textes_du_noyau(github, monkeypatch):
    faux_depot(github / "autre", url="https://github.com/Proprio-Test/autre.git")
    donnees = chemins.donnees()
    donnees.mkdir(parents=True)
    (donnees / "projets.yaml").write_text(
        "schema: 1\nchantiers:\n  mon-chantier:\n    projets: [demo, autre]\n"
        "dependances:\n  - demo ← autre\n", "utf-8")
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh(release=None))
    assert scanner(github) == 0
    texte = chemins.tableau().read_text("utf-8")
    titres = [ligne for ligne in texte.splitlines() if ligne.startswith("## ")]
    assert titres == [
        "## 🔴 Attend Personne Test (0)", "## 🟠 À relancer (2)", "## 🟢 Tourne (0)",
        "## ⚪ Rien à faire (0)", "## Chantiers", "## Dépendances", "## Fraîcheur des PC",
    ]
    assert ("- **autre** : run non terminé · phase : status-dev · chantier : mon-chantier"
            in texte)
    assert ("- **mon-chantier** : 🟠 À relancer, run non terminé · projets : autre, demo"
            in texte)
    assert "- demo ← autre" in texte


def test_libelle_identique_a_raison_texte_et_quoi_entier():
    quoi = "x" * 200
    raison = {"code": "attend-utilisateur", "params": {"type": "choix"},
              "texte": f"vous attend : {quoi}"}
    carte = {"nom": "p", "genre": "projet", "action": "attend-utilisateur", "raison": raison,
             "quoi": quoi, "type": "choix", "chantier": None, "categorie": "classé"}
    texte = tableau.rendre({"cartes": [carte]}, {"p": None}, [], datetime(2026, 11, 6, tzinfo=UTC))
    assert f"- **p** : {raison['texte']} · type : choix · phase : — · chantier : —" in texte
    assert quoi in texte
    assert "## 🔴 Vous attend (1)" in texte  # sans nom passé : libellé neutre
    nomme = tableau.rendre({"cartes": [carte]}, {"p": None}, [],
                           datetime(2026, 11, 6, tzinfo=UTC), utilisateur="Camille")
    assert "## 🔴 Attend Camille (1)" in nomme
    assert "Vous attend" not in nomme


def test_tableau_sans_nom_configure_libelle_neutre(github, monkeypatch):
    monkeypatch.delenv(chemins.VARIABLE_UTILISATEUR)
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh(release=None))
    assert scanner(github) == 0
    texte = chemins.tableau().read_text("utf-8")
    assert "## 🔴 Vous attend (0)" in texte
    assert "Attend " not in texte


@pytest.mark.parametrize("objet", [
    [], {"schema": 1}, {"schema": 2, "alertes": []}, {"schema": 1, "alertes": [], "x": 1},
    {"schema": 1, "alertes": [{"code": "a", "message": "m"}]},
    {"schema": 1, "alertes": [{"source": "web", "code": "a", "message": "m"}]},
    {"schema": 1, "alertes": [{"source": "scan", "code": "A b", "message": "m"}]},
    {"schema": 1, "alertes": [{"source": "scan", "code": "a", "message": ""}]},
    {"schema": 1, "alertes": [{"source": "scan", "code": "a", "message": "m" * 301}]},
])
def test_schema_alertes_refuse(objet):
    with pytest.raises(ErreurValidation):
        schemas.valider("alertes", objet)


def test_schema_alertes_accepte_la_limite():
    schemas.valider("alertes", {"schema": 1, "alertes": [
        {"source": "operation", "code": "a" * 64, "message": "m" * 300}]})


@windows
def test_mutex_libere_apres_le_scan(github, monkeypatch):
    """Une seule prise du mutex : aucune poignée ne reste ouverte après `main` (serveur en
    processus long)."""
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    assert scanner(github) == 0
    assert impl.occupe() is False


def test_sans_proprietaire_scan_en_echec_avec_message_clair(github, monkeypatch, capsys):
    monkeypatch.delenv(chemins.VARIABLE_PROPRIETAIRE)
    appels = []
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh(appels=appels))
    assert scanner(github) == 1
    assert appels == []
    err = capsys.readouterr().err
    assert "lancer.py scan : échec ('proprietaire_github' absent ou invalide" in err
    alertes = json.loads(chemins.alertes_json().read_text("utf-8"))["alertes"]
    assert alertes == [{"source": "scan", "code": "scan-echec", "params": {}}]
    assert not chemins.tableau().exists()
