"""Panneau de reprise du tiroir (story 5.5) sous node, faux DOM `tests/faux_dom.mjs` : cinq cas,
liste des sessions, commande du serveur rendue telle quelle, brief, erreurs, réponses tardives.

`ctx.appeler` est un double passé à `initialiserTiroir` (frontière : le serveur local). Sauté sans
`node` (échec si `PILOTAGE_EXIGER_NODE=1`).
"""

import json

import pytest

from tests.test_web_tiroir import HOSTILES, executer, sans_node, url

INJOIGNABLE = "Serveur local injoignable. Relancez l'appli par lancer.py."
PAS_CLONE = "Pas cloné sur ce PC. Clonez le dépôt sous Documents\\GitHub, puis relancez un scan."
AUCUNE = "Aucune session à reprendre sur ce projet."
DOSSIER_ABSENT = ("Dossier de la session introuvable sur ce PC. Choisissez une autre session ou "
                  "relancez un scan.")
BRIEF_ABSENT = ("Brief introuvable (purgé ou effacé). Fermez puis rouvrez le tiroir pour en "
                "préparer un autre.")
TRONQUE = "… (brief tronqué à l'affichage)"
# Commande factice : le panneau ne la lit pas, il la rend octet pour octet.
COMMANDE = "faux-outil --reprendre 'x'; echo $(calc) `whoami` & | > <b>"
BRIEF_ID = "20261106T101501Z-0a1b2c3d"


def session(id_, pc, ce_pc=False, debut="2026-11-06T09:05:00Z", dernier="2026-11-06T11:30:00Z"):
    return {"session": id_, "pc": pc, "ce_pc": ce_pc, "debut": debut, "dernier_tour": dernier,
            "branche": "main", "statut": "attente", "fin": None}


def liste(sessions, proposee=None, clone_ici=True):
    return {"statut": 200, "corps": {"ok": True, "donnees": {
        "projet": "demo", "pc": "pc-a", "clone_ici": clone_ici, "sessions": sessions,
        "proposee": proposee}}}


def reprise(commande=COMMANDE, mode="resume", raison=None, dossier="D:\\depots\\demo",
            chemin_brief=None, brief=None):
    return {"statut": 200, "corps": {"ok": True, "donnees": {
        "commande": commande, "mode": mode, "brief": brief, "raison": raison,
        "dossier": dossier, "chemin_brief": chemin_brief}}}


def en_brief(commande=COMMANDE):
    return reprise(commande=commande, mode="brief", brief=BRIEF_ID,
                   chemin_brief=f"C:\\attente\\briefs\\{BRIEF_ID}.md")


SESSIONS = [session("s-ici", "pc-a", ce_pc=True), session("s-autre", "pc-b"),
            session("s-vieille", "pc-c", debut="2026-11-05T08:00:00Z",
                    dernier="2026-11-05T09:00:00Z")]

# Page : tiroir + panneau, `appeler` répond par `REPONSES` (clé : méthode et début du chemin ;
# valeur : réponse, liste consommée dans l'ordre, ou "attendre" pour une promesse pilotée).
PAGE = """
// Horloge figée (frontière) : `new Date()` sans argument rend MAINTENANT.
const VraieDate = Date;
globalThis.Date = class extends VraieDate {
  constructor(...a) { super(...(a.length ? a : ["2026-11-06T12:00:00Z"])); }
};
const T = await import(%s);
await import(%s);
const racine = new N("div"); racine.id = "racine"; body.append(racine);
const main = new N("main"); racine.append(main);
const origine = new N("button"); main.append(origine);
const appels = [];
const differes = [];
let REPONSES = {};
const appeler = (methode, chemin, options) => {
  appels.push([methode, chemin, options === undefined ? null : options]);
  const cle = Object.keys(REPONSES).find((k) => (methode + " " + chemin).startsWith(k));
  let r = cle === undefined ? { statut: 500, corps: null } : REPONSES[cle];
  if (Array.isArray(r)) { r = r.length > 1 ? r.shift() : r[0]; }
  if (r === "long") {
    return Promise.resolve({ statut: 200, corps: null, texte: "ab\\n" + "x".repeat(40000) });
  }
  if (r === "attendre") {
    return new Promise((resoudre) => differes.push(resoudre));
  }
  return Promise.resolve(r);
};
T.initialiserTiroir({ hote: racine, page: racine, appeler, retrouver: () => null });
const dialog = () => body.querySelector(".tiroir");
const panneau = () => parClasse(dialog(), "panneau-reprise")[0];
const vue = () => {
  const p = panneau();
  const select = parBalise(p, "select")[0] || null;
  return {
    busy: p.getAttribute("aria-busy"),
    textes: textes(p),
    commandes: parClasse(dialog(), "commande").map((c) => c.x),
    chemins: parClasse(p, "chemin-reprise").map((c) => c.x),
    btn1: parClasse(dialog(), "btn1").length,
    options: select ? select.options.map((o) => [o.value, o.x]) : null,
    choisie: select ? select.selectedIndex : null,
  };
};
const sortir = (o) => process.stdout.write(JSON.stringify(o));
"""


def lancer(corps: str, reponses: dict | None = None) -> object:
    entete = PAGE % (json.dumps(url("tiroir.js")), json.dumps(url("reprise.js")))
    debut = f"REPONSES = {json.dumps(reponses or {})};\n"
    return executer(debut + corps, entete)


OUVRIR = 'T.ouvrirTiroir("demo", origine, { section: "reprise" }); await tour(10);\n'


@sans_node
def test_rendu_immediat_puis_cas_pas_clone_sans_post():
    sortie = lancer("""
T.ouvrirTiroir("demo", origine, { section: "reprise" });
const avant = vue();
await tour(10);
sortir({ avant, apres: vue(), appels, titre: parClasse(dialog(), "tiroir-section-titre")
  .map((h) => h.x) });
""", {"GET /api/sessions/": liste(SESSIONS, "s-ici", clone_ici=False)})
    assert sortie["avant"]["busy"] == "true"
    assert sortie["avant"]["textes"] == ["Recherche des sessions…"]
    assert sortie["apres"]["busy"] is None
    assert sortie["apres"]["textes"] == [PAS_CLONE]
    assert sortie["appels"] == [["GET", "/api/sessions/demo", None]]
    assert sortie["titre"] == ["Reprise"]


@sans_node
def test_aucune_session():
    sortie = lancer(OUVRIR + "sortir({ vue: vue(), appels });",
                    {"GET /api/sessions/": liste([])})
    assert sortie["vue"]["textes"] == [AUCUNE]
    assert len(sortie["appels"]) == 1


@sans_node
def test_une_session_de_ce_pc_commande_et_dossier():
    sortie = lancer(OUVRIR + "sortir({ vue: vue(), appels });", {
        "GET /api/sessions/": liste([session("s-ici", "pc-a", ce_pc=True)], "s-ici"),
        "POST /api/reprise": reprise(),
    })
    v = sortie["vue"]
    assert v["options"] is None
    assert v["textes"][0] == "pc-a (ce PC) · début 09:05 · dernier tour 11:30"
    assert v["commandes"] == [COMMANDE]
    assert v["chemins"] == ["Dossier : D:\\depots\\demo"]
    assert v["btn1"] == 1 and v["busy"] is None
    assert sortie["appels"][1] == ["POST", "/api/reprise", {
        "json": {"projet": "demo", "session": "s-ici", "pc": "pc-a"}}]


@sans_node
def test_plusieurs_sessions_proposee_choisie_et_mode_brief():
    sortie = lancer(OUVRIR + """
const p = panneau();
const label = parBalise(p, "label")[0];
const select = parBalise(p, "select")[0];
const bouton = parClasse(p, "voir-brief")[0];
sortir({ vue: vue(), appels, label: [label.x, label.a.for === select.id, select.id !== ""],
  bouton: [bouton.x, bouton.className, bouton.a["aria-expanded"],
    bouton.a["aria-controls"] === parClasse(p, "brief")[0].id, parClasse(p, "brief")[0].hidden] });
""", {"GET /api/sessions/": liste(SESSIONS, "s-autre"), "POST /api/reprise": en_brief()})
    v = sortie["vue"]
    assert v["options"] == [
        ["0", "pc-a (ce PC) · début 09:05 · dernier tour 11:30"],
        ["1", "pc-b · début 09:05 · dernier tour 11:30"],
        ["2", "pc-c · début hier 08:00 · dernier tour hier 09:00"],
    ]
    assert v["choisie"] == 1
    assert sortie["label"] == ["Session à reprendre", True, True]
    assert v["commandes"] == [COMMANDE]
    assert v["chemins"] == [f"Brief : C:\\attente\\briefs\\{BRIEF_ID}.md"]
    assert sortie["bouton"] == ["Voir le brief", "btn2 voir-brief", "false", True, True]
    assert sortie["appels"][1][2] == {"json": {"projet": "demo", "session": "s-autre",
                                               "pc": "pc-b"}}


@sans_node
def test_proposee_absente_premiere_choisie():
    sortie = lancer(OUVRIR + "sortir(vue());", {
        "GET /api/sessions/": liste(SESSIONS, None), "POST /api/reprise": reprise()})
    assert sortie["choisie"] == 0


@sans_node
@pytest.mark.parametrize(("raison", "attendu"), [
    ("pas cloné ici", PAS_CLONE),
    ("dossier de la session introuvable", DOSSIER_ABSENT),
    ("<b>autre</b> raison", "<b>autre</b> raison"),
])
def test_sans_commande_textes_de_la_raison(raison, attendu):
    sortie = lancer(OUVRIR + "sortir(vue());", {
        "GET /api/sessions/": liste([session("s", "pc-b")]),
        "POST /api/reprise": reprise(commande=None, mode=None, raison=raison, dossier=None)})
    assert sortie["textes"][1:] == [attendu]
    assert sortie["commandes"] == [] and sortie["btn1"] == 0 and sortie["chemins"] == []


@sans_node
def test_change_poste_la_session_de_l_option_et_garde_le_focus():
    sortie = lancer(OUVRIR + """
const select = parBalise(panneau(), "select")[0];
select.focus();
select.selectedIndex = 2;
select.dispatchEvent(new F.Evenement("change"));
await tour(10);
sortir({ vue: vue(), appels, focus: document.activeElement === select });
""", {"GET /api/sessions/": liste(SESSIONS, "s-ici"),
      "POST /api/reprise": [reprise(commande="premiere"), reprise(commande="seconde")]})
    assert [a[:2] for a in sortie["appels"]] == [
        ["GET", "/api/sessions/demo"], ["POST", "/api/reprise"], ["POST", "/api/reprise"]]
    corps = sortie["appels"][2][2]["json"]
    assert corps == {"projet": "demo", "session": "s-vieille", "pc": "pc-c"}
    assert sortie["vue"]["commandes"] == ["seconde"] and sortie["vue"]["btn1"] == 1
    assert sortie["focus"] is True


@sans_node
def test_nom_de_projet_encode_dans_le_chemin():
    sortie = lancer("""
T.ouvrirTiroir("a b/c?d", origine); await tour(10);
sortir(appels[0]);
""", {"GET /api/sessions/": liste([])})
    assert sortie == ["GET", "/api/sessions/a%20b%2Fc%3Fd", None]


@sans_node
@pytest.mark.parametrize("hostile", [*HOSTILES, "$(calc)"])
def test_valeurs_hostiles_inertes(hostile):
    sortie = lancer(OUVRIR + """
parClasse(panneau(), "voir-brief")[0].click(); await tour(10);
const noeuds = tous(dialog());
sortir({ vue: vue(), balises: [...new Set(noeuds.map((n) => n.t))],
  attributs: noeuds.flatMap((n) => Object.entries(n.a)),
  brief: parClasse(panneau(), "brief")[0].x });
""", {"GET /api/sessions/": liste([session("s", hostile), session("t", "pc-b")], "s"),
      "POST /api/reprise": reprise(commande=hostile, mode="brief", dossier=hostile,
                                   chemin_brief=hostile, brief=BRIEF_ID),
      "GET /api/brief/": {"statut": 200, "corps": None, "texte": hostile}})
    v = sortie["vue"]
    assert v["commandes"] == [hostile]
    assert v["chemins"] == [f"Brief : {hostile}"]
    assert v["options"][0][1].startswith(f"{hostile} · ")
    assert sortie["brief"] == hostile
    assert set(sortie["balises"]) <= {"dialog", "div", "h2", "h3", "button", "section", "p",
                                      "label", "select", "option", "code", "pre"}
    assert all(hostile not in valeur and not nom.startswith("on")
               for nom, valeur in sortie["attributs"])


@sans_node
def test_brief_tronque_bascule_sans_second_appel():
    sortie = lancer(OUVRIR + """
const bouton = parClasse(panneau(), "voir-brief")[0];
const pre = parClasse(panneau(), "brief")[0];
const etapes = [];
const note = () => etapes.push([bouton.x, bouton.a["aria-expanded"], pre.hidden]);
bouton.click(); await tour(10); note();
bouton.click(); await tour(10); note();
bouton.click(); await tour(10); note();
sortir({ etapes, appels: appels.slice(2), longueur: pre.x.length, fin: pre.x.slice(-40),
  tabindex: pre.tabIndex, debut: pre.x.slice(0, 3), busy: panneau().getAttribute("aria-busy") });
""", {"GET /api/sessions/": liste([session("s", "pc-b")]),
      "POST /api/reprise": en_brief(),
      "GET /api/brief/": "long"})
    assert sortie["appels"] == [["GET", f"/api/brief/{BRIEF_ID}", {"texte": True}]]
    assert sortie["etapes"] == [["Masquer le brief", "true", False],
                                ["Voir le brief", "false", True],
                                ["Masquer le brief", "true", False]]
    assert sortie["longueur"] == 32768 + len(TRONQUE)
    assert sortie["fin"].endswith("x" + TRONQUE)
    assert sortie["debut"] == "ab\n" and sortie["tabindex"] == 0 and sortie["busy"] is None


@sans_node
def test_brief_court_entier_et_404():
    sortie = lancer(OUVRIR + """
const bouton = parClasse(panneau(), "voir-brief")[0];
bouton.click(); await tour(10);
sortir({ textes: textes(panneau()), cache: parClasse(panneau(), "brief")[0].hidden,
  bouton: bouton.x, annonces: F.annonces });
""", {"GET /api/sessions/": liste([session("s", "pc-b")]),
      "POST /api/reprise": en_brief(),
      "GET /api/brief/": {"statut": 404, "corps": {"ok": False, "erreur": "Brief inconnu."}}})
    assert sortie["textes"][-1] == BRIEF_ABSENT
    assert sortie["cache"] is True and sortie["bouton"] == "Voir le brief"
    assert sortie["annonces"] == [BRIEF_ABSENT]


@sans_node
@pytest.mark.parametrize(("reponse", "attendu"), [
    ({"statut": 0, "corps": None}, INJOIGNABLE),
    ({"statut": 400, "corps": {"ok": False, "erreur": "Identifiant invalide."}},
     "Identifiant invalide."),
    ({"statut": 404, "corps": {"ok": False, "erreur": "Projet inconnu."}}, "Projet inconnu."),
    ({"statut": 503, "corps": {"ok": False, "erreur": ""}}, "Erreur du serveur local."),
    ({"statut": 403, "corps": None}, "Erreur du serveur local."),
])
def test_erreurs_du_get_des_sessions(reponse, attendu):
    sortie = lancer(OUVRIR + "sortir({ vue: vue(), annonces: F.annonces, appels });",
                    {"GET /api/sessions/": reponse})
    assert sortie["vue"]["textes"] == [attendu] and sortie["vue"]["busy"] is None
    assert sortie["annonces"] == [attendu]
    assert len(sortie["appels"]) == 1


@sans_node
@pytest.mark.parametrize(("reponse", "attendu"), [
    ({"statut": 0, "corps": None}, INJOIGNABLE),
    ({"statut": 400, "corps": {"ok": False, "erreur": "Chemin refusé."}}, "Chemin refusé."),
    ({"statut": 503, "corps": {"ok": False, "erreur": "PC local inconnu."}}, "PC local inconnu."),
])
def test_erreurs_du_post_et_du_brief(reponse, attendu):
    sortie = lancer(OUVRIR + """
const premiere = vue();
REPONSES["POST /api/reprise"] = __BRIEF__;
const select = parBalise(panneau(), "select")[0];
select.selectedIndex = 1; select.dispatchEvent(new F.Evenement("change")); await tour(10);
parClasse(panneau(), "voir-brief")[0].click(); await tour(10);
sortir({ premiere, apres: vue(), annonces: F.annonces });
""".replace("__BRIEF__", json.dumps(en_brief())), {
        "GET /api/sessions/": liste(SESSIONS), "POST /api/reprise": reponse,
        "GET /api/brief/": reponse})
    assert sortie["premiere"]["textes"][-1] == attendu and sortie["premiere"]["btn1"] == 0
    assert sortie["premiere"]["busy"] is None
    assert sortie["apres"]["textes"][-1] == attendu and sortie["apres"]["btn1"] == 1
    assert sortie["annonces"] == [attendu, attendu]


@sans_node
def test_401_rien_n_est_ecrit():
    sortie = lancer(OUVRIR + "sortir({ vue: vue(), annonces: F.annonces });",
                    {"GET /api/sessions/": {"statut": 401, "corps": None}})
    assert sortie["vue"]["textes"] == ["Recherche des sessions…"]
    assert sortie["annonces"] == []


@sans_node
def test_reponses_tardives_ignorees():
    sortie = lancer("""
const etapes = [];
// autre projet : la réponse de « demo » arrive pendant l'affichage de « autre »
T.ouvrirTiroir("demo", origine); await tour(3);
T.ouvrirTiroir("autre", origine); await tour(3);
differes[0]({ statut: 0, corps: null }); await tour(10);
etapes.push(["autre projet", vue().textes, F.annonces.length]);
// tiroir fermé avant la réponse
differes[1]({ statut: 0, corps: null });
T.ouvrirTiroir("demo", origine); await tour(3);
T.fermerTiroir(); await tour(3);
differes[2]({ statut: 0, corps: null }); await tour(10);
etapes.push(["ferme", vue().textes, F.annonces.length]);
// rouvert : seule la réponse de la nouvelle ouverture s'applique
T.ouvrirTiroir("demo", origine); await tour(3);
T.fermerTiroir(); await tour(3);
T.ouvrirTiroir("demo", origine); await tour(3);
differes[3]({ statut: 0, corps: null }); await tour(10);
etapes.push(["rouvert, ancienne", vue().textes, F.annonces.length]);
differes[4]({ statut: 200, corps: { ok: true, donnees: { clone_ici: true, sessions: [],
  proposee: null } } }); await tour(10);
etapes.push(["rouvert, nouvelle", vue().textes, F.annonces.length]);
sortir(etapes);
""", {"GET /api/sessions/": "attendre"})
    assert sortie == [
        ["autre projet", ["Recherche des sessions…"], 0],
        ["ferme", ["Recherche des sessions…"], 0],
        ["rouvert, ancienne", ["Recherche des sessions…"], 0],
        ["rouvert, nouvelle", [AUCUNE], 0],
    ]


@sans_node
def test_change_rapide_seule_la_derniere_reponse_s_applique():
    sortie = lancer(OUVRIR + """
REPONSES["POST /api/reprise"] = "attendre";
const select = parBalise(panneau(), "select")[0];
select.selectedIndex = 1; select.dispatchEvent(new F.Evenement("change"));
select.selectedIndex = 2; select.dispatchEvent(new F.Evenement("change"));
await tour(3);
differes[1](__C__); await tour(10);
differes[0](__B__); await tour(10);
sortir(vue());
""".replace("__B__", json.dumps(reprise(commande="de-pc-b")))
       .replace("__C__", json.dumps(reprise(commande="de-pc-c"))), {
        "GET /api/sessions/": liste(SESSIONS, "s-ici"),
        "POST /api/reprise": reprise(commande="de-pc-a")})
    assert sortie["commandes"] == ["de-pc-c"] and sortie["btn1"] == 1


@sans_node
def test_brief_tardif_apres_change_ignore():
    sortie = lancer(OUVRIR + """
REPONSES["GET /api/brief/"] = "attendre";
parClasse(panneau(), "voir-brief")[0].click(); await tour(3);
REPONSES["POST /api/reprise"] = __R__;
const select = parBalise(panneau(), "select")[0];
select.selectedIndex = 0; select.dispatchEvent(new F.Evenement("change")); await tour(10);
differes[0]({ statut: 200, corps: null, texte: "vieux brief" }); await tour(10);
sortir({ vue: vue(), pre: parClasse(dialog(), "brief").length });
""".replace("__R__", json.dumps(reprise(commande="nouvelle"))), {
        "GET /api/sessions/": liste(SESSIONS, "s-autre"), "POST /api/reprise": en_brief()})
    assert sortie["vue"]["commandes"] == ["nouvelle"] and sortie["pre"] == 0
    assert "vieux brief" not in sortie["vue"]["textes"]


COPIE = """
const presse = [];
Object.defineProperty(globalThis, "navigator", { configurable: true, writable: true,
  value: __PRESSE__ });
const selections = [];
window.getSelection = () => ({ selectAllChildren: (n) => selections.push(n.className) });
// Le retour à « Copier la commande » (2 s) est noté, pas joué.
const minuteurs = [];
const avant = window.setTimeout;
window.setTimeout = (f, ms) => (ms === 2000 ? minuteurs.push(ms) : avant(f, ms));
""" + OUVRIR + """
const bouton = parClasse(dialog(), "btn1")[0];
bouton.click(); await tour(10);
const code = parClasse(dialog(), "commande")[0];
const consigne = parClasse(dialog(), "consigne")[0];
sortir({ presse, bouton: bouton.x, minuteurs, annonces: F.annonces, selections,
  decrit: code.a["aria-describedby"] === consigne.id, consigne: consigne.hidden,
  btn1: parClasse(dialog(), "btn1").length });
"""


@sans_node
def test_copie_reussie_un_seul_btn1():
    presse = "{ clipboard: { writeText: (t) => { presse.push(t); return Promise.resolve(); } } }"
    sortie = lancer(COPIE.replace("__PRESSE__", presse), {
        "GET /api/sessions/": liste([session("s", "pc-a", ce_pc=True)]),
        "POST /api/reprise": reprise()})
    assert sortie["btn1"] == 1
    assert sortie["presse"] == [COMMANDE]
    assert sortie["bouton"] == "Copié" and sortie["annonces"] == ["Copié"]
    assert sortie["minuteurs"] == [2000]
    assert sortie["consigne"] is True


@sans_node
def test_copie_impossible_repli_selection_et_consigne():
    sortie = lancer(COPIE.replace("__PRESSE__", "{}"), {
        "GET /api/sessions/": liste([session("s", "pc-a", ce_pc=True)]),
        "POST /api/reprise": reprise()})
    assert sortie["selections"] == ["commande"]
    assert sortie["consigne"] is False and sortie["decrit"] is True
    assert sortie["annonces"] == ["Ctrl+C pour copier"]
