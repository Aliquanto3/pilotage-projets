"""Tests de `noyau.etat` pour les champs d'affichage (story 4.8) : famille, attente
vieillissante, comptes de l'accueil par projet, `pc` et `dernier_tour` des cartes À relancer.

Horloge injectée (`MAINTENANT`) : aucun test ne dépend de la date du jour.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pilotage.noyau import etat
from pilotage.noyau.etat import calculer_action

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


def faits(*sessions, **champs):
    base = {"categorie": "classé", "pause": None, "depot": DEPOT, "attente": None,
            "sessions": list(sessions)}
    return {**base, **champs}


def calcul(f, maintenant=MAINTENANT):
    return calculer_action(f, maintenant, PARIS)


# Un cas par famille de la table de `etats-action.md` § Champs d'affichage (dix au total).
CAS_FAMILLES = {
    "arretee": faits(session(vivante=False)),
    "sans-nouvelles": faits(session(vivante=False, distante=True,
                                    nouvelles="2026-11-06T09:00:00Z")),
    "run-bloque": faits(depot={**DEPOT, "run": "bloque"}),
    "sans-session": faits(depot={**DEPOT, "stories_ouvertes": 2}),
    "pause-a-revoir": faits(pause={"revue": "2026-11-01"}),
    "non-relu": faits(depot=None),
    "a-stabiliser": faits(depot={**DEPOT, "tag": None}),
    "stable": faits(),
    "pause": faits(pause={"revue": "2026-12-01"}),
    "a-classer": faits(categorie=etat.CATEGORIE_A_CLASSER),
}


def test_la_table_couvre_les_dix_familles_dans_l_ordre_fixe():
    assert list(CAS_FAMILLES) == list(etat.FAMILLES)
    assert len(etat.FAMILLES) == 10
    assert etat.FAMILLES == etat.FAMILLES_A_RELANCER + etat.FAMILLES_RIEN


@pytest.mark.parametrize("famille", list(CAS_FAMILLES))
def test_famille_un_cas_par_famille(famille):
    a = calcul(CAS_FAMILLES[famille])
    attendue = etat.A_RELANCER if famille in etat.FAMILLES_A_RELANCER else etat.RIEN
    assert (a.action, a.famille, a.vieillissante) == (attendue, famille, False)


def test_session_arretee_meme_code_deux_familles_selon_la_session_retenue():
    ici = calcul(CAS_FAMILLES["arretee"])
    ailleurs = calcul(CAS_FAMILLES["sans-nouvelles"])
    assert ici.raison["code"] == ailleurs.raison["code"] == "session-arretee"
    assert (ici.famille, ailleurs.famille) == ("arretee", "sans-nouvelles")
    # session de ce PC et session distante arrêtées : celle de ce PC est retenue
    mixte = calcul(faits(session(vivante=False),
                         session(session=SID2, pc="pc-b", vivante=False, distante=True,
                                 debut="2026-11-06T11:00:00Z")))
    assert (mixte.raison["params"]["pc"], mixte.famille) == ("pc-a", "arretee")


def test_run_en_cours_est_aussi_sans_session():
    a = calcul(faits(depot={**DEPOT, "run": "en_cours"}))
    assert (a.raison["code"], a.famille) == ("run-en-cours", "sans-session")


def test_run_bloque_garde_sa_famille_meme_avec_une_session_vivante():
    a = calcul(faits(session(), depot={**DEPOT, "run": "bloque"}))
    assert (a.action, a.famille) == (etat.A_RELANCER, "run-bloque")


def test_famille_none_pour_attend_et_tourne():
    attend = calcul(faits(attente={"origine": "marqueur", "type": "test", "quoi": "q"}))
    tourne = calcul(faits(session()))
    assert (attend.action, attend.famille) == (etat.ATTEND, None)
    assert (tourne.action, tourne.famille) == (etat.TOURNE, None)


def _attente_depuis(depuis):
    return faits(session(attente={"quoi": "valider X", "depuis": depuis}))


@pytest.mark.parametrize(("depuis", "attendu"), [
    ("2026-11-06T04:01:00Z", False),  # 7 h 59
    ("2026-11-06T04:00:00Z", False),  # 8 h 00 : strictement plus de 8 h exigé
    ("2026-11-06T03:59:00Z", True),   # 8 h 01
])
def test_vieillissante_au_seuil_de_8_h(depuis, attendu):
    a = calcul(_attente_depuis(depuis))
    assert (a.action, a.vieillissante) == (etat.ATTEND, attendu)


@pytest.mark.parametrize(("depuis", "attendu"), [
    ("2026-11-06T04:00:00+00:00", False),  # 8 h 00, décalage explicite
    ("2026-11-06T03:59:00+00:00", True),   # 8 h 01
    ("2026-11-06T05:01:00+01:00", False),  # 7 h 59 dans un autre fuseau
    ("2026-11-06T04:59:00+01:00", True),   # 8 h 01 dans un autre fuseau
    ("2026-11-06T03:00:00", False),        # sans fuseau : illisible
])
def test_vieillissante_lit_les_decalages_et_refuse_l_heure_sans_fuseau(depuis, attendu):
    assert calcul(_attente_depuis(depuis)).vieillissante is attendu


def test_vieillissante_suit_l_horloge_injectee():
    f = _attente_depuis("2026-11-06T04:00:00Z")
    assert calcul(f, MAINTENANT).vieillissante is False
    assert calcul(f, MAINTENANT + timedelta(seconds=1)).vieillissante is True


@pytest.mark.parametrize("attente", [
    {"origine": "marqueur", "type": "choix", "quoi": "q"},  # sans `depuis`
    {"origine": "marqueur", "type": "choix", "quoi": "q", "depuis": None},
    {"origine": "marqueur", "type": "choix", "quoi": "q", "depuis": "hier"},
    {"origine": "marqueur", "type": "choix", "quoi": "q", "depuis": "2026-11-01 03:00:00"},
])
def test_attente_sans_depuis_ou_illisible_jamais_vieillissante(attente):
    a = calcul(faits(attente=attente))
    assert (a.action, a.vieillissante) == (etat.ATTEND, False)


def test_depuis_illisible_d_une_session_jamais_vieillissante():
    a = calcul(_attente_depuis("2026-11-01T03:00"))
    assert (a.action, a.vieillissante) == (etat.ATTEND, False)


def test_vieillissante_jamais_vraie_hors_d_attend():
    vieux = "2026-11-01T00:00:00Z"
    morte = calcul(faits(session(vivante=False, attente={"quoi": "q", "depuis": vieux})))
    repondue = calcul(faits(session(dernier_prompt="2026-11-06T11:00:00Z",
                                    attente={"quoi": "q", "depuis": vieux})))
    assert (morte.action, morte.vieillissante) == (etat.A_RELANCER, False)
    assert (repondue.action, repondue.vieillissante) == (etat.TOURNE, False)
    for f in CAS_FAMILLES.values():
        assert calcul(f).vieillissante is False


def test_carte_porte_famille_et_vieillissante():
    r = etat.assembler({"p": _attente_depuis("2026-11-06T03:00:00Z"), "q": faits()},
                       MAINTENANT, PARIS)
    (attend,) = r["colonnes"]["attend-utilisateur"]
    (stable,) = r["colonnes"]["rien-a-faire"]
    assert (attend["famille"], attend["vieillissante"]) == (None, True)
    assert (stable["famille"], stable["vieillissante"]) == ("stable", False)


def _tous():
    projets = {f"p-{nom}": f for nom, f in CAS_FAMILLES.items()}
    projets["p-stable-2"] = faits(chantier="Zeta")
    projets["p-arretee-2"] = faits(session(vivante=False), chantier="Zeta")
    projets["t-1"] = faits(session(pc="pc-b"))
    projets["t-2"] = faits(session(pc="pc-a"))
    projets["t-3"] = faits(session(pc="pc-b"), chantier="Zeta")
    projets["a-1"] = faits(attente={"origine": "marqueur", "type": "test", "quoi": "q"})
    projets["a-2"] = faits(attente={"origine": "heuristique", "quoi": ""})
    return etat.assembler(projets, MAINTENANT, PARIS)


def test_comptes_de_l_accueil_par_projet():
    r = _tous()
    comptes = r["comptes"]
    assert comptes["actions"] == {"attend-utilisateur": 2, "a-relancer": 8, "tourne": 3,
                                  "rien-a-faire": 4}
    assert comptes["types"] == {"a-qualifier": 1, "test": 1}
    assert comptes["familles"] == {
        "arretee": 2, "sans-nouvelles": 1, "run-bloque": 1, "sans-session": 1,
        "pause-a-revoir": 1, "non-relu": 1, "a-stabiliser": 1,
        "stable": 2, "pause": 1, "a-classer": 1,
    }
    assert list(comptes["familles"]) == list(etat.FAMILLES)
    assert list(comptes["pcs_tourne"].items()) == [("pc-a", 1), ("pc-b", 2)]
    assert (comptes["suivis"], comptes["stables"]) == (17, 2)
    assert comptes["suivis"] == sum(comptes["actions"].values()) == len(r["cartes"])
    (zeta,) = r["chantiers"]
    assert (zeta["action"], zeta["famille"]) == (etat.A_RELANCER, "arretee")


def test_somme_des_familles_egale_le_compte_de_chaque_colonne():
    comptes = _tous()["comptes"]
    familles = comptes["familles"]
    assert sum(familles.get(f, 0) for f in etat.FAMILLES_A_RELANCER) == (
        comptes["actions"]["a-relancer"]
    )
    assert sum(familles.get(f, 0) for f in etat.FAMILLES_RIEN) == comptes["actions"]["rien-a-faire"]


def test_familles_a_zero_omises_dans_l_ordre_fixe():
    r = etat.assembler({
        "z": faits(categorie=etat.CATEGORIE_A_CLASSER),
        "y": faits(depot=None),
        "x": faits(),
    }, MAINTENANT, PARIS)
    assert list(r["comptes"]["familles"].items()) == [
        ("non-relu", 1), ("stable", 1), ("a-classer", 1),
    ]


def test_carte_a_relancer_porte_pc_et_dernier_tour_de_sa_cle_de_tri():
    r = etat.assembler({
        "r-recent": faits(
            session(vivante=False, dernier_tour="2026-11-05T10:00:00Z"),
            session(session=SID2, pc="pc-b", vivante=False, distante=True,
                    dernier_tour="2026-11-06T11:00:00Z"),
        ),
        "r-vieux": faits(session(pc="pc-c", vivante=False, debut="2026-11-04T08:00:00Z")),
        "r-sans": faits(depot=None),
        "attend": faits(attente={"origine": "marqueur", "type": "test", "quoi": "q"}),
        "stable": faits(),
    }, MAINTENANT, PARIS)
    colonne = r["colonnes"]["a-relancer"]
    rendu = [(c["nom"], c["pc"], c["dernier_tour"]) for c in colonne]
    assert rendu == [
        ("r-vieux", "pc-c", "2026-11-04T08:00:00Z"),
        ("r-recent", "pc-b", "2026-11-06T11:00:00Z"),
        ("r-sans", None, None),
    ]
    tours = [c["dernier_tour"] for c in colonne if c["dernier_tour"]]
    assert tours == sorted(tours)  # même ordre que la clé de tri de la colonne
    for action in (etat.ATTEND, etat.RIEN):
        (carte,) = r["colonnes"][action]
        assert carte["dernier_tour"] is None
