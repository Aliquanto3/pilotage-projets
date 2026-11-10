import ast
import base64
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilotage import chemins
from pilotage.noyau import faits, schemas
from pilotage.noyau.schemas import ErreurValidation
from pilotage.scan import faits_gh
from pilotage.scan.inventaire import Inventaire

SPRINT = (
    "development_status:\n  epic-1: in-progress\n  1-1-a: done\n  1-2-b: review\n"
    "  1-3-c: backlog\n  epic-1-retrospective: optional\n"
)
RUN = "## Journal\n- 2026-11-06 10:00 · 1.1 · dev · lancé · abc\n"
MAINTENANT = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)


def _ok(sortie) -> subprocess.CompletedProcess:
    texte = sortie if isinstance(sortie, str) else json.dumps(sortie)
    return subprocess.CompletedProcess([], 0, texte, "")


def _b64(texte: str) -> str:
    return base64.encodebytes(texte.encode()).decode()


def faux_gh(*, release="v1.2.3", commits=None, prs=2, run=None, sprint=SPRINT, journal=RUN,
            topics=("status-dev", "ai-portfolio", "secret"), echec=(), appels=None):
    """Exécuteur `gh` simulé ; `echec` : sous-chaînes d'arguments dont l'appel échoue."""
    par_defaut = ["feat: x", "fix(a): y", "Merge pull request", "chore!: z"]
    commits = par_defaut if commits is None else commits
    run = [{"status": "completed", "conclusion": "success"}] if run is None else run

    def executeur(args, delai):
        if appels is not None:
            appels.append((list(args), delai))
        ligne = " ".join(args)
        for motif in echec:
            if motif in ligne:
                return subprocess.CompletedProcess([], 1, "", "boom")
        if args[:2] == ["repo", "view"]:
            return _ok({"defaultBranchRef": {"name": "main"},
                        "repositoryTopics": [{"name": t} for t in topics]})
        if args[:2] == ["release", "list"]:
            return _ok([{"tagName": release}] if release else [])
        if args[0] == "api" and "/compare/" in ligne:
            return _ok("".join(json.dumps(m) + "\n" for m in commits))
        if args[0] == "api" and "/commits?" in ligne:
            return _ok(commits)
        if args[:2] == ["pr", "list"]:
            return _ok([{"number": n} for n in range(prs)])
        if args[:2] == ["run", "list"]:
            return _ok(run)
        if "sprint-status.yaml" in ligne or "run-autonome.md" in ligne:
            contenu = sprint if "sprint-status" in ligne else journal
            if contenu is None:
                return subprocess.CompletedProcess([], 1, "", "gh: Not Found (HTTP 404)")
            return _ok(["base64", _b64(contenu)])
        raise AssertionError(ligne)

    return executeur


def test_faits_complets_et_commandes_exactes():
    appels = []
    resultat = faits_gh.lire_faits_depot("demo", faux_gh(appels=appels))
    assert resultat == {
        "tag": "v1.2.3",
        "commits": {"feat": 1, "fix": 1, "chore": 1, "autre": 1},
        "prs_ouvertes": 2,
        "ci": "verte",
        "topics": ["ai-portfolio", "status-dev"],
        "stories_ouvertes": 2,
        "sprint_status": "present",
        "run": "en_cours",
    }
    args = [a for a, _ in appels]
    assert args[0] == ["repo", "view", "proprio-test/demo", "--json",
                       "defaultBranchRef,repositoryTopics"]
    assert args[1] == ["release", "list", "--repo", "proprio-test/demo", "--limit", "1",
                       "--json", "tagName"]
    assert args[2] == ["api", "repos/proprio-test/demo/compare/v1.2.3...main?per_page=100",
                       "--paginate", "--jq", faits_gh._JQ_MESSAGES]
    assert ["pr", "list", "--repo", "proprio-test/demo", "--state", "open", "--limit", "1000",
            "--json", "number"] in args
    assert ["run", "list", "--repo", "proprio-test/demo", "--branch", "main", "--limit", "1",
            "--json", "status,conclusion"] in args
    assert ["api", "repos/proprio-test/demo/contents/_bmad-output/implementation-artifacts/"
            "sprint-status.yaml?ref=main", "--jq", "[.encoding, .content]"] in args
    assert {d for _, d in appels} == {faits_gh.DELAI_S}


def test_sans_release_commits_de_la_branche_et_tag_invalide():
    appels = []
    r = faits_gh.lire_faits_depot("demo", faux_gh(release=None, appels=appels))
    assert r["tag"] is None
    assert appels[2][0][1] == "repos/proprio-test/demo/commits?sha=main&per_page=100"
    r = faits_gh.lire_faits_depot("demo", faux_gh(release="beta-2"))
    assert r["tag"] is None


def test_sprint_absent_et_run_absent():
    r = faits_gh.lire_faits_depot("demo", faux_gh(sprint=None, journal=None))
    assert (r["stories_ouvertes"], r["sprint_status"], r["run"]) == (0, "absent", "aucun")


def test_sprint_illisible_ou_ci_vide():
    with pytest.raises(faits_gh.ErreurGh):
        faits_gh.lire_faits_depot("demo", faux_gh(sprint="a: [1"))
    assert faits_gh.lire_faits_depot("demo", faux_gh(run=[]))["ci"] == "aucune"


@pytest.mark.parametrize("motif", ["repo view", "release list", "compare", "pr list", "run list",
                                   "sprint-status", "run-autonome"])
def test_chaque_echec_gh_leve(motif):
    with pytest.raises(faits_gh.ErreurGh):
        faits_gh.lire_faits_depot("demo", faux_gh(echec=(motif,)))


def test_branche_par_defaut_suspecte_refusee():
    def executeur(args, delai):
        return _ok({"defaultBranchRef": {"name": "a b;rm"}, "repositoryTopics": []})

    with pytest.raises(faits_gh.ErreurGh):
        faits_gh.lire_faits_depot("demo", executeur)


def test_echec_pour_un_projet_les_autres_lus_avec_alerte():
    inv = Inventaire(projets=[{"projet": "bon"}, {"projet": "mauvais"}])
    instantane = faits_gh.construire_instantane(
        inv, faux_gh(echec=("proprio-test/mauvais",)), MAINTENANT
    )
    assert instantane["projets"]["mauvais"] == {"faits_depot": None, "sessions_vivantes": []}
    assert instantane["projets"]["bon"]["faits_depot"]["prs_ouvertes"] == 2
    assert instantane["genere_a"] == "2026-11-06T12:00:00Z"
    assert inv.alertes == [
        {"code": "faits-github-non-relus", "message": "Faits GitHub non relus : mauvais.",
         "params": {"projet": "mauvais"}}
    ]


def test_instantane_sans_texte_libre():
    messages = ["feat: SECRET-TITRE", "texte libre quelconque"]
    inv = Inventaire(projets=[{"projet": "demo"}])
    instantane = faits_gh.construire_instantane(inv, faux_gh(commits=messages), MAINTENANT)
    texte = json.dumps(instantane)
    assert "SECRET" not in texte and "libre" not in texte and "secret" not in texte
    assert instantane["projets"]["demo"]["faits_depot"]["commits"] == {"feat": 1, "autre": 1}


def test_executeur_reel_sans_gh_leve(monkeypatch):
    def boum(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", boum)
    with pytest.raises(faits_gh.ErreurGh):
        faits_gh.executeur_gh(["--version"], 1.0)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(
        subprocess.TimeoutExpired("gh", 1)))
    with pytest.raises(faits_gh.ErreurGh):
        faits_gh.executeur_gh(["--version"], 1.0)


def test_executeur_reel_appelle_gh_sans_shell(monkeypatch):
    vu = {}

    def faux_run(cmd, **kw):
        vu.update(cmd=cmd, **kw)
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", faux_run)
    assert faits_gh.executeur_gh(["pr", "list"], 5.0).stdout == "ok"
    assert vu["cmd"] == ["gh", "pr", "list"]
    assert vu["timeout"] == 5.0 and not vu.get("shell")


def test_scan_n_importe_aucun_client_de_modele():
    interdits = {"anthropic", "openai", "ollama", "litellm", "httpx", "requests", "aiohttp",
                 "urllib3", "cohere", "mistralai", "google", "langchain", "transformers"}
    dossier = Path(__file__).resolve().parent.parent / "pilotage" / "scan"
    trouves = set()
    for fichier in dossier.glob("*.py"):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Import):
                trouves |= {a.name.split(".")[0] for a in noeud.names}
            elif isinstance(noeud, ast.ImportFrom) and noeud.module and not noeud.level:
                trouves.add(noeud.module.split(".")[0])
    assert trouves & interdits == set()


# --- noyau.faits ---

@pytest.mark.parametrize(("message", "attendu"), [
    ("feat: a", "feat"), ("Fix(core): a", "fix"), ("feat!: a", "feat"), ("revert: a", "revert"),
    ("autre: a", "autre"), ("wip: a", "autre"), ("pas de préfixe", "autre"),
    ("feat sans deux-points", "autre"),
    (None, "autre"), ("", "autre"),
])
def test_type_commit(message, attendu):
    assert faits.type_commit(message) == attendu


@pytest.mark.parametrize(("valeur", "attendu"), [
    ("v1.2.3", "v1.2.3"), ("1.2.3", "1.2.3"), ("v1.2", None), ("v1.2.3-rc1", None),
    ("xv1.2.3", None), (None, None), (3, None),
])
def test_tag(valeur, attendu):
    assert faits.tag_ou_none(valeur) == attendu


@pytest.mark.parametrize(("statut", "conclusion", "attendu"), [
    (None, None, "aucune"), ("in_progress", None, "en_cours"), ("queued", None, "en_cours"),
    ("completed", "success", "verte"), ("completed", "failure", "rouge"),
    ("completed", "timed_out", "rouge"), ("completed", "cancelled", "aucune"),
    ("completed", "skipped", "aucune"),
])
def test_ci(statut, conclusion, attendu):
    assert faits.ci_depuis(statut, conclusion) == attendu


def test_topics_et_stories():
    assert faits.topics_connus(["status-dev", "x", "status-dev", 3, "ai-portfolio"]) == [
        "ai-portfolio", "status-dev"]
    assert faits.topics_connus("status-dev") == []
    assert faits.stories_ouvertes({"1-1-a": "done", "1-2-b": "review", "epic-1": "x", 5: "x"}) == 1
    assert faits.stories_ouvertes(None) == 0


def test_etat_run():
    entete = "## Journal\n"
    dev = "- 2026-11-06 10:00 · 1.1 · dev · lancé · abc\n"
    bloque = "- 2026-11-06 11:00 · 1.2 · blocked · cause · -\n"
    menage = "- 2026-11-06 12:00 · run · ménage · ok · -\n"
    assert faits.etat_run(None) == "aucun"
    assert faits.etat_run("ETAT: reprise\nrien") == "aucun"
    assert faits.etat_run(entete + dev) == "en_cours"
    assert faits.etat_run(entete + dev + bloque) == "bloque"
    assert faits.etat_run(entete + bloque + dev) == "en_cours"
    assert faits.etat_run(entete + dev + bloque + menage) == "termine"


# --- schéma instantané ---

def _valide():
    return {"schema": 1, "genere_a": "2026-11-06T12:00:00Z", "projets": {"demo": {
        "faits_depot": {"tag": None, "commits": {"feat": 1}, "prs_ouvertes": 0, "ci": "aucune",
                        "topics": [], "stories_ouvertes": 0, "sprint_status": "absent",
                        "run": "aucun"},
        "sessions_vivantes": ["12345678-1234-1234-1234-123456789abc"]}}}


def test_instantane_valide_et_null():
    schemas.valider("instantane", _valide())
    o = _valide()
    o["projets"]["demo"]["faits_depot"] = None
    schemas.valider("instantane", o)


def _modif(chemin, valeur):
    o = _valide()
    cible = o
    for c in chemin[:-1]:
        cible = cible[c]
    if valeur is KeyError:
        del cible[chemin[-1]]
    else:
        cible[chemin[-1]] = valeur
    return o


F = ("projets", "demo", "faits_depot")


@pytest.mark.parametrize(("objet", "motif"), [
    ([], "un objet est attendu"),
    (_modif(("extra",), 1), "champ inconnu : extra"),
    (_modif(("schema",), 2), "schema 1 attendu"),
    (_modif(("genere_a",), "hier"), "genere_a"),
    (_modif(("projets", "Bad Name"), {}), "projet"),
    (_modif(("projets", "demo", "titre"), "x"), "champ inconnu : titre"),
    (_modif((*F, "titre_pr"), "x"), "champ inconnu : titre_pr"),
    (_modif((*F, "ci"), "vert"), "ci hors de l'énumération"),
    (_modif((*F, "run"), "x"), "run hors"),
    (_modif((*F, "tag"), "branche libre"), "tag"),
    (_modif((*F, "commits"), {"message libre": 1}), "type de commit"),
    (_modif((*F, "commits"), {"feat": -1}), "entier"),
    (_modif((*F, "prs_ouvertes"), True), "entier"),
    (_modif((*F, "topics"), ["texte"]), "topic"),
    (_modif((*F, "topics"), ["status-dev", "ai-portfolio"]), "triés"),
    (_modif((*F, "sprint_status"), "oui"), "sprint_status"),
    (_modif((*F, "run"), KeyError), "champ manquant : run"),
    (_modif(("projets", "demo", "sessions_vivantes"), ["pas-un-uuid"]), "session"),
    (_modif(("projets", "demo", "faits_depot"), "texte"), "un objet ou null"),
])
def test_instantane_refuse(objet, motif):
    with pytest.raises(ErreurValidation, match=motif):
        schemas.valider("instantane", objet)


@pytest.mark.parametrize(
    "faux",
    [
        faux_gh(sprint="d: 2026-13-45\n"),  # date YAML invalide : ValueError
        faux_gh(release=None, commits={"pas": "une liste"}),  # sortie inattendue
    ],
)
def test_projet_illisible_isole_les_autres_lus(faux):
    def executeur(args, delai):
        if "proprio-test/mauvais" in " ".join(args):
            return faux(args, delai)
        return faux_gh()(args, delai)

    inv = Inventaire(projets=[{"projet": "bon"}, {"projet": "mauvais"}])
    instantane = faits_gh.construire_instantane(inv, executeur, MAINTENANT)
    assert instantane["projets"]["mauvais"]["faits_depot"] is None
    assert instantane["projets"]["bon"]["faits_depot"]["prs_ouvertes"] == 2
    assert [a["code"] for a in inv.alertes] == [faits_gh.ALERTE_NON_RELUS]


def test_branche_de_forme_inattendue_isolee():
    def executeur(args, delai):
        if args[:2] == ["repo", "view"]:
            return _ok({"defaultBranchRef": "main", "repositoryTopics": []})
        raise AssertionError(args)

    inv = Inventaire(projets=[{"projet": "demo"}])
    instantane = faits_gh.construire_instantane(inv, executeur, MAINTENANT)
    assert instantane["projets"]["demo"]["faits_depot"] is None
    assert len(inv.alertes) == 1


def test_branche_commencant_par_tiret_refusee():
    def executeur(args, delai):
        return _ok({"defaultBranchRef": {"name": "-x"}, "repositoryTopics": []})

    with pytest.raises(faits_gh.ErreurGh):
        faits_gh.lire_faits_depot("demo", executeur)


def test_fichier_trop_gros_est_un_echec_pas_zero_story():
    base = faux_gh()

    def executeur(args, delai):
        if "sprint-status.yaml" in " ".join(args):
            return _ok(["none", ""])
        return base(args, delai)

    with pytest.raises(faits_gh.ErreurGh):
        faits_gh.lire_faits_depot("demo", executeur)


def test_compare_compte_toutes_les_pages():
    messages = ["feat: a"] * 300 + ["fix: b"] * 5
    r = faits_gh.lire_faits_depot("demo", faux_gh(commits=messages))
    assert r["commits"] == {"feat": 300, "fix": 5}


def test_statut_non_textuel_compte_ouvert():
    r = faits_gh.lire_faits_depot("demo", faux_gh(sprint="development_status:\n  1-1-a: [x]\n"))
    assert r["stories_ouvertes"] == 1


def test_proprietaire_lu_dans_la_configuration(monkeypatch):
    monkeypatch.setenv(chemins.VARIABLE_PROPRIETAIRE, "Autre-Proprio")
    appels = []
    faits_gh.lire_faits_depot("demo", faux_gh(appels=appels))
    assert appels[0][0][:3] == ["repo", "view", "Autre-Proprio/demo"]
    appels.clear()
    faits_gh.lire_faits_depot("demo", faux_gh(appels=appels), "explicite")
    assert appels[0][0][:3] == ["repo", "view", "explicite/demo"]


@pytest.mark.parametrize("valeur", [None, "", "-tiret", "a" * 40])
def test_sans_proprietaire_instantane_refuse_sans_appel_gh(monkeypatch, valeur):
    if valeur is None:
        monkeypatch.delenv(chemins.VARIABLE_PROPRIETAIRE)
    else:
        monkeypatch.setenv(chemins.VARIABLE_PROPRIETAIRE, valeur)
    appels = []
    inv = Inventaire(projets=[{"projet": "demo"}])
    with pytest.raises(chemins.ConfigurationGithubAbsente, match="proprietaire_github"):
        faits_gh.construire_instantane(inv, faux_gh(appels=appels), MAINTENANT)
    assert appels == []
