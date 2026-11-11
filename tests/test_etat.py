"""Tests de `noyau.etat` : un cas par règle de `etats-action.md` (AD-11)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pilotage.noyau import etat
from pilotage.noyau.etat import calculer_action, critere_manquant
from pilotage.scan import inventaire

PARIS = timezone(timedelta(hours=1))
MAINTENANT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def depot(**champs):
    base = {
        "tag": "v1.0.0", "commits": {"docs": 2, "chore": 1}, "prs_ouvertes": 0, "ci": "verte",
        "topics": [], "stories_ouvertes": 0, "sprint_status": "present", "run": "aucun",
    }
    return {**base, **champs}


def faits(**champs):
    return {"categorie": "classé", "pause": None, "depot": depot(), "attente": None, **champs}


def calcul(f, maintenant=MAINTENANT):
    return calculer_action(f, maintenant, PARIS)


def test_constante_a_classer_alignee_sur_le_scan():
    assert etat.CATEGORIE_A_CLASSER == inventaire.CATEGORIE_A_CLASSER


def test_stable():
    a = calcul(faits())
    assert a.action == "rien-a-faire"
    assert a.raison == {"code": "stable", "params": {}, "texte": "stable"}
    assert (a.quoi, a.type) == ("", None)
    assert etat.LIBELLES_ACTION[a.action] == "Rien à faire"


def test_feat_apres_release_sort_de_rien_a_faire():
    a = calcul(faits(depot=depot(commits={"feat": 1})))
    assert a.action == "a-relancer"
    assert a.raison["critere"] == "commits-depuis-release"


@pytest.mark.parametrize(
    ("depot_", "critere", "texte"),
    [
        (depot(tag=None), "pas-de-release", "à stabiliser : pas de release"),
        (depot(commits={"docs": 1, "fix": 2}), "commits-depuis-release",
         "à stabiliser : commits hors docs/chore depuis v1.0.0"),
        (depot(prs_ouvertes=1), "pr-ouverte", "à stabiliser : PR ouverte"),
        (depot(ci="rouge"), "ci-rouge", "à stabiliser : CI de main rouge"),
        (depot(ci="aucune"), "pas-de-ci", "à stabiliser : pas de CI"),
        (depot(ci="en_cours"), "ci-en-cours", "à stabiliser : CI de main en cours"),
    ],
)
def test_a_stabiliser_un_cas_par_critere(depot_, critere, texte):
    a = calcul(faits(depot=depot_))
    assert a.action == "a-relancer"
    assert a.raison["code"] == "a-stabiliser"
    assert a.raison["critere"] == critere
    assert a.raison["texte"] == texte


def test_params_du_critere_commits():
    a = calcul(faits(depot=depot(commits={"feat": 1})))
    assert a.raison["params"] == {"tag": "v1.0.0"}


def test_story_ouverte_sur_la_fonction_des_criteres_seule():
    assert critere_manquant(depot(stories_ouvertes=2)) == "story-ouverte"


def test_ordre_des_criteres():
    pire = depot(tag=None, commits={"feat": 1}, stories_ouvertes=1, prs_ouvertes=1, ci="rouge")
    assert critere_manquant(pire) == "pas-de-release"
    assert critere_manquant({**pire, "tag": "v1.0.0"}) == "commits-depuis-release"
    assert critere_manquant({**pire, "tag": "v1.0.0", "commits": {}}) == "story-ouverte"
    assert critere_manquant(depot(prs_ouvertes=1, ci="rouge")) == "pr-ouverte"
    assert critere_manquant(depot()) is None
    assert set(etat.CRITERES) >= {"pas-de-release", "ci-en-cours"}


def test_travail_en_cours_story():
    a = calcul(faits(depot=depot(stories_ouvertes=1)))
    assert a.action == "a-relancer"
    assert a.raison == {"code": "story-ouverte", "params": {"n": 1}, "texte": "1 story ouverte"}
    assert calcul(faits(depot=depot(stories_ouvertes=3))).raison["texte"] == "3 stories ouvertes"


def test_travail_en_cours_run_bloque_avant_run_en_cours_avant_story():
    a = calcul(faits(depot=depot(run="bloque", stories_ouvertes=2)))
    assert a.raison["code"] == "run-bloque"
    a = calcul(faits(depot=depot(run="en_cours", stories_ouvertes=2)))
    assert a.raison["code"] == "run-en-cours"
    assert calcul(faits(depot=depot(run="termine"))).raison["code"] == "stable"


def test_pause_non_echue_puis_echue():
    f = faits(pause={"revue": "2026-12-03"})
    a = calcul(f)
    assert a.action == "rien-a-faire"
    assert a.raison["texte"] == "pause jusqu'au 03/12"
    assert a.raison["code"] == "pause"
    a = calcul(f, datetime(2026, 12, 3, 12, tzinfo=UTC))  # le jour même : pas passée
    assert a.action == "rien-a-faire"
    a = calcul(f, datetime(2026, 12, 4, 12, tzinfo=UTC))
    assert a.action == "a-relancer"
    assert a.raison["code"] == "pause-a-revoir"
    assert a.raison["texte"] == "pause à revoir"


def test_pause_echeance_selon_le_fuseau():
    f = faits(pause={"revue": "2026-12-03"})
    # 23:30 UTC le 3 = 00:30 le 4 à Paris (UTC+1) : la revue est passée
    assert calcul(f, datetime(2026, 12, 3, 23, 30, tzinfo=UTC)).action == "a-relancer"
    assert calculer_action(f, datetime(2026, 12, 3, 23, 30, tzinfo=UTC), UTC).action == (
        "rien-a-faire"
    )


def test_travail_en_cours_passe_avant_la_pause():
    f = faits(pause={"revue": "2027-01-01"}, depot=depot(stories_ouvertes=1))
    assert calcul(f).raison["code"] == "story-ouverte"


def test_a_classer_sans_travail():
    a = calcul(faits(categorie=etat.CATEGORIE_A_CLASSER, depot=depot(tag=None)))
    assert a.action == "rien-a-faire"
    assert a.raison["code"] == "a-classer"
    assert "critere" not in a.raison


def test_a_classer_avec_travail_en_cours():
    a = calcul(faits(categorie=etat.CATEGORIE_A_CLASSER, depot=depot(run="en_cours")))
    assert a.action == "a-relancer"


def test_faits_du_depot_non_relus():
    a = calcul(faits(depot=None))
    assert (a.action, a.raison["code"]) == ("a-relancer", "faits-absents")
    assert calcul(faits(depot=None, pause={"revue": "2027-01-01"})).raison["code"] == "pause"


@pytest.mark.parametrize("type_", ["choix", "test", "donnees", "acces"])
def test_attente_un_cas_par_type(type_):
    a = calcul(faits(attente={"origine": "marqueur", "type": type_, "quoi": "valider X"}))
    assert a.action == "attend-utilisateur"
    assert (a.type, a.quoi) == (type_, "valider X")
    assert a.raison == {
        "code": "attend-utilisateur", "params": {"type": type_}, "texte": "vous attend : valider X",
    }


@pytest.mark.parametrize(
    "attente",
    [
        {"origine": "marqueur", "type": None, "quoi": "q"},
        {"origine": "marqueur", "type": "inconnu", "quoi": "q"},
        {"origine": "marqueur", "type": "decision", "quoi": "q"},
        {"origine": "heuristique", "type": None, "quoi": "q"},
        {"origine": "heuristique", "type": "choix", "quoi": "q"},
    ],
)
def test_a_qualifier_un_cas_par_origine(attente):
    a = calcul(faits(attente=attente))
    assert (a.action, a.type) == ("attend-utilisateur", "a-qualifier")


def test_attente_quoi_vide_et_priorite():
    f = faits(attente={"origine": "heuristique", "type": None}, depot=depot(run="bloque"))
    a = calcul(f)
    assert a.action == "attend-utilisateur"
    assert (a.quoi, a.raison["texte"]) == ("", "vous attend")


def test_maintenant_naif_refuse():
    with pytest.raises(ValueError, match="fuseau"):
        calculer_action(faits(), datetime(2026, 11, 6), PARIS)


def test_assemblage_chantier_et_colonnes():
    projets = {
        "beta": faits(chantier="Zeta"),
        "alpha": faits(chantier="Zeta", depot=depot(prs_ouvertes=1)),
        "gamma": faits(attente={"origine": "marqueur", "type": "test", "quoi": "q"}),
        "delta": faits(categorie=etat.CATEGORIE_A_CLASSER),
        "Epsilon": faits(),
        "eta": faits(attente={"origine": "heuristique", "quoi": ""}),
    }
    r = etat.assembler(projets, MAINTENANT, PARIS)
    (zeta,) = r["chantiers"]
    assert (zeta["nom"], zeta["genre"], zeta["chantier"]) == ("Zeta", "chantier", "Zeta")
    assert zeta["action"] == "a-relancer"
    assert (zeta["raison"]["critere"], zeta["famille"]) == ("pr-ouverte", "a-stabiliser")
    assert [p["nom"] for p in zeta["projets"]] == ["alpha", "beta"]
    assert all(c["genre"] == "projet" for c in r["cartes"])
    assert [c["nom"] for c in r["cartes"]] == ["alpha", "beta", "delta", "Epsilon", "eta", "gamma"]
    assert list(r["colonnes"]) == list(etat.ACTIONS)
    noms = {a: [c["nom"] for c in cs] for a, cs in r["colonnes"].items()}
    assert noms == {  # une carte par projet, chantier compris (story 4.8)
        "attend-utilisateur": ["eta", "gamma"],
        "a-relancer": ["alpha"],
        "tourne": [],
        "rien-a-faire": ["beta", "delta", "Epsilon"],
    }
    assert r["comptes"] == {
        "actions": {"attend-utilisateur": 2, "a-relancer": 1, "tourne": 0, "rien-a-faire": 3},
        "types": {"a-qualifier": 1, "test": 1},
        "familles": {"a-stabiliser": 1, "stable": 2, "a-classer": 1},
        "pcs_tourne": {},
        "suivis": 6,
        "stables": 2,
    }


def test_assemblage_vide():
    r = etat.assembler({}, MAINTENANT, PARIS)
    assert list(r) == ["cartes", "colonnes", "chantiers", "comptes", "details"]
    assert (r["cartes"], r["chantiers"], r["details"]) == ([], [], {})
    assert r["comptes"] == {
        "actions": dict.fromkeys(etat.ACTIONS, 0), "types": {}, "familles": {},
        "pcs_tourne": {}, "suivis": 0, "stables": 0,
    }


def test_commits_autre_seul_sort_de_stable():
    assert critere_manquant(depot(commits={"autre": 1})) == "commits-depuis-release"


@pytest.mark.parametrize(
    "depot_",
    [
        {"tag": "v1.0.0", "ci": "verte"},  # champs manquants
        depot(prs_ouvertes=None),
        depot(stories_ouvertes="2"),
        depot(commits=None),
        "pas un objet",
    ],
)
def test_faits_incomplets_ou_mal_types_jamais_stables(depot_):
    assert calcul(faits(depot=depot_)).raison["code"] == "faits-absents"


@pytest.mark.parametrize("pause", [{"revue": "pas une date"}, {"revue": None}, {"autre": 1}])
def test_pause_illisible_a_revoir(pause):
    a = calcul(faits(pause=pause))
    assert (a.action, a.raison["code"], a.raison["params"]) == (
        "a-relancer", "pause-a-revoir", {"revue": None},
    )


def test_pause_revue_datetime_ramenee_a_la_date():
    a = calcul(faits(pause={"revue": datetime(2026, 11, 7, 8, 0)}))
    assert a.raison["texte"] == "pause jusqu'au 07/11"


def test_fuseau_absent_refuse():
    with pytest.raises(ValueError, match="fuseau"):
        calculer_action(faits(), MAINTENANT, None)


def test_tri_deterministe_a_casse_pres():
    r = etat.assembler({"b": faits(), "B": faits()}, MAINTENANT, PARIS)
    assert [c["nom"] for c in r["cartes"]] == ["B", "b"]


# --- Story 7.2 : action renommée, libellé neutre, nom passé par l'appelant --------------------


def test_action_attend_renommee_et_code_identique():
    assert etat.ATTEND == "attend-utilisateur"
    assert etat.ACTIONS[0] == etat.ATTEND and etat.ATTEND in etat.CODES
    assert "attend-anael" not in etat.ACTIONS + etat.CODES
    assert etat.LIBELLES_ACTION[etat.ATTEND] == "Vous attend"


@pytest.mark.parametrize(("utilisateur", "attendu"), [
    ("", "Vous attend"), ("   ", "Vous attend"), (None, "Vous attend"),
    ("Camille", "Attend Camille"), ("  Zoë  ", "Attend Zoë"),
    ("# X", "Vous attend"), ("**X**", "Vous attend"),  # Markdown de TABLEAU.md : nom refusé
])
def test_libelle_action_attend(utilisateur, attendu):
    assert etat.libelle_action(etat.ATTEND, utilisateur) == attendu


def test_libelle_action_autres_actions_sans_nom():
    for action in (etat.A_RELANCER, etat.TOURNE, etat.RIEN):
        assert etat.libelle_action(action, "Camille") == etat.LIBELLES_ACTION[action]
    assert etat.libelle_action(etat.ATTEND) == "Vous attend"


def test_chantiers_tries_par_action_puis_par_nom():
    attente = {"origine": "marqueur", "type": "test", "quoi": "q"}
    projets = {
        "a1": faits(chantier="alpha"),  # stable : Rien à faire
        "b1": faits(chantier="Beta", depot=depot(prs_ouvertes=1)),  # À relancer
        "c1": faits(chantier="charlie", attente=attente),  # Attend
        "d1": faits(chantier="delta"),  # Rien à faire
        "e1": faits(chantier="Echo", depot=depot(tag=None)),  # À relancer
        "e2": faits(chantier="Echo", attente=attente),  # Attend : le chantier prend Attend
    }
    r = etat.assembler(projets, MAINTENANT, PARIS)
    assert [(c["nom"], c["action"]) for c in r["chantiers"]] == [
        ("charlie", "attend-utilisateur"), ("Echo", "attend-utilisateur"),
        ("Beta", "a-relancer"), ("alpha", "rien-a-faire"), ("delta", "rien-a-faire"),
    ]
