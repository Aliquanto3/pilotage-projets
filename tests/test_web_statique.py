"""DOM sûr et clé d'accès du front (story 4.4, AD-15, M14, UX-DR17) : analyse statique."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tests.test_imports import RACINE_DEPOT

WEB = RACINE_DEPOT / "pilotage" / "web"
MODULES = sorted(WEB.glob("*.js"))

LITTERAL = r"""(?:"[^"\\\n]*"|'[^'\\\n]*')"""
# Une assignation (`=` seul, pas `==` ni `=>`) à une valeur qui n'est pas un littéral de chaîne
# terminé par `;`, `,` ou une fin de ligne.
NON_LITTERAL = rf"""\s*=(?![=>])(?!\s*{LITTERAL}\s*(?:[;,)]|$))"""

INTERDITS = (
    (r"\binnerHTML\b", "innerHTML"),
    (r"\bouterHTML\b", "outerHTML"),
    (r"\binsertAdjacentHTML\b", "insertAdjacentHTML"),
    (r"\bdocument\s*\.\s*write(?:ln)?\b", "document.write"),
    (r"\beval\s*\(", "eval"),
    (r"\bnew\s+Function\b", "new Function"),
    (r"\bDOMParser\b", "DOMParser"),
    (r"\bcreateContextualFragment\b", "createContextualFragment"),
    (r"\blocalStorage\b", "localStorage"),
    (r"\bsessionStorage\b", "sessionStorage"),
    (r"\bcookie\b", "cookie"),
    (r"\bbeforeunload\b", "beforeunload"),
    # Fin de ligne permise : l'appel coupé est jugé une fois recollé (`_joindre_suites`).
    (rf"\.setAttribute(?:NS)?\s*\((?!\s*(?:{LITTERAL}\s*,|$))", "setAttribute : nom non littéral"),
    (r"""\.setAttribute(?:NS)?\s*\(\s*["']on""", "setAttribute : nom en on*"),
    (r"""\.setAttribute(?:NS)?\s*\(\s*["'](?:xlink:)?(?:href|src|srcdoc|style|formaction)["']""",
     "setAttribute : href/src/srcdoc/style/formaction"),
    (r"\b(?:setHTMLUnsafe|parseHTMLUnsafe)\b", "setHTMLUnsafe"),
    (r"""\b(?:createElement|el)\s*\(\s*["'](?:script|iframe|object|embed)["']""",
     "élément actif (script, iframe, object, embed)"),
    (r"""\[\s*(?:`|["'][^"'\n]*["']\s*\+)|\+\s*["'][^"'\n]*["']\s*\]""",
     "accès calculé sur un nom construit"),
    (r"\.createElementNS\s*\((?!\s*SVG\s*,)", "createElementNS hors de la constante SVG"),
    (r"\.on[a-zA-Z]+\s*=(?![=>])", "assignation on*"),
    (r"""\[\s*["']on[a-zA-Z]*["']\s*\]""", "propriété on* calculée"),
    (rf"\.(?:href|src|srcdoc|formAction){NON_LITTERAL}", "href/src/srcdoc/formAction non littéral"),
    (rf"\.style(?:\.[a-zA-Z]+)?{NON_LITTERAL}", "style non littéral"),
    (r"\.style\s*\.\s*(?:setProperty|cssText)\b", "style.setProperty / cssText"),
    (rf"\.dataset(?:\.[a-zA-Z]+)?{NON_LITTERAL}", "dataset non littéral"),
    (r"\.dataset\s*\[", "dataset calculé"),
)
CONSTANTE_SVG = 'export const SVG = "http://www.w3.org/2000/svg";'


def _par_ligne(source: str) -> list[tuple[int, str]]:
    trouves = []
    for numero, ligne in enumerate(source.splitlines(), start=1):
        for motif, nom in INTERDITS:
            if re.search(motif, ligne):
                trouves.append((numero, nom))
        if re.search(r"\bSVG\s*=", ligne) and ligne.strip() != CONSTANTE_SVG:
            trouves.append((numero, "constante SVG redéfinie"))
    return trouves


def _joindre_suites(source: str) -> str:
    """Recolle les instructions coupées autour de `.`, `(`, `[`, `=` ou `,`."""
    source = re.sub(r"(?m)^[ \t]*//.*$", "", source)
    source = re.sub(r"\s*\n\s*(?=[.(\[=])", "", source)
    return re.sub(r"([.(\[=,])[ \t]*\n\s*", r"\1", source)


def constats(source: str) -> list[str]:
    """Règles M14 violées par `source` (une entrée par ligne fautive et par règle), puis celles
    qui n'apparaissent qu'une fois recollées les instructions coupées sur plusieurs lignes."""
    trouves = _par_ligne(source)
    resultat = [f"{numero}: {nom}" for numero, nom in trouves]
    noms = [nom for _, nom in trouves]
    joints = [nom for _, nom in _par_ligne(_joindre_suites(source))]
    for nom in dict.fromkeys(joints):
        resultat += [f"multi-ligne: {nom}"] * max(0, joints.count(nom) - noms.count(nom))
    return resultat


@pytest.mark.parametrize(
    ("fautif", "regle"),
    [
        ("noeud.innerHTML = texte;", "innerHTML"),
        ("const h = noeud.outerHTML;", "outerHTML"),
        ('noeud.insertAdjacentHTML("beforeend", x);', "insertAdjacentHTML"),
        ("document.write(x);", "document.write"),
        ("document . writeln(x);", "document.write"),
        ("eval(code);", "eval"),
        ('const f = new Function("x");', "new Function"),
        ("new DOMParser();", "DOMParser"),
        ("range.createContextualFragment(x);", "createContextualFragment"),
        ('localStorage.setItem("k", jeton);', "localStorage"),
        ('window.sessionStorage.setItem("k", jeton);', "sessionStorage"),
        ('document.cookie = "k=" + jeton;', "cookie"),
        ('window.addEventListener("beforeunload", f);', "beforeunload"),
        ("noeud.setAttribute(nom, valeur);", "setAttribute : nom non littéral"),
        ("noeud.setAttribute(`aria-${x}`, valeur);", "setAttribute : nom non littéral"),
        ('noeud.setAttributeNS(null, "href", x);', "setAttribute : nom non littéral"),
        ('noeud.setAttribute("onclick", "f()");', "setAttribute : nom en on*"),
        ('document.createElementNS(espace, "svg");', "createElementNS hors de la constante SVG"),
        ('document.createElementNS("http://www.w3.org/1999/xhtml", "a");',
         "createElementNS hors de la constante SVG"),
        ("bouton.onclick = f;", "assignation on*"),
        ('bouton["onclick"] = f;', "propriété on* calculée"),
        ("lien.href = donnees.url;", "href/src/srcdoc/formAction non littéral"),
        ('lien.href = "a" + x;', "href/src/srcdoc/formAction non littéral"),
        ("image.src = x;", "href/src/srcdoc/formAction non littéral"),
        ("cadre.srcdoc = x;", "href/src/srcdoc/formAction non littéral"),
        ("bouton.formAction = x;", "href/src/srcdoc/formAction non littéral"),
        ("noeud.style = x;", "style non littéral"),
        ("noeud.style.color = couleur;", "style non littéral"),
        ('noeud.style.setProperty("color", "red");', "style.setProperty / cssText"),
        ("noeud.dataset.id = carte.id;", "dataset non littéral"),
        ("noeud.dataset[cle] = 1;", "dataset calculé"),
        ('const SVG = "http://example.org/";', "constante SVG redéfinie"),
        ('lien.setAttribute("href", x);', "setAttribute : href/src/srcdoc/style/formaction"),
        ("image.setAttribute('src', x);", "setAttribute : href/src/srcdoc/style/formaction"),
        ('cadre.setAttribute("srcdoc", x);', "setAttribute : href/src/srcdoc/style/formaction"),
        ('noeud.setAttribute("style", x);', "setAttribute : href/src/srcdoc/style/formaction"),
        ('lien.setAttribute("xlink:href", x);', "setAttribute : href/src/srcdoc/style/formaction"),
        ("noeud.setHTMLUnsafe(x);", "setHTMLUnsafe"),
        ("Document.parseHTMLUnsafe(x);", "setHTMLUnsafe"),
        ('document.createElement("script");', "élément actif (script, iframe, object, embed)"),
        ("document.createElement('iframe');", "élément actif (script, iframe, object, embed)"),
        ('el("object");', "élément actif (script, iframe, object, embed)"),
        ('document.createElement("embed");', "élément actif (script, iframe, object, embed)"),
        ('noeud["inner" + "HTML"] = x;', "accès calculé sur un nom construit"),
        ("noeud[`inner${x}`] = x;", "accès calculé sur un nom construit"),
        ('noeud[nom + "HTML"] = x;', "accès calculé sur un nom construit"),
        ("noeud\n  .style = x;", "style non littéral"),
        ("noeud.style\n  = x;", "style non littéral"),
        ("noeud.setAttribute(\n  nom, x);", "setAttribute : nom non littéral"),
        ('noeud.setAttribute(\n  "onclick", x);', "setAttribute : nom en on*"),
    ],
)
def test_chaque_regle_m14_detecte_son_exemple(fautif, regle):
    assert [c.split(": ", 1)[1] for c in constats(fautif)] == [regle]


@pytest.mark.parametrize(
    "sain",
    [
        'noeud.setAttribute("aria-current", "page");',
        'noeud.setAttribute("aria-describedby", idConsigne);',
        'document.createElementNS(SVG, "path");',
        "noeud.textContent = donnees.quoi;",
        'lien.href = "index.html";',
        "if (a.src === b) {}",
        "const f = (x) => x;",
        CONSTANTE_SVG,
        'window.addEventListener("keydown", surTouche);',
        'document.createElement("button");',
        "liste[indice] = x;",
        'noeud.setAttribute(\n  "aria-label", "Vues");',
        "const a = b\n  .then(f);",
    ],
)
def test_constructions_permises_ne_sont_pas_signalees(sain):
    assert constats(sain) == []


def test_modules_presents():
    noms = {chemin.name for chemin in MODULES}
    assert {"app.js", "dom.js", "temps.js", "barre.js", "bandeaux.js", "cle.js", "accueil.js",
            "chantiers.js"} <= noms


@pytest.mark.parametrize("module", MODULES, ids=lambda chemin: chemin.name)
def test_module_respecte_m14(module):
    assert constats(module.read_text(encoding="utf-8")) == []


def test_constante_svg_definie_une_seule_fois_dans_dom():
    definitions = [m.name for m in MODULES if CONSTANTE_SVG in m.read_text(encoding="utf-8")]
    assert definitions == ["dom.js"]


@pytest.mark.parametrize("module", MODULES, ids=lambda chemin: chemin.name)
def test_imports_relatifs_resolus(module):
    source = module.read_text(encoding="utf-8")
    cibles = re.findall(r"""^import\s.*?\sfrom\s+["']([^"']+)["'];""", source, re.MULTILINE)
    for cible in cibles:
        assert cible.startswith("./") and cible.endswith(".js"), cible
        assert (WEB / cible[2:]).is_file(), cible


def test_jeton_tenu_seulement_par_app_js():
    """Seul `app.js` lit le fragment, appelle `fetch` et envoie l'en-tête `Authorization`."""
    for module in MODULES:
        source = module.read_text(encoding="utf-8")
        for motif in (r"location\s*\.\s*hash", r"\bfetch\s*\(", r"Authorization", r"\bjeton\b"):
            if re.search(motif, source):
                assert module.name == "app.js", (module.name, motif)
    app = (WEB / "app.js").read_text(encoding="utf-8")
    effacement = "history.replaceState(null, \"\", window.location.pathname"
    assert effacement + " + window.location.search)" in app
    assert re.search(r"Authorization: `Bearer \$\{jeton\}`", app)


def test_temps_js_sans_dom():
    source = (WEB / "temps.js").read_text(encoding="utf-8")
    assert not re.search(r"\b(document|window|import)\b", source)


def test_textes_exacts_de_l_epic():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    cle = (WEB / "cle.js").read_text(encoding="utf-8")
    for texte in (
        "Scan en cours…", "Synchro en cours…", "Synchro faite à ${heure}",
        "Une synchro tourne déjà. L'accueil se mettra à jour à sa fin.",
    ):
        assert texte in app, texte
    for texte in (
        "Clé d'accès perdue", "uv run lancer.py appli", "Copier la commande", '"Copié"',
        "Ctrl+C pour copier", "Une autre fenêtre de l'appli a été ouverte. Fermez cet onglet.",
        "Cette page a perdu sa clé en se rechargeant. Relancez l'appli depuis un terminal.",
        'setAttribute("aria-describedby", idConsigne)', "DUREE_COPIE_MS = 2000",
    ):
        assert texte in cle, texte


def test_css_sans_couleur_en_dur():
    for feuille in ("appli.css",):
        source = (WEB / feuille).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", source), feuille


class _Analyse(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.balises: list[tuple[str, dict[str, str | None]]] = []
        self.texte_script = ""
        self._dans_script = False

    def handle_starttag(self, tag, attrs):
        self.balises.append((tag, dict(attrs)))
        self._dans_script = tag == "script"

    def handle_endtag(self, tag):
        if tag == "script":
            self._dans_script = False

    def handle_data(self, data):
        if self._dans_script:
            self.texte_script += data


def _index() -> _Analyse:
    analyse = _Analyse()
    analyse.feed((WEB / "index.html").read_text(encoding="utf-8"))
    return analyse


def test_index_sans_script_ni_style_en_ligne():
    analyse = _index()
    scripts = [a for tag, a in analyse.balises if tag == "script"]
    assert scripts == [{"type": "module", "src": "app.js"}]
    assert analyse.texte_script.strip() == ""
    assert all(tag != "style" for tag, _ in analyse.balises)
    for tag, attributs in analyse.balises:
        for nom in attributs:
            assert nom != "style" and not nom.startswith("on"), (tag, nom)
        for nom in ("href", "src"):
            valeur = attributs.get(nom) or ""
            assert "//" not in valeur and ":" not in valeur, (tag, valeur)  # aucun CDN


def test_index_regions_d_annonce_des_le_chargement():
    attributs = {a.get("id"): a for _, a in _index().balises if a.get("id")}
    assert attributs["annonce"]["aria-live"] == "polite"
    assert attributs["alerte"]["role"] == "alert"
    assert "racine" in attributs


def test_index_feuilles_de_la_charte_presentes():
    feuilles = [
        a["href"] for tag, a in _index().balises if tag == "link" and a.get("rel") == "stylesheet"
    ]
    assert feuilles == ["polices.css", "charte.css", "charte-base.css", "appli.css"]
    for feuille in feuilles:
        assert Path(WEB / feuille).is_file()


def test_codes_erreur_des_bandeaux_sont_les_refus_de_depot():
    """Revue 7.1 : les bandeaux « erreur » sont des codes du catalogue, dont les deux arrêts de
    la synchro sur le dépôt de données (`depot-public`, `depot-non-configure`)."""
    from pilotage.noyau import alertes

    texte = (WEB / "bandeaux.js").read_text(encoding="utf-8")
    trouve = re.search(r"CODES_ERREUR\s*=\s*new Set\(\[([^\]]*)\]\)", texte)
    assert trouve
    codes = set(re.findall(r'"([^"]+)"', trouve.group(1)))
    assert codes == {alertes.DEPOT_PUBLIC, alertes.DEPOT_NON_CONFIGURE}
    assert codes <= set(alertes.MODELES)
