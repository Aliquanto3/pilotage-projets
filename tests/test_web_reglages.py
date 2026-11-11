"""Section « Réglages » du tiroir (story 5.6) sous node, faux DOM `tests/faux_dom.mjs` : patch
exact de chaque geste, libellés, file d'attente, rejets, contrôle en cours gardé par la relecture,
confirmation de l'exclusion, projet disparu, une seule lecture de la file pour deux sections.

`ctx.appeler` est un double (frontière : le serveur local). Sauté sans `node` (échec si
`PILOTAGE_EXIGER_NODE=1`).
"""

import json

import pytest

from tests.test_web_boite import etat_page, lancer, operations
from tests.test_web_tiroir import carte, sans_node

ILLISIBLE = "Date de revue illisible dans projets.yaml : corrigez-la à la main."
ABSENT = "Projet exclu ou retiré : il n'apparaît plus dans l'appli."
CONFIRMATION = ("Le projet disparaîtra de l'appli sur tous les PC après la synchro. On le "
                "réintègre en éditant projets.yaml.")
REJET = "Modification refusée : projets.yaml a changé ailleurs (champ pause de demo)."
ACCEPTE = {"statut": 202, "corps": {"ok": True, "donnees": {
    "id": "x", "verbe": "modifier_projets", "projet": "demo", "sync": "lance"}}}
CONNUS = ["alpha", "outils", "vide"]


def etat_demo(chantier="alpha", categorie="classé", pause=None, **plus):
    return etat_page(cartes=[carte("demo", chantier=chantier, categorie=categorie)],
                     details={"demo": {"sessions": [], "depot": None, "depot_de": None,
                                       "criteres": None, "pause": pause}},
                     chantiers_connus=CONNUS, **plus)


def modif(patch, projet="demo"):
    return {"id": "20261106T101500Z-0a1b2c3d", "verbe": "modifier_projets", "projet": projet,
            "patch": patch}


OUVRIR = 'T.ouvrirTiroir("demo", origine); await tour(10);\n'
VUE = """
const r = () => section("reglages");
const un = (c) => parClasse(r(), c)[0];
const vue = () => {
  const s = un("choix-chantier");
  const d = un("date-revue");
  const bouton = (c) => {
    const b = un(c);
    return b ? [b.x, !b.disabled, !b.hidden] : null;
  };
  return {
    vigueur: un("en-vigueur") ? un("en-vigueur").x : null,
    chantier: s ? [s.value, !s.disabled, s.options.map((o) => [o.value, o.x])] : null,
    date: d ? [d.value, !d.disabled, d.min, d.type] : null,
    rattacher: bouton("rattacher"), mettre: bouton("mettre-en-pause"), lever: bouton("lever-pause"),
    exclure: bouton("exclure"), confirmer: bouton("confirmer-exclusion"),
    confirmation: un("confirmation-exclusion") ? !un("confirmation-exclusion").hidden : null,
    attentes: parClasse(r(), "attente-reglage").map((p) => p.x),
    bandeaux: parClasse(r(), "bandeau-local").map((d) => [d.className, d.x]),
    textes: textes(r()),
    focus: document.activeElement ? document.activeElement.className : null,
    busy: r().getAttribute("aria-busy"),
    btn1: parClasse(dialog(), "btn1").length,
    boutons: parBalise(r(), "button").map((b) => b.className.split(" ")[0]),
  };
};
const posts = () => appels.filter((a) => a[0] === "POST").map((a) => a[2]);
"""


def lancer_r(corps, reponses=None, etat=None):
    base = {"GET /api/operations": operations(), "POST /api/projets": ACCEPTE}
    return lancer(OUVRIR + VUE + corps, {**base, **(reponses or {})}, etat or etat_demo())


@sans_node
def test_structure_en_vigueur_et_libelles():
    sortie = lancer_r("""
const labels = parBalise(r(), "label").map((l) => [l.x, l.a.for === (l.x === "Chantier"
  ? un("choix-chantier").id : un("date-revue").id)]);
sortir({ vue: vue(), labels });
""")
    v = sortie["vue"]
    assert v["vigueur"] == "En vigueur : Chantier : alpha · pas de pause"
    assert v["chantier"] == ["alpha", True, [["", "Aucun (à classer)"], ["alpha", "alpha"],
                                             ["outils", "outils"], ["vide", "vide"]]]
    assert v["rattacher"] == ["Rattacher", False, True]  # valeur identique : inactif
    assert v["date"] == ["", True, "2026-11-06", "date"]
    assert v["mettre"] == ["Mettre en pause", False, True]
    assert v["lever"][2] is False  # pas en pause : caché
    assert v["exclure"] == ["Exclure", True, True] and v["confirmation"] is False
    assert sortie["labels"] == [["Chantier", True], ["Date de revue", True]]
    assert set(v["boutons"]) == {"btn2"} and v["btn1"] == 0


@sans_node
@pytest.mark.parametrize(("etat", "geste", "patch", "libelle"), [
    (etat_demo(chantier=None, categorie="découvert, à classer"),
     'saisir(un("choix-chantier"), "outils", "change"); un("rattacher").click();',
     {"chantier": {"attendu": None, "voulu": "outils"}}, "Classer"),
    (etat_demo(),
     'saisir(un("choix-chantier"), "vide", "change"); un("rattacher").click();',
     {"chantier": {"attendu": "alpha", "voulu": "vide"}}, "Rattacher"),
    (etat_demo(),
     'saisir(un("choix-chantier"), "", "change"); un("rattacher").click();',
     {"chantier": {"attendu": "alpha", "voulu": None}}, "Rattacher"),
    (etat_demo(),
     'saisir(un("date-revue"), "2026-12-01"); un("mettre-en-pause").click();',
     {"pause": {"attendu": None, "voulu": "2026-12-01"}}, "Rattacher"),
    (etat_demo(pause={"revue": "2026-12-01"}),
     'saisir(un("date-revue"), "2026-12-15", "change"); un("mettre-en-pause").click();',
     {"pause": {"attendu": "2026-12-01", "voulu": "2026-12-15"}}, "Rattacher"),
    (etat_demo(pause={"revue": "2026-12-01"}), 'un("lever-pause").click();',
     {"pause": {"attendu": "2026-12-01", "voulu": None}}, "Rattacher"),
    (etat_demo(), 'un("exclure").click(); un("confirmer-exclusion").click();',
     {"exclu": {"attendu": False, "voulu": True}}, "Rattacher"),
])
def test_patch_exact_de_chaque_geste(etat, geste, patch, libelle):
    sortie = lancer_r(f"const avant = vue();\n{geste}\nawait tour(10);\n"
                      "sortir({ avant, posts: posts(), apres: vue() });", etat=etat)
    assert sortie["avant"]["rattacher"][0] == libelle
    assert sortie["posts"] == [{"json": {"projet": "demo", "patch": patch}}]


@sans_node
def test_en_pause_libelles_et_valeur_en_vigueur():
    sortie = lancer_r("sortir(vue());",
                      etat=etat_demo(chantier=None, pause={"revue": "2026-12-01"}))
    assert sortie["vigueur"] == "En vigueur : Aucun chantier (à classer) · en pause jusqu'au 01/12"
    assert sortie["date"][:2] == ["2026-12-01", True]
    assert sortie["mettre"] == ["Changer la date de revue", False, True]  # même date : inactif
    assert sortie["lever"] == ["Lever la pause", True, True]


@sans_node
@pytest.mark.parametrize("revue", ["01/12/2026", "2026-02-30", None])
def test_revue_illisible_controles_de_pause_inactifs(revue):
    sortie = lancer_r('saisir(un("date-revue"), "2026-12-20"); sortir(vue());',
                      etat=etat_demo(pause={"revue": revue}))
    assert ILLISIBLE in sortie["textes"]
    assert sortie["date"][1] is False and sortie["mettre"][1] is False
    assert sortie["lever"][1:] == [False, True]
    assert sortie["chantier"][1] is True  # le chantier reste réglable
    assert sortie["vigueur"] == "En vigueur : Chantier : alpha · en pause"


@sans_node
@pytest.mark.parametrize(("patch", "texte", "inactifs"), [
    ({"chantier": {"attendu": "alpha", "voulu": "outils"}}, "rattachement à outils",
     ["chantier", "rattacher"]),
    ({"chantier": {"attendu": "alpha", "voulu": None}}, "retrait du chantier",
     ["chantier", "rattacher"]),
    ({"pause": {"attendu": None, "voulu": "2026-12-24"}}, "pause jusqu'au 24/12",
     ["date", "mettre"]),
    ({"pause": {"attendu": "2026-12-01", "voulu": None}}, "levée de la pause", ["date", "mettre"]),
    ({"exclu": {"attendu": False, "voulu": True}}, "exclusion", ["exclure"]),
])
def test_en_attente_de_synchro_puis_disparait(patch, texte, inactifs):
    sortie = lancer_r("""
saisir(un("date-revue"), "2026-12-30");
const pendant = vue();
T.majTiroir(ETAT);
await tour(10);
sortir({ pendant, apres: vue() });
""".replace("ETAT", json.dumps(etat_demo())), {"GET /api/operations": [
        operations(ops=[modif(patch), modif({"exclu": {"attendu": False, "voulu": True}},
                                            projet="autre")]),
        operations()]})
    p = sortie["pendant"]
    assert p["attentes"] == [f"En attente de synchro : {texte}"]
    actifs = {"chantier": p["chantier"][1], "rattacher": p["rattacher"][1], "date": p["date"][1],
              "mettre": p["mettre"][1], "exclure": p["exclure"][1]}
    for nom in ("chantier", "date", "exclure"):
        assert actifs[nom] is (nom not in inactifs), nom
    for nom in ("rattacher", "mettre"):
        if nom in inactifs:
            assert actifs[nom] is False, nom
    assert p["vigueur"] == "En vigueur : Chantier : alpha · pas de pause"  # jamais `voulu`
    assert sortie["apres"]["attentes"] == []


@sans_node
def test_rejet_bandeau_du_serveur_et_valeur_en_vigueur_reprise():
    alertes = [
        {"source": "operation", "code": "valeur-differente",
         "params": {"id": "x", "projet": "demo", "champ": "pause"}, "texte": REJET},
        {"source": "operation", "code": "valeur-differente",
         "params": {"id": "y", "projet": "autre", "champ": "pause"}, "texte": "pas pour demo"},
        {"source": "scan", "code": "x", "params": {"projet": "demo"}, "texte": "autre source"},
    ]
    sortie = lancer_r("""
saisir(un("choix-chantier"), "outils", "change");
un("rattacher").click();
await tour(10);
const apres202 = vue();
T.majTiroir(ETAT);
await tour(10);
sortir({ apres202, rejete: vue() });
""".replace("ETAT", json.dumps(etat_demo(alertes=alertes))))
    assert sortie["apres202"]["chantier"][0] == "alpha"  # jamais la valeur voulue avant application
    rejete = sortie["rejete"]
    assert rejete["bandeaux"] == [["bandeau-local alerte", REJET]]
    assert rejete["textes"][0] == REJET  # en tête de section
    assert rejete["chantier"][0] == "alpha" and rejete["attentes"] == []


@sans_node
def test_maj_n_ecrase_pas_un_controle_en_cours_ni_le_focus():
    autre = etat_demo(chantier="vide", pause={"revue": "2026-11-30"})
    autre["chantiers_connus"] = ["alpha", "beta", "outils", "vide"]
    sortie = lancer_r("""
saisir(un("choix-chantier"), "outils", "change");
saisir(un("date-revue"), "2026-12-20");
un("date-revue").focus();
T.majTiroir(ETAT);
await tour(10);
sortir(vue());
""".replace("ETAT", json.dumps(autre)))
    assert sortie["chantier"][0] == "outils"
    assert len(sortie["chantier"][2]) == 4  # options gardées : contrôle en cours
    assert sortie["date"][0] == "2026-12-20" and sortie["focus"] == "date-revue"
    assert sortie["vigueur"] == "En vigueur : Chantier : vide · en pause jusqu'au 30/11"
    assert sortie["mettre"][0] == "Changer la date de revue"


@sans_node
def test_controle_au_repos_reprend_la_valeur_en_vigueur():
    autre = etat_demo(chantier="outils", pause={"revue": "2026-11-30"})
    sortie = lancer_r("T.majTiroir(ETAT); await tour(10); sortir(vue());"
                      .replace("ETAT", json.dumps(autre)))
    assert sortie["chantier"][0] == "outils" and sortie["date"][0] == "2026-11-30"


@sans_node
def test_confirmation_focalisee_nommee_annuler_et_echap():
    sortie = lancer_r("""
un("exclure").click();
const ouverte = vue();
un("annuler-exclusion").click();
const annulee = vue();
un("exclure").click();
const e = new F.Evenement("keydown", { key: "Escape" });
un("confirmation-exclusion").dispatchEvent(e);
document.dispatchEvent(e);  // remontée jusqu'au document (le faux DOM ne propage pas)
await tour(10);
sortir({ ouverte, annulee, echap: vue(), prevenu: e.defaultPrevented, ouvert: dialog().open,
  posts: posts() });
""")
    o = sortie["ouverte"]
    assert o["confirmation"] is True and o["exclure"][2] is False
    assert o["confirmer"][0] == "Confirmer l'exclusion de demo"
    assert o["focus"] == "btn2 confirmer-exclusion"
    assert CONFIRMATION in o["textes"]
    for etape in ("annulee", "echap"):
        assert sortie[etape]["confirmation"] is False and sortie[etape]["exclure"][2] is True
        assert sortie[etape]["focus"] == "btn2 exclure"
    assert sortie["prevenu"] is True and sortie["ouvert"] is True
    assert sortie["posts"] == []


@sans_node
def test_projet_disparu_controles_retires():
    sortie = lancer_r("""
const avant = vue();
T.majTiroir(ETAT);
await tour(10);
sortir({ avant, apres: vue() });
""".replace("ETAT", json.dumps(etat_page(cartes=[]))))
    assert sortie["avant"]["exclure"] is not None
    apres = sortie["apres"]
    assert apres["textes"] == [ABSENT] and apres["boutons"] == [] and apres["chantier"] is None


@sans_node
def test_projet_absent_a_l_ouverture():
    sortie = lancer_r("sortir({ vue: vue(), gets: ops() });", etat=etat_page(cartes=[]))
    assert sortie["vue"]["textes"] == [ABSENT]


@sans_node
def test_un_seul_get_par_relecture_pour_les_deux_sections():
    sortie = lancer_r("""
const ouverture = ops();
T.majTiroir(ETAT);
await tour(10);
sortir({ ouverture, relecture: ops() });
""".replace("ETAT", json.dumps(etat_demo())))
    assert sortie == {"ouverture": 1, "relecture": 2}


@sans_node
def test_un_seul_envoi_a_la_fois():
    sortie = lancer_r("""
saisir(un("choix-chantier"), "outils", "change");
saisir(un("date-revue"), "2026-12-01");
un("rattacher").click();
const pendant = vue();
un("mettre-en-pause").click();
un("exclure").click();
differes.forEach((r) => r({ statut: 202, corps: null }));
await tour(10);
sortir({ pendant, posts: posts(), apres: vue() });
""", {"POST /api/projets": "attendre"})
    p = sortie["pendant"]
    assert p["busy"] == "true"
    assert [p[c][1] for c in ("rattacher", "mettre", "exclure")] == [False, False, False]
    assert len(sortie["posts"]) == 1
    assert sortie["apres"]["busy"] is None
    assert sortie["apres"]["date"][0] == "2026-12-01"  # pause encore en cours de saisie


@sans_node
@pytest.mark.parametrize(("reponse", "attendu"), [
    ({"statut": 400, "corps": {"ok": False, "erreur": "Chantier inconnu : zz."}},
     "Chantier inconnu : zz."),
    ({"statut": 0, "corps": None}, "Serveur local injoignable. Relancez l'appli par lancer.py."),
])
def test_refus_affiche_tel_quel_saisie_gardee(reponse, attendu):
    sortie = lancer_r("""
saisir(un("choix-chantier"), "outils", "change");
un("rattacher").click();
await tour(10);
sortir({ vue: vue(), journal: F.journal });
""", {"POST /api/projets": reponse})
    v = sortie["vue"]
    assert v["bandeaux"] == [["bandeau-local erreur", attendu]]
    assert v["chantier"][0] == "outils" and v["rattacher"][1] is True
    assert f"alerte:{attendu}" in sortie["journal"]
