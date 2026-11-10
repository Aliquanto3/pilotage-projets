"""Tests de `noyau.assemblage` et des sessions d'autres PC dans `calculer_action` (story 3.4)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pilotage.noyau import assemblage, etat

PARIS = timezone(timedelta(hours=1))
MAINTENANT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
SID = "0a1b2c3d-0000-4000-8000-000000000001"
DEPOT = {
    "tag": "v1.0.0", "commits": {}, "prs_ouvertes": 0, "ci": "verte", "topics": [],
    "stories_ouvertes": 0, "sprint_status": "present", "run": "aucun",
}


def horodatage(secondes_avant):
    """Instant `MAINTENANT - secondes_avant` (négatif : dans le futur)."""
    instant = MAINTENANT - timedelta(seconds=secondes_avant)
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes(n):
    return n * 60


def instantane(genere, projets):
    return {"schema": 1, "genere_a": genere, "projets": projets}


def entree(depot=DEPOT, vivantes=()):
    return {"faits_depot": depot, "sessions_vivantes": list(vivantes)}


def etat_session(pc="pc-b", session=SID, **champs):
    return {"session": session, "pc": pc, "debut": "2026-11-06T08:00:00Z", **champs}


def assembler(locaux, instantanes, distants=None, pc="pc-a", **kw):
    return assemblage.assembler_faits(locaux, instantanes, distants or {}, pc, MAINTENANT, **kw)


# --- faits de dépôt ---


def test_depot_de_l_instantane_le_plus_recent_qui_les_contient():
    instantanes = {
        "pc-a": instantane(horodatage(minutes(120)), {"p": entree(dict(DEPOT, tag="v1.0.0"))}),
        "pc-b": instantane(horodatage(minutes(10)), {"p": entree(dict(DEPOT, tag="v2.0.0"))}),
    }
    assert assemblage.depot_le_plus_recent(instantanes, "p")[1]["tag"] == "v2.0.0"


def test_depot_null_plus_recent_ne_masque_pas_un_plus_ancien():
    instantanes = {
        "pc-a": instantane(horodatage(minutes(120)), {"p": entree(dict(DEPOT, tag="v1.0.0"))}),
        "pc-b": instantane(horodatage(60), {"p": entree(None)}),
    }
    assert assemblage.depot_le_plus_recent(instantanes, "p")[1]["tag"] == "v1.0.0"


def test_depot_null_partout_ou_projet_absent_rend_none():
    instantanes = {"pc-a": instantane(horodatage(60), {"p": entree(None)})}
    assert assemblage.depot_le_plus_recent(instantanes, "p") == (None, None)
    assert assemblage.depot_le_plus_recent(instantanes, "autre") == (None, None)


def test_depot_egalite_de_genere_a_departagee_par_le_nom_du_pc():
    genere = horodatage(minutes(5))
    instantanes = {
        "pc-a": instantane(genere, {"p": entree(dict(DEPOT, tag="v1.0.0"))}),
        "pc-b": instantane(genere, {"p": entree(dict(DEPOT, tag="v2.0.0"))}),
    }
    assert assemblage.depot_le_plus_recent(instantanes, "p")[1]["tag"] == "v2.0.0"


def test_depot_d_un_instantane_date_dans_le_futur_ne_masque_pas_les_autres():
    instantanes = {
        "pc-a": instantane(horodatage(minutes(30)), {"p": entree(dict(DEPOT, tag="v1.0.0"))}),
        "pc-z": instantane("2099-01-01T00:00:00Z", {"p": entree(dict(DEPOT, tag="v9.0.0"))}),
    }
    assert assemblage.depot_le_plus_recent(instantanes, "p", MAINTENANT)[1]["tag"] == "v1.0.0"
    seul = {"pc-z": instantanes["pc-z"]}  # seul à les porter : repris quand même
    assert assemblage.depot_le_plus_recent(seul, "p", MAINTENANT)[1]["tag"] == "v9.0.0"


def test_origine_du_depot_notee_seulement_s_il_vient_d_un_autre_pc():
    instantanes = {
        "pc-a": instantane(horodatage(60), {"p": entree(None), "q": entree()}),
        "pc-b": instantane("2026-11-06T11:00:00Z", {"p": entree()}),
    }
    faits = assembler({"p": {}, "q": {}}, instantanes)
    assert faits["p"]["depot_de"] == {"pc": "pc-b", "genere_a": "2026-11-06T11:00:00Z"}
    assert faits["q"]["depot_de"] is None


def test_session_arretee_citee_d_abord_la_locale_la_plus_recente():
    locale = [
        {**etat_session(pc="pc-a", session=f"{c}a1b2c3d-0000-4000-8000-000000000001",
                        dernier_tour=t), "vivante": False}
        for c, t in (("1", "2026-11-06T09:00:00Z"), ("2", "2026-11-06T10:00:00Z"))
    ]
    distante = assemblage.session_distante(
        etat_session(session="0" * 8 + SID[8:], dernier_tour="2026-11-06T11:30:00Z"), "p", {},
        MAINTENANT,
    )
    a = calcul(distante, *locale)
    assert a.raison["params"]["session"] == "2a1b2c3d"
    assert "arrêtée sans fin propre (pc-a)" in a.raison["texte"]


# --- faits de poste, projet cloné ailleurs ---


def test_projet_clone_seulement_ailleurs_apparait_pas_clone_ici_avec_les_faits_distants():
    instantanes = {
        "pc-a": instantane(horodatage(60), {"local": entree()}),
        "pc-b": instantane(horodatage(120), {"local": entree(), "ailleurs": entree()}),
    }
    locaux = {"local": {"categorie": "classé", "chantier": None, "pause": None}}
    faits = assembler(locaux, instantanes, defauts={"ailleurs": {"categorie": "classé"}})
    assert faits["local"]["clone_ici"] is True
    assert faits["local"]["pcs"] == ["pc-a", "pc-b"]  # chaque PC garde ses postes
    assert faits["ailleurs"]["clone_ici"] is False
    assert faits["ailleurs"]["pcs"] == ["pc-b"]
    assert faits["ailleurs"]["depot"] == DEPOT
    cartes = etat.assembler(faits, MAINTENANT, PARIS)["cartes"]
    assert [(c["nom"], c["clone_ici"], c["pcs"], c["action"]) for c in cartes] == [
        ("ailleurs", False, ["pc-b"], "rien-a-faire"),
        ("local", True, ["pc-a", "pc-b"], "rien-a-faire"),
    ]


def test_projet_exclu_n_apparait_jamais():
    instantanes = {"pc-b": instantane(horodatage(60), {"x": entree(), "y": entree()})}
    assert list(assembler({}, instantanes, exclus={"x"})) == ["y"]


def test_defaut_a_classer_pour_un_projet_inconnu_de_la_config():
    instantanes = {"pc-b": instantane(horodatage(60), {"y": entree()})}
    faits = assembler({}, instantanes, defauts={"y": {"categorie": etat.CATEGORIE_A_CLASSER}})
    assert faits["y"]["categorie"] == etat.CATEGORIE_A_CLASSER


# --- sessions d'un autre PC (M4, L4) ---


def vivante(secondes_avant, **champs):
    instantanes = {"pc-b": instantane(horodatage(secondes_avant), {"p": entree(vivantes=[SID])})}
    return assemblage.session_distante(etat_session(**champs), "p", instantanes, MAINTENANT)


def test_session_citee_par_un_instantane_recent_est_vivante():
    s = vivante(minutes(10))
    assert (s["vivante"], s["distante"], s["nouvelles"]) == (True, True, horodatage(minutes(10)))


def test_session_non_citee_n_est_pas_vivante():
    instantanes = {"pc-b": instantane(horodatage(60), {"p": entree()})}
    s = assemblage.session_distante(etat_session(), "p", instantanes, MAINTENANT)
    assert s["vivante"] is False


def test_instantane_d_un_autre_pc_ne_cite_pas_la_session_de_pc_b():
    instantanes = {"pc-c": instantane(horodatage(60), {"p": entree(vivantes=[SID])})}
    s = assemblage.session_distante(etat_session(), "p", instantanes, MAINTENANT)
    assert (s["vivante"], s["nouvelles"]) == (False, None)


@pytest.mark.parametrize(
    ("secondes", "attendu"),
    [
        (0, True), (minutes(44), True), (minutes(45), True),  # 45 min : dans la tolérance
        (minutes(50) - 1, True), (minutes(50), False), (minutes(51), False),
        (-minutes(5), True), (-minutes(5) - 1, False), (-minutes(30), False),
    ],
)
def test_bornes_de_fraicheur_45_minutes_avec_derive_de_5(secondes, attendu):
    objet = instantane(horodatage(secondes), {"p": entree(vivantes=[SID])})
    assert assemblage.instantane_recent(objet, MAINTENANT) is attendu


def test_instantane_sans_date_lisible_n_est_pas_recent():
    assert assemblage.instantane_recent(None, MAINTENANT) is False
    assert assemblage.instantane_recent({"genere_a": "hier"}, MAINTENANT) is False


@pytest.mark.parametrize("champs", [{"fin": "2026-11-06T09:00:00Z"}, {"statut": "finie"}])
def test_session_finie_jamais_vivante_meme_citee(champs):
    assert vivante(60, **champs)["vivante"] is False


def calcul(*sessions):
    faits = {"categorie": "classé", "pause": None, "depot": DEPOT, "sessions": list(sessions)}
    return etat.calculer_action(faits, MAINTENANT, PARIS)


def test_session_distante_vivante_donne_tourne_sur_le_pc():
    a = calcul(vivante(minutes(10), dernier_tour="2026-11-06T11:00:00Z"))
    assert a.action == "tourne"
    assert a.raison["texte"] == "tourne sur pc-b, session 0a1b2c3d, état du 06/11 12:00"


def test_session_distante_non_vivante_sans_nouvelles_a_relancer_avec_heure_locale():
    a = calcul(vivante(minutes(60)))  # instantané de 11:00 UTC = 12:00 à Paris (+1)
    assert a.action == "a-relancer"
    assert a.raison["code"] == "session-arretee"
    assert a.raison["texte"] == "session 0a1b2c3d : sans nouvelles de pc-b depuis 06/11 12:00"


def test_session_distante_sans_instantane_utilise_le_dernier_etat():
    a = calcul(assemblage.session_distante(etat_session(), "p", {}, MAINTENANT))
    assert a.raison["texte"] == "session 0a1b2c3d : sans nouvelles de pc-b depuis 06/11 09:00"


@pytest.mark.parametrize("champs", [{"fin": "2026-11-06T09:00:00Z"}, {"statut": "finie"}])
def test_m4_session_avec_fin_ou_statut_finie_n_est_jamais_tourne(champs):
    a = calcul({**etat_session(**champs), "vivante": True})
    assert a.action == "rien-a-faire"  # ni Tourne ni session arrêtée : elle s'est terminée


def test_m4_attente_d_une_session_finie_ignoree():
    attente = {"quoi": "x", "depuis": "2026-11-06T09:00:00Z"}
    s = {**etat_session(statut="finie", attente=attente), "vivante": True}
    assert calcul(s).action == "rien-a-faire"


def test_assembler_faits_rattache_les_etats_distants_et_ignore_ce_pc():
    instantanes = {
        "pc-a": instantane(horodatage(60), {"p": entree()}),
        "pc-b": instantane(horodatage(60), {"p": entree(vivantes=[SID])}),
    }
    distants = {
        "pc-b": {"p": [etat_session()]},
        "pc-a": {"p": [etat_session(pc="pc-a", session="0a1b2c3d-0000-4000-8000-000000000009")]},
    }
    locaux = {"p": {"categorie": "classé", "chantier": None, "pause": None, "sessions": []}}
    sessions = assembler(locaux, instantanes, distants)["p"]["sessions"]
    assert [(s["pc"], s["vivante"]) for s in sessions] == [("pc-b", True)]  # M5 : pas pc-a


# --- fraîcheur ---


def test_fraicheur_une_ligne_par_pc_ce_pc_compris():
    instantanes = {"pc-b": instantane("2026-11-06T11:30:00Z", {})}
    lignes = assemblage.fraicheur(instantanes, "pc-a", PARIS)
    assert [(ligne["pc"], ligne["texte"]) for ligne in lignes] == [
        ("pc-a", "pc-a (ce PC) : aucun instantané"),
        ("pc-b", "pc-b : instantané du 06/11 12:30"),
    ]
    assert lignes[1]["genere_a"] == "2026-11-06T11:30:00Z"
