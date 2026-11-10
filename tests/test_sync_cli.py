"""`lancer.py sync` : cycle complet contre un dépôt nu local, `gh` simulé (story 3.1).

Aucun test ne contacte GitHub : `https://github.com/Proprio-Test/donnees-test.git` est réécrit
vers un dépôt nu sous `tmp_path` par `url.<…>.insteadOf` d'une configuration git isolée, et
`faits_gh.executeur_gh` (frontière `gh`) est remplacé par un faux.
"""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilotage import chemins
from pilotage.noyau import alertes
from pilotage.scan import faits_gh, inventaire
from pilotage.scan import verrou as impl
from pilotage.sync import cli, copie, cycle, depot
from tests.test_faits_gh import faux_gh
from tests.test_imports import RACINE_DEPOT
from tests.test_inventaire import faux_depot
from tests.test_verrou import ENFANT

windows = pytest.mark.skipif(sys.platform != "win32", reason="mutex nommé Windows")

PC = "pc-test"
SESSION = "0123abcd-0000-4000-8000-00000000abcd"
AUTRE = "0123abcd-0000-4000-8000-0000000000ff"
ETAT_AUTRE_PC = f"etat/demo/autre-pc/{AUTRE}.json"
INSTANT = datetime(2026, 11, 6, 9, 5).astimezone()
MESSAGE = "etat(pc-test): 2026-11-06 09:05"
TEXTE_PUBLIC = "Envoi refusé : le dépôt de données n'est pas privé."
IGNORES = ("fichiers-ignores", "Fichiers locaux illisibles ou invalides : non copiés")
DEPUIS = "2026-11-06T10:05:00Z"


def g(args, cwd=None):
    return depot.git_ok(args, cwd)


def etat(pc=PC, session=SESSION, **champs):
    objet = {
        "schema": 1, "projet": "demo", "pc": pc, "session": session, "pid": 1234,
        "pid_cree": None, "dossier": "demo", "branche": "main",
        "debut": "2026-11-06T10:00:00Z", "statut": "active",
    }
    objet.update(champs)
    return objet


def poser(racine, relatif, objet):
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    texte = objet if isinstance(objet, str) else json.dumps(objet, indent=2) + "\n"
    chemin.write_text(texte, encoding="utf-8", newline="")
    return chemin


@pytest.fixture(autouse=True)
def nom_propre(monkeypatch, tmp_path):
    monkeypatch.setenv(impl.VARIABLE_NOM, f"Local\\pilotage-test-sync-{abs(hash(str(tmp_path)))}")


@pytest.fixture(autouse=True)
def horloge(monkeypatch):
    """Horloge figée : message de commit et `genere_a` de l'instantané."""

    class Fige(datetime):
        @classmethod
        def now(cls, tz=None):
            return INSTANT.astimezone(tz or UTC)

    monkeypatch.setattr(cycle, "_maintenant", lambda: INSTANT)
    monkeypatch.setattr(faits_gh, "datetime", Fige)


@pytest.fixture
def distant(tmp_path, monkeypatch):
    """Dépôt nu `donnees` (projets.yaml, un état d'un autre PC), joignable par l'URL GitHub."""
    nu = tmp_path / "distant.git"
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n\tname = Test\n\temail = test@example.invalid\n"
        "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
        f'[url "{nu.as_uri()}"]\n\tinsteadOf = {depot.url_distant()}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # Le dépôt nu tient lieu de github.com : son URL effective (après `insteadOf`) est admise
    # comme celle du dépôt privé ; toute autre URL passe par le vrai `depot_de_url`.
    vrai = depot.depot_de_url
    monkeypatch.setattr(
        depot,
        "depot_de_url",
        lambda url: depot.depot_attendu() if url.strip() == nu.as_uri() else vrai(url),
    )
    g(["init", "--quiet", "--bare", str(nu)])
    graine = tmp_path / "graine"
    g(["init", "--quiet", str(graine)])
    g(["checkout", "--quiet", "--orphan", "donnees"], graine)
    poser(graine, "projets.yaml", "schema: 1\n")
    poser(graine, ETAT_AUTRE_PC, etat(pc="autre-pc", session=AUTRE))
    g(["add", "--", "projets.yaml", ETAT_AUTRE_PC], graine)
    g(["commit", "--quiet", "-m", "graine"], graine)
    g(["push", "--quiet", str(nu), "donnees"], graine)
    return nu


@pytest.fixture
def github(tmp_path):
    racine = tmp_path / "github"
    faux_depot(racine / "demo", url="https://github.com/Proprio-Test/demo.git")
    return racine


@pytest.fixture
def gh(monkeypatch):
    """`gh` simulé : `isPrivate` répond, dans l'ordre, les réponses de `etat.reponses`."""
    scan = faux_gh()
    etat_gh = type("EtatGh", (), {})()
    etat_gh.reponses, etat_gh.appels, etat_gh.pendant = [], [], None

    def executeur(args, delai):
        if args == ["repo", "view", depot.depot_attendu(), "--json", "isPrivate"]:
            etat_gh.appels.append(args)
            if etat_gh.pendant is not None:  # geste extérieur pendant le cycle (hook, M2)
                etat_gh.pendant()
            reponse = etat_gh.reponses.pop(0) if etat_gh.reponses else True
            if reponse == "exception":
                raise faits_gh.ErreurGh("gh indisponible")
            if reponse == "echec":
                return subprocess.CompletedProcess(args, 1, "", "HTTP 401")
            if isinstance(reponse, str):
                return subprocess.CompletedProcess(args, 0, reponse, "")
            return subprocess.CompletedProcess(args, 0, json.dumps({"isPrivate": reponse}), "")
        return scan(args, delai)

    monkeypatch.setattr(faits_gh, "executeur_gh", executeur)
    return etat_gh


def synchro(github):
    return cli.main(["--racine-github", str(github), "--pc", PC])


def arbre(nu):
    return set(g(["--git-dir", str(nu), "ls-tree", "-r", "--name-only", "donnees"]).split())


def nb_commits(nu):
    return int(g(["--git-dir", str(nu), "rev-list", "--count", "donnees"]))


def alertes_sync():
    objet = json.loads(chemins.alertes_json().read_text("utf-8"))
    sync = [a for a in objet["alertes"] if a["source"] == "sync"]
    assert all("message" not in a for a in sync)  # M8 : code et params seulement
    return [(a["code"], alertes.texte(a, INSTANT.tzinfo)) for a in sync]


def test_ordre_des_etapes():
    assert [nom for nom, _ in cycle.ETAPES] == [
        "reprise", "controle-prive", "pull", "archivage", "copie-attente", "operations", "scan",
        "copie-instantane", "commit", "controle-prive-envoi", "push", "operations-nettoyage",
    ]


def test_message_de_commit():
    instant = datetime(2026, 1, 2, 3, 4, 59)
    assert cycle.message_commit("pc-a", instant) == "etat(pc-a): 2026-01-02 03:04"


def test_premier_cycle_clone_copie_commite_et_pousse(distant, github, gh):
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 0
    donnees = chemins.donnees()
    assert (donnees / ".git").is_dir()
    # Clone mono-branche de `donnees`, origine brute = URL GitHub (contrôlée).
    assert g(["config", "--get-all", "remote.origin.fetch"], donnees).split() == [
        "+refs/heads/donnees:refs/remotes/origin/donnees"
    ]
    assert depot.urls_origine(donnees) == [depot.url_distant(), distant.as_uri(), distant.as_uri()]
    assert g(["symbolic-ref", "--short", "HEAD"], donnees).strip() == "donnees"
    assert arbre(distant) == {
        "projets.yaml", ETAT_AUTRE_PC, f"etat/demo/{PC}/{SESSION}.json", f"instantanes/{PC}.json"
    }
    assert nb_commits(distant) == 2
    assert g(["--git-dir", str(distant), "log", "-1", "--format=%s", "donnees"]).strip() == MESSAGE
    assert len(gh.appels) == 2  # avant le pull et avant le push
    assert alertes_sync() == []


def test_pull_tire_l_etat_des_autres_pc(distant, github, gh, tmp_path):
    assert synchro(github) == 0
    autre = tmp_path / "autre-clone"
    g(["clone", "--quiet", "--branch", "donnees", str(distant), str(autre)])
    poser(autre, "instantanes/autre-pc.json", "{}\n")
    g(["add", "--", "instantanes/autre-pc.json"], autre)
    g(["commit", "--quiet", "-m", "etat(autre-pc): 2026-11-06 10:00"], autre)
    g(["push", "--quiet", "origin", "donnees"], autre)
    assert synchro(github) == 0
    assert (chemins.donnees() / "instantanes" / "autre-pc.json").read_text("utf-8") == "{}\n"


def test_sans_changement_aucun_commit(distant, github, gh):
    assert synchro(github) == 0
    avant = nb_commits(distant)
    assert synchro(github) == 0
    assert nb_commits(distant) == avant


def test_filtre_de_secrets_rejoue(distant, github, gh):
    racine = str(github)
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat(
        statut="attente",
        attente={"type": "permission", "quoi": "colle ghp_abc123", "depuis": DEPUIS},
        reprise="clé sk-live dans la note",
    ))
    poser(chemins.attente(), f"etat/demo/{PC}/{AUTRE}.json", etat(
        session=AUTRE, attente=None, reprise=f"voir {racine}\\demo\\notes.md",
    ))
    assert synchro(github) == 0
    suspect = json.loads((chemins.donnees() / f"etat/demo/{PC}/{SESSION}.json").read_text("utf-8"))
    assert suspect["attente"] == {"type": "permission", "quoi": "", "depuis": DEPUIS}
    assert "reprise" not in suspect
    sain = json.loads((chemins.donnees() / f"etat/demo/{PC}/{AUTRE}.json").read_text("utf-8"))
    assert sain["reprise"] == "voir {{RACINE_GITHUB}}\\demo\\notes.md"
    # L'original dans `attente/` n'est pas modifié.
    local = json.loads((chemins.attente() / f"etat/demo/{PC}/{SESSION}.json").read_text("utf-8"))
    assert local["reprise"] == "clé sk-live dans la note"


def test_fichiers_invalides_ignores_avec_alerte(distant, github, gh):
    attente = chemins.attente()
    poser(attente, f"etat/demo/{PC}/{SESSION}.json", "{ pas du json")
    poser(attente, f"etat/demo/{PC}/{AUTRE}.json", etat(session=SESSION))  # nom ≠ contenu
    poser(attente, f"etat/demo/{PC}/{SESSION}.json.1.ab.tmp", etat())
    poser(attente, f"etat/autre/{PC}/{SESSION}.json", etat())  # projet ≠ contenu
    assert synchro(github) == 0
    assert not (chemins.donnees() / "etat" / "demo" / PC).exists()
    assert {p for p in arbre(distant) if p.startswith("etat/")} == {ETAT_AUTRE_PC}
    assert alertes_sync() == [IGNORES]


def test_fichier_d_un_autre_pc_jamais_copie_ni_commite(distant, github, gh):
    assert synchro(github) == 0
    original = g(["--git-dir", str(distant), "show", f"donnees:{ETAT_AUTRE_PC}"])
    attente, donnees = chemins.attente(), chemins.donnees()
    poser(attente, f"etat/demo/autre-pc/{SESSION}.json", etat(pc="autre-pc"))
    poser(donnees, ETAT_AUTRE_PC, etat(pc="autre-pc", session=AUTRE, statut="finie",
                                       fin="2026-11-06T11:00:00Z"))
    poser(attente, f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 0
    assert not (donnees / f"etat/demo/autre-pc/{SESSION}.json").exists()
    fichiers = g(["--git-dir", str(distant), "show", "--name-only", "--format=", "donnees"])
    assert set(fichiers.split()) <= {f"etat/demo/{PC}/{SESSION}.json", f"instantanes/{PC}.json"}
    assert f"etat/demo/{PC}/{SESSION}.json" in fichiers.split()
    assert g(["--git-dir", str(distant), "show", f"donnees:{ETAT_AUTRE_PC}"]) == original


def test_projets_yaml_edite_a_la_main_est_commite(distant, github, gh):
    assert synchro(github) == 0
    poser(chemins.donnees(), "projets.yaml", "schema: 1\nexclus: [demo]\n")
    assert synchro(github) == 0
    fichiers = g(["--git-dir", str(distant), "show", "--name-only", "--format=", "donnees"])
    assert "projets.yaml" in fichiers.split()
    assert g(["--git-dir", str(distant), "show", "donnees:projets.yaml"]) == (
        "schema: 1\nexclus: [demo]\n"
    )


@pytest.mark.parametrize(
    "reponse", [False, "echec", "exception", "pas du json", '{"isPrivate": "true"}', "[]", "{}"]
)
def test_depot_non_prive_avant_le_pull(distant, github, gh, reponse):
    gh.reponses = [reponse]
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 1
    assert not chemins.donnees().exists()  # ni clone ni copie
    assert nb_commits(distant) == 1
    assert alertes_sync() == [("depot-public", TEXTE_PUBLIC)]


def test_depot_devenu_public_avant_le_push(distant, github, gh):
    assert synchro(github) == 0
    avant = nb_commits(distant)
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    gh.reponses = [True, False]
    assert synchro(github) == 1
    assert nb_commits(distant) == avant  # rien poussé
    assert g(["log", "-1", "--format=%s"], chemins.donnees()).strip() == MESSAGE  # commit local
    assert alertes_sync() == [("depot-public", TEXTE_PUBLIC)]
    gh.reponses = []
    assert synchro(github) == 0  # le cycle suivant pousse et efface l'alerte
    assert nb_commits(distant) == avant + 1
    assert alertes_sync() == []


@pytest.mark.parametrize("cle", ["remote.origin.url", "remote.origin.pushurl"])
def test_origine_d_un_autre_depot_refusee_sans_gh(distant, github, gh, cle):
    assert synchro(github) == 0
    avant = nb_commits(distant)
    g(["config", cle, "https://github.com/Proprio-Test/autre.git"], chemins.donnees())
    gh.appels.clear()
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 1
    assert gh.appels == []
    assert nb_commits(distant) == avant
    assert alertes_sync() == [("depot-public", TEXTE_PUBLIC)]


def nu_vide(tmp_path, nom):
    autre = tmp_path / nom
    g(["init", "--quiet", "--bare", str(autre)])
    return autre


def test_push_insteadof_vers_un_autre_depot_refuse_sans_gh(distant, github, gh, tmp_path):
    """`pushInsteadOf` de la config globale : l'URL brute est bonne, l'URL de push ne l'est pas."""
    assert synchro(github) == 0
    avant = nb_commits(distant)
    autre = nu_vide(tmp_path, "autre.git")
    config = tmp_path / "gitconfig"
    config.write_text(
        config.read_text("utf-8")
        + f'[url "{autre.as_uri()}"]\n\tpushInsteadOf = {depot.url_distant()}\n',
        encoding="utf-8",
    )
    gh.appels.clear()
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 1
    assert gh.appels == []
    assert nb_commits(distant) == avant
    assert g(["--git-dir", str(autre), "for-each-ref"]) == ""  # rien poussé ailleurs
    assert alertes_sync() == [("depot-public", TEXTE_PUBLIC)]


def test_insteadof_vers_un_autre_depot_refuse_avant_le_clone(distant, github, gh, tmp_path):
    autre = tmp_path / "autre.git"
    g(["clone", "--quiet", "--bare", str(distant), str(autre)])  # clonable : le contrôle arrête
    config = tmp_path / "gitconfig"
    config.write_text(
        config.read_text("utf-8").replace(distant.as_uri(), autre.as_uri()), encoding="utf-8"
    )
    assert synchro(github) == 1
    assert gh.appels == []
    assert not chemins.donnees().exists()
    assert alertes_sync() == [("depot-public", TEXTE_PUBLIC)]


def _lien(cible, lien, dossier):
    try:
        if dossier and sys.platform == "win32":
            import _winapi

            _winapi.CreateJunction(str(cible), str(lien))
        else:
            lien.symlink_to(cible, target_is_directory=dossier)
    except OSError as exc:
        pytest.skip(f"lien non créé : {exc}")


@pytest.mark.parametrize("dossier", [False, True], ids=["fichier", "dossier"])
def test_lien_ou_jonction_jamais_copie(distant, github, gh, tmp_path, dossier):
    """Un lien vers un état valide (hors de `attente/` ou dedans) n'entre pas dans la copie."""
    ailleurs = poser(tmp_path / "ailleurs", f"{PC}/{SESSION}.json", etat())
    lien = chemins.attente() / "etat" / "demo"
    lien.parent.mkdir(parents=True, exist_ok=True)
    if dossier:
        _lien(ailleurs.parent.parent, lien, True)
    else:
        (lien / PC).mkdir(parents=True)
        _lien(ailleurs, lien / PC / f"{SESSION}.json", False)
    assert synchro(github) == 0
    assert {p for p in arbre(distant) if p.startswith("etat/")} == {ETAT_AUTRE_PC}
    if not dossier:  # une jonction de dossier n'est même pas parcourue
        assert alertes_sync() == [IGNORES]


def test_projets_yaml_lien_non_commite(distant, github, gh, tmp_path):
    assert synchro(github) == 0
    projets = chemins.donnees() / "projets.yaml"
    externe = poser(tmp_path, "externe.yaml", "schema: 1\nexclus: [secret]\n")
    projets.unlink()
    _lien(externe, projets, False)
    synchro(github)
    assert g(["--git-dir", str(distant), "show", "donnees:projets.yaml"]) == "schema: 1\n"


@windows
def test_mutex_libere_apres_le_cycle(distant, github, gh):
    assert synchro(github) == 0
    assert impl.occupe() is False


@pytest.mark.parametrize(
    ("url", "attendu"),
    [
        ("https://github.com/Proprio-Test/donnees-test.git", "Proprio-Test/donnees-test"),
        ("https://github.com/proprio-test/Donnees-Test", "proprio-test/Donnees-Test"),
        ("git@github.com:Proprio-Test/donnees-test.git", "Proprio-Test/donnees-test"),
        ("ssh://git@github.com/Proprio-Test/donnees-test/", "Proprio-Test/donnees-test"),
        ("https://gitlab.com/Proprio-Test/donnees-test.git", None),
        ("https://github.com.evil.test/Proprio-Test/donnees-test.git", None),
        ("https://github.com/Proprio-Test/donnees-test/extra", None),
        ("file:///C:/distant.git", None),
    ],
)
def test_depot_de_url(url, attendu):
    assert depot.depot_de_url(url) == attendu


@pytest.mark.parametrize(
    "url",
    ["https://github.com/Proprio-Test/autre.git", "https://github.com/Autre/donnees-test.git",
     "https://github.com/Proprio-Test/donnees-test.git.evil", "C:/distant.git"],
)
def test_verifier_url_refuse(url):
    with pytest.raises(depot.DepotNonPrive):
        depot.verifier_url(url)


TEXTE_NON_CONFIGURE = (
    "Synchro arrêtée : dépôt de données non configuré. Renseignez depot_donnees "
    "(propriétaire/nom) dans config.json ou relancez l'installation."
)


def test_depot_lu_dans_la_configuration_a_l_appel(monkeypatch):
    assert depot.depot_attendu() == "proprio-test/donnees-test"
    assert depot.url_distant() == "https://github.com/proprio-test/donnees-test.git"
    depot.verifier_url("https://github.com/PROPRIO-TEST/Donnees-Test.git")  # casse ignorée
    monkeypatch.setenv(chemins.VARIABLE_DEPOT_DONNEES, "autre-proprio/autre-depot")
    assert depot.url_distant() == "https://github.com/autre-proprio/autre-depot.git"
    with pytest.raises(depot.DepotNonPrive):
        depot.verifier_url("https://github.com/proprio-test/donnees-test.git")


def test_controle_prive_interroge_gh_sur_le_depot_configure(distant, github, gh):
    assert synchro(github) == 0
    assert gh.appels == [["repo", "view", "proprio-test/donnees-test", "--json", "isPrivate"]] * 2


@pytest.mark.parametrize("valeur", [None, "", "sans-barre", "-x/depot", "proprio/-depot",
                                    "proprio/depot.git", "proprio/a..b", "proprio/a/b"])
def test_depot_non_configure_arrete_sans_git_ni_gh(distant, github, gh, monkeypatch, valeur):
    if valeur is None:
        monkeypatch.delenv(chemins.VARIABLE_DEPOT_DONNEES)
    else:
        monkeypatch.setenv(chemins.VARIABLE_DEPOT_DONNEES, valeur)
    appels_git = []
    vrai_git = depot.git
    monkeypatch.setattr(depot, "git", lambda args, cwd=None: appels_git.append(args) or vrai_git(
        args, cwd))
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 1
    assert appels_git == [] and gh.appels == []
    assert not chemins.donnees().exists()
    assert nb_commits(distant) == 1
    assert alertes_sync() == [("depot-non-configure", TEXTE_NON_CONFIGURE)]


def test_config_modifiee_entre_controle_et_clone_clone_le_depot_controle(
    distant, github, gh, monkeypatch
):
    """Revue 7.1 : `depot_donnees` change pendant `isPrivate` (réinstallation en plein cycle) ;
    le clone vise la valeur contrôlée, jamais un dépôt dont la confidentialité n'a pas été lue."""
    appels_git = []
    vrai_git = depot.git
    monkeypatch.setattr(depot, "git", lambda args, cwd=None: appels_git.append(args) or vrai_git(
        args, cwd))

    def reinstaller():
        gh.pendant = None
        monkeypatch.setenv(chemins.VARIABLE_DEPOT_DONNEES, "proprio-test/autre-donnees")

    gh.pendant = reinstaller
    synchro(github)
    clones = [a for a in appels_git if a[0] == "clone"]
    assert len(clones) == 1
    assert "https://github.com/proprio-test/donnees-test.git" in clones[0]
    assert not any("autre-donnees" in arg for a in appels_git for arg in a)
    assert gh.appels[0] == ["repo", "view", "proprio-test/donnees-test", "--json", "isPrivate"]


def test_origine_differente_du_depot_configure_refusee(distant, github, gh, monkeypatch):
    assert synchro(github) == 0
    avant = nb_commits(distant)
    monkeypatch.setenv(chemins.VARIABLE_DEPOT_DONNEES, "proprio-test/autre-donnees")
    gh.appels.clear()
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 1
    assert gh.appels == []  # refus sur l'URL d'origine, avant gh
    assert nb_commits(distant) == avant
    assert alertes_sync() == [("depot-public", TEXTE_PUBLIC)]


def test_push_refuse_alerte_avec_l_etape(distant, github, gh):
    crochet = distant / "hooks" / "pre-receive"
    crochet.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
    crochet.chmod(0o755)
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 1
    assert nb_commits(distant) == 1
    assert alertes_sync() == [("sync-echec", "Synchro en échec à l'étape push")]


def test_donnees_non_clone_refuse(distant, github, gh):
    poser(chemins.donnees(), "projets.yaml", "schema: 1\n")
    assert synchro(github) == 1
    assert alertes_sync() == [("sync-echec", "Synchro en échec à l'étape pull")]
    assert nb_commits(distant) == 1


def test_echec_du_scan_n_arrete_pas_la_synchro(distant, github, gh, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("panne")

    monkeypatch.setattr(inventaire, "inventorier", boom)
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    assert synchro(github) == 0
    assert f"etat/demo/{PC}/{SESSION}.json" in arbre(distant)
    objet = json.loads(chemins.alertes_json().read_text("utf-8"))
    assert {"source": "scan", "code": "scan-echec", "params": {}} in objet["alertes"]


@windows
def test_mutex_occupe_code_3_sans_rien_ecrire(distant, github, gh):
    enfant = subprocess.Popen(
        [sys.executable, "-c", ENFANT], cwd=RACINE_DEPOT, stdout=subprocess.PIPE, text=True
    )
    try:
        assert enfant.stdout.readline().strip() == "acquis"
        assert synchro(github) == 3
    finally:
        enfant.kill()
        enfant.wait()
    assert not chemins.attente().exists()
    assert not chemins.donnees().exists()
    assert gh.appels == []
    assert nb_commits(distant) == 1


def test_sans_lien_refuse_une_jonction_intermediaire(tmp_path):
    """Chemin joué par la CI Windows : une jonction sur un segment intermédiaire (comme
    `instantanes/` ou `etat/<projet>/`) suffit au refus, le fichier final étant ordinaire."""
    poser(tmp_path / "ailleurs", "x.json", "{}")
    (tmp_path / "racine").mkdir()
    assert copie.sans_lien(tmp_path, "ailleurs", "x.json") is True
    _lien(tmp_path / "ailleurs", tmp_path / "racine" / "instantanes", True)
    assert copie.sans_lien(tmp_path / "racine", "instantanes", "x.json") is False


class _EntreeLien:
    """`DirEntry` vu comme un lien symbolique de fichier (le runner Windows sans privilège ne
    peut pas en créer : on simule ce que `scandir` et `islink` rendent pour un vrai lien)."""

    def __init__(self, entree):
        self.name, self.path = entree.name, entree.path

    def is_file(self, follow_symlinks=True):
        return follow_symlinks

    def is_dir(self, follow_symlinks=True):
        return False

    def is_symlink(self):
        return True

    def is_junction(self):
        return False


def test_lien_de_fichier_simule_ignore_et_signale(distant, github, gh, monkeypatch):
    poser(chemins.attente(), f"etat/demo/{PC}/{SESSION}.json", etat())
    vrai_scandir, vrai_islink = os.scandir, os.path.islink
    cible = f"{SESSION}.json"

    class _Scandir:
        def __init__(self, dossier):
            self._it = vrai_scandir(dossier)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._it.close()

        def __iter__(self):
            return (_EntreeLien(e) if e.name == cible else e for e in self._it)

    monkeypatch.setattr(copie.os, "scandir", _Scandir)
    monkeypatch.setattr(
        copie.os.path, "islink", lambda p: Path(p).name == cible or vrai_islink(p)
    )
    assert synchro(github) == 0
    assert {p for p in arbre(distant) if p.startswith("etat/")} == {ETAT_AUTRE_PC}
    assert alertes_sync() == [IGNORES]


# --- Demande des hooks (M2, story 3.6) ----------------------------------------------------


def demander():
    chemins.sync_demande().parent.mkdir(parents=True, exist_ok=True)
    chemins.sync_demande().write_bytes(b"")


def journal_sync():
    chemin = chemins.journal_sync("2026-11")
    return chemin.read_text("utf-8") if chemin.exists() else ""


def test_demande_d_avant_le_cycle_consommee_sans_cycle_de_plus(distant, github, gh):
    demander()
    assert synchro(github) == 0
    assert not chemins.sync_demande().exists()
    assert len(gh.appels) == 2  # un seul cycle
    assert "demande pendant le cycle" not in journal_sync()


def test_demande_apparue_pendant_le_cycle_un_seul_cycle_de_plus(distant, github, gh):
    gh.pendant = demander  # un hook redemande à chaque contrôle `isPrivate`
    assert synchro(github) == 0
    assert len(gh.appels) == 4  # deux cycles complets, jamais trois
    assert journal_sync().count("demande pendant le cycle : nouveau cycle") == 1
    assert chemins.sync_demande().exists()  # apparue pendant le cycle de plus : au sync suivant


def test_demande_apparue_une_fois_puis_consommee(distant, github, gh):
    vues = []

    def une_fois():
        if not vues:
            vues.append(1)
            demander()

    gh.pendant = une_fois
    assert synchro(github) == 0
    assert len(gh.appels) == 4
    assert not chemins.sync_demande().exists()


def test_cycle_en_echec_garde_la_demande(distant, github, gh):
    gh.reponses = [False]  # dépôt public : échec dès le premier contrôle
    gh.pendant = demander
    assert synchro(github) == 1
    assert len(gh.appels) == 1
    assert chemins.sync_demande().exists()
    assert alertes_sync() == [("depot-public", TEXTE_PUBLIC)]


@windows
def test_mutex_occupe_laisse_la_demande_au_detenteur(distant, github, gh):
    demander()
    enfant = subprocess.Popen(
        [sys.executable, "-c", ENFANT], cwd=RACINE_DEPOT, stdout=subprocess.PIPE, text=True
    )
    try:
        assert enfant.stdout.readline().strip() == "acquis"
        assert synchro(github) == 3
    finally:
        enfant.kill()
        enfant.wait()
    assert chemins.sync_demande().exists()


def test_demande_insupprimable_journalisee_le_cycle_continue(distant, github, gh, monkeypatch):
    demander()
    vrai_unlink = Path.unlink

    def verrouille(chemin, *args, **kwargs):
        if chemin == chemins.sync_demande():
            raise PermissionError(13, "fichier verrouillé")
        return vrai_unlink(chemin, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", verrouille)
    assert synchro(github) == 0
    assert len(gh.appels) == 2  # un seul cycle, sans boucle sur la demande restée en place
    assert "sync-demande non supprimée : PermissionError" in journal_sync()


ID_MESSAGE = "20261106T101500Z-0000000a"
ID_MESSAGE_2 = "20261106T101600Z-0000000b"


def acquittement(identifiant=ID_MESSAGE, pc=PC, projet="demo"):
    return {"schema": 1, "id": identifiant, "projet": projet, "pc": pc, "session": SESSION,
            "heure": "2026-11-06T10:15:00Z"}


def test_acquittements_de_ce_pc_copies_et_commites(distant, github, gh):
    """Story 5.3 : `attente/boite/<projet>/<id>.lu.<pc>` de ce PC recopié dans `donnees/boite/`
    (état « lu par <pc> », M17) ; autre PC, invalide ou divergent : jamais copié."""
    attente, donnees = chemins.attente(), chemins.donnees()
    lu = f"boite/demo/{ID_MESSAGE}.lu.{PC}"
    poser(attente, lu, acquittement())
    poser(attente, f"boite/demo/{ID_MESSAGE}.lu.autre-pc", acquittement(pc="autre-pc"))
    poser(attente, f"boite/demo/{ID_MESSAGE_2}.lu.{PC}", "")  # vide : coupure à l'écriture
    poser(attente, f"boite/autre/{ID_MESSAGE}.lu.{PC}", acquittement())  # projet ≠ contenu
    assert synchro(github) == 0
    assert (donnees / lu).read_text("utf-8") == (attente / lu).read_text("utf-8")
    assert {p for p in arbre(distant) if p.startswith("boite/")} == {lu}
    assert alertes_sync() == [IGNORES]


def test_copier_acquittements_sans_lien_ni_autre_pc(tmp_path):
    attente = chemins.attente()
    poser(attente, f"boite/demo/{ID_MESSAGE}.lu.{PC}", acquittement())
    poser(attente, f"boite/demo/{ID_MESSAGE}.lu.{PC}.1.ab.tmp", acquittement())
    poser(attente, f"boite/demo/{ID_MESSAGE}.json", "{}")  # pas un acquittement
    poser(attente, f"boite/demo/{ID_MESSAGE_2}.lu.{PC}", acquittement())  # id ≠ nom
    assert copie.copier_acquittements(PC) == ([f"boite/demo/{ID_MESSAGE}.lu.{PC}"], 1)
    assert copie.copier_acquittements("autre-pc") == ([], 0)
