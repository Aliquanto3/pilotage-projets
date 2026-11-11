"""Détail du tiroir (story 4.7) : `noyau.etat.criteres` et `noyau.etat.detail`."""

import itertools
from datetime import UTC, datetime, timedelta, timezone

import pytest

from pilotage.noyau import etat

PARIS = timezone(timedelta(hours=1))
MAINTENANT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def depot(**champs):
    base = {
        "tag": "v1.0.0", "commits": {"docs": 2, "chore": 1}, "prs_ouvertes": 0, "ci": "verte",
        "topics": [], "stories_ouvertes": 0, "sprint_status": "present", "run": "aucun",
    }
    return {**base, **champs}


def remplis(depot_):
    return {c["code"]: (c["rempli"], c["precision"]) for c in etat.criteres(depot_)}


def test_criteres_tous_remplis_ordre_et_libelles():
    rendu = etat.criteres(depot())
    assert rendu == [
        {"code": "release", "libelle": "une release publiée", "rempli": True,
         "precision": "v1.0.0"},
        {"code": "commits", "libelle": "aucun commit hors docs/chore depuis la release",
         "rempli": True, "precision": None},
        {"code": "stories", "libelle": "aucune story ouverte", "rempli": True,
         "precision": None},
        {"code": "prs", "libelle": "aucune PR ouverte", "rempli": True, "precision": None},
        {"code": "ci", "libelle": "CI de main verte", "rempli": True, "precision": None},
    ]


@pytest.mark.parametrize(("champs", "code", "attendu"), [
    ({"tag": None}, "release", (False, None)),
    ({"commits": {"feat": 3, "fix": 1, "docs": 5}}, "commits", (False, "4 commits")),
    ({"commits": {"autre": 1}}, "commits", (False, "1 commit")),
    ({"commits": {"docs": 4, "chore": 2}}, "commits", (True, None)),
    ({"commits": {"feat": 0}}, "commits", (True, None)),
    ({"stories_ouvertes": 1}, "stories", (False, "1 story ouverte")),
    ({"stories_ouvertes": 2}, "stories", (False, "2 stories ouvertes")),
    ({"sprint_status": "absent"}, "stories", (True, "pas de sprint-status.yaml")),
    ({"prs_ouvertes": 2}, "prs", (False, None)),
    ({"ci": "rouge"}, "ci", (False, "rouge")),
    ({"ci": "en_cours"}, "ci", (False, "en cours")),
    ({"ci": "aucune"}, "ci", (False, "aucune CI")),
    ({"ci": "inconnue"}, "ci", (False, "aucune CI")),
])
def test_chaque_critere_rempli_ou_non_avec_sa_precision(champs, code, attendu):
    rendu = remplis(depot(**champs))
    assert rendu[code] == attendu
    # les autres critères ne bougent pas
    autres = {c: v for c, v in rendu.items() if c != code}
    assert autres == {c: v for c, v in remplis(depot()).items() if c != code}


GRILLE = list(itertools.product(
    [None, "v1.0.0"],
    [{}, {"docs": 1}, {"feat": 1}, {"autre": 2, "chore": 1}],
    [0, 1, 3],
    [0, 1],
    list(etat.noyau_faits.CI) + ["inconnue"],
    ["present", "absent"],
))


def test_premier_non_rempli_suit_critere_manquant():
    for tag, commits, stories, prs, ci, sprint in GRILLE:
        d = depot(tag=tag, commits=commits, stories_ouvertes=stories, prs_ouvertes=prs, ci=ci,
                  sprint_status=sprint)
        non_remplis = [c["code"] for c in etat.criteres(d) if not c["rempli"]]
        manquant = etat.critere_manquant(d)
        attendu = [] if manquant is None else [etat.CRITERE_DU_CODE[manquant]]
        assert non_remplis[:1] == attendu, d
    assert set(etat.CRITERE_DU_CODE) == set(etat.CRITERES)


def session(**champs):
    base = {"session": "abcdef1234567890", "pc": "pc-a", "pid": 42, "pid_cree": "1",
            "dossier": "demo", "branche": "main", "debut": "2026-11-06T08:41:00Z",
            "statut": "active", "vivante": True}
    return {**base, **champs}


ATTENTE = {"quoi": "q", "depuis": "2026-11-06T09:00:00Z", "type": "choix"}


@pytest.mark.parametrize(("champs", "statut"), [
    ({"attente": ATTENTE, "statut": "attente"}, {"code": "attend", "texte": "en attente"}),
    # attente suivie d'un prompt : la session tourne
    ({"attente": ATTENTE, "dernier_prompt": "2026-11-06T09:30:00Z"},
     {"code": "active", "texte": "active"}),
    ({}, {"code": "active", "texte": "active"}),
    ({"fin": "2026-11-06T10:00:00Z", "statut": "finie", "vivante": False},
     {"code": "finie", "texte": "finie"}),
    ({"statut": "finie", "vivante": True}, {"code": "finie", "texte": "finie"}),
    ({"vivante": False}, {"code": "arretee", "texte": "arrêtée sans fin propre"}),
    ({"vivante": False, "distante": True, "pc": "pc-bureau"},
     {"code": "sans-nouvelles", "texte": "sans nouvelles de pc-bureau"}),
    # attente d'une session morte : pas « en attente »
    ({"attente": ATTENTE, "vivante": False},
     {"code": "arretee", "texte": "arrêtée sans fin propre"}),
])
def test_statut_de_chaque_cas_de_session(champs, statut):
    (rendue,) = etat.detail({"sessions": [session(**champs)]}, PARIS)["sessions"]
    assert rendue["statut"] == statut


def test_session_en_liste_blanche():
    s = session(dernier_tour="2026-11-06T09:47:00Z", fin=None, reprise="reprendre\nla 3.2",
                attente=ATTENTE, nouvelles="2026-11-06T09:00:00Z", distante=False)
    (rendue,) = etat.detail({"sessions": [s]}, PARIS)["sessions"]
    assert rendue == {
        "pc": "pc-a", "statut": {"code": "attend", "texte": "en attente"},
        "debut": "2026-11-06T08:41:00Z", "dernier_tour": "2026-11-06T09:47:00Z", "fin": None,
        "branche": "main", "note": "reprendre\nla 3.2",
    }
    for interdit in ("session", "dossier", "pid", "pid_cree", "attente", "vivante"):
        assert interdit not in rendue


def test_session_sans_champs_facultatifs():
    s = {"vivante": False, "branche": None, "debut": 12, "reprise": ""}
    (rendue,) = etat.detail({"sessions": [s, "pas un objet"]}, PARIS)["sessions"]
    assert rendue == {"pc": "?", "statut": {"code": "arretee", "texte": "arrêtée sans fin propre"},
                      "debut": None, "dernier_tour": None, "fin": None, "branche": None,
                      "note": None}


def test_sessions_triees_par_pc_puis_plus_recente():
    sessions = [
        session(pc="pc-b", debut="2026-11-06T08:00:00Z"),
        session(pc="PC-A", debut="2026-11-05T08:00:00Z"),
        session(pc="pc-b", debut="2026-11-05T08:00:00Z", dernier_tour="2026-11-06T11:00:00Z"),
        session(pc="pc-a", debut="2026-11-06T07:00:00Z"),
    ]
    rendu = etat.detail({"sessions": sessions}, PARIS)["sessions"]
    assert [(s["pc"], s["debut"]) for s in rendu] == [
        ("pc-a", "2026-11-06T07:00:00Z"),
        ("PC-A", "2026-11-05T08:00:00Z"),
        ("pc-b", "2026-11-05T08:00:00Z"),  # dernier tour à 11:00 : la plus récente
        ("pc-b", "2026-11-06T08:00:00Z"),
    ]


def test_depot_en_liste_blanche_commits_dans_l_ordre_sans_zeros():
    d = depot(commits={"fix": 1, "autre": 2, "feat": 3, "docs": 0}, topics=["status-dev"],
              run="en_cours", stories_ouvertes=2, sprint_status="present")
    rendu = etat.detail({"depot": d, "depot_de": {"pc": "pc-b", "genere_a": "x"}}, PARIS)
    assert rendu["depot"] == {
        "tag": "v1.0.0", "commits": {"feat": 3, "fix": 1, "autre": 2}, "prs_ouvertes": 0,
        "stories_ouvertes": 2, "ci": "verte", "sprint_status": "present",
    }
    assert list(rendu["depot"]["commits"]) == ["feat", "fix", "autre"]
    assert rendu["depot_de"] == {"pc": "pc-b", "genere_a": "x"}
    assert rendu["criteres"] == etat.criteres(d)


@pytest.mark.parametrize("depot_", [None, {"tag": "v1.0.0"}, depot(prs_ouvertes=-1),
                                     depot(commits={"feat": "3"})])
def test_depot_absent_ou_illisible(depot_):
    rendu = etat.detail({"depot": depot_}, PARIS)
    assert rendu == {"sessions": [], "depot": None, "depot_de": None, "criteres": None}


def test_fuseau_obligatoire():
    with pytest.raises(ValueError, match="fuseau"):
        etat.detail({}, "Europe/Paris")


def test_assembler_rend_un_detail_par_projet_a_part_des_cartes():
    projets = {"b": {"depot": depot(), "sessions": [session()]}, "a": {"depot": None}}
    r = etat.assembler(projets, MAINTENANT, PARIS)
    assert list(r["details"]) == ["a", "b"]
    assert r["details"]["b"] == etat.detail(projets["b"], PARIS)
    assert all("sessions" not in c and "criteres" not in c for c in r["cartes"])


@pytest.mark.parametrize("commits", [{"feat": 2, "fix": -2}, {"fix": -1}])
def test_criteres_suit_critere_manquant_meme_sur_des_comptes_negatifs(commits):
    # hors schéma (`instantane` refuse n < 0) : le critère des commits suit `any`, comme lui
    d = depot(commits=commits)
    assert etat.critere_manquant(d) == "commits-depuis-release"
    rendu = {c["code"]: c for c in etat.criteres(d)}["commits"]
    assert rendu["rempli"] is False
