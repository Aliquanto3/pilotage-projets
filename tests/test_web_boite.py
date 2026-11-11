"""Section « Messages » du tiroir (story 5.6) sous node, faux DOM `tests/faux_dom.mjs` : compteur
en octets, corps du dépôt, liste relue sur `GET /api/operations`, erreurs, textes hostiles inertes,
relecture des 30 s sans toucher la saisie, réponses tardives.

`ctx.appeler` est un double passé à `initialiserTiroir` (frontière : le serveur local). Sauté sans
`node` (échec si `PILOTAGE_EXIGER_NODE=1`).
"""

import json

import pytest

from tests.test_web_tiroir import HOSTILES, carte, executer, sans_node, url

INJOIGNABLE = "Serveur local injoignable. Relancez l'appli par lancer.py."
DEPOSE = "Message déposé, en attente de synchro."
SECRET = "Message refusé : il ressemble à un secret (jeton ghp_)."
DELIMITEUR = "<<<PILOTAGE-MESSAGE-0123456789abcdef>>> fin\n<<<PILOTAGE-MESSAGE-FIN>>>"
FRAICHEUR = [{"pc": "pc-a", "genere_a": "2026-11-06T11:00:00Z", "texte": "pc-a il y a 1 h"},
             {"pc": "pc-b", "genere_a": "2026-11-06T10:00:00Z", "texte": "pc-b il y a 2 h"},
             {"pc": "pc-jamais", "genere_a": None, "texte": "pc-jamais jamais"}]


def message(n, texte="bonjour", pc=None, projet="demo", etat="en-attente",
            libelle="en attente de synchro"):
    return {"id": f"20261106T1{n:05d}Z-0a1b2c3d", "projet": projet, "pc": pc, "texte": texte,
            "etat": etat, "lectures": [], "libelle": libelle}


def operations(messages=(), ops=()):
    return {"statut": 200, "corps": {"ok": True, "donnees": {
        "operations": list(ops), "messages": list(messages)}}}


def etat_page(cartes=None, details=None, **plus):
    return {"cartes": [carte("demo")] if cartes is None else cartes, "details": details or {},
            "dependances": [], "fraicheur": FRAICHEUR, "alertes": [], "chantiers_connus": [],
            **plus}


ACCEPTE = {"statut": 202, "corps": {"ok": True, "donnees": {
    "id": "x", "verbe": "deposer_message", "projet": "demo", "sync": "lance"}}}

# Page : tiroir, sections « Messages » et « Réglages » ; `appeler` répond par `REPONSES` (clé :
# méthode et début du chemin ; valeur : réponse, liste consommée dans l'ordre, ou "attendre"
# pour une promesse pilotée par `differes`).
PAGE = """
const VraieDate = Date;
globalThis.Date = class extends VraieDate {
  constructor(...a) { super(...(a.length ? a : ["2026-11-06T12:00:00Z"])); }
};
const T = await import(%s);
await import(%s);
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
  if (r === "attendre") {
    return new Promise((resoudre) => differes.push(resoudre));
  }
  return Promise.resolve(JSON.parse(JSON.stringify(r)));
};
T.initialiserTiroir({ hote: racine, page: racine, appeler, retrouver: () => null });
const dialog = () => body.querySelector(".tiroir");
const section = (c) => parClasse(dialog(), c)[0];
const saisir = (noeud, valeur, type = "input") => {
  noeud.value = valeur;
  noeud.dispatchEvent(new F.Evenement(type));
};
const ops = (m) => appels.filter((a) => a[1] === "/api/operations").length;
const sortir = (o) => process.stdout.write(JSON.stringify(o));
"""


def lancer(corps: str, reponses: dict | None = None, etat: dict | None = None) -> object:
    entete = PAGE % tuple(json.dumps(url(m)) for m in ("tiroir.js", "boite.js", "reglages.js"))
    debut = (f"REPONSES = {json.dumps(reponses or {})};\n"
             f"T.majTiroir({json.dumps(etat or etat_page())});\n")
    return executer(debut + corps, entete)


OUVRIR = 'T.ouvrirTiroir("demo", origine); await tour(10);\n'
# Vue de la section « Messages ».
VUE = """
const vue = () => {
  const b = section("boite");
  const zone = parBalise(b, "textarea")[0];
  const compteur = b.querySelector("#boite-compteur");
  const bouton = parClasse(b, "deposer")[0];
  const select = parBalise(b, "select")[0];
  return {
    zone: zone.value, compteur: compteur.x, classe: compteur.className, actif: !bouton.disabled,
    decrit: zone.a["aria-describedby"], live: compteur.getAttribute("aria-live"),
    busy: b.getAttribute("aria-busy"),
    options: select.options.map((o) => [o.value, o.x]), choisi: select.value,
    textes: parClasse(b, "texte-message").map((p) => p.x),
    metas: parClasse(section("messages-projet"), "meta").map((p) => p.x),
    erreurs: parClasse(b, "bandeau-local").map((d) => [d.className, d.x]),
    focus: document.activeElement === zone ? "zone" : document.activeElement === bouton
      ? "bouton" : null,
    ul: parClasse(b, "liste-messages").length,
  };
};
const zone = () => parBalise(section("boite"), "textarea")[0];
const bouton = () => parClasse(section("boite"), "deposer")[0];
const select = () => parBalise(section("boite"), "select")[0];
"""


@sans_node
def test_structure_libelles_compteur_relie_non_annonce_et_pc_connus():
    sortie = lancer(OUVRIR + VUE + """
const b = section("boite");
const labels = parBalise(b, "label").map((l) => [l.x, l.a.for]);
sortir({ vue: vue(), labels, ids: [zone().id, select().id],
  titre: parClasse(dialog(), "tiroir-section-titre").map((h) => h.x),
  bouton: bouton().className });
""", {"GET /api/operations": operations()})
    v = sortie["vue"]
    assert sortie["titre"] == ["Messages", "Réglages"]
    assert sortie["labels"] == [["Message", sortie["ids"][0]], ["PC visé", sortie["ids"][1]]]
    assert v["decrit"] == "boite-compteur" and v["live"] is None
    assert v["compteur"] == "2048 octets restants" and v["classe"] == "meta"
    assert v["actif"] is False  # zone vide
    assert v["options"] == [["", "Tous les PC"], ["pc-a", "pc-a"], ["pc-b", "pc-b"]]
    assert sortie["bouton"] == "btn2 deposer"
    assert v["metas"] == ["Aucun message."]


@sans_node
@pytest.mark.parametrize(("valeur", "compteur", "erreur", "actif"), [
    ("a", "2047 octets restants", False, True),
    ("é", "2046 octets restants", False, True),
    ("😀", "2044 octets restants", False, True),
    ("a" * 2047, "1 octet restant", False, True),
    ("a" * 2048, "0 octet restant", False, True),
    ("a" * 2049, "1 octet de trop", True, False),
    ("é" * 1025, "2 octets de trop", True, False),
    ("   \n\t ", "2042 octets restants", False, False),
])
def test_compteur_en_octets_bornes_et_blancs(valeur, compteur, erreur, actif):
    sortie = lancer(OUVRIR + VUE + f"saisir(zone(), {json.dumps(valeur)}); sortir(vue());",
                    {"GET /api/operations": operations()})
    assert sortie["compteur"] == compteur
    assert ("erreur" in sortie["classe"].split()) is erreur
    assert sortie["actif"] is actif


@sans_node
def test_tous_les_pc_corps_a_deux_cles_puis_zone_videe_et_liste_relue():
    deposee = message(1, texte="  à relire  ")
    sortie = lancer(OUVRIR + VUE + """
saisir(zone(), "  à relire  ");
bouton().focus();
bouton().click();
const pendant = vue();
await tour(10);
await tour(10);
sortir({ pendant, apres: vue(), appels, annonces: F.annonces });
""", {"GET /api/operations": [operations(), operations([deposee])], "POST /api/message": ACCEPTE})
    assert sortie["pendant"]["busy"] == "true" and sortie["pendant"]["actif"] is False
    post = [a for a in sortie["appels"] if a[0] == "POST"]
    assert post == [["POST", "/api/message", {"json": {"projet": "demo", "texte": "  à relire  "}}]]
    apres = sortie["apres"]
    assert apres["zone"] == "" and apres["compteur"] == "2048 octets restants"
    assert apres["focus"] == "zone" and apres["busy"] is None
    assert apres["textes"] == ["  à relire  "]  # relu sur le serveur, jamais inséré localement
    assert apres["metas"] == ["Pour tous les PC · en attente de synchro"]
    assert DEPOSE in sortie["annonces"]
    gets = [a for a in sortie["appels"] if a[1] == "/api/operations"]
    assert len(gets) == 2  # ouverture (partagée par les deux sections), puis relecture du 202


@sans_node
def test_pc_choisi_corps_a_trois_cles():
    sortie = lancer(OUVRIR + VUE + """
saisir(zone(), "salut");
saisir(select(), "pc-b", "change");
bouton().click();
await tour(10);
sortir({ appels, vue: vue() });
""", {"GET /api/operations": operations(), "POST /api/message": ACCEPTE})
    post = [a for a in sortie["appels"] if a[0] == "POST"]
    assert post[0][2] == {"json": {"projet": "demo", "texte": "salut", "pc": "pc-b"}}
    assert sortie["vue"]["choisi"] == "pc-b"  # le PC visé reste choisi


@sans_node
@pytest.mark.parametrize(("reponse", "attendu"), [
    ({"statut": 400, "corps": {"ok": False, "erreur": SECRET}}, SECRET),
    ({"statut": 503, "corps": {"ok": False, "erreur": "Écriture impossible."}},
     "Écriture impossible."),
    ({"statut": 500, "corps": None}, "Erreur du serveur local."),
    ({"statut": 0, "corps": None}, INJOIGNABLE),
])
def test_refus_affiche_tel_quel_saisie_gardee(reponse, attendu):
    sortie = lancer(OUVRIR + VUE + """
saisir(zone(), "mon texte ghp_x");
saisir(select(), "pc-a", "change");
bouton().click();
await tour(10);
sortir({ vue: vue(), journal: F.journal, gets: ops() });
""", {"GET /api/operations": operations(), "POST /api/message": reponse})
    v = sortie["vue"]
    assert v["erreurs"] == [["bandeau-local erreur", attendu]]
    assert v["zone"] == "mon texte ghp_x" and v["choisi"] == "pc-a" and v["actif"] is True
    assert f"alerte:{attendu}" in sortie["journal"]
    assert sortie["gets"] == 1  # pas de relecture sans 202


@sans_node
def test_401_rien_affiche():
    sortie = lancer(OUVRIR + VUE + """
saisir(zone(), "texte");
bouton().click();
await tour(10);
sortir({ vue: vue(), journal: F.journal });
""", {"GET /api/operations": operations(), "POST /api/message": {"statut": 401, "corps": None}})
    assert sortie["vue"]["erreurs"] == [] and sortie["vue"]["zone"] == "texte"
    assert not [j for j in sortie["journal"] if j.startswith("alerte:")]


@sans_node
@pytest.mark.parametrize(("reponse", "attendu"), [
    ({"statut": 0, "corps": None}, INJOIGNABLE),
    ({"statut": 503, "corps": {"ok": False, "erreur": "Boîte illisible."}}, "Boîte illisible."),
])
def test_lecture_en_echec_bandeau_puis_efface_a_la_relecture(reponse, attendu):
    sortie = lancer(OUVRIR + VUE + """
const avant = vue();
T.majTiroir(ETAT);
await tour(10);
sortir({ avant, apres: vue() });
""".replace("ETAT", json.dumps(etat_page())),
        {"GET /api/operations": [reponse, operations([message(1)])]})
    assert sortie["avant"]["erreurs"] == [["bandeau-local erreur", attendu]]
    assert sortie["avant"]["metas"] == []
    assert sortie["apres"]["erreurs"] == []
    assert sortie["apres"]["textes"] == ["bonjour"]


@sans_node
def test_401_en_lecture_rien():
    sortie = lancer(OUVRIR + VUE + "sortir(vue());",
                    {"GET /api/operations": {"statut": 401, "corps": None}})
    assert sortie["erreurs"] == [] and sortie["metas"] == ["Lecture des messages…"]


@sans_node
def test_liste_du_projet_plus_recente_d_abord_bornee_a_20():
    messages = [message(n, texte=f"m{n}", pc="pc-a" if n % 2 else None,
                        libelle="lu par pc-a à 08:12" if n == 25 else "déposé")
                for n in range(1, 26)]
    messages.append(message(99, texte="autre projet", projet="autre"))
    sortie = lancer(OUVRIR + VUE + "sortir(vue());", {"GET /api/operations": operations(messages)})
    assert sortie["textes"] == [f"m{n}" for n in range(25, 5, -1)]
    assert sortie["metas"][0] == "Pour pc-a · lu par pc-a à 08:12"
    assert sortie["metas"][1] == "Pour tous les PC · déposé"
    assert sortie["metas"][-1] == "5 messages plus anciens non affichés."
    assert len(sortie["metas"]) == 21


@sans_node
def test_lecture_en_cours_puis_corps_illisible_aucun_message():
    sortie = lancer("""
T.ouvrirTiroir("demo", origine);
""" + VUE + """
const avant = vue();
differes.forEach((r) => r({ statut: 200, corps: { ok: true, donnees: "illisible" } }));
await tour(10);
sortir({ avant, apres: vue() });
""", {"GET /api/operations": "attendre"})
    assert sortie["avant"]["metas"] == ["Lecture des messages…"]
    assert sortie["apres"]["metas"] == ["Aucun message."] and sortie["apres"]["ul"] == 0


@sans_node
def test_textes_hostiles_inertes():
    hostiles = [*HOSTILES, DELIMITEUR, "ligne 1\n\n  ligne 3"]
    messages = [message(i + 1, texte=t, pc=t if i == 0 else None) for i, t in enumerate(hostiles)]
    sortie = lancer(OUVRIR + VUE + """
const b = section("boite");
sortir({ vue: vue(), balises: [...new Set(F.tous(b).map((n) => n.t))].sort() });
""", {"GET /api/operations": operations(messages)})
    assert sortie["vue"]["textes"] == list(reversed(hostiles))
    assert sortie["vue"]["metas"][-1] == f"Pour {HOSTILES[0]} · en attente de synchro"
    assert sortie["balises"] == sorted(
        {"div", "label", "textarea", "p", "select", "option", "button", "ul", "li"})


@sans_node
def test_maj_relit_la_liste_sans_toucher_zone_pc_ni_focus():
    sortie = lancer(OUVRIR + VUE + """
saisir(zone(), "brouillon");
saisir(select(), "pc-b", "change");
zone().focus();
const z = zone();
T.majTiroir(ETAT);
await tour(10);
sortir({ vue: vue(), meme: z === zone(), gets: ops() });
""".replace("ETAT", json.dumps(etat_page(
        fraicheur=[{"pc": "pc-z", "genere_a": "x", "texte": "z"}]))),
        {"GET /api/operations": [operations(), operations([message(1, texte="nouveau")])]})
    v = sortie["vue"]
    assert v["zone"] == "brouillon" and v["compteur"] == "2039 octets restants"
    assert v["choisi"] == "pc-b" and v["focus"] == "zone" and sortie["meme"] is True
    assert v["options"] == [["", "Tous les PC"], ["pc-a", "pc-a"], ["pc-b", "pc-b"]]
    assert v["textes"] == ["nouveau"]
    assert sortie["gets"] == 2


@sans_node
def test_reponses_tardives_ignorees():
    sortie = lancer("""
T.ouvrirTiroir("demo", origine);
""" + VUE + """
saisir(zone(), "texte");
bouton().click();
T.ouvrirTiroir("autre", origine);
await tour(5);
// GET de l'ouverture (partagé : même état chargé), puis POST de demo : réponses dans le désordre.
differes[1]({ statut: 400, corps: { ok: false, erreur: "trop tard" } });
differes[0]({ statut: 200, corps: { ok: true, donnees: { operations: [], messages: [
  { id: "x", projet: "demo", pc: null, texte: "demo tardif", libelle: "déposé" }] } } });
await tour(10);
const b = section("boite");
sortir({ textes: textes(b), journal: F.journal, titre: parClasse(dialog(), "tiroir-titre")[0].x });
""", {"GET /api/operations": "attendre", "POST /api/message": "attendre"},
        etat_page(cartes=[carte("demo"), carte("autre")]))
    assert sortie["titre"] == "autre"
    assert "demo tardif" not in sortie["textes"] and "trop tard" not in sortie["textes"]
    assert "Aucun message." in sortie["textes"]  # liste d'autre, d'après la même lecture
    assert "alerte:trop tard" not in sortie["journal"]
