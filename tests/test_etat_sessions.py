"""Tests de `noyau.etat` pour les sessions (story 2.6) : attente M1, Tourne, arrêtée M16."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pilotage.noyau.etat import A_QUALIFIER, calculer_action

PARIS = timezone(timedelta(hours=1))
MAINTENANT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
SID = "0a1b2c3d-0000-4000-8000-000000000001"
SID2 = "0a1b2c3d-0000-4000-8000-000000000002"
DEPOT = {
    "tag": "v1.0.0", "commits": {}, "prs_ouvertes": 0, "ci": "verte", "topics": [],
    "stories_ouvertes": 0, "sprint_status": "present", "run": "aucun",
}


def session(**champs):
    base = {"session": SID, "pc": "pc-a", "debut": "2026-11-06T08:00:00Z", "vivante": True}
    return {**base, **champs}


def attente(**champs):
    return {"quoi": "valider X", "depuis": "2026-11-06T09:00:00Z", **champs}


def calcul(*sessions, depot=DEPOT, **champs):
    faits = {"categorie": "classé", "pause": None, "depot": depot, "sessions": list(sessions)}
    return calculer_action({**faits, **champs}, MAINTENANT, PARIS)


def test_attente_sans_prompt_posterieur_donne_attend_avec_quoi_et_type():
    a = calcul(session(attente=attente(type="choix")))
    assert (a.action, a.quoi, a.type) == ("attend-utilisateur", "valider X", "choix")
    assert a.raison["texte"] == "vous attend : valider X"


@pytest.mark.parametrize(
    ("prompt", "compte"),
    [
        (None, True),
        ("2026-11-06T09:00:00Z", True),  # même seconde : l'attente reste (règle des hooks, 2.3)
        ("2026-11-06T08:59:59Z", True),
        ("2026-11-06T09:00:01Z", False),  # prompt passé (verrou tenu 30 ms pendant le prompt)
    ],
)
def test_m1_attente_comptee_seulement_sans_prompt_posterieur(prompt, compte):
    champs = {} if prompt is None else {"dernier_prompt": prompt}
    a = calcul(session(attente=attente(), **champs))
    assert (a.action == "attend-utilisateur") is compte
    if not compte:
        assert a.action == "tourne"


@pytest.mark.parametrize("type_", ["choix", "test", "donnees", "acces"])
def test_type_marqueur_passe_tel_quel(type_):
    assert calcul(session(attente=attente(type=type_))).type == type_


@pytest.mark.parametrize(
    "type_", [None, "inconnu", "decision", "ressource", "recette", "validation", "info"],
)
def test_a_qualifier_type_absent_inconnu_ou_ancien(type_):
    champs = {} if type_ is None else {"type": type_}
    assert calcul(session(attente=attente(**champs))).type == A_QUALIFIER


@pytest.mark.parametrize("source", ["askuserquestion", "permission", "question"])
@pytest.mark.parametrize("type_", ["choix", "test", "donnees", "acces"])
def test_a_qualifier_pour_chaque_origine_heuristique(source, type_):
    a = calcul(session(attente=attente(type=type_, source=source)))
    assert (a.action, a.type) == ("attend-utilisateur", A_QUALIFIER)


def test_source_marqueur_explicite_garde_le_type():
    assert calcul(session(attente=attente(type="test", source="marqueur"))).type == "test"


def test_m16_session_morte_en_attente_est_a_relancer_pas_attend():
    a = calcul(session(vivante=False, attente=attente(type="choix")))
    assert a.action == "a-relancer"
    assert a.raison["code"] == "session-arretee"
    assert "arrêtée sans fin propre" in a.raison["texte"]
    assert (a.quoi, a.type) == ("", None)
    assert a.raison["params"] == {"pc": "pc-a", "session": SID[:8]}


def test_session_morte_sans_attente_est_a_relancer():
    assert calcul(session(vivante=False)).raison["code"] == "session-arretee"


def test_session_morte_avec_fin_propre_est_ignoree():
    a = calcul(session(vivante=False, fin="2026-11-06T10:00:00Z"))
    assert a.raison["code"] == "stable"


def test_attente_d_une_session_finie_est_ignoree():
    a = calcul(session(fin="2026-11-06T10:00:00Z", attente=attente()))
    assert a.action == "rien-a-faire"


def test_session_morte_et_autre_vivante_donne_tourne():
    a = calcul(session(vivante=False), session(session=SID2))
    assert a.action == "tourne"


def test_attente_vivante_l_emporte_sur_session_morte():
    a = calcul(session(vivante=False), session(session=SID2, attente=attente()))
    assert a.action == "attend-utilisateur"


def test_tourne_pc_session_et_heure_du_dernier_etat():
    a = calcul(session(dernier_tour="2026-11-06T10:30:00Z"))
    assert a.action == "tourne"
    assert a.raison["code"] == "tourne"
    assert a.raison["params"] == {"pc": "pc-a", "session": SID[:8], "dernier_etat": "06/11 11:30"}
    assert a.raison["texte"] == f"tourne sur pc-a, session {SID[:8]}, état du 06/11 11:30"
    assert (a.quoi, a.type) == ("", None)


def test_dernier_etat_est_le_plus_recent_des_trois_champs():
    a = calcul(session(dernier_tour="2026-11-06T10:00:00Z", dernier_prompt="2026-11-06T10:05:00Z"))
    assert a.raison["params"]["dernier_etat"] == "06/11 11:05"


def test_tourne_sans_date_lisible_omet_l_heure():
    a = calcul(session(debut=None))
    assert a.raison["texte"] == f"tourne sur pc-a, session {SID[:8]}"


def test_tourne_l_emporte_sur_story_ouverte_et_pause_mais_pas_sur_run_bloque():
    assert calcul(session(), depot={**DEPOT, "stories_ouvertes": 2}).action == "tourne"
    assert calcul(session(), pause={"revue": "2027-01-01"}).action == "tourne"
    a = calcul(session(), depot={**DEPOT, "run": "bloque"})
    assert (a.action, a.raison["code"]) == ("a-relancer", "run-bloque")


def test_attente_la_plus_prioritaire_puis_la_plus_recente():
    a = calcul(
        session(attente=attente(quoi="secours", source="question", depuis="2026-11-06T10:00:00Z")),
        session(session=SID2, attente=attente(quoi="marqueur ancien")),
    )
    assert a.quoi == "marqueur ancien"
    b = calcul(
        session(attente=attente(quoi="ancien", type="test")),
        session(session=SID2, attente=attente(quoi="récent", depuis="2026-11-06T09:30:00Z")),
    )
    assert b.quoi == "récent"


def test_sans_sessions_le_comportement_de_1_5_est_inchange():
    assert calcul().raison["code"] == "stable"
    assert calculer_action({"depot": DEPOT, "sessions": None}, MAINTENANT, PARIS).action == (
        "rien-a-faire"
    )


def test_attente_heritee_derive_l_origine_de_source():
    legacy = {"type": "choix", "quoi": "q", "source": "permission"}
    assert calcul(attente=legacy).type == A_QUALIFIER
    assert calcul(attente={"type": "choix", "quoi": "q"}).type == "choix"


def test_source_inconnue_est_a_qualifier_et_passe_apres_le_marqueur():
    assert calcul(session(attente=attente(type="choix", source="autre"))).type == A_QUALIFIER
    a = calcul(
        session(attente=attente(quoi="inconnue", source="autre", depuis="2026-11-06T10:00:00Z")),
        session(session=SID2, attente=attente(quoi="marqueur")),
    )
    assert a.quoi == "marqueur"


def test_tourne_montre_la_session_vivante_la_plus_recente():
    a = calcul(
        session(dernier_tour="2026-11-06T09:00:00Z"),
        session(
            session="ffffffff-0000-4000-8000-000000000003", dernier_tour="2026-11-06T11:00:00Z"
        ),
    )
    assert a.raison["params"]["session"] == "ffffffff"


# --- Assemblage (story 4.5) : PC et `depuis` de l'attente, tri des colonnes (UX-DR6) ---------

def _faits(*sessions, **champs):
    return {"categorie": "classé", "pause": None, "depot": DEPOT, "attente": None,
            "sessions": list(sessions), **champs}


def _colonnes(projets):
    from pilotage.noyau import etat
    r = etat.assembler(projets, MAINTENANT, PARIS)
    return r, {a: [c["nom"] for c in cs] for a, cs in r["colonnes"].items()}


def test_carte_attend_porte_pc_et_depuis_de_l_attente_retenue():
    r, _ = _colonnes({
        "p": _faits(
            session(session=SID, pc="pc-a", attente=attente(depuis="2026-11-06T08:30:00Z",
                                                          source="heuristique")),
            session(session=SID2, pc="pc-b", attente=attente(depuis="2026-11-06T07:00:00Z")),
        ),
        "q": _faits(),
    })
    (carte,) = r["colonnes"]["attend-utilisateur"]
    # le marqueur (pc-b) l'emporte sur l'heuristique plus récente : même choix que le verdict
    assert (carte["pc"], carte["depuis"]) == ("pc-b", "2026-11-06T07:00:00Z")
    (stable,) = r["colonnes"]["rien-a-faire"]
    assert (stable["pc"], stable["depuis"]) == (None, None)


def test_tri_des_colonnes_selon_experience():
    tard = {"revue": "2026-12-20"}
    tot = {"revue": "2026-11-20"}
    _, noms = _colonnes({
        # Attend : plus ancienne attente d'abord, sans date après
        "a1": _faits(session(attente=attente(depuis="2026-11-06T10:00:00Z"))),
        "a2": _faits(session(attente=attente(depuis="2026-11-06T07:00:00Z"))),
        "a0": _faits(attente={"origine": "marqueur", "type": "test", "quoi": "q"}),
        # Relancer : plus ancien dernier tour d'abord, sans session après
        "r1": _faits(session(vivante=False, dernier_tour="2026-11-06T11:00:00Z")),
        "r2": _faits(session(vivante=False, dernier_tour="2026-11-05T11:00:00Z")),
        "r0": _faits(depot={**DEPOT, "tag": None}),
        # Tourne : dernier état le plus récent d'abord
        "t1": _faits(session(dernier_tour="2026-11-06T09:00:00Z")),
        "t2": _faits(session(dernier_tour="2026-11-06T11:00:00Z")),
        # Rien à faire : pauses par date de revue, puis les autres par nom
        "z-stable": _faits(),
        "p-tard": _faits(pause=tard),
        "p-tot": _faits(pause=tot),
        "b-stable": _faits(),
    })
    assert noms == {
        "attend-utilisateur": ["a2", "a1", "a0"],
        "a-relancer": ["r2", "r1", "r0"],
        "tourne": ["t2", "t1"],
        "rien-a-faire": ["p-tot", "p-tard", "b-stable", "z-stable"],
    }


def test_chantier_prend_son_depot_le_plus_urgent_hors_des_colonnes():
    r, noms = _colonnes({
        "m1": _faits(session(attente=attente(depuis="2026-11-06T06:00:00Z")), chantier="Zeta"),
        "m2": _faits(chantier="Zeta"),
        "solo": _faits(session(attente=attente(depuis="2026-11-06T10:00:00Z"))),
    })
    # chaque dépôt garde sa carte (4.8) ; le chantier prend l'action de son dépôt le plus urgent
    assert noms["attend-utilisateur"] == ["m1", "solo"]
    assert noms["rien-a-faire"] == ["m2"]
    (zeta,) = r["chantiers"]
    assert (zeta["nom"], zeta["action"], zeta["depuis"]) == (
        "Zeta", "attend-utilisateur", "2026-11-06T06:00:00Z",
    )
    assert [p["nom"] for p in zeta["projets"]] == ["m1", "m2"]


def test_pc_et_depuis_ignorent_session_morte_et_attente_repondue():
    r, _ = _colonnes({
        "p": _faits(
            # marqueur plus ancien mais session morte : ignoré
            session(session=SID, pc="pc-mort", vivante=False,
                    attente=attente(quoi="vieux", depuis="2026-11-06T05:00:00Z")),
            # marqueur auquel l'utilisateur a répondu : ignoré
            session(session=SID2, pc="pc-repondu", dernier_prompt="2026-11-06T10:00:00Z",
                    attente=attente(quoi="repondu", depuis="2026-11-06T09:00:00Z")),
            session(session="0a1b2c3d-0000-4000-8000-000000000003", pc="pc-vif",
                    attente=attente(quoi="neuf", depuis="2026-11-06T08:30:00Z",
                                    source="question")),
        ),
    })
    (carte,) = r["colonnes"]["attend-utilisateur"]
    assert (carte["quoi"], carte["pc"], carte["depuis"]) == ("neuf", "pc-vif",
                                                             "2026-11-06T08:30:00Z")
