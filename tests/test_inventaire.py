import json
import os
import subprocess
import sys

import pytest

pytest.importorskip("yaml")  # PyYAML : groupe `outils` ; absent, ces tests sont sautés

from pilotage import chemins  # noqa: E402
from pilotage.noyau.schemas import ErreurValidation  # noqa: E402
from pilotage.scan import inventaire as inv  # noqa: E402


def faux_depot(dossier, url="https://github.com/Proprio-Test/Mon-Depot.git", branche="main"):
    git = dossier / ".git"
    git.mkdir(parents=True)
    ligne = f'[remote "origin"]\n\turl = {url}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
    (git / "config").write_text('[core]\n\tbare = false\n' + (ligne if url else ""), "utf-8")
    (git / "HEAD").write_text(f"ref: refs/heads/{branche}\n", "utf-8")
    return dossier


def faux_worktree(dossier, principal, nom="wt", branche="story/1-3"):
    gitdir = principal / ".git" / "worktrees" / nom
    gitdir.mkdir(parents=True)
    (gitdir / "commondir").write_text("../..\n", "utf-8")
    (gitdir / "HEAD").write_text(f"ref: refs/heads/{branche}\n", "utf-8")
    dossier.mkdir(parents=True)
    (dossier / ".git").write_text(f"gitdir: {gitdir}\n", "utf-8")
    return dossier


def ecrire(chemin, texte):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, "utf-8")
    return chemin


@pytest.fixture
def racine(tmp_path):
    return tmp_path / "github"


def test_un_projet_deux_postes_et_ignores(racine):
    principal = faux_depot(racine / "Mon-Depot")
    faux_worktree(racine / "_worktrees" / "mon-depot-1-3", principal)
    faux_depot(racine / "etranger", url="git@github.com:Autre/etranger.git")
    faux_depot(racine / "sans-remote", url="")
    (racine / "vide").mkdir()
    res = inv.inventorier(racine)
    assert res.alertes == []
    assert len(res.projets) == 1
    projet = res.projets[0]
    assert projet["projet"] == "mon-depot"
    assert projet["categorie"] == "découvert, à classer"
    assert projet["postes"] == [
        {"dossier": "Mon-Depot", "type": "dossier", "branche": "main", "run": None},
        {
            "dossier": "_worktrees/mon-depot-1-3",
            "type": "worktree",
            "branche": "story/1-3",
            "run": None,
        },
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/Proprio-Test/depot",
        "https://github.com/proprio-test/depot.git",
        "https://user:tok@github.com/Proprio-Test/depot.git",
        "git@github.com:Proprio-Test/depot.git",
        "ssh://git@github.com/Proprio-Test/depot.git",
        "ssh://git@github.com:22/Proprio-Test/depot",
    ],
)
def test_formes_d_url(racine, url):
    faux_depot(racine / "d", url=url)
    assert [p["projet"] for p in inv.inventorier(racine).projets] == ["depot"]


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/Proprio-Test3/depot.git",
        "https://gitlab.com/Proprio-Test/depot.git",
        "https://github.com/Autre/Proprio-Test.git",
    ],
)
def test_url_hors_proprietaire(racine, url):
    faux_depot(racine / "d", url=url)
    assert inv.inventorier(racine).projets == []


def test_origin_ignore_puis_autre_remote(racine):
    d = faux_depot(racine / "d", url="https://github.com/Autre/x.git")
    with open(d / ".git" / "config", "a", encoding="utf-8") as f:
        f.write('[remote "perso"]\n\turl = git@github.com:Proprio-Test/vrai.git\n')
    assert [p["projet"] for p in inv.inventorier(racine).projets] == ["vrai"]


def test_head_detachee_et_config_illisible(racine):
    d = faux_depot(racine / "d")
    (d / ".git" / "HEAD").write_text("0123456789abcdef\n", "utf-8")
    assert inv.inventorier(racine).projets[0]["postes"][0]["branche"] is None
    (d / ".git" / "config").write_text("pas de section\n", "utf-8")
    assert inv.inventorier(racine).projets == []


def test_profondeur_et_dossiers_caches(racine):
    faux_depot(racine / "a" / "b" / "c")
    faux_depot(racine / ".cache" / "x")
    faux_depot(racine / "a" / "b2", url="https://github.com/Proprio-Test/b2.git")
    noms = [p["projet"] for p in inv.inventorier(racine).projets]
    assert noms == ["b2"]


def test_nom_de_projet_invalide_alerte(racine):
    faux_depot(racine / "d", url="https://github.com/Proprio-Test/nul")
    res = inv.inventorier(racine)
    assert res.projets == []
    assert [a["code"] for a in res.alertes] == ["depot-ignore"]


def projets_yaml(tmp_path, texte):
    return ecrire(tmp_path / "projets.yaml", texte)


def test_exclus_absent_de_toute_sortie(racine, tmp_path):
    faux_depot(racine / "a", url="https://github.com/Proprio-Test/garde.git")
    faux_depot(racine / "b", url="https://github.com/Proprio-Test/jette.git")
    py = projets_yaml(tmp_path, "schema: 1\nexclus: [jette]\n")
    res = inv.inventorier(racine, py)
    assert [p["projet"] for p in res.projets] == ["garde"]
    assert inv.table_dossiers(res) == {"schema": 1, "dossiers": {"a": "garde"}}
    chemin = inv.ecrire_table(res)
    assert "jette" not in chemin.read_text("utf-8")


def test_classe_et_a_classer_et_pause(racine, tmp_path):
    faux_depot(racine / "a", url="https://github.com/Proprio-Test/a.git")
    faux_depot(racine / "b", url="https://github.com/Proprio-Test/b.git")
    py = projets_yaml(
        tmp_path,
        "schema: 1\nchantiers:\n  outils:\n    projets: [a]\ndependances: ['a ← b']\n"
        "pauses:\n  b:\n    revue: 2026-12-01\n",
    )
    a, b = inv.inventorier(racine, py).projets
    assert (a["categorie"], a["chantier"], a["pause"]) == ("classé", "outils", None)
    assert (b["categorie"], b["chantier"], b["pause"]) == (
        "découvert, à classer",
        None,
        {"revue": "2026-12-01"},
    )


def test_projets_yaml_absent(racine, tmp_path):
    faux_depot(racine / "a")
    res = inv.inventorier(racine, tmp_path / "absent.yaml")
    assert res.alertes == [] and not res.lecture_seule and len(res.projets) == 1


def test_projets_yaml_par_defaut_sous_donnees(racine):
    faux_depot(racine / "a", url="https://github.com/Proprio-Test/a.git")
    ecrire(chemins.donnees() / "projets.yaml", "schema: 1\nexclus: [a]\n")
    assert inv.inventorier(racine).projets == []


def test_schema_plus_recent_lecture_seule(racine, tmp_path):
    faux_depot(racine / "a", url="https://github.com/Proprio-Test/a.git")
    py = projets_yaml(
        tmp_path,
        "schema: 2\nchantiers:\n  c:\n    projets: [a]\nnouveau_champ: {x: 1}\n",
    )
    res = inv.inventorier(racine, py)
    assert res.lecture_seule is True
    assert res.alertes == [
        {
            "code": "projets-version-recente",
            "message": "PC en version plus récente : projets.yaml en lecture seule",
        }
    ]
    assert res.projets[0]["chantier"] == "c"


@pytest.mark.parametrize(
    "texte",
    [
        "schema: 1\ninconnu: 1\n",
        "chantiers: {}\n",
        "schema: [\n",
        "- liste\n",
        "schema: 1\ndependances: ['a - b']\n",
    ],
)
def test_projets_yaml_invalide_ignore(racine, tmp_path, texte):
    faux_depot(racine / "a", url="https://github.com/Proprio-Test/a.git")
    res = inv.inventorier(racine, projets_yaml(tmp_path, texte))
    assert res.lecture_seule is False
    assert [a["code"] for a in res.alertes] == ["projets-invalide"]
    assert res.alertes[0]["message"].startswith("projets.yaml ignoré : ")
    assert len(res.projets) == 1 and res.projets[0]["categorie"] == "découvert, à classer"


def test_projets_yaml_illisible(racine, tmp_path):
    (tmp_path / "projets.yaml").mkdir()
    res = inv.inventorier(racine, tmp_path / "projets.yaml")
    assert [a["code"] for a in res.alertes] == ["projets-illisible"]


def test_table_ecrite_atomiquement(racine):
    principal = faux_depot(racine / "Mon-Depot")
    faux_worktree(racine / "_worktrees" / "wt", principal)
    chemin = inv.ecrire_table(inv.inventorier(racine))
    assert chemin == chemins.table_dossiers()
    attendu = {"schema": 1, "dossiers": {"mon-depot": "mon-depot", "_worktrees/wt": "mon-depot"}}
    assert json.loads(chemin.read_text("utf-8")) == attendu
    assert list(chemin.parent.glob("*.tmp")) == []


def test_ecrire_table_refuse_si_invalide(racine, tmp_path):
    res = inv.Inventaire(projets=[{"projet": "X", "postes": [{"dossier": "a"}]}])
    cible = tmp_path / "t.json"
    with pytest.raises(ErreurValidation):
        inv.ecrire_table(res, cible)
    assert not cible.exists()


def run(dossier, texte):
    return ecrire(dossier / "_bmad-output" / "implementation-artifacts" / "run-autonome.md", texte)


def test_run_non_termine_puis_termine(racine):
    d = faux_depot(racine / "a")
    assert inv.etat_run(d) is None
    run(d, "# Run\n## Journal\n\n- 2026-11-06 10:00 · 1.1 · dev · lancé · —\nETAT: x\n")
    assert inv.etat_run(d) == {"present": True, "termine": False}
    run(d, "## Journal\n- 2026-11-06 10:00 · 1.1 · dev · lancé · —\n"
           "- 2026-11-06 11:00 · run · ménage · fait · abc\n")
    assert inv.etat_run(d) == {"present": True, "termine": True}
    run(d, "## Journal\n\n")
    assert inv.etat_run(d) == {"present": True, "termine": True}
    assert inv.inventorier(racine).projets[0]["postes"][0]["run"] == inv.etat_run(d)


def test_scan_avec_vrai_git(racine):
    git = pytest.importorskip("shutil").which("git")
    if git is None:
        pytest.skip("git absent")
    d = racine / "reel"
    d.mkdir(parents=True)
    for args in (
        ["init", "-q", "-b", "trunk"],
        ["remote", "add", "origin", "https://github.com/Proprio-Test/Reel.git"],
    ):
        subprocess.run([git, "-C", str(d), *args], check=True, capture_output=True)
    wt = racine / "_worktrees" / "reel-wt"
    subprocess.run(
        [git, "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
         "--allow-empty", "-m", "i"],
        check=True, capture_output=True,
    )
    subprocess.run(
        [git, "-C", str(d), "worktree", "add", "-q", "-b", "autre", str(wt)],
        check=True, capture_output=True,
    )
    (projet,) = inv.inventorier(racine).projets
    assert projet["projet"] == "reel"
    assert [(p["dossier"], p["type"], p["branche"]) for p in projet["postes"]] == [
        ("_worktrees/reel-wt", "worktree", "autre"),
        ("reel", "dossier", "trunk"),
    ]




def test_jonction_hors_racine_non_suivie(racine, tmp_path):
    dehors = faux_depot(tmp_path / "dehors" / "d", url="https://github.com/Proprio-Test/fuite.git")
    racine.mkdir()
    lien = racine / "lien"
    if sys.platform == "win32":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(lien), str(dehors.parent)],
                           capture_output=True, check=False)
        cree = r.returncode == 0
    else:
        try:
            os.symlink(dehors.parent, lien, target_is_directory=True)
            cree = True
        except OSError:
            cree = False
    if not cree:
        pytest.skip("création de jonction ou de lien impossible sur ce poste")
    assert inv.inventorier(racine).projets == []


@pytest.mark.parametrize(
    "texte",
    [
        "schema: 1\nexclus:\nchantiers:\ndependances:\npauses:\n",
        "schema: 1\nchantiers:\n  vide:\n  autre:\n    projets:\n",
    ],
)
def test_cles_sans_valeur_lues_comme_vides(racine, tmp_path, texte):
    faux_depot(racine / "a", url="https://github.com/Proprio-Test/a.git")
    res = inv.inventorier(racine, projets_yaml(tmp_path, texte))
    assert res.alertes == []
    assert res.projets[0]["categorie"] == "découvert, à classer"


def test_cle_dupliquee_refusee(racine, tmp_path):
    faux_depot(racine / "a", url="https://github.com/Proprio-Test/a.git")
    res = inv.inventorier(racine, projets_yaml(tmp_path, "schema: 1\nexclus: [a]\nexclus: []\n"))
    assert res.alertes == [
        {"code": "projets-invalide", "message": "projets.yaml ignoré : clé dupliquée (ligne 3)",
         "params": {"detail": "clé dupliquée (ligne 3)"}}
    ]
    imbrique = "schema: 1\nchantiers:\n  c:\n    projets: [a]\n    projets: []\n"
    assert [a["code"] for a in inv.lire_projets(projets_yaml(tmp_path, imbrique))[2]] == [
        "projets-invalide"
    ]


def test_table_cle_normalisee_et_doublon_de_casse():
    res = inv.Inventaire(
        projets=[
            {"projet": "a", "postes": [{"dossier": "Perso/Depot"}]},
            {"projet": "b", "postes": [{"dossier": "perso/depot"}, {"dossier": "Autre"}]},
        ]
    )
    assert inv.table_dossiers(res) == {"schema": 1, "dossiers": {"perso/depot": "a", "autre": "b"}}
    assert [a["code"] for a in res.alertes] == ["dossier-doublon-casse"]


def test_proprietaire_configure_casse_ignoree(racine, monkeypatch):
    monkeypatch.setenv(chemins.VARIABLE_PROPRIETAIRE, "PROPRIO-test")
    faux_depot(racine / "a", url="https://github.com/proprio-TEST/a.git")
    faux_depot(racine / "b", url="https://github.com/autre/b.git")
    assert [p["projet"] for p in inv.inventorier(racine).projets] == ["a"]
    monkeypatch.setenv(chemins.VARIABLE_PROPRIETAIRE, "autre")
    assert [p["projet"] for p in inv.inventorier(racine).projets] == ["b"]


@pytest.mark.parametrize("valeur", [None, "", "a b", "fin-"])
def test_sans_proprietaire_inventaire_refuse(racine, monkeypatch, valeur):
    if valeur is None:
        monkeypatch.delenv(chemins.VARIABLE_PROPRIETAIRE)
    else:
        monkeypatch.setenv(chemins.VARIABLE_PROPRIETAIRE, valeur)
    faux_depot(racine / "a", url="https://github.com/Proprio-Test/a.git")
    with pytest.raises(chemins.ConfigurationGithubAbsente, match="proprietaire_github"):
        inv.inventorier(racine)
