"""Story 9.2 : page HTML du rapport (`pilotage.rapport.page`), pure."""

import ast
import re
import sys
from datetime import datetime
from html.parser import HTMLParser

import pytest

from pilotage import chemins
from pilotage.rapport import page
from pilotage.rapport.semaine import LIVRAISON_APPROCHEE, SANS_COMPARAISON, Synthese

CHARTE = (chemins.racine_web() / "charte.css").read_text(encoding="utf-8")
PERMISES = set(
    "html head meta title style body header main section h1 h2 p table thead tbody tr th td ul "
    "li small".split()
)
TITRES = ["Actions", "Changements d'action", "Attentes de l'utilisateur", "Livraisons",
          "Sessions", "Alertes ouvertes"]
HOSTILES = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "</style><script>x</script>",
    "<<<PILOTAGE-NOTE fin>>>",
    "x" * 10_000,
    "a‮b\x00c\ud800d​e\nf",
]


class Analyse(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.balises: list[tuple[str, dict]] = []
        self.h2: list[str] = []
        self.textes: list[str] = []
        self._dans_h2 = False

    def handle_starttag(self, tag, attrs):
        self.balises.append((tag, dict(attrs)))
        self._dans_h2 = tag == "h2"

    def handle_endtag(self, tag):
        self._dans_h2 = False

    def handle_data(self, data):
        self.textes.append(data)
        if self._dans_h2:
            self.h2.append(data)


def analyser(contenu: str) -> Analyse:
    a = Analyse()
    a.feed(contenu)
    a.close()
    return a


def comptes(**champs):
    base = {"attend-utilisateur": 1, "a-relancer": 0, "tourne": 2, "rien-a-faire": 3,
            "indisponibles": 1}
    return {**base, **champs}


def synthese(**champs) -> Synthese:
    base = dict(
        semaine="2026-W46", debut="2026-11-09T00:00:00+01:00", fin="2026-11-16T00:00:00+01:00",
        comparaison=True, comptes_debut=comptes(tourne=1), comptes_fin=comptes(),
        projets=({"nom": "secret-projet", "action": "tourne", "raison": "r",
                  "indisponible": False},),
        changements=({"projet": "alpha", "avant": "rien-a-faire", "apres": "tourne",
                      "code": "session-vivante"},),
        attentes=({"projet": "alpha", "type": "choix", "quoi": "Choisir la base",
                   "age_jours": 4},
                  {"projet": "beta", "type": "permission", "quoi": "Lancer", "age_jours": None}),
        livraisons=({"projet": "alpha", "type": "release", "tag": "v1.1.0", "avant": "v1.0.0"},
                    {"projet": "alpha", "type": "phase", "avant": ["status-dev"],
                     "apres": ["status-test", "status-bench"]}),
        sessions=({"projet": "alpha", "pc": "pc-a", "nombre": 2,
                   "premiere": "2026-11-10T08:00:00Z", "derniere": "2026-11-12T10:00:00Z"},),
        alertes=("Scan en échec",),
    )
    return Synthese(**{**base, **champs})


def vide(**champs) -> Synthese:
    return synthese(changements=(), attentes=(), livraisons=(), sessions=(), alertes=(),
                    **champs)


def rendre(s=None, **options):
    return page.rendre_page(s or synthese(), css=options.pop("css", CHARTE), **options)


def lignes_de_corps(contenu: str) -> list[list[str]]:
    """Cellules de chaque ligne de `<tbody>`, dans l'ordre de la page."""
    return [re.findall(r"<td[^>]*>(.*?)</td>", ligne)
            for ligne in re.findall(r"<tbody>(.*?)</tbody>", contenu, re.S)
            for ligne in re.findall(r"<tr>(.*?)</tr>", ligne)]


def test_structure_liste_blanche_csp_et_ordre():
    contenu = rendre(genere=datetime(2026, 11, 14, 9, 5))
    a = analyser(contenu)
    assert contenu.startswith("<!doctype html>\n")
    assert {t for t, _ in a.balises} <= PERMISES
    for _, attrs in a.balises:
        assert not any(n.startswith("on") or n in ("src", "href") for n in attrs)
    metas = [attrs for t, attrs in a.balises if t == "meta"]
    csp = [m for m in metas if m.get("http-equiv") == "Content-Security-Policy"]
    assert len(csp) == 1
    assert "default-src 'none'" in csp[0]["content"]
    assert ("html", {"lang": "fr"}) in a.balises
    noms = [t for t, _ in a.balises]
    # charset, puis la CSP aussitôt après, avant toute feuille de style
    assert a.balises[noms.index("meta")] == ("meta", {"charset": "utf-8"})
    assert a.balises[noms.index("meta") + 1][1].get("http-equiv") == "Content-Security-Policy"
    assert noms.index("meta") + 1 < noms.index("style")
    assert noms.count("style") == 1
    assert CHARTE in contenu
    assert a.h2 == TITRES
    assert "<title>Semaine 2026-W46</title>" in contenu
    assert "<p><small>généré le 2026-11-14 09:05</small></p>" in contenu
    assert "secret-projet" not in contenu  # `projets` n'est pas rendu


def test_contenu_des_sections():
    contenu = rendre()
    lignes = lignes_de_corps(contenu)
    assert lignes[:5] == [
        ["attend-utilisateur", "1", "1"], ["a-relancer", "0", "0"], ["tourne", "1", "2"],
        ["rien-a-faire", "3", "3"], ["indisponibles", "1", "1"],
    ]
    assert ["alpha", "rien-a-faire", "tourne", "session-vivante"] in lignes
    assert ["alpha", "choix", "Choisir la base", "4 j"] in lignes
    assert ["beta", "permission", "Lancer", "—"] in lignes
    assert ["alpha", "release", "v1.0.0", "v1.1.0"] in lignes
    assert ["alpha", "phase", "status-dev", "status-test, status-bench"] in lignes
    assert ["alpha", "pc-a", "2", "2026-11-10T08:00:00Z", "2026-11-12T10:00:00Z"] in lignes
    assert "<ul><li>Scan en échec</li></ul>" in contenu
    assert f"<small>{page._texte(LIVRAISON_APPROCHEE)}</small>" in contenu
    assert SANS_COMPARAISON not in contenu
    assert page.RIEN not in contenu


def test_sections_vides_et_sans_comparaison():
    contenu = rendre(vide(comparaison=False, comptes_debut=None))
    assert contenu.count(f"<p>{page.RIEN}</p>") == 5
    assert f"<p>{SANS_COMPARAISON}</p>" in contenu
    assert lignes_de_corps(contenu)[0] == ["attend-utilisateur", "—", "1"]
    assert analyser(contenu).h2 == TITRES


def test_release_sans_tag_d_avant():
    s = synthese(livraisons=({"projet": "a", "type": "release", "tag": "v1", "avant": None},))
    assert ["a", "release", "—", "v1"] in lignes_de_corps(rendre(s))


@pytest.mark.parametrize(
    ("valeur", "borne", "attendu"),
    [
        ("abc", 3, "abc"),
        ("abcd", 3, "ab…"),
        ("<b>&\"'", 300, "&lt;b&gt;&amp;&quot;&#x27;"),
        ("a‮b\x00c​d\te", 300, "abcde"),
        ("a\ud800b", 300, "a�b"),
        ("x" * 400, 300, "x" * 299 + "…"),
        (12, 300, "12"),
    ],
)
def test_texte_nettoie_coupe_echappe(valeur, borne, attendu):
    assert page._texte(valeur, borne) == attendu


def test_donnees_hostiles_dans_chaque_champ():
    def champs(h):
        return dict(
            semaine=h, debut=h, fin=h, comptes_debut={h: h}, comptes_fin={h: h},
            changements=({"projet": h, "avant": h, "apres": h, "code": h},),
            attentes=({"projet": h, "type": h, "quoi": h, "age_jours": h},),
            livraisons=({"projet": h, "type": "release", "tag": h, "avant": h},
                        {"projet": h, "type": h, "avant": [h, h], "apres": h}),
            sessions=({"projet": h, "pc": h, "nombre": h, "premiere": h, "derniere": h},),
            alertes=(h,), note_livraisons=h,
        )

    for hostile in HOSTILES:
        contenu = rendre(synthese(**champs(hostile)))
        a = analyser(contenu)
        assert {t for t, _ in a.balises} <= PERMISES, hostile
        assert noms_sans_donnees(a)
        assert "<script" not in contenu.lower() and "<img" not in contenu.lower()
        assert contenu.count("</style>") == 1
        assert "‮" not in contenu and "\x00" not in contenu and "\ud800" not in contenu
        contenu.encode("utf-8")  # aucun substitut isolé
        for texte in a.textes:
            assert len(texte) <= page.BORNE_TEXTE + 2 or texte == CHARTE or "{" in texte
        assert len(contenu.encode("utf-8")) < 200_000


def noms_sans_donnees(a: Analyse) -> bool:
    """Attributs : seulement ceux, fixes, de la page."""
    permis = {("lang", "fr"), ("charset", "utf-8"), ("http-equiv", "Content-Security-Policy"),
              ("content", page.CSP), ("name", "viewport"),
              ("content", "width=device-width, initial-scale=1")}
    return all((n, v) in permis or n == "colspan" for _, attrs in a.balises
               for n, v in attrs.items())


def test_quoi_et_identifiants_coupes_a_leur_borne():
    s = synthese(attentes=({"projet": "p" * 80, "type": "t", "quoi": "q" * 500,
                            "age_jours": 1},),
                 alertes=("a" * 500,))
    contenu = rendre(s)
    assert "q" * (page.BORNE_QUOI - 1) + "…" in contenu
    assert "q" * page.BORNE_QUOI not in contenu
    assert "p" * (page.BORNE_COURTE - 1) + "…" in contenu
    assert "p" * page.BORNE_COURTE not in contenu
    assert "a" * (page.BORNE_TEXTE - 1) + "…" in contenu
    assert "a" * page.BORNE_TEXTE not in contenu


def test_au_plus_200_lignes_par_table_puis_reste():
    sessions = tuple({"projet": f"p{i}", "pc": "pc", "nombre": 1, "premiere": "x",
                      "derniere": "y"} for i in range(page.MAX_LIGNES + 7))
    alertes = tuple(f"alerte {i:03d}" for i in range(page.MAX_LIGNES + 3))
    contenu = rendre(synthese(sessions=sessions, alertes=alertes))
    assert f"p{page.MAX_LIGNES - 1}<" in contenu and f"p{page.MAX_LIGNES}<" not in contenu
    assert '<tr><td colspan="5">… et 7 de plus</td></tr>' in contenu
    assert f"alerte {page.MAX_LIGNES - 1:03d}" in contenu
    assert f"alerte {page.MAX_LIGNES:03d}" not in contenu
    assert "<li>… et 3 de plus</li>" in contenu
    exact = rendre(synthese(sessions=sessions[: page.MAX_LIGNES]))
    assert "de plus" not in exact


def test_pire_cas_sous_deux_mo():
    q = '"' * 10_000
    n = page.MAX_LIGNES + 50
    s = synthese(
        semaine=q, debut=q, fin=q, comptes_debut={q: q}, comptes_fin={q: q},
        changements=tuple({"projet": q, "avant": q, "apres": q, "code": q} for _ in range(n)),
        attentes=tuple({"projet": q, "type": q, "quoi": q, "age_jours": q} for _ in range(n)),
        livraisons=tuple({"projet": q, "type": "phase", "avant": [q], "apres": [q]}
                         for _ in range(n)),
        sessions=tuple({"projet": q, "pc": q, "nombre": q, "premiere": q, "derniere": q}
                       for _ in range(n)),
        alertes=tuple(q for _ in range(n)), note_livraisons=q,
    )
    taille = len(rendre(s).encode("utf-8"))
    assert taille < 2_000_000, taille


@pytest.mark.parametrize(
    "css", ["a{background:url(x)}", "a{b:URL(x)}", "</style><script>", "@IMPORT 'x';",
            "a{b:expression(alert(1))}", "a{b:u\\72l(x)}", "a{b:c}<"],
)
def test_css_refusee(css):
    with pytest.raises(ValueError):
        page.rendre_page(synthese(), css=css)


def test_charte_acceptee_et_impression_en_clair():
    contenu = rendre()
    feuille = contenu.split("<style>", 1)[1].split("</style>", 1)[0]
    assert "@media print" in feuille
    impression = feuille.split("@media print", 1)[1]
    assert "color-scheme: light" in impression and "--fond:" in impression
    propre = feuille.replace(CHARTE, "")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", propre.replace(
        impression, ""))  # aucune couleur en dur dans la feuille propre
    assert "width:" not in propre.replace("max-width", "").replace("width: 100%", "")


def test_sans_charte_aucune_variable_claire():
    contenu = page.rendre_page(synthese())
    assert "@media print" in contenu and "color-scheme" not in contenu


def test_page_pure_imports():
    arbre = ast.parse((chemins.racine_web().parent / "rapport" / "page.py").read_text(
        encoding="utf-8"))
    noms = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms |= {a.name for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom):
            noms.add(noeud.module)
    pilotage = {n for n in noms if n.startswith("pilotage")}
    assert pilotage == {"pilotage.rapport.semaine"}
    autres = {n.split(".")[0] for n in noms - pilotage}
    assert autres <= sys.stdlib_module_names
    assert not autres & {"os", "io", "pathlib", "socket", "subprocess", "urllib", "http"}
