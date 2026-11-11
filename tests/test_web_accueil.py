"""Rendu de l'accueil kanban (story 4.5) sous node avec un DOM factice, et règles statiques.

Texte non fiable : un *quoi* hostile reste du texte. Sauté sans `node` (échec si
`PILOTAGE_EXIGER_NODE=1`).
"""

import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime

import pytest

from pilotage import chemins
from pilotage.noyau import etat

WEB = chemins.racine_web()
NODE = shutil.which("node")
if NODE is None and os.environ.get("PILOTAGE_EXIGER_NODE") == "1":
    raise RuntimeError("node absent alors que PILOTAGE_EXIGER_NODE=1")
sans_node = pytest.mark.skipif(NODE is None, reason="node absent")

HOSTILES = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    '"><svg onload=alert(1)>',
    "**gras** [lien](http://x.example)",
]

FAUX_DOM = """
class N {
  constructor(t, ns) { this.t = t; this.ns = ns || null; this.a = {}; this.k = []; this.x = "";
    this.className = ""; }
  setAttribute(n, v) { this.a[n] = String(v); }
  addEventListener(t, f) { (this.ev = this.ev || {})[t] = f; }
  click() { if (this.ev && this.ev.click) { this.ev.click(); } }
  append(...e) { for (const n of e) { this.k.push(n); } }
  removeChild(n) { this.k = this.k.filter((c) => c !== n); }
  insertBefore(n, ref) {
    this.k = this.k.filter((c) => c !== n);
    const i = ref === null ? -1 : this.k.indexOf(ref);
    if (i < 0) { this.k.push(n); } else { this.k.splice(i, 0, n); }
  }
  get childNodes() { return this.k; }
  contains(n) { return n === this || this.k.some((c) => c.contains(n)); }
  querySelector(s) {
    const c = s.slice(1);
    for (const f of this.k) {
      if (f.className.split(" ").includes(c)) { return f; }
      const r = f.querySelector(s);
      if (r) { return r; }
    }
    return null;
  }
  focus() { document.activeElement = this; }
  get firstChild() { return this.k[0] || null; }
  set textContent(v) { this.x = String(v); this.k = []; }
}
globalThis.document = {
  createElement: (t) => new N(t),
  createElementNS: (ns, t) => new N(t, ns),
  getElementById: () => null,
  activeElement: null,
};
const plat = (n) => ({
  t: n.t, c: n.className || n.a.class || "", x: n.x, a: n.a, k: n.k.map(plat),
});
"""


MAINTENANT = "2026-11-06T12:00:00Z"  # horloge figée : aucun test ne dépend du jour


def _rendre(etat, maintenant=MAINTENANT) -> dict:
    url = (WEB / "accueil.js").as_uri()
    script = (
        FAUX_DOM
        + f"const m = await import({json.dumps(url)});"
        + "const r = new N('div');"
        + f"m.rendreAccueil(r, {json.dumps(etat)}, new Date({json.dumps(maintenant)}));"
        + "process.stdout.write(JSON.stringify(plat(r)));"
    )
    sortie = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
        env={**os.environ, "TZ": "UTC"},
    )
    return json.loads(sortie.stdout)


def _tous(n):
    yield n
    for fils in n["k"]:
        yield from _tous(fils)


def _textes(n) -> list[str]:
    return [m["x"] for m in _tous(n) if m["x"]]


def _classe(n, classe):
    return [m for m in _tous(n) if classe in m["c"].split()]


def _carte(nom, action, **plus):
    base = {"nom": nom, "genre": "projet", "action": action, "chantier": None, "quoi": "",
            "type": None, "raison": {"code": "x", "params": {}, "texte": "raison"},
            "phase": [], "categorie": "classé", "clone_ici": True, "pcs": ["pc-a"],
            "depot_de": None, "pc": None, "depuis": None}
    return {**base, **plus}


def _etat(cartes, types=None):
    colonnes = {a: [c for c in cartes if c["action"] == a]
                for a in ("attend-utilisateur", "a-relancer", "tourne", "rien-a-faire")}
    return {"cartes": cartes, "colonnes": colonnes,
            "comptes": {"actions": {a: len(v) for a, v in colonnes.items()},
                        "types": types or {}, "familles": {}, "suivis": len(cartes),
                        "stables": 0}}


@sans_node
def test_chargement():
    racine = _rendre(None)
    textes = _textes(racine)
    assert textes[0] == "Projets" and textes[-1] == "Chargement…"
    assert len(_classe(racine, "reserve-synthese")) == 1
    assert len(_classe(racine, "reserve-barre")) == 1
    assert not _classe(racine, "synthese") and not _classe(racine, "barre-repartition")
    assert [_textes(a)[0] for a in _classe(racine, "aide")] == [
        "Les types d'attente, en clair", "Quand un projet est-il stable ?"]


@sans_node
def test_aucun_projet_quatre_colonnes_vides():
    racine = _rendre(_etat([]))
    assert ("Aucun projet trouvé sous Documents\\GitHub. Lancez un scan avec le bouton Scan de la "
            "barre du haut.") in _textes(racine)
    colonnes = _classe(racine, "colonne")
    assert [_textes(c) for c in colonnes] == [
        ["0", "Vous attend", ", 0 projet", "aucune attente en cours",
         "Personne ne vous attend."],
        ["0", "À relancer", ", 0 projet", "Rien à relancer."],
        ["0", "Tourne", ", 0 projet", "Aucune session active."],
        ["0", "Rien à faire", ", 0 projet", "Aucun projet stable ni en pause."]]
    for c in colonnes:
        (chiffre,) = _classe(c, "chiffre-tuile")
        assert chiffre["a"]["aria-hidden"] == "true" and "chiffre-zero" in chiffre["c"].split()
        assert _classe(c, "icone-action")
    # phrase d'Attend vide masquée (déjà dite par la synthèse et le détail), pas les autres
    assert [_classe(c, "vide")[0]["a"].get("aria-hidden") for c in colonnes] == [
        "true", None, None, None]
    assert not _classe(racine, "compteur-types")
    assert not [m for m in _tous(racine) if m["t"] == "button"]


@sans_node
def test_colonne_attend_compteur_cartes_et_ordre():
    cartes = [
        _carte("zeta", "attend-utilisateur", type="acces", quoi="mot de passe", chantier="ch",
               pc="pc-b", depuis="2026-11-06T09:05:00Z"),
        _carte("alpha", "attend-utilisateur", type="a-qualifier", quoi=""),
        _carte("beta", "attend-utilisateur", type="choix", quoi="A ou B ?"),
        _carte("gamma", "attend-utilisateur", type="choix", quoi="C ?"),
    ]
    racine = _rendre(_etat(cartes, {"a-qualifier": 1, "acces": 1, "choix": 2}))
    colonne = _classe(racine, "colonne-attend-utilisateur")[0]
    assert _textes(colonne)[:4] == [
        "4", "Vous attend", ", 4 projets", "plus ancienne : zeta, 09:05"]
    (titre,) = [m for m in _tous(colonne) if m["t"] == "h2"]
    assert colonne["a"]["aria-labelledby"] == titre["a"]["id"] == "titre-attend-utilisateur"
    assert colonne["k"][0]["c"] == "tuile-colonne"
    assert _classe(colonne, "chiffre-tuile")[0]["c"] == "chiffre-tuile chiffre-attend-utilisateur"
    (compteur,) = _classe(colonne, "compteur-types")
    assert compteur["a"]["aria-label"] == "Attentes par type"
    items = [_textes(li) for li in compteur["k"]]
    assert items == [["choix", " : ", "2"], ["accès", " : ", "1"], ["à qualifier", " : ", "1"]]
    assert sum(int(i[2]) for i in items) == 4
    (liste,) = _classe(colonne, "cartes")
    assert [li["t"] for li in liste["k"]] == ["li"] * 4
    assert all(li["k"][0]["t"] == "article" for li in liste["k"])
    noms = [_textes(h)[1:] for h in _classe(colonne, "carte-nom")]
    assert noms == [["zeta"], ["alpha"], ["beta"], ["gamma"]]  # ordre du serveur
    h3 = _classe(colonne, "carte-nom")[0]
    assert h3["t"] == "h3" and h3["k"][0]["x"] == "Vous attend : "
    assert "masque" in h3["k"][0]["c"]
    bouton = h3["k"][1]
    # le nom ouvre le tiroir (story 4.7) : plus d'aria-disabled
    assert bouton["t"] == "button" and bouton["a"] == {"type": "button"}
    # *quoi* vide : aucun texte de remplacement, aucun paragraphe
    alpha = _classe(colonne, "carte-attend")[1]
    assert not _classe(alpha, "quoi")
    assert _textes(alpha) == ["Vous attend : ", "alpha", "à qualifier", "Reprendre", " alpha"]
    assert [_textes(q) for q in _classe(colonne, "quoi")] == [
        ["mot de passe"], ["A ou B ?"], ["C ?"]]
    zeta = _classe(colonne, "carte-attend")[0]
    assert _textes(_classe(zeta, "meta")[0]) == ["pc-b", " · ", "depuis 09:05"]  # pas `pcs`
    assert not _classe(zeta, "depuis-vieillissante") and not _classe(zeta, "icone-sablier")
    assert "ch" not in _textes(zeta)  # plus d'étiquette de chantier
    # « Reprendre » (5.5) : bouton secondaire seul dans sa place, en dernier dans le DOM de la carte
    for a in _classe(colonne, "carte-attend"):
        place = a["k"][-1]
        assert place["c"] == "carte-reprise" and len(place["k"]) == 1
        reprendre = place["k"][0]
        assert (reprendre["t"], reprendre["c"], reprendre["a"]) == (
            "button", "btn2 reprendre", {"type": "button"})
        assert [(f["c"], f["x"]) for f in reprendre["k"]] == [
            ("masque", f" {_textes(_classe(a, 'nom-projet')[0])[0]}")]
        assert reprendre["x"] == "Reprendre"


@sans_node
@pytest.mark.parametrize("hostile", HOSTILES)
def test_texte_non_fiable_reste_du_texte(hostile):
    cartes = [
        _carte(hostile, "attend-utilisateur", type="choix", quoi=hostile, pc=hostile,
               chantier=hostile, depuis="2026-11-05T22:00:00Z", pcs=[hostile],
               vieillissante=True),
        _carte("r", "a-relancer", raison={"code": "x", "params": {}, "texte": hostile},
               phase=[hostile, {"a": hostile}, 3], chantier=hostile, etiquettes=[hostile],
               pc=hostile, dernier_tour=hostile, famille=hostile),
        _carte("t", "tourne", raison={"code": "tourne", "texte": "t",
                                      "params": {"pc": hostile, "session": "abcd1234",
                                                 "dernier_etat": "06/11 10:00"}}),
        _carte(hostile, "rien-a-faire", raison={"code": "x", "params": {}, "texte": hostile},
               famille=hostile),
    ]
    etat_ = _etat(cartes, {"choix": 1, hostile: 2})
    etat_["comptes"]["familles"] = {hostile: 1, "arretee": 1}
    etat_["comptes"]["pcs_tourne"] = {hostile: 1}
    etat_["fraicheur"] = [{"pc": hostile, "genere_a": hostile}]
    racine = _rendre(etat_)
    noeuds = list(_tous(racine))
    assert {n["t"] for n in noeuds} <= {
        "div", "h2", "h3", "section", "ul", "li", "article", "p", "span", "button", "svg",
        "path", "details", "summary", "ol"}
    for n in noeuds:
        assert all(not nom.startswith("on") for nom in n["a"])
        assert all(hostile not in v for v in n["a"].values())
        assert "href" not in n["a"] and "src" not in n["a"]
    # nom + quoi + PC (Attend) + détail de sa tuile, raison + PC (Relancer), PC (Tourne) + détail
    # de sa tuile, nom + motif (Rien), nom dans la phrase-synthèse (story 4.10) ; chantier, phase,
    # famille et compte inconnus ne s'affichent pas ; nom masqué de « Reprendre » (Attend, 5.5)
    assert sum(hostile in n["x"] for n in noeuds) == 12
    assert f"plus ancienne : {hostile}, hier 22:00" in _textes(racine)
    assert f"1 sur {hostile}" in _textes(racine)
    assert "1 arrêtée" in _textes(racine)  # famille hostile ignorée
    assert "depuis hier 22:00" in _textes(racine)  # fraîcheur illisible : sans nouvelles
    assert not _classe(racine, "icone-motif")
    assert all(n["x"] != "[object Object]" and n["x"] != "3" for n in noeuds)  # phase non chaîne


@sans_node
def test_relancer_tourne_rien_et_etiquettes():
    cartes = [
        _carte("rel", "a-relancer", raison={"code": "x", "params": {}, "texte": "run bloqué"},
               chantier="ch", phase=["status-dev"], clone_ici=False, pc="pc-c",
               dernier_tour="2026-11-05T22:47:00Z", categorie="découvert, à classer",
               message_en_attente=True),
        _carte("tou", "tourne", raison={"code": "tourne", "texte": "t",
                                        "params": {"pc": "pc-b", "session": "abcd1234",
                                                   "dernier_etat": "06/11 10:00"}}),
        _carte("rie", "rien-a-faire",
               raison={"code": "a-classer", "params": {}, "texte": "à classer"},
               categorie="découvert, à classer"),
    ]
    racine = _rendre(_etat(cartes))
    (rel,) = _classe(racine, "carte-relancer")
    # nom, raison, méta « PC · dernier tour » de la carte ; étiquettes sans chantier ni phase
    assert _textes(rel) == ["À relancer : ", "rel", "run bloqué", "pc-c", " · ",
                            "dernier tour hier 22:47", "message en attente", "pas cloné ici",
                            "à classer", "Reprendre", " rel"]
    assert rel["k"][-1]["c"] == "carte-reprise"
    assert _classe(rel["k"][-1], "reprendre")[0]["t"] == "button"
    tou = _classe(racine, "colonne-tourne")[0]
    assert _textes(_classe(tou, "carte-nom")[0]) == ["Tourne : ", "tou"]
    assert "pc-b · abcd1234 · 06/11 10:00" in _textes(tou)
    assert not _classe(tou, "carte-reprise") and not _classe(tou, "reprendre")
    rie = _classe(racine, "colonne-rien-a-faire")[0]
    (ligne,) = _classe(rie, "ligne-rien")
    # « à classer » une seule fois
    assert _textes(ligne) == ["Rien à faire : ", "rie", "à classer"]
    # un bouton de nom par carte et ligne, sans aria-disabled, plus « Afficher » de Rien à faire
    boutons = [m for m in _tous(racine) if m["t"] == "button"]
    assert [_textes(b) for b in boutons] == [["rel"], ["Reprendre", " rel"], ["tou"], ["Afficher"],
                                             ["rie"]]
    assert not _classe(rie, "reprendre")
    assert all("aria-disabled" not in b["a"] for b in boutons)


@sans_node
def test_depuis_hier_et_autre_jour():
    carte = _carte("p", "attend-utilisateur", type="choix", quoi="q", pc="pc-a",
                   depuis="2026-11-06T09:05:00Z")
    meta = lambda maintenant: _textes(_classe(_rendre(_etat([carte]), maintenant), "meta")[0])  # noqa: E731
    assert meta("2026-11-07T08:00:00Z") == ["pc-a", " · ", "depuis hier 09:05"]
    assert meta("2026-11-09T08:00:00Z") == ["pc-a", " · ", "depuis le 06/11"]


def _regles(css: str) -> dict[str, str]:
    """{sélecteur : corps} des règles de premier niveau (sélecteurs groupés éclatés)."""
    regles: dict[str, str] = {}
    for selecteurs, corps in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for selecteur in selecteurs.split(","):
            regles[selecteur.strip()] = regles.get(selecteur.strip(), "") + corps
    return regles


def test_aucune_troncature_css_ni_js():
    css = (WEB / "appli.css").read_text(encoding="utf-8")
    assert not re.search(r"text-overflow|line-clamp", css)
    regles = _regles(css)
    for selecteur in (".quoi", ".raison", ".meta", ".carte-nom", ".nom-projet", ".etiquette",
                      ".carte", ".ligne-rien", ".tuile-detail", ".colonne-titre"):
        assert re.search(r"overflow-wrap:\s*anywhere", regles.get(selecteur, "")), selecteur
    # Seule exception nommée : app.js lit le fragment de l'URL (`#…`), pas une donnée affichée.
    # Story 5.5 : le brief (texte brut, déjà borné par le serveur) est borné à l'affichage.
    exceptions = {"app.js": ["window.location.hash.slice(1)"],
                  "reprise.js": ["brut.slice(0, fin)"]}
    for module in WEB.glob("*.js"):
        source = module.read_text(encoding="utf-8")
        for permis in exceptions.get(module.name, []):
            assert permis in source, (module.name, permis)
            source = source.replace(permis, "")
        assert not re.search(r"\.(?:substr|substring|slice)\s*\(", source), module.name


def test_css_sans_couleur_en_dur_ni_emoji():
    for feuille in WEB.glob("*.css"):
        if feuille.name.startswith("charte") or feuille.name == "polices.css":
            continue
        source = feuille.read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", source), feuille.name
    for module in WEB.glob("*.js"):
        source = module.read_text(encoding="utf-8")
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", source), module.name


@sans_node
def test_accueil_sur_la_forme_du_noyau_une_carte_par_projet_de_chantier():
    # forme réelle de `noyau.etat.assembler` (story 4.8) : aucune carte de chantier en colonne
    maintenant = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
    depot = {"tag": "v1.0.0", "commits": {}, "prs_ouvertes": 0, "ci": "verte", "topics": [],
             "stories_ouvertes": 0, "sprint_status": "present", "run": "aucun"}
    base = {"categorie": "classé", "pause": None, "depot": depot, "attente": None,
            "sessions": []}
    attente = {"origine": "marqueur", "type": "test", "quoi": "q", "pc": "pc-a",
               "depuis": "2026-11-06T09:05:00Z"}
    etat_ = etat.assembler({
        "zeta-api": {**base, "chantier": "Zeta", "attente": attente},
        "zeta-web": {**base, "chantier": "Zeta"},
        "seul": base,
    }, maintenant, UTC)
    assert all(c["genre"] == "projet" for v in etat_["colonnes"].values() for c in v)
    assert [c["nom"] for c in etat_["chantiers"]] == ["Zeta"]
    racine = _rendre(json.loads(json.dumps(etat_)))
    noms = ["".join(_textes(n)) for n in _classe(racine, "carte-nom")]
    assert sorted(n.rsplit(" : ", 1)[-1] for n in noms) == ["seul", "zeta-api", "zeta-web"]
    attend = _classe(racine, "colonne-attend-utilisateur")[0]
    assert [_textes(m) for m in _classe(attend, "meta")] == [["pc-a", " · ", "depuis 09:05"]]
    assert "Zeta" not in _textes(racine)  # plus d'étiquette de chantier sur les cartes
    rien = _classe(racine, "colonne-rien-a-faire")[0]
    assert _textes(_classe(rien, "tuile-detail")[0]) == ["2 stables"]
    assert len(_classe(rien, "icone-motif-stable")) == 2


# --- Story 4.6 : relecture sur place, focus, annonce ---------------------------------------

SUITE = """
const m = await import(%s);
const tous = (n) => [n, ...n.k.flatMap(tous)];
const parClasse = (n, c) => tous(n).filter((x) => x.className.split(" ").includes(c));
const annonces = [];
const region = { set textContent(v) { if (v) { annonces.push(v); } } };
globalThis.window = { setTimeout: (f) => f() };
document.getElementById = (id) => (id === "annonce" ? region : null);
const r = new N("div");
const rendre = (e, o) => m.rendreAccueil(r, e, new Date(%s), o);
const auto = { annoncer: true };
const nomDe = (h) => tous(h).map((x) => x.x).join("");
const li = (nom) => {
  const h = parClasse(r, "carte-nom").find((x) => nomDe(x).endsWith(nom));
  return tous(r).find((x) => x.t === "li" && x.contains(h));
};
const bouton = (nom) => parClasse(li(nom), "nom-projet")[0];
%s
"""


def _suite(corps: str):
    url = (WEB / "accueil.js").as_uri()
    script = FAUX_DOM + SUITE % (json.dumps(url), json.dumps(MAINTENANT), corps)
    sortie = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
        env={**os.environ, "TZ": "UTC"},
    )
    return json.loads(sortie.stdout)


def _js(etat) -> str:
    return json.dumps(etat)


@sans_node
def test_relecture_garde_les_noeuds_inchanges_et_remplace_le_modifie():
    a = _carte("Alpha", "attend-utilisateur", type="test", quoi="q1", pc="pc-a")
    b = _carte("Beta", "attend-utilisateur", type="choix", quoi="q2", pc="pc-a")
    c = _carte("Gamma", "a-relancer")
    types = {"test": 1, "choix": 1}
    sortie = _suite(
        f"rendre({_js(_etat([a, b, c], types))});"
        "const avant = { a: li('Alpha'), b: li('Beta'), c: li('Gamma') };"
        f"rendre({_js(_etat([a, {**b, 'quoi': 'q2 modifié'}, c], types))});"
        "process.stdout.write(JSON.stringify({"
        "  a: li('Alpha') === avant.a, c: li('Gamma') === avant.c, b: li('Beta') === avant.b,"
        "  quoi: parClasse(li('Beta'), 'quoi')[0].x, annonces }));"
    )
    assert sortie == {"a": True, "c": True, "b": False, "quoi": "q2 modifié", "annonces": []}


@sans_node
def test_focus_suit_la_carte_et_retombe_sur_le_titre_de_colonne():
    a = _carte("Alpha", "attend-utilisateur", type="test", quoi="q1")
    b = _carte("Beta", "attend-utilisateur", type="choix", quoi="q2")
    types = {"test": 1, "choix": 1}
    sortie = _suite(
        f"rendre({_js(_etat([a, b], types))});"
        "bouton('Beta').focus();"
        "const noeud = li('Beta');"
        # Beta change de texte : nœud remplacé, le focus passe au bouton du nouveau nœud.
        f"rendre({_js(_etat([a, {**b, 'quoi': 'autre'}], types))});"
        "const suit = document.activeElement === bouton('Beta') && li('Beta') !== noeud;"
        # Beta passe dans Tourne : le focus suit son bouton dans sa nouvelle colonne (4.7).
        f"rendre({_js(_etat([a, {**b, 'action': 'tourne'}], {'test': 1}))});"
        "const titre = document.activeElement === bouton('Beta')"
        "  && parClasse(r, 'colonne-tourne')[0].contains(document.activeElement);"
        # Alpha disparaît à son tour : focus sur le titre de sa colonne.
        "bouton('Alpha').focus();"
        f"rendre({_js(_etat([], {}))});"
        "process.stdout.write(JSON.stringify({ suit, titre, fin: document.activeElement.a.id }));"
    )
    assert sortie == {"suit": True, "titre": True, "fin": "titre-attend-utilisateur"}




def test_css_grille_responsive_et_mouvement_reduit():
    css = (WEB / "appli.css").read_text(encoding="utf-8")
    assert re.search(r"@media \(min-width: 47\.5em\)\s*\{\s*\.kanban\s*\{[^}]*repeat\(2,", css)
    assert re.search(
        r"@media \(min-width: 80em\)\s*\{\s*\.kanban\s*\{[^}]*minmax\(0, 4fr\)\s*minmax\(0, 3fr\)"
        r"\s*minmax\(0, 2fr\)\s*minmax\(0, 2fr\)", css)
    assert re.search(r"\.kanban\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\);", css)
    reduit = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", css, re.S)
    assert reduit and "transition: none" in reduit.group(1)
    assert "animation: none" in reduit.group(1)
    # Défilement : jamais horizontal (`overflow`, `overflow-x`, `overflow-inline`) ; vertical
    # (`overflow-y`, `overflow-block`) seulement par exception nommée : le tiroir (4.7) et le
    # brief de reprise (5.5, texte brut en pre-wrap, borné en hauteur).
    defilement_vertical = {"appli.css": {"dialog.tiroir", "pre.brief"}}
    vus = set()
    for feuille in WEB.glob("*.css"):
        source = re.sub(r"/\*.*?\*/", "", feuille.read_text(encoding="utf-8"), flags=re.S)
        permis = defilement_vertical.get(feuille.name, set())
        for selecteurs, corps in re.findall(r"([^{}]+)\{([^{}]*)\}", source):
            for axe, valeur in re.findall(r"(?<![\w-])overflow(-[a-z]+)?\s*:\s*([^;]*)", corps):
                if not re.search(r"\b(scroll|auto)\b", valeur):
                    continue
                selecteur = " ".join(selecteurs.split())
                assert axe in ("-y", "-block") and selecteur in permis, (feuille.name, selecteur)
                vus.add(selecteur)
    assert vus == {"dialog.tiroir", "pre.brief"}


@sans_node
def test_focus_sur_le_titre_de_colonne_survit_au_changement_de_compte():
    a = _carte("Alpha", "attend-utilisateur", type="test", quoi="q1")
    b = _carte("Beta", "attend-utilisateur", type="choix", quoi="q2")
    sortie = _suite(
        f"rendre({_js(_etat([a], {'test': 1}))});"
        "const h2 = parClasse(r, 'colonne-titre')[0];"
        "h2.focus();"
        f"rendre({_js(_etat([a, b], {'test': 1, 'choix': 1}))});"
        "const titre = parClasse(r, 'colonne-titre')[0];"
        "process.stdout.write(JSON.stringify({ meme: titre === h2,"
        "  focus: document.activeElement === h2, dedans: r.contains(h2),"
        "  textes: tous(titre).map((x) => x.x).filter(Boolean) }));"
    )
    assert sortie == {"meme": True, "focus": True, "dedans": True,
                      "textes": ["Vous attend", ", 2 projets"]}


@sans_node
def test_focus_hors_accueil_jamais_deplace_et_resume_du_repli_rattrape():
    a = _carte("Alpha", "attend-utilisateur", type="test", quoi="q1")
    r1 = _carte("R1", "rien-a-faire")
    sortie = _suite(
        "const dehors = new N('input'); dehors.focus();"
        f"rendre({_js(_etat([a, r1], {'test': 1}))});"
        f"rendre({_js(_etat([r1], {}))});"  # Alpha disparaît : le focus reste dehors
        "const reste = document.activeElement === dehors;"
        "parClasse(r, 'repli-bouton')[0].focus();"
        f"rendre({_js(_etat([], {}))});"  # le bouton disparaît : le titre de la colonne
        "process.stdout.write(JSON.stringify({ reste, fin: document.activeElement.a.id }));"
    )
    assert sortie == {"reste": True, "fin": "titre-rien-a-faire"}


@sans_node
def test_aucun_projet_puis_projets_en_place():
    a = _carte("Alpha", "a-relancer")
    sortie = _suite(
        f"rendre({_js(_etat([]))});"
        "const avant = parClasse(r, 'aucun-projet').length;"
        "const grille = parClasse(r, 'kanban')[0];"
        f"rendre({_js(_etat([a]))});"
        "process.stdout.write(JSON.stringify({ avant, apres: parClasse(r, 'aucun-projet').length,"
        "  grille: parClasse(r, 'kanban')[0] === grille,"
        "  colonnes: parClasse(r, 'colonne').length }));"
    )
    assert sortie == {"avant": 1, "apres": 0, "grille": True, "colonnes": 4}


# --- Story 4.11 : colonnes « Coup d'œil » ---------------------------------------------------

def _tuile(racine, action):
    colonne = _classe(racine, f"colonne-{action}")[0]
    (chiffre,) = _classe(colonne, "chiffre-tuile")
    (h2,) = [m for m in _tous(colonne) if m["t"] == "h2"]
    detail = _classe(colonne, "tuile-detail")
    return {"chiffre": chiffre["x"], "zero": "chiffre-zero" in chiffre["c"].split(),
            "cache": chiffre["a"].get("aria-hidden"), "h2": "".join(_textes(h2)),
            "detail": detail[0]["x"] if detail else None}


@sans_node
def test_tuiles_un_et_plusieurs_projets_et_details_par_colonne():
    cartes = [
        _carte("projet-a", "attend-utilisateur", type="choix", quoi="q",
               depuis="2026-11-05T22:47:00Z"),
        _carte("projet-b", "attend-utilisateur", type="test", quoi="q",
               depuis="2026-11-06T09:00:00Z"),
        _carte("a", "a-relancer"), _carte("b", "a-relancer"), _carte("c", "a-relancer"),
        _carte("t", "tourne"),
        _carte("s1", "rien-a-faire"), _carte("s2", "rien-a-faire"), _carte("p", "rien-a-faire"),
    ]
    etat_ = _etat(cartes, {"choix": 1, "test": 1})
    # ordre reçu volontairement mélangé : l'ordre affiché est l'ordre fixe des familles
    etat_["comptes"]["familles"] = {"a-stabiliser": 1, "pause": 1, "arretee": 2,
                                    "sans-nouvelles": 0, "stable": 2, "run-bloque": 1}
    etat_["comptes"]["pcs_tourne"] = {"pc-bureau": 1, "pc-portable": 2}
    racine = _rendre(etat_)
    assert _tuile(racine, "attend-utilisateur") == {
        "chiffre": "2", "zero": False, "cache": "true", "h2": "Vous attend, 2 projets",
        "detail": "plus ancienne : projet-a, hier 22:47"}
    assert _tuile(racine, "a-relancer") == {
        "chiffre": "3", "zero": False, "cache": "true", "h2": "À relancer, 3 projets",
        "detail": "2 arrêtées · 1 run bloqué · 1 à stabiliser"}
    assert _tuile(racine, "tourne") == {
        "chiffre": "1", "zero": False, "cache": "true", "h2": "Tourne, 1 projet",
        "detail": "1 sur pc-bureau · 2 sur pc-portable"}
    assert _tuile(racine, "rien-a-faire") == {
        "chiffre": "3", "zero": False, "cache": "true", "h2": "Rien à faire, 3 projets",
        "detail": "2 stables · 1 en pause"}
    # compteur par type sous la tuile d'Attend seulement
    attend = _classe(racine, "colonne-attend-utilisateur")[0]
    assert [k["c"] for k in attend["k"][:2]] == ["tuile-colonne", "compteur-types"]
    assert len(_classe(racine, "compteur-types")) == 1


FAMILLES = ("arretee", "sans-nouvelles", "run-bloque", "sans-session", "pause-a-revoir",
            "non-relu", "a-stabiliser", "stable", "pause", "a-classer")


@sans_node
def test_accords_des_familles_au_singulier_et_au_pluriel():
    cartes = [_carte(n, "a-relancer") for n in "abcdefg"] + [
        _carte("s", "rien-a-faire"), _carte("p", "rien-a-faire"), _carte("c", "rien-a-faire")]
    etat_ = _etat(cartes)
    etat_["comptes"]["familles"] = dict.fromkeys(FAMILLES, 1)
    racine = _rendre(etat_)
    assert _tuile(racine, "a-relancer")["detail"] == (
        "1 arrêtée · 1 sans nouvelles · 1 run bloqué · 1 sans session · 1 pause à revoir · "
        "1 non relu · 1 à stabiliser")
    assert _tuile(racine, "rien-a-faire")["detail"] == "1 stable · 1 en pause · 1 à classer"
    etat_["comptes"]["familles"] = dict.fromkeys(FAMILLES, 2)
    racine = _rendre(etat_)
    assert _tuile(racine, "a-relancer")["detail"] == (
        "2 arrêtées · 2 sans nouvelles · 2 runs bloqués · 2 sans session · 2 pauses à revoir · "
        "2 non relus · 2 à stabiliser")
    assert _tuile(racine, "rien-a-faire")["detail"] == "2 stables · 2 en pause · 2 à classer"


@sans_node
def test_colonnes_vides_sans_ligne_de_detail_sauf_attend():
    racine = _rendre(_etat([_carte("x", "attend-utilisateur", quoi="q")]))
    assert _tuile(racine, "attend-utilisateur")["detail"] == "plus ancienne : x"  # sans heure
    for action, titre in (("a-relancer", "À relancer"), ("tourne", "Tourne"),
                          ("rien-a-faire", "Rien à faire")):
        assert _tuile(racine, action) == {"chiffre": "0", "zero": True, "cache": "true",
                                          "h2": f"{titre}, 0 projet", "detail": None}


@sans_node
@pytest.mark.parametrize(("maintenant", "fraicheur", "attendu"), [
    ("2026-11-06T08:46:00Z", "2026-11-06T08:40:00Z", "depuis plus de 9 h"),
    ("2026-11-06T22:47:00Z", "2026-11-06T22:40:00Z", "depuis plus de 24 h"),
    ("2026-11-06T22:48:00Z", "2026-11-06T22:40:00Z", "depuis hier 22:47"),
    ("2026-11-08T08:00:00Z", "2026-11-08T07:59:00Z", "depuis le 05/11"),
    # PC sans nouvelles (dernier instantané il y a plus de 45 min) : l'heure de début seule
    ("2026-11-06T08:46:00Z", "2026-11-06T07:00:00Z", "depuis hier 22:47"),
])
def test_attente_vieillissante_sablier_et_formes(maintenant, fraicheur, attendu):
    carte = _carte("projet-a", "attend-utilisateur", type="choix", quoi="q", pc="pc-a",
                   depuis="2026-11-05T22:47:00Z", vieillissante=True)
    etat_ = _etat([carte], {"choix": 1})
    etat_["fraicheur"] = [{"pc": "pc-b", "genere_a": "2026-11-01T00:00:00Z"},
                          {"pc": "pc-a", "genere_a": fraicheur}]
    racine = _rendre(etat_, maintenant)
    (meta,) = _classe(racine, "meta")
    assert _textes(meta) == ["pc-a", " · ", attendu]
    (partie,) = _classe(meta, "depuis-vieillissante")
    assert partie["k"][0]["c"] == "icone-sablier"
    assert partie["k"][0]["t"] == "svg" and partie["k"][0]["a"]["aria-hidden"] == "true"


@sans_node
def test_attente_non_vieillissante_sans_sablier():
    carte = _carte("projet-a", "attend-utilisateur", quoi="q", pc="pc-a",
                   depuis="2026-11-06T09:05:00Z")
    racine = _rendre(_etat([carte]))
    assert not _classe(racine, "depuis-vieillissante") and not _classe(racine, "icone-sablier")
    assert _textes(_classe(racine, "meta")[0]) == ["pc-a", " · ", "depuis 09:05"]


@sans_node
def test_rien_a_faire_icone_et_motif():
    cartes = [
        _carte("p", "rien-a-faire", famille="pause",
               raison={"code": "pause", "params": {}, "texte": "pause jusqu'au 12/11"}),
        _carte("s", "rien-a-faire", famille="stable",
               raison={"code": "stable", "params": {}, "texte": "stable"}),
        _carte("c", "rien-a-faire", famille="a-classer", categorie="découvert, à classer",
               raison={"code": "a-classer", "params": {}, "texte": "à classer"}),
    ]
    racine = _rendre(_etat(cartes))
    lignes = _classe(racine, "ligne-rien")
    assert [_textes(li)[1:] for li in lignes] == [["p", "pause jusqu'au 12/11"],
                                                  ["s", "stable"], ["c", "à classer"]]
    assert [[i["c"] for i in _classe(li, "icone-motif")] for li in lignes] == [
        ["icone-motif icone-motif-pause"], ["icone-motif icone-motif-stable"],
        ["icone-motif icone-motif-a-classer"]]
    assert all(i["a"]["aria-hidden"] == "true" for i in _classe(racine, "icone-motif"))


@sans_node
@pytest.mark.parametrize("famille", ["constructor", "__proto__", "toString", "hasOwnProperty"])
def test_rien_a_faire_famille_hors_liste_sans_icone(famille):
    racine = _rendre(_etat([_carte("p", "rien-a-faire", famille=famille)]))
    (ligne,) = _classe(racine, "ligne-rien")
    assert _textes(ligne) == ["Rien à faire : ", "p", "raison"]
    assert not [n for n in _tous(ligne) if n["t"] == "svg" or "icone-motif" in n["c"]]


@sans_node
def test_rien_a_faire_ordre_conserve_et_noeuds_gardes():
    r1 = _carte("R1", "rien-a-faire")
    r2 = _carte("R2", "rien-a-faire")
    sortie = _suite(
        f"rendre({_js(_etat([r1, r2]))});"
        "const avant = { a: li('R1'), b: li('R2') };"
        f"rendre({_js(_etat([r2, r1]))});"
        "const liste = parClasse(r, 'cartes-rien-a-faire')[0];"
        "process.stdout.write(JSON.stringify({ ordre: parClasse(liste, 'carte-nom').map(nomDe),"
        "  gardes: li('R1') === avant.a && li('R2') === avant.b }));"
    )
    assert sortie == {"ordre": ["Rien à faire : R2", "Rien à faire : R1"], "gardes": True}


@sans_node
def test_focus_apres_sortie_d_une_carte_relancer():
    a = _carte("Alpha", "attend-utilisateur", type="test", quoi="q1")
    g = _carte("Gamma", "a-relancer")
    d = _carte("Delta", "a-relancer")
    sortie = _suite(
        f"rendre({_js(_etat([a, g, d], {'test': 1}))});"
        # Alpha passe dans À relancer : le focus suit son bouton dans sa nouvelle colonne.
        "bouton('Alpha').focus();"
        f"rendre({_js(_etat([{**a, 'action': 'a-relancer'}, g, d]))});"
        "const suit = document.activeElement === bouton('Alpha')"
        "  && parClasse(r, 'colonne-a-relancer')[0].contains(document.activeElement);"
        # Gamma quitte À relancer : le titre de la colonne reprend le focus.
        "bouton('Gamma').focus();"
        f"rendre({_js(_etat([{**a, 'action': 'a-relancer'}, d]))});"
        "process.stdout.write(JSON.stringify({ suit, fin: document.activeElement.a.id }));"
    )
    assert sortie == {"suit": True, "fin": "titre-a-relancer"}


@sans_node
def test_repli_afficher_attributs_et_etat_conserve():
    r1 = _carte("R1", "rien-a-faire")
    sortie = _suite(
        f"rendre({_js(_etat([r1]))});"
        "const b = parClasse(r, 'repli-bouton')[0];"
        "const col = parClasse(r, 'colonne-rien-a-faire')[0];"
        "const liste = parClasse(col, 'cartes')[0];"
        "const avant = { ...b.a, texte: b.x, ordre: col.k.map((k) => k.className),"
        "  t: b.t, id: liste.a.id };"
        "b.click();"
        "const ouvert = b.a['aria-expanded'];"
        f"rendre({_js(_etat([r1]))});"  # relecture : l'état reste
        "const apresRelecture = parClasse(r, 'repli-bouton')[0].a['aria-expanded'];"
        "r.k = [];"  # retour depuis Chantiers : contexte recréé, état conservé
        f"rendre({_js(_etat([r1]))});"
        "const b2 = parClasse(r, 'repli-bouton')[0];"
        "const apresRetour = { meme: b2 === b, etat: b2.a['aria-expanded'] };"
        "b2.click();"
        "process.stdout.write(JSON.stringify({ avant, ouvert, apresRelecture, apresRetour,"
        "  referme: b2.a['aria-expanded'] }));"
    )
    assert sortie["avant"] == {
        "type": "button", "aria-label": "Afficher la liste de Rien à faire",
        "aria-controls": "liste-rien-a-faire", "aria-expanded": "false", "texte": "Afficher",
        "ordre": ["tuile-colonne", "btn2 repli-bouton", "cartes cartes-rien-a-faire"],
        "t": "button", "id": "liste-rien-a-faire"}
    assert sortie["ouvert"] == "true" and sortie["apresRelecture"] == "true"
    assert sortie["apresRetour"] == {"meme": False, "etat": "true"}
    assert sortie["referme"] == "false"


def test_css_repli_survol_et_tuiles():
    css = (WEB / "appli.css").read_text(encoding="utf-8")
    # Masquage de la liste borné sous 760 px par sa règle même (pas par l'ordre des règles) ;
    # au-delà, le bouton disparaît et aucune règle ne masque la liste.
    sans_commentaires = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    masques = re.findall(r"(@media [^{]*\{)?\s*\.repli-bouton\[aria-expanded=\"false\"\] "
                         r"\+ \.cartes\s*\{\s*display: none;", sans_commentaires)
    assert masques == ["@media not all and (min-width: 47.5em) {"]
    assert re.search(r"@media \(min-width: 47\.5em\)\s*\{\s*\.repli-bouton\s*\{\s*display: none;",
                     css)
    regles = _regles(re.sub(r"/\*.*?\*/", "", css, flags=re.S))
    for carte in (".carte-attend", ".carte-relancer", ".carte-tourne"):
        assert "var(--halo)" in regles[f"{carte}:hover"]
        assert "var(--halo)" in regles[f"{carte}:focus-within"]
        assert "inset-block-end: -3px" in regles[f"{carte}::after"]
    debut = css.index(".carte-tourne::after")
    mouvement = re.search(r"@media \(prefers-reduced-motion: no-preference\)\s*\{(.*?)\n\}",
                          css[debut:], re.S).group(1)
    assert "transition: box-shadow 200ms, transform 200ms" in mouvement
    assert "transform: translateY(-2px)" in mouvement
    # hors préférence « pas de réduction », ni soulèvement : sous mouvement réduit, le halo seul
    assert "translateY" not in css.replace(mouvement, "")
    assert "var(--halo)" not in regles.get(".ligne-rien", "") + regles.get(".tuile-colonne", "")
    assert "var(--accent-texte)" in regles[".depuis-vieillissante"]
    assert "font-weight: 700" in regles[".depuis-vieillissante"]
    assert "var(--texte-attenue)" in regles[".chiffre-tuile.chiffre-zero"]
    for action, role in (("attend-utilisateur", "accent-texte"), ("a-relancer", "alerte-texte"),
                         ("tourne", "succes"), ("rien-a-faire", "texte")):
        assert f"var(--{role})" in regles[f".chiffre-{action}"]


def _hausse(avant, noms):
    url = (WEB / "accueil.js").as_uri()
    script = (FAUX_DOM + f"const m = await import({json.dumps(url)});"
              f"process.stdout.write(JSON.stringify(m.texteHausse({json.dumps(avant)}, "
              f"{json.dumps(noms)})));")
    sortie = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True,
                            text=True, encoding="utf-8", timeout=30, check=True)
    return json.loads(sortie.stdout)


@sans_node
@pytest.mark.parametrize(("avant", "noms", "attendu"), [
    (None, ["projet-a"], None),  # premier chargement
    (["projet-a"], ["projet-a"], None),  # identique
    (["projet-a", "projet-b"], ["projet-b"], None),  # baisse
    (["projet-a"], ["projet-a", "projet-b"], "Nouvelle attente : projet-b"),
    (["projet-b"], ["projet-b", "projet-a", "claude-config"],
     "Nouvelles attentes : projet-a, claude-config"),
    # un départ et deux arrivées : hausse de 1, les deux arrivées sont nommées
    (["projet-a"], ["projet-b", "claude-config"], "Nouvelles attentes : projet-b, claude-config"),
    ([], [], None),
    ("x", ["a"], None),  # forme inattendue : rien
])
def test_texte_hausse(avant, noms, attendu):
    assert _hausse(avant, noms) == attendu


@sans_node
@pytest.mark.parametrize("hostile", HOSTILES)
def test_texte_hausse_d_un_nom_hostile_reste_du_texte(hostile):
    assert _hausse([], [hostile]) == f"Nouvelle attente : {hostile}"


@sans_node
def test_rendre_accueil_n_annonce_plus_rien():
    a = _carte("projet-a", "attend-utilisateur", quoi="q")
    b = _carte("projet-b", "attend-utilisateur", quoi="q")
    sortie = _suite(
        f"rendre({_js(_etat([a]))}, auto);"
        f"rendre({_js(_etat([a, b]))}, auto);"
        "process.stdout.write(JSON.stringify(annonces));"
    )
    assert sortie == []


def _lecture(contexte):
    url = (WEB / "accueil.js").as_uri()
    script = (FAUX_DOM + f"const m = await import({json.dumps(url)});"
              f"process.stdout.write(JSON.stringify(m.lectureAutomatique({json.dumps(contexte)})));")
    sortie = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True,
                            text=True, encoding="utf-8", timeout=30, check=True)
    return json.loads(sortie.stdout)


@sans_node
@pytest.mark.parametrize(("contexte", "attendu"), [
    ({"premiere": False, "actionUtilisateur": False, "cycle": None}, True),  # relecture des 30 s
    # synchro planifiée
    ({"premiere": False, "actionUtilisateur": False, "cycle": "observe"}, True),
    ({"premiere": True, "actionUtilisateur": False, "cycle": None}, False),  # premier chargement
    ({"premiere": False, "actionUtilisateur": True, "cycle": None}, False),  # Actualiser, F5
    # Scan ou Sync lancé
    ({"premiere": False, "actionUtilisateur": False, "cycle": "lance"}, False),
    ({"premiere": False, "actionUtilisateur": False, "cycle": "deja"}, False),  # 409 après un clic
])
def test_lecture_automatique(contexte, attendu):
    assert _lecture(contexte) is attendu


def test_app_ne_demande_l_annonce_que_hors_action_utilisateur():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert re.search(r"const automatique = lectureAutomatique\(\{\s*premiere: premiereLecture,"
                     r" actionUtilisateur: annoncerLecture \|\| lancement,"
                     r"\s*cycle: suivi \? suivi\.motif"
                     r" : null,", app)
    assert app.index("const automatique") < app.index("suivreCycle(donnees.cycle)")
    assert "vue(contenu, etat, new Date())" in app


def test_attente_sans_description_retiree():
    for module in WEB.glob("*.js"):
        source = module.read_text(encoding="utf-8")
        assert "ATTENTE_SANS_DESCRIPTION" not in source, module.name
        assert "Attente sans description" not in source, module.name


# --- Story 7.2 : titre « Attend <nom> », nom affiché venu de /api/etat ------------------------


@sans_node
def test_titre_attend_avec_nom_configure():
    etat_ = _etat([_carte("projet-a", "attend-utilisateur", type="choix", quoi="q")], {"choix": 1})
    etat_["utilisateur"] = "Camille"
    racine = _rendre(etat_)
    assert _tuile(racine, "attend-utilisateur")["h2"] == "Attend Camille, 1 projet"
    (h3,) = _classe(racine, "carte-nom")
    assert _textes(h3) == ["Attend Camille : ", "projet-a"]
    assert "Vous attend" not in _textes(racine)
    # la synthèse garde « vous attend », la phrase vide aussi (texte adressé à la personne)
    assert "projet-a" in _textes(_classe(racine, "synthese")[0])


@sans_node
@pytest.mark.parametrize("valeur", [None, "", "   ", 42, ["Camille"]])
def test_titre_attend_sans_nom_vous_attend(valeur):
    etat_ = _etat([])
    if valeur is not None:
        etat_["utilisateur"] = valeur
    racine = _rendre(etat_)
    colonne = _classe(racine, "colonne-attend-utilisateur")[0]
    assert _textes(colonne) == ["0", "Vous attend", ", 0 projet", "aucune attente en cours",
                                "Personne ne vous attend."]


@sans_node
@pytest.mark.parametrize("hostile", HOSTILES)
def test_nom_affiche_hostile_reste_du_texte(hostile):
    etat_ = _etat([_carte("p", "attend-utilisateur", quoi="q")])
    etat_["utilisateur"] = hostile
    noeuds = list(_tous(_rendre(etat_)))
    for n in noeuds:
        assert all(hostile not in v for v in n["a"].values())
    assert {n["t"] for n in noeuds} <= {
        "div", "h2", "h3", "section", "ul", "li", "article", "p", "span", "button", "svg",
        "path", "details", "summary", "ol"}
    # légende de la barre, titre de colonne, préfixe masqué de la carte
    assert [n["x"] for n in noeuds if hostile in n["x"]] == [
        f"Attend {hostile}", f"Attend {hostile}", f"Attend {hostile} : "]


@sans_node
def test_changement_de_nom_reecrit_titre_et_cartes_sans_perdre_le_titre():
    a = _carte("Alpha", "attend-utilisateur", type="test", quoi="q1")
    avant = _etat([a], {"test": 1})
    apres = {**_etat([a], {"test": 1}), "utilisateur": "Camille"}
    sortie = _suite(
        f"rendre({_js(avant)});"
        "const h2 = parClasse(r, 'colonne-titre')[0]; const noeud = li('Alpha');"
        "const t1 = nomDe(h2);"
        f"rendre({_js(apres)});"
        "const t2 = nomDe(h2);"
        "process.stdout.write(JSON.stringify({ t1, t2, meme: parClasse(r, 'colonne-titre')[0]"
        "  === h2, carte: li('Alpha') === noeud, prefixe: parClasse(li('Alpha'), 'masque')[0].x"
        "}));"
    )
    assert sortie == {"t1": "Vous attend, 1 projet", "t2": "Attend Camille, 1 projet",
                      "meme": True, "carte": False, "prefixe": "Attend Camille : "}


# --- Story 4.7 : annonce décidée par app.js, quel que soit l'onglet ------------------------------


def _donnees(attentes):
    """`/api/etat` du noyau : un projet par nom de `attentes` dans Attend, plus un stable."""
    depot = {"tag": "v1.0.0", "commits": {}, "prs_ouvertes": 0, "ci": "verte", "topics": [],
             "stories_ouvertes": 0, "sprint_status": "present", "run": "aucun"}
    base = {"categorie": "classé", "pause": None, "depot": depot, "attente": None,
            "sessions": [], "chantier": "Zeta"}
    projets = {"stable": base}
    for nom in attentes:
        projets[nom] = {**base, "attente": {"origine": "marqueur", "type": "test", "quoi": "q",
                                            "depuis": "2026-11-06T09:00:00Z"}}
    rendu = etat.assembler(projets, datetime(2026, 11, 6, 12, 0, tzinfo=UTC), UTC)
    return json.loads(json.dumps({**rendu, "dependances": [], "fraicheur": [], "alertes": [],
                                  "cycle": None, "utilisateur": ""}))


@sans_node
def test_app_annonce_la_hausse_pendant_chantiers_une_fois():
    from tests.test_web_tiroir import executer

    lectures = [_donnees(["projet-a"]), _donnees(["projet-a", "projet-b"]),
                _donnees(["projet-a", "projet-b"])]
    sortie = executer(f"""
const lectures = {json.dumps(lectures)};
let i = 0;
window.fetch = async () => ({{ status: 200,
  json: async () => ({{ ok: true, donnees: lectures[Math.min(i++, lectures.length - 1)] }}) }});
window.location.hash = "#" + "a".repeat(20);
let horloge = 100000;
Date.now = () => horloge;
const racine = new N("div"); racine.id = "racine"; body.append(racine);
await import({json.dumps((WEB / "app.js").as_uri())});
await tour(10);
const onglet = (nom) => parBalise(racine, "button").find((b) => texte(b) === nom).click();
const etapes = [["premier", [...F.annonces]]];
onglet("Chantiers");
await tour(10);
horloge += 31000; window.periodique(); await tour(10);
etapes.push(["hausse sur Chantiers", [...F.annonces]]);
onglet("Projets");
await tour(10);
etapes.push(["retour sur Projets", [...F.annonces]]);
horloge += 31000; window.periodique(); await tour(10);
etapes.push(["identique", [...F.annonces]]);
// le nom d'une carte ouvre le tiroir unique de l'appli
const bouton = parClasse(racine, "nom-projet").find((b) => texte(b) === "projet-b");
bouton.click();
etapes.push(["tiroir", parBalise(racine, "dialog").length, parClasse(racine, "tiroir-titre")[0].x,
  racine.className]);
process.stdout.write(JSON.stringify({{ etapes, lectures: i }}));
""")
    assert sortie["lectures"] == 3
    assert sortie["etapes"] == [
        ["premier", []],
        ["hausse sur Chantiers", ["Nouvelle attente : projet-b"]],
        ["retour sur Projets", ["Nouvelle attente : projet-b"]],
        ["identique", ["Nouvelle attente : projet-b"]],
        ["tiroir", 1, "projet-b", "tiroir-ouvert"],
    ]


@sans_node
def test_session_remplacee_ferme_le_tiroir_et_rend_la_marge():
    from tests.test_web_tiroir import executer

    lectures = [_donnees(["projet-a"])]
    sortie = executer(f"""
const lectures = {json.dumps(lectures)};
let statut = 200;
window.fetch = async () => ({{ status: statut,
  json: async () => ({{ ok: true, donnees: lectures[0] }}) }});
window.location.hash = "#" + "a".repeat(20);
let horloge = 100000;
Date.now = () => horloge;
const racine = new N("div"); racine.id = "racine"; body.append(racine);
await import({json.dumps((WEB / "app.js").as_uri())});
await tour(10);
parClasse(racine, "nom-projet").find((b) => texte(b) === "projet-a").click();
const avant = [parBalise(racine, "dialog").length, racine.className];
const dialog = parBalise(racine, "dialog")[0];
statut = 401;
horloge += 31000; window.periodique(); await tour(10);
process.stdout.write(JSON.stringify({{ avant, apres: [dialog.open, racine.className,
  parBalise(racine, "dialog").length] }}));
""")
    assert sortie == {"avant": [1, "tiroir-ouvert"], "apres": [False, "", 0]}


# --- Clé d'accès gardée le temps d'un rechargement (correctif r-cle, AD-14) ---------------------

JETON_A = "a" * 20
JETON_B = "b" * 20
TITRE_PERDUE = "Clé d'accès perdue"
TITRE_REMPLACEE = "Une autre fenêtre de l'appli a été ouverte. Fermez cet onglet."


def _executer_cle(corps: str, *, hash_="", garde=None, leve=False, statut0=200):
    """Importe app.js avec un `sessionStorage` simulé (`magasin`, `leve` : il lève) et un `fetch`
    qui répond `statut` ; `ecoute` garde les écouteurs de `window`, `titres()` les h2 affichés."""
    from tests.test_web_tiroir import executer

    return executer(f"""
const ecoute = {{}};
window.addEventListener = (t, f) => {{ (ecoute[t] = ecoute[t] || []).push(f); }};
const magasin = {json.dumps({} if garde is None else {"pilotage-cle": garde})};
let leve = {json.dumps(leve)};
window.sessionStorage = {{
  getItem: (k) => {{
    if (leve) {{ throw new Error("stockage"); }}
    return k in magasin ? magasin[k] : null;
  }},
  setItem: (k, v) => {{ if (leve) {{ throw new Error("stockage"); }} magasin[k] = v; }},
  removeItem: (k) => {{ if (leve) {{ throw new Error("stockage"); }} delete magasin[k]; }},
}};
let statut = {statut0};
const entetes = [];
const donnees = {json.dumps(_donnees(["projet-a"]))};
window.fetch = async (chemin, options) => {{
  entetes.push(options.headers.Authorization);
  return {{ status: statut, json: async () => ({{ ok: true, donnees }}) }};
}};
window.location.hash = {json.dumps(hash_)};
let horloge = 100000;
Date.now = () => horloge;
const racine = new N("div"); racine.id = "racine"; body.append(racine);
const titres = () => parClasse(racine, "ecran-titre").map((h) => h.x);
await import({json.dumps((WEB / "app.js").as_uri())});
await tour(10);
{corps}
""")


@sans_node
def test_cle_gardee_relue_puis_effacee_au_chargement():
    sortie = _executer_cle("""
process.stdout.write(JSON.stringify({ magasin, entetes, titres: titres(),
  projets: parClasse(racine, "nom-projet").length }));
""", garde=JETON_A)
    assert sortie["magasin"] == {}
    assert sortie["entetes"] == [f"Bearer {JETON_A}"]
    assert sortie["titres"] == []
    assert sortie["projets"] >= 1


@sans_node
def test_pagehide_garde_la_cle_et_rien_avant():
    sortie = _executer_cle("""
const avant = { ...magasin };
for (const f of ecoute.pagehide) { f({}); }
process.stdout.write(JSON.stringify({ avant, apres: magasin,
  types: Object.keys(ecoute).sort() }));
""", hash_="#" + JETON_A)
    assert sortie["avant"] == {}
    assert sortie["apres"] == {"pilotage-cle": JETON_A}
    assert "pagehide" in sortie["types"] and "pageshow" in sortie["types"]


@sans_node
def test_fragment_valable_l_emporte_et_le_stockage_est_vide():
    sortie = _executer_cle("""
process.stdout.write(JSON.stringify({ magasin, entetes }));
""", hash_="#" + JETON_A, garde=JETON_B)
    assert sortie == {"magasin": {}, "entetes": [f"Bearer {JETON_A}"]}


@sans_node
def test_fragment_invalide_ne_masque_pas_le_stockage():
    sortie = _executer_cle("""
process.stdout.write(JSON.stringify({ magasin, entetes }));
""", hash_="#court", garde=JETON_B)
    assert sortie == {"magasin": {}, "entetes": [f"Bearer {JETON_B}"]}


@sans_node
def test_cle_du_stockage_refusee_mene_a_cle_perdue_et_stockage_vide():
    sortie = _executer_cle("""
process.stdout.write(JSON.stringify({ magasin, titres: titres() }));
""", garde=JETON_A, statut0=401)
    assert sortie == {"magasin": {}, "titres": [TITRE_PERDUE]}


@sans_node
def test_fragment_refuse_reste_session_remplacee():
    sortie = _executer_cle("""
process.stdout.write(JSON.stringify({ titres: titres() }));
""", hash_="#" + JETON_A, statut0=401)
    assert sortie == {"titres": [TITRE_REMPLACEE]}


@sans_node
def test_cle_du_stockage_acceptee_puis_refusee_est_session_remplacee():
    sortie = _executer_cle("""
statut = 401;
horloge += 31000; window.periodique(); await tour(10);
process.stdout.write(JSON.stringify({ titres: titres() }));
""", garde=JETON_A)
    assert sortie == {"titres": [TITRE_REMPLACEE]}


@sans_node
def test_rien_n_est_ecrit_au_pagehide_apres_session_remplacee():
    sortie = _executer_cle("""
statut = 401;
horloge += 31000; window.periodique(); await tour(10);
for (const f of ecoute.pagehide) { f({}); }
process.stdout.write(JSON.stringify({ magasin, titres: titres() }));
""", hash_="#" + JETON_A)
    assert sortie == {"magasin": {}, "titres": [TITRE_REMPLACEE]}


@sans_node
def test_rien_n_est_ecrit_au_pagehide_apres_arret_sur_cle_perdue():
    sortie = _executer_cle("""
for (const f of ecoute.pagehide || []) { f({}); }
process.stdout.write(JSON.stringify({ magasin, titres: titres() }));
""", garde=JETON_A, statut0=401)
    assert sortie == {"magasin": {}, "titres": [TITRE_PERDUE]}


@sans_node
def test_pageshow_persiste_efface_le_stockage():
    sortie = _executer_cle("""
magasin["pilotage-cle"] = "reste";
for (const f of ecoute.pageshow) { f({ persisted: false }); }
const non = { ...magasin };
for (const f of ecoute.pageshow) { f({ persisted: true }); }
process.stdout.write(JSON.stringify({ non, oui: magasin }));
""", hash_="#" + JETON_A)
    assert sortie == {"non": {"pilotage-cle": "reste"}, "oui": {}}


@sans_node
def test_stockage_qui_leve_ne_casse_rien_et_donne_cle_perdue():
    # Fragment valable : l'appli s'ouvre, le pagehide n'échoue pas.
    sortie = _executer_cle("""
for (const f of ecoute.pagehide) { f({}); }
for (const f of ecoute.pageshow) { f({ persisted: true }); }
process.stdout.write(JSON.stringify({ titres: titres(), entetes }));
""", hash_="#" + JETON_A, leve=True)
    assert sortie == {"titres": [], "entetes": [f"Bearer {JETON_A}"]}
    # Rechargement sans fragment : clé perdue, sans erreur.
    sortie = _executer_cle("""
process.stdout.write(JSON.stringify({ titres: titres(), entetes }));
""", leve=True)
    assert sortie == {"titres": [TITRE_PERDUE], "entetes": []}


# --- Story 5.5 : « Reprendre » et appels du panneau de reprise par app.js -----------------------


def _executer_reprise(corps: str, *, statut_sessions=200, mode="resume"):
    """app.js sous node : `fetch` routé par chemin, appels gardés dans `requetes`."""
    from tests.test_web_tiroir import executer

    sessions = {"projet": "projet-a", "pc": "pc-a", "clone_ici": True, "proposee": "s1",
                "sessions": [{"session": "s1", "pc": "pc-b", "ce_pc": False,
                              "debut": "2026-11-06T09:00:00Z", "dernier_tour": None,
                              "branche": None, "statut": "attente", "fin": None}]}
    reprise_ = {"commande": "commande-du-serveur", "mode": mode,
                "brief": "20261106T101501Z-0a1b2c3d" if mode == "brief" else None,
                "raison": None, "dossier": "D:\\demo",
                "chemin_brief": "C:\\briefs\\b.md" if mode == "brief" else None}
    return executer(f"""
const requetes = [];
const donnees = {json.dumps(_donnees(["projet-a"]))};
const sessions = {json.dumps(sessions)};
const reprise = {json.dumps(reprise_)};
window.fetch = async (chemin, options) => {{
  requetes.push([chemin, options]);
  if (chemin.startsWith("/api/sessions/")) {{
    return {{ status: {statut_sessions}, json: async () => ({{ ok: true, donnees: sessions }}) }};
  }}
  if (chemin === "/api/reprise") {{
    return {{ status: 200, json: async () => ({{ ok: true, donnees: reprise }}) }};
  }}
  if (chemin.startsWith("/api/brief/")) {{
    return {{ status: 200, text: async () => "brief <b>brut</b>",
      json: async () => {{ throw new Error("pas du JSON"); }} }};
  }}
  return {{ status: 200, json: async () => ({{ ok: true, donnees }}) }};
}};
window.location.hash = "#" + "a".repeat(20);
let horloge = 100000;
Date.now = () => horloge;
const racine = new N("div"); racine.id = "racine"; body.append(racine);
await import({json.dumps((WEB / "app.js").as_uri())});
const A = await import({json.dumps((WEB / "accueil.js").as_uri())});
await tour(10);
const dialog = () => parBalise(racine, "dialog")[0];
const reprendre = () => parClasse(racine, "reprendre")[0];
{corps}
""")


@sans_node
def test_reprendre_ouvre_la_section_reprise_et_rend_le_focus():
    sortie = _executer_reprise("""
const bouton = reprendre();
const contenu = parBalise(racine, "main")[0];
const nom = A.boutonNom(contenu, "projet-a");
bouton.click(); await tour(10);
const section = parClasse(dialog(), "tiroir-section-reprise")[0];
const titre = parClasse(dialog(), "tiroir-titre")[0];
const ouvert = [dialog().open, titre.x, document.activeElement === titre, section.vus];
parClasse(dialog(), "tiroir-fermer")[0].click(); await tour(10);
const post = requetes.find((r) => r[0] === "/api/reprise")[1];

process.stdout.write(JSON.stringify({ ouvert, rendu: document.activeElement === bouton,
  nom: nom.className, nombre: parClasse(racine, "reprendre").length,
  post: [post.method, post.headers, post.body],
  get: requetes.find((r) => r[0].startsWith("/api/sessions/"))[1],
  commandes: parClasse(dialog(), "commande").map((c) => c.x) }));
""")
    assert sortie["ouvert"] == [True, "projet-a", True, [{"block": "nearest"}]]
    assert sortie["rendu"] is True
    assert sortie["nom"] == "btn-lien nom-projet"
    assert sortie["nombre"] == 1  # projet-a (Attend) seulement, pas la carte stable
    assert sortie["post"] == ["POST", {"Authorization": "Bearer " + "a" * 20,
                                       "Content-Type": "application/json"},
                              json.dumps({"projet": "projet-a", "session": "s1", "pc": "pc-b"},
                                         separators=(",", ":"))]
    get = sortie["get"]
    assert get["method"] == "GET" and get["headers"] == {"Authorization": "Bearer " + "a" * 20}
    assert "body" not in get
    assert sortie["commandes"] == ["commande-du-serveur"]


@sans_node
def test_appeler_en_mode_texte_lit_le_brief_brut():
    sortie = _executer_reprise("""
reprendre().click(); await tour(10);
parClasse(dialog(), "voir-brief")[0].click(); await tour(10);
const brief = requetes.find((r) => r[0].startsWith("/api/brief/"));
process.stdout.write(JSON.stringify({ pre: parClasse(dialog(), "brief")[0].x,
  chemin: brief[0], options: brief[1],
  cites: parClasse(dialog(), "chemin-reprise").map((c) => c.x) }));
""", mode="brief")
    assert sortie["pre"] == "brief <b>brut</b>"
    assert sortie["cites"] == ["Brief : C:\\briefs\\b.md"]
    assert sortie["chemin"] == "/api/brief/20261106T101501Z-0a1b2c3d"
    assert sortie["options"] == {"method": "GET", "cache": "no-store", "credentials": "omit",
                                 "headers": {"Authorization": "Bearer " + "a" * 20}}


@sans_node
def test_401_sur_les_sessions_remplace_l_ecran_et_ferme_le_tiroir():
    sortie = _executer_reprise("""
reprendre().click();
const d = dialog();
await tour(10);
process.stdout.write(JSON.stringify({ ouvert: d.open, marge: racine.className,
  titres: parClasse(racine, "ecran-titre").map((h) => h.x),
  dialogs: parBalise(racine, "dialog").length }));
""", statut_sessions=401)
    assert sortie == {"ouvert": False, "marge": "",
                      "titres": ["Une autre fenêtre de l'appli a été ouverte. Fermez cet onglet."],
                      "dialogs": 0}


# --- Story 5.6 : un message ou un réglage accepté lance le suivi de la synchro -----------------


GESTES_5_6 = {
    "/api/message": """
const zone = parBalise(dialog(), "textarea")[0];
zone.value = "salut"; zone.dispatchEvent(new F.Evenement("input"));
parClasse(dialog(), "deposer")[0].click();
""",
    "/api/projets": """
parClasse(dialog(), "exclure")[0].click();
parClasse(dialog(), "confirmer-exclusion")[0].click();
""",
}


@sans_node
@pytest.mark.parametrize("route", sorted(GESTES_5_6))
def test_depot_accepte_suivi_lance_sans_annonce_de_hausse(route):
    from tests.test_web_tiroir import executer

    lectures = [_donnees(["projet-a"]), _donnees(["projet-a", "projet-b"])]
    sortie = executer(f"""
const lectures = {json.dumps(lectures)};
const requetes = [];
let i = 0;
window.fetch = async (chemin, options) => {{
  requetes.push([chemin, options.method]);
  if (chemin === "/api/operations") {{
    return {{ status: 200, json: async () => ({{ ok: true,
      donnees: {{ operations: [], messages: [] }} }}) }};
  }}
  if (options.method === "POST") {{
    return {{ status: 202, json: async () => ({{ ok: true, donnees: {{ id: "x" }} }}) }};
  }}
  if (chemin !== "/api/etat") {{
    return {{ status: 200, json: async () => ({{ ok: true, donnees: null }}) }};
  }}
  return {{ status: 200,
    json: async () => ({{ ok: true, donnees: lectures[Math.min(i++, lectures.length - 1)] }}) }};
}};
window.location.hash = "#" + "a".repeat(20);
let horloge = 100000;
Date.now = () => horloge;
const racine = new N("div"); racine.id = "racine"; body.append(racine);
await import({json.dumps((WEB / "app.js").as_uri())});
await tour(10);
parClasse(racine, "nom-projet").find((b) => texte(b) === "projet-a").click();
await tour(10);
const dialog = () => parBalise(racine, "dialog")[0];
horloge += 2000;
{GESTES_5_6[route]}
await tour(20);
process.stdout.write(JSON.stringify({{ lectures: i, annonces: [...F.annonces],
  posts: requetes.filter((r) => r[1] === "POST").map((r) => r[0]),
  attend: parClasse(racine, "nom-projet").map((b) => texte(b)) }}));
""")
    assert sortie["posts"] == [route]
    assert sortie["lectures"] == 2  # relecture tout de suite après le 202
    assert "projet-b" in sortie["attend"]
    assert not [a for a in sortie["annonces"] if a.startswith("Nouvelle attente")]


def test_app_suit_la_synchro_d_un_depot_accepte():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'const DEPOTS = ["/api/message", "/api/projets"];' in app
    assert 'import "./boite.js";' in app and 'import "./reglages.js";' in app
    assert re.search(r'if \(methode === "POST" && reponse\.status === 202 && '
                     r"DEPOTS\.includes\(chemin\)\) \{\s*syncDemandee\(\);", app)
    assert re.search(r'suivi = \{ motif: "lance", finAvant: finDe\(etat \? etat\.cycle : null\) \};'
                     r"\s*\}\s*relire\(\);", app)
