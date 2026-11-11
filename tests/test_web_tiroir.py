"""Tiroir de détail (story 4.7) sous node, faux DOM `tests/faux_dom.mjs` : registre de sections,
modes modal et non modal, focus, fermeture, seuil, mises à jour sans reconstruction, sections.

Sauté sans `node` (échec si `PILOTAGE_EXIGER_NODE=1`).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pilotage import chemins

WEB = chemins.racine_web()
FAUX_DOM = (Path(__file__).parent / "faux_dom.mjs").as_uri()
NODE = shutil.which("node")
if NODE is None and os.environ.get("PILOTAGE_EXIGER_NODE") == "1":
    raise RuntimeError("node absent alors que PILOTAGE_EXIGER_NODE=1")
sans_node = pytest.mark.skipif(NODE is None, reason="node absent")

MAINTENANT = "2026-11-06T12:00:00Z"
HOSTILES = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '"><svg onload=alert(1)>',
    "**gras** [lien](http://x.example)",
]


def url(module: str) -> str:
    return (WEB / module).as_uri()


def executer(corps: str, entete: str = "") -> object:
    """Exécute `corps` (module ES, `F` = faux DOM) et rend le JSON écrit sur la sortie."""
    script = (
        f"const F = await import({json.dumps(FAUX_DOM)});\n"
        "const { N, body, tous, parClasse, parBalise, texte, textes, tour, touche } = F;\n"
        f"{entete}\n{corps}"
    )
    sortie = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
        env={**os.environ, "TZ": "UTC"},
    )
    assert sortie.returncode == 0, sortie.stderr
    return json.loads(sortie.stdout)


def carte(nom, action="rien-a-faire", **plus):
    base = {"nom": nom, "genre": "projet", "action": action, "chantier": None, "quoi": "",
            "type": None, "raison": {"code": "stable", "params": {}, "texte": "stable"},
            "phase": [], "etiquettes": [], "categorie": "classé", "clone_ici": True,
            "pcs": ["pc-a"], "depot_de": None}
    return {**base, **plus}


DEPOT = {"tag": "v1.2.0", "commits": {"feat": 3, "fix": 1}, "prs_ouvertes": 0,
         "stories_ouvertes": 0, "ci": "verte", "sprint_status": "present"}
CRITERES = [
    {"code": "release", "libelle": "une release publiée", "rempli": True, "precision": "v1.2.0"},
    {"code": "commits", "libelle": "aucun commit hors docs/chore depuis la release",
     "rempli": False, "precision": "4 commits"},
    {"code": "stories", "libelle": "aucune story ouverte", "rempli": True,
     "precision": "pas de sprint-status.yaml"},
    {"code": "prs", "libelle": "aucune PR ouverte", "rempli": True, "precision": None},
    {"code": "ci", "libelle": "CI de main verte", "rempli": True, "precision": None},
]


def etat(cartes, details=None, **plus):
    return {"cartes": cartes, "details": details or {}, "dependances": [], **plus}


# Page minimale : `#racine` qui porte un `main` et un bouton d'origine par projet.
PAGE = """
const T = await import(%s);
const racine = new N("div"); racine.id = "racine"; body.append(racine);
const main = new N("main"); racine.append(main);
const origines = new Map();
const origine = (nom) => {
  if (!origines.has(nom)) {
    const b = new N("button"); b.x = nom; main.append(b); origines.set(nom, b);
  }
  return origines.get(nom);
};
const appels = [];
T.initialiserTiroir({ hote: racine, page: racine, appeler: (...a) => appels.push(a),
  retrouver: (nom) => (globalThis.RETROUVE ? globalThis.RETROUVE(nom) : null) });
const dialog = () => body.querySelector(".tiroir");
const sections = () => parClasse(dialog(), "tiroir-section").map((s) => s.k[0].x);
const sortir = (o) => process.stdout.write(JSON.stringify(o));
"""


def page(avec_sections: bool = True) -> str:
    entete = PAGE % json.dumps(url("tiroir.js"))
    if avec_sections:
        entete = f"await import({json.dumps(url('sections-projet.js'))});\n" + entete
    return entete


# --- Registre ---------------------------------------------------------------------------------


@sans_node
def test_registre_ordre_fixe_erreurs_et_section_absente():
    sortie = executer(page(avec_sections=False) + """
const erreurs = [];
for (const def of [{ id: "inconnue", titre: "x", rendre: () => null }, { titre: "x" }, null]) {
  try { T.enregistrerSection(def); } catch (e) { erreurs.push(e.message); }
}
const bloc = (t) => () => { const p = new N("p"); p.x = t; return p; };
// enregistrées dans le désordre : l'ordre affiché reste celui d'ORDRE_SECTIONS
T.enregistrerSection({ id: "chantier", titre: "Chantier", rendre: bloc("c") });
T.enregistrerSection({ id: "reprise", titre: "Reprise", rendre: bloc("r") });
T.enregistrerSection({ id: "etat", titre: "État", rendre: bloc("e") });
T.enregistrerSection({ id: "messages", titre: "Messages", rendre: () => null });
try { T.enregistrerSection({ id: "etat", titre: "bis", rendre: bloc("x") }); }
catch (e) { erreurs.push(e.message); }
T.majTiroir({ cartes: [] });
T.ouvrirTiroir("p", origine("p"));
const titres = parClasse(dialog(), "tiroir-section-titre").map((h) => [h.x, h.a.id]);
const liees = parClasse(dialog(), "tiroir-section").map((s) => s.a["aria-labelledby"]);
sortir({ erreurs, ordre: T.ORDRE_SECTIONS, titres, liees });
""")
    assert sortie["erreurs"] == [
        "Section de tiroir inconnue : inconnue", "Section de tiroir inconnue : ",
        "Section de tiroir inconnue : ", "Section de tiroir déjà enregistrée : etat"]
    assert sortie["ordre"] == ["etat", "reprise", "messages", "sessions", "faits", "criteres",
                               "chantier", "reglages"]
    # « messages » rend null : section absente ; « reprise » factice à sa place
    assert sortie["titres"] == [["État", "tiroir-section-etat"],
                                ["Reprise", "tiroir-section-reprise"],
                                ["Chantier", "tiroir-section-chantier"]]
    assert sortie["liees"] == ["tiroir-section-etat", "tiroir-section-reprise",
                               "tiroir-section-chantier"]


# --- Modes, focus, fermeture ------------------------------------------------------------------


@sans_node
def test_large_non_modal_titre_focalise_echap_rend_le_focus():
    sortie = executer(page() + f"""
T.majTiroir({json.dumps(etat([carte("alpha")]))});
const o = origine("alpha");
o.click = () => T.ouvrirTiroir("alpha", o);
o.click();
const d = dialog();
const h2 = parClasse(d, "tiroir-titre")[0];
const ouvert = {{ open: d.open, modal: d.modal, page: racine.className,
  focus: document.activeElement === h2, titre: h2.x, lie: d.a["aria-labelledby"],
  tabindex: h2.a.tabindex, nom: T.tiroirOuvert(),
  fermer: textes(parClasse(d, "tiroir-fermer")[0]) }};
touche("Escape");
const ferme = {{ open: d.open, nom: T.tiroirOuvert() }};
await tour();
sortir({{ ouvert, ferme, page: racine.className, focus: document.activeElement === o,
  journal: F.journal, dialogs: parBalise(body, "dialog").length }});
""")
    assert sortie["ouvert"] == {
        "open": True, "modal": False, "page": "tiroir-ouvert", "focus": True, "titre": "alpha",
        "lie": "tiroir-titre", "tabindex": "-1", "nom": "alpha", "fermer": ["Fermer"]}
    assert sortie["ferme"] == {"open": False, "nom": None}
    assert sortie["page"] == "" and sortie["focus"] is True
    assert sortie["journal"] == ["show", "close"] and sortie["dialogs"] == 1


@sans_node
def test_etroit_modal_cancel_et_bouton_fermer():
    sortie = executer(page() + f"""
F.largeur(false);
T.majTiroir({json.dumps(etat([carte("alpha")]))});
const o = origine("alpha");
T.ouvrirTiroir("alpha", o);
const d = dialog();
const ouvert = {{ open: d.open, modal: d.modal, page: racine.className }};
// Échap au document ne ferme pas en modal (le navigateur envoie `cancel`)
touche("Escape");
const apresEchap = d.open;
const annulation = new F.Evenement("cancel");
d.dispatchEvent(annulation);
await tour();
const parCancel = {{ open: d.open, empeche: annulation.defaultPrevented,
  focus: document.activeElement === o }};
T.ouvrirTiroir("alpha", o);
parClasse(d, "tiroir-fermer")[0].click();
await tour();
sortir({{ ouvert, apresEchap, parCancel, parFermer: !d.open && document.activeElement === o,
  journal: F.journal }});
""")
    assert sortie["ouvert"] == {"open": True, "modal": True, "page": ""}
    assert sortie["apresEchap"] is True
    assert sortie["parCancel"] == {"open": False, "empeche": True, "focus": True}
    assert sortie["parFermer"] is True
    assert sortie["journal"] == ["showModal", "close", "showModal", "close"]


@sans_node
def test_echap_deja_traite_ignore():
    sortie = executer(page() + """
T.ouvrirTiroir("alpha", origine("alpha"));
const e = new F.Evenement("keydown", { key: "Escape" });
e.preventDefault();
document.dispatchEvent(e);
touche("Enter");
sortir({ open: dialog().open });
""")
    assert sortie == {"open": True}


@sans_node
def test_origine_detachee_focus_au_bouton_retrouve_sinon_a_main():
    sortie = executer(page() + """
const remplacant = new N("button"); main.append(remplacant);
globalThis.RETROUVE = (nom) => (nom === "alpha" ? remplacant : null);
const o = origine("alpha");
T.ouvrirTiroir("alpha", o);
o.remove();
T.fermerTiroir();
await tour();
const retrouve = document.activeElement === remplacant;
const o2 = origine("beta");
T.ouvrirTiroir("beta", o2);
o2.remove();
T.fermerTiroir();
await tour();
const tabindex = main.getAttribute("tabindex");
sortir({ retrouve, main: document.activeElement === main, tabindex });
""")
    # `main` rendu focalisable (sans `tabindex`, un vrai navigateur laisserait le focus à `body`)
    assert sortie == {"retrouve": True, "main": True, "tabindex": "-1"}


@sans_node
def test_un_seul_tiroir_autre_projet_remplace_contenu_et_origine():
    sortie = executer(page() + f"""
T.majTiroir({json.dumps(etat([carte("alpha"), carte("beta")]))});
const a = origine("alpha"), b = origine("beta");
T.ouvrirTiroir("alpha", a);
const d = dialog();
T.ouvrirTiroir("beta", b);
const meme = dialog() === d;
const titre = parClasse(d, "tiroir-titre")[0].x;
T.initialiserTiroir({{ hote: racine, page: racine, appeler: () => {{}}, retrouver: () => null }});
T.fermerTiroir();
await tour();
sortir({{ meme, titre, dialogs: parBalise(body, "dialog").length,
  focusB: document.activeElement === b,
  journal: F.journal }});
""")
    assert sortie == {"meme": True, "titre": "beta", "dialogs": 1, "focusB": True,
                      "journal": ["show", "close"]}


@sans_node
def test_seuil_franchi_rouvre_dans_l_autre_mode_sans_reconstruction():
    sortie = executer(page() + f"""
T.majTiroir({json.dumps(etat([carte("alpha")]))});
const o = origine("alpha");
T.ouvrirTiroir("alpha", o);
const d = dialog();
const avant = parClasse(d, "tiroir-section")[0];
const fermer = parClasse(d, "tiroir-fermer")[0];
fermer.focus();
F.largeur(false);
await tour();
const premiere = () => parClasse(d, "tiroir-section")[0];
const etroit = {{ open: d.open, modal: d.modal, page: racine.className, meme: premiere() === avant,
  focus: document.activeElement === fermer, nom: T.tiroirOuvert() }};
F.largeur(true);
await tour();
const large = {{ open: d.open, modal: d.modal, page: racine.className,
  meme: premiere() === avant }};
// seuil franchi tiroir fermé : rien ne s'ouvre
T.fermerTiroir();
await tour();
F.largeur(false);
await tour();
sortir({{ etroit, large, ferme: d.open, journal: F.journal, focus: document.activeElement === o }});
""")
    assert sortie["etroit"] == {"open": True, "modal": True, "page": "", "meme": True,
                                "focus": True, "nom": "alpha"}
    assert sortie["large"] == {"open": True, "modal": False, "page": "tiroir-ouvert",
                               "meme": True}
    assert sortie["ferme"] is False and sortie["focus"] is True
    assert sortie["journal"] == ["show", "close", "showModal", "close", "show", "close"]


@sans_node
def test_section_demandee_amenee_a_l_ecran_focus_sur_le_titre():
    sortie = executer(page() + f"""
T.majTiroir({json.dumps(etat([carte("alpha")]))});
T.ouvrirTiroir("alpha", origine("alpha"), {{ section: "chantier" }});
const vues = parClasse(dialog(), "tiroir-section").map((s) => s.vus.length);
sortir({{ vues, focus: document.activeElement === parClasse(dialog(), "tiroir-titre")[0] }});
""")
    assert sortie == {"vues": [0, 0, 0, 1], "focus": True}


@sans_node
def test_sans_initialisation_ouvrir_ne_fait_rien():
    sortie = executer(f"""
const T = await import({json.dumps(url("tiroir.js"))});
T.ouvrirTiroir("alpha", null);
T.majTiroir({{}});
T.fermerTiroir();
const dialogs = parBalise(body, "dialog").length;
process.stdout.write(JSON.stringify({{ nom: T.tiroirOuvert(), dialogs }}));
""")
    assert sortie == {"nom": None, "dialogs": 0}


# --- Mises à jour des 30 s --------------------------------------------------------------------


@sans_node
def test_maj_tiroir_ne_reconstruit_rien_et_n_appelle_que_maj():
    changee = etat([carte("alpha", raison={"code": "x", "params": {}, "texte": "changée"})])
    sortie = executer(page(avec_sections=False) + f"""
const compte = {{ rendre: 0, maj: [] }};
T.enregistrerSection({{ id: "etat", titre: "État", rendre: (ctx) => {{
  compte.rendre += 1;
  const p = new N("p");
  p.x = ctx.carte.raison.texte;
  return p;
}} }});
T.enregistrerSection({{ id: "reglages", titre: "Réglages", rendre: () => new N("div"),
  maj: (noeud, ctx) => compte.maj.push(
    [noeud.t, ctx.nom, ctx.carte.raison.texte, typeof ctx.appeler]) }});
T.majTiroir({json.dumps(etat([carte("alpha")]))});
T.ouvrirTiroir("alpha", origine("alpha"));
const noeuds = tous(dialog());
T.majTiroir({json.dumps(changee)});
const apresMaj = tous(dialog());
const memes = apresMaj.length === noeuds.length && apresMaj.every((n, i) => n === noeuds[i]);
const texteEtat = parClasse(dialog(), "tiroir-section")[0].k[1].x;
// réouverture (geste) : contenu reconstruit avec les données mémorisées
T.ouvrirTiroir("alpha", origine("alpha"));
sortir({{ compte, memes, texteEtat, apres: parClasse(dialog(), "tiroir-section")[0].k[1].x }});
""")
    assert sortie["compte"] == {"rendre": 2,
                                "maj": [["div", "alpha", "changée", "function"]]}
    assert sortie["memes"] is True and sortie["texteEtat"] == "stable"
    assert sortie["apres"] == "changée"


# --- Sections de la story 4.7 -----------------------------------------------------------------


def _ouvrir(etat_, nom="alpha", maintenant=MAINTENANT):
    return executer(page() + f"""
const vraie = Date;
const fige = {json.dumps(maintenant)};
globalThis.Date = class extends vraie {{
  constructor(...a) {{ super(...(a.length ? a : [fige])); }}
}};
T.majTiroir({json.dumps(etat_)});
T.ouvrirTiroir({json.dumps(nom)}, origine({json.dumps(nom)}));
const plat = (n) => ({{ t: n.t, c: n.className, x: n.x, a: n.a, k: n.k.map(plat) }});
const contenu = parClasse(dialog(), "tiroir-section").map((s) => plat(s.k[1]));
sortir({{ sections: sections(), contenu, tout: plat(dialog()) }});
""")


def _tous(n):
    yield n
    for fils in n["k"]:
        yield from _tous(fils)


def _textes(n):
    return [m["x"] for m in _tous(n) if m["x"]]


def _classe(n, classe):
    return [m for m in _tous(n) if classe in m["c"].split()]


@sans_node
def test_sections_dans_l_ordre_et_contenus_complets():
    attente = carte("alpha", "attend-utilisateur", quoi="choisir A ou B", type="choix",
                    phase=["status-dev"], chantier="outillage", clone_ici=False,
                    raison={"code": "attend-utilisateur", "params": {}, "texte": "vous attend"})
    detail = {
        "sessions": [
            {"pc": "pc-a", "statut": {"code": "attend", "texte": "en attente"},
             "debut": "2026-11-06T08:41:00Z", "dernier_tour": "2026-11-05T22:47:00Z",
             "fin": None, "branche": "story/3-2", "note": "ligne 1\n  ligne 2"},
            {"pc": "pc-a", "statut": {"code": "finie", "texte": "finie"},
             "debut": "2026-11-04T08:00:00Z", "dernier_tour": None,
             "fin": "2026-11-04T09:00:00Z", "branche": None, "note": None},
            {"pc": "pc-bureau", "statut": {"code": "sans-nouvelles",
                                           "texte": "sans nouvelles de pc-bureau"},
             "debut": "2026-11-06T07:00:00Z", "dernier_tour": None, "fin": None,
             "branche": "main", "note": None},
        ],
        "depot": DEPOT, "depot_de": {"pc": "pc-bureau", "genere_a": "2026-11-05T23:10:00Z"},
        "criteres": CRITERES,
    }
    e = etat([attente], {"alpha": detail}, dependances=["alpha ← beta", "gamma ← delta",
                                                         "zeta ← alpha"],
             utilisateur="Camille")
    sortie = _ouvrir(e)
    assert sortie["sections"] == ["État", "Sessions par PC", "Faits du dépôt",
                                  "Critères de stabilité", "Chantier et dépendances"]
    etat_, sessions, faits, criteres, chantier = sortie["contenu"]
    assert _textes(etat_) == ["Attend Camille", "choix", "choisir A ou B", "phase : status-dev",
                              "pas cloné ici"]
    assert _classe(etat_, "pastille-action")[0]["c"] == "pastille-action pastille-attend"
    assert [m["x"] for m in _tous(sessions) if m["t"] == "h4"] == ["pc-a", "pc-bureau"]
    lignes = [_textes(li) for li in _tous(sessions) if li["t"] == "li"]
    assert lignes == [
        ["en attente", " · ", "début 08:41", " · ", "dernier tour hier 22:47", " · ",
         "story/3-2", "ligne 1\n  ligne 2"],
        ["finie", " · ", "début 04/11", " · ", "fin 04/11"],
        ["sans nouvelles de pc-bureau", " · ", "début 07:00", " · ", "main"],
    ]
    (note,) = _classe(sessions, "note-reprise")
    assert note["t"] == "p" and note["x"] == "ligne 1\n  ligne 2"
    assert _textes(faits) == [
        "Release : v1.2.0", "Commits depuis la release : 3 feat, 1 fix", "PR ouvertes : 0",
        "Stories ouvertes : 0", "CI de main : verte", "relus sur pc-bureau, hier 23:10"]
    assert _textes(criteres) == [
        "une release publiée : rempli (v1.2.0)",
        "aucun commit hors docs/chore depuis la release : non rempli (4 commits)",
        "aucune story ouverte : rempli (pas de sprint-status.yaml)",
        "aucune PR ouverte : rempli", "CI de main verte : rempli"]
    assert _textes(chantier) == ["Chantier : outillage", "alpha ← beta", "zeta ← alpha"]
    assert [d["c"] for d in _classe(chantier, "dependance")] == ["dependance", "dependance"]


@sans_node
def test_textes_vides_exacts_et_criteres_absents():
    e = etat([carte("alpha", raison={"code": "faits-absents", "params": {},
                                     "texte": "faits du dépôt non relus"},
                    action="a-relancer")],
             {"alpha": {"sessions": [], "depot": None, "depot_de": None, "criteres": None}})
    sortie = _ouvrir(e)
    assert sortie["sections"] == ["État", "Sessions par PC", "Faits du dépôt",
                                  "Chantier et dépendances"]
    etat_, sessions, faits, chantier = sortie["contenu"]
    assert _textes(etat_) == ["À relancer", "faits du dépôt non relus"]  # pas de phase
    assert _textes(sessions) == ["Aucune session connue."]
    assert _textes(faits) == ["Faits du dépôt non relus. Lancez un scan."]
    assert _textes(chantier) == ["Hors chantier."]
    assert "bientôt" not in json.dumps(sortie, ensure_ascii=False)


@sans_node
def test_projet_sans_detail_ni_carte():
    sortie = _ouvrir(etat([]), nom="inconnu")
    assert sortie["sections"] == ["Sessions par PC", "Faits du dépôt", "Chantier et dépendances"]
    assert [_textes(c) for c in sortie["contenu"]] == [
        ["Aucune session connue."], ["Faits du dépôt non relus. Lancez un scan."],
        ["Hors chantier."]]


@sans_node
def test_faits_sans_commits_sans_sprint_status_et_ci_en_cours():
    depot = {**DEPOT, "tag": None, "commits": {}, "sprint_status": "absent", "ci": "en_cours",
             "prs_ouvertes": 2}
    e = etat([carte("alpha")], {"alpha": {"sessions": [], "depot": depot, "depot_de": None,
                                          "criteres": CRITERES}})
    faits = _ouvrir(e)["contenu"][2]
    assert _textes(faits) == [
        "Release : aucune", "Commits depuis la release : aucun", "PR ouvertes : 2",
        "Stories ouvertes : pas de sprint-status.yaml", "CI de main : en cours"]


@sans_node
@pytest.mark.parametrize("hostile", HOSTILES)
def test_valeurs_hostiles_restent_du_texte(hostile):
    detail = {"sessions": [{"pc": hostile, "statut": {"code": "active", "texte": "active"},
                            "debut": hostile, "dernier_tour": None, "fin": None,
                            "branche": hostile, "note": hostile}],
              "depot": {**DEPOT, "tag": hostile}, "depot_de": {"pc": hostile, "genere_a": hostile},
              "criteres": [{**CRITERES[0], "precision": hostile}]}
    e = etat([carte(hostile, "attend-utilisateur", quoi=hostile, chantier=hostile,
                    phase=[hostile])], {hostile: detail}, dependances=[f"{hostile} ← b"],
             utilisateur=hostile)
    sortie = _ouvrir(e, nom=hostile)
    noeuds = list(_tous(sortie["tout"]))
    for n in noeuds:
        assert all(hostile not in v for v in n["a"].values())
    assert {n["t"] for n in noeuds} <= {"dialog", "div", "h2", "h3", "h4", "button", "section",
                                         "p", "span", "ul", "li", "svg", "path"}
    textes = [n["x"] for n in noeuds if hostile in n["x"]]
    assert hostile in textes  # titre, *quoi*, PC, branche, note… posés tels quels
    assert f"Chantier : {hostile}" in textes and f"{hostile} ← b" in textes


@sans_node
def test_accueil_nom_ouvre_le_tiroir_et_echap_rend_le_focus():
    tourne = carte("alpha", "tourne", raison={"code": "tourne", "texte": "t", "params": {}})
    sortie = executer(page() + f"""
const A = await import({json.dumps(url("accueil.js"))});
const cartes = [{json.dumps(tourne)}];
const e = {{ cartes, colonnes: {{ "attend-utilisateur": [], "a-relancer": [], tourne: cartes,
  "rien-a-faire": [] }},
  comptes: {{ actions: {{}}, types: {{}}, familles: {{}} }}, details: {{}} }};
T.majTiroir(e);
A.rendreAccueil(main, e, new Date({json.dumps(MAINTENANT)}));
const bouton = A.boutonNom(main, "alpha");
bouton.focus();
bouton.click();
const ouvert = T.tiroirOuvert();
touche("Escape");
await tour();
sortir({{ ouvert, focus: document.activeElement === bouton, absent: A.boutonNom(main, "zz") }});
""")
    assert sortie == {"ouvert": "alpha", "focus": True, "absent": None}


def test_css_du_tiroir():
    css = (WEB / "appli.css").read_text(encoding="utf-8")
    regle = css.split("dialog.tiroir {", 1)[1].split("}", 1)[0]
    for attendu in ("position: fixed", "background: var(--surface)",
                    "border: var(--trait-largeur) solid var(--trait-fort)",
                    "box-shadow: var(--halo)", "border-radius: var(--rayon-grand)"):
        assert attendu in regle, attendu
    assert "dialog.tiroir::backdrop {\n  background: var(--voile);" in css
    large = css.split("@media (min-width: 80em) {\n  dialog.tiroir {", 1)[1].split("}", 1)[0]
    assert "width: 30rem" in large
    assert ".tiroir-ouvert {\n    margin-right: 30rem;" in css
    mouvement = css.split("@media (prefers-reduced-motion: no-preference) {\n  dialog.tiroir", 1)
    assert len(mouvement) == 2 and "150ms" in mouvement[1].split("}", 1)[0]
    assert "@media (min-width: 80em) and (max-width: 109.999em) {\n  .tiroir-ouvert .kanban {\n"\
           "    grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    note = css.split(".note-reprise {", 1)[1].split("}", 1)[0]
    assert "white-space: pre-wrap" in note and "overflow-wrap: anywhere" in note
    titre = css.split(".tiroir-titre {", 1)[1].split("}", 1)[0]
    assert "font-size: var(--taille-titre-4)" in titre
    cibles = css.split(".tiroir-fermer,\n.nom-projet {", 1)[1].split("}", 1)[0]
    assert "min-height: 24px" in cibles and "min-width: 24px" in cibles
