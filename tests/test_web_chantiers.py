"""Vue Chantiers (story 4.7) sous node, faux DOM `tests/faux_dom.mjs` : blocs, ordre, Découverts,
Hors chantier, dépendances, ouverture du tiroir, focus et absence de reconstruction.

Sauté sans `node` (échec si `PILOTAGE_EXIGER_NODE=1`).
"""

import json
from datetime import UTC, datetime

import pytest

from pilotage.noyau import etat as noyau_etat
from tests.test_web_tiroir import HOSTILES, carte, executer, page, sans_node, url

ENTETE = f"""
const C = await import({json.dumps(url("chantiers.js"))});
const plat = (n) => ({{ t: n.t, c: n.className, x: n.x, a: n.a, k: n.k.map(plat) }});
const blocs = () => parClasse(main, "bloc-chantier").map((b) => textes(b));
"""


def vue(cartes, chantiers, dependances=(), **plus):
    return {"cartes": cartes, "chantiers": chantiers, "dependances": list(dependances),
            "details": {}, **plus}


def chantier(nom, action, projets):
    return {"nom": nom, "genre": "chantier", "action": action, "projets": projets}


def lancer(corps):
    return executer(page() + ENTETE + corps)


@sans_node
def test_blocs_dans_l_ordre_decouverts_puis_hors_chantier():
    a1 = carte("api", "attend-utilisateur", chantier="Zeta")
    a2 = carte("web", "rien-a-faire", chantier="Zeta")
    b1 = carte("outil", "a-relancer", chantier="atelier")
    d1 = carte("trouve", "rien-a-faire", categorie="découvert, à classer")
    h1 = carte("seul", "tourne")
    h2 = carte("autre", "rien-a-faire")
    e = vue([a1, h2, b1, h1, d1, a2],
            [chantier("Zeta", "attend-utilisateur", [a1, a2]),
             chantier("atelier", "a-relancer", [b1])],
            dependances=["api ← outil", "outil ← web", "seul ← api", "trouve ← web"],
            utilisateur="Camille")
    sortie = lancer(f"""
C.rendreChantiers(main, {json.dumps(e)});
const pastilles = parClasse(main, "pastille-action").map((p) => p.className);
const deps = parClasse(main, "dependance").map((p) => [p.t, p.x]);
sortir({{ titre: [main.k[0].t, main.k[0].className, main.k[0].x], blocs: blocs(), pastilles,
  deps }});
""")
    assert sortie["titre"] == ["h2", "masque", "Chantiers"]
    assert sortie["blocs"] == [
        ["Zeta", "Attend Camille", "api", "Attend Camille", "web", "Rien à faire",
         "api ← outil"],
        ["atelier", "À relancer", "outil", "À relancer", "outil ← web"],
        ["Découverts, à classer", "trouve", "Rien à faire", "trouve ← web"],
        ["Hors chantier", "autre", "Rien à faire", "seul", "Tourne", "seul ← api"],
    ]
    assert sortie["pastilles"][:3] == ["pastille-action pastille-attend"] * 2 + [
        "pastille-action pastille-rien"]
    assert sortie["deps"] == [["p", "api ← outil"], ["p", "outil ← web"],
                              ["p", "trouve ← web"], ["p", "seul ← api"]]


@sans_node
def test_bloc_vide_absent_et_aucun_projet():
    sortie = lancer(f"""
C.rendreChantiers(main, {json.dumps(vue([carte("seul")], []))});
const un = blocs();
C.rendreChantiers(main, {json.dumps(vue([], []))});
sortir({{ un, vide: blocs(), textes: textes(main) }});
""")
    assert sortie["un"] == [["Hors chantier", "seul", "Rien à faire"]]
    assert sortie["vide"] == []
    assert sortie["textes"][0] == "Chantiers"
    assert sortie["textes"][1].startswith("Aucun projet trouvé sous Documents")


@sans_node
def test_chargement():
    sortie = lancer("C.rendreChantiers(main, null); sortir(textes(main));")
    assert sortie == ["Chantiers", "Chargement…"]


@sans_node
def test_nom_d_un_depot_ouvre_son_tiroir_focus_rendu_au_bouton():
    e = vue([carte("api", chantier="Zeta")], [chantier("Zeta", "rien-a-faire",
                                                       [carte("api", chantier="Zeta")])])
    sortie = lancer(f"""
T.majTiroir({json.dumps(e)});
C.rendreChantiers(main, {json.dumps(e)});
const bouton = C.boutonNom(main, "api");
bouton.click();
const h2 = parClasse(dialog(), "tiroir-titre")[0];
const ouvert = [T.tiroirOuvert(), document.activeElement === h2];
touche("Escape");
await tour();
sortir({{ ouvert, focus: document.activeElement === bouton, classe: bouton.className,
  type: bouton.a.type, absent: C.boutonNom(main, "zz") }});
""")
    assert sortie == {"ouvert": ["api", True], "focus": True, "classe": "btn-lien nom-projet",
                      "type": "button", "absent": None}


@sans_node
def test_pas_de_reconstruction_sans_changement_focus_conserve_sinon():
    a = carte("api", chantier="Zeta")
    b = carte("web", chantier="Zeta")
    e1 = vue([a, b], [chantier("Zeta", "rien-a-faire", [a, b])])
    # seules des données non lues changent (depot_de, pcs, details) : mêmes nœuds
    a_bis = {**a, "depot_de": {"pc": "pc-b", "genere_a": "2026-11-06T10:00:00Z"}, "pcs": ["x"]}
    e2 = {**vue([a_bis, b], [chantier("Zeta", "rien-a-faire", [a_bis, b])]),
          "details": {"api": {"sessions": []}}}
    # l'action de web change : reconstruction, le focus suit le bouton de web
    b_ter = {**b, "action": "a-relancer"}
    e3 = vue([a, b_ter], [chantier("Zeta", "a-relancer", [a, b_ter])])
    e4 = vue([a], [chantier("Zeta", "rien-a-faire", [a])])
    sortie = lancer(f"""
C.rendreChantiers(main, {json.dumps(e1)});
const vueAvant = parClasse(main, "chantiers")[0];
C.boutonNom(main, "web").focus();
C.rendreChantiers(main, {json.dumps(e2)});
const meme = parClasse(main, "chantiers")[0] === vueAvant;
C.rendreChantiers(main, {json.dumps(e3)});
const reconstruit = parClasse(main, "chantiers")[0] !== vueAvant;
const suit = document.activeElement === C.boutonNom(main, "web")
  && main.contains(document.activeElement);
C.rendreChantiers(main, {json.dumps(e4)});
sortir({{ meme, reconstruit, suit, repli: document.activeElement === main.k[0],
  tabindex: main.k[0].a.tabindex }});
""")
    assert sortie == {"meme": True, "reconstruit": True, "suit": True, "repli": True,
                      "tabindex": "-1"}


@sans_node
def test_retour_depuis_l_accueil_reconstruit():
    e = vue([carte("api")], [])
    sortie = lancer(f"""
C.rendreChantiers(main, {json.dumps(e)});
const avant = parClasse(main, "chantiers")[0];
main.textContent = "";
C.rendreChantiers(main, {json.dumps(e)});
const apres = parClasse(main, "chantiers")[0];
sortir({{ refait: apres !== avant && main.contains(apres) }});
""")
    assert sortie == {"refait": True}


@sans_node
def test_sur_la_forme_du_noyau_ordre_action_puis_nom():
    depot = {"tag": "v1.0.0", "commits": {}, "prs_ouvertes": 0, "ci": "verte", "topics": [],
             "stories_ouvertes": 0, "sprint_status": "present", "run": "aucun"}
    base = {"categorie": "classé", "pause": None, "depot": depot, "attente": None}
    rendu = noyau_etat.assembler({
        "a1": {**base, "chantier": "alpha"},
        "b1": {**base, "chantier": "beta", "depot": {**depot, "prs_ouvertes": 1}},
        "trouve": {**base, "categorie": "découvert, à classer"},
        "seul": base,
    }, datetime(2026, 11, 6, 12, 0, tzinfo=UTC), UTC)
    sortie = lancer(f"""
C.rendreChantiers(main, {json.dumps(rendu)});
sortir(parClasse(main, "bloc-chantier-titre").map((h) => h.x));
""")
    assert sortie == ["beta", "alpha", "Découverts, à classer", "Hors chantier"]


@sans_node
@pytest.mark.parametrize("hostile", HOSTILES)
def test_nom_hostile_reste_du_texte(hostile):
    c = carte(hostile, chantier=hostile)
    e = vue([c], [chantier(hostile, "constructor", [c])], dependances=[f"{hostile} ← b"])
    sortie = lancer(f"""
C.rendreChantiers(main, {json.dumps(e)});
sortir(plat(main));
""")

    def tous(n):
        yield n
        for f in n["k"]:
            yield from tous(f)

    noeuds = list(tous(sortie))
    for n in noeuds:
        assert all(hostile not in v for v in n["a"].values())
    assert [n["x"] for n in noeuds if hostile in n["x"]] == [hostile, hostile, f"{hostile} ← b"]
    # action inconnue du chantier : pastille neutre, sans libellé
    assert [n["c"] for n in noeuds if "pastille-action" in n["c"]] == [
        "pastille-action pastille-neutre", "pastille-action pastille-rien"]
