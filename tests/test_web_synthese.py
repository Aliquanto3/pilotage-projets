"""Tête de l'accueil « Coup d'œil » (story 4.10) sous node avec un DOM factice.

Phrase-synthèse (règles 1 à 7 d'EXPERIENCE § Phrase-synthèse, horloge injectée, TZ=UTC), bloc
des stables, barre de répartition et légende, aides repliables, aucun projet, chargement lent.
"""

import json
import os
import re
import subprocess

import pytest

from tests.test_web_accueil import FAUX_DOM, NODE, WEB, _classe, _textes, _tous, sans_node

AUCUN = ("Aucun projet trouvé sous Documents\\GitHub. Lancez un scan avec le bouton Scan de la "
         "barre du haut.")


def _node(corps: str):
    script = (
        FAUX_DOM
        + "N.prototype.removeAttribute = function (n) { delete this.a[n]; };"
        + f"const s = await import({json.dumps((WEB / 'synthese.js').as_uri())});"
        + f"const acc = await import({json.dumps((WEB / 'accueil.js').as_uri())});"
        + "const sortir = (v) => process.stdout.write(JSON.stringify(v));"
        + corps
    )
    sortie = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
        env={**os.environ, "TZ": "UTC"},
    )
    return json.loads(sortie.stdout)


def _attente(nom, depuis):
    return {"nom": nom, "genre": "projet", "action": "attend-utilisateur", "depuis": depuis}


def _relance(nom, dernier_tour):
    return {"nom": nom, "genre": "projet", "action": "a-relancer", "dernier_tour": dernier_tour}


def _etat(attentes=(), relances=(), tourne=0, rien=0, familles=None, suivis=None, stables=0):
    attentes, relances = list(attentes), list(relances)
    n_relancer = len(relances)
    cartes = attentes + relances + [{"nom": f"t{i}"} for i in range(tourne)] + [
        {"nom": f"r{i}"} for i in range(rien)]
    return {
        "cartes": cartes,
        "colonnes": {"attend-utilisateur": attentes, "a-relancer": relances, "tourne": [],
                     "rien-a-faire": []},
        "comptes": {
            "actions": {"attend-utilisateur": len(attentes), "a-relancer": n_relancer,
                        "tourne": tourne, "rien-a-faire": rien},
            "types": {}, "familles": familles or {},
            "suivis": len(cartes) if suivis is None else suivis, "stables": stables,
        },
    }


def _phrase(etat, maintenant):
    parties = _node(
        f"sortir(s.partiesSynthese({json.dumps(etat)}, new Date({json.dumps(maintenant)})));")
    return "".join(p.get("texte", p.get("nom", "")) for p in parties)


def _tete(etat, maintenant="2026-11-07T10:00:00Z"):
    return _node(
        "const t = s.creerTete();"
        f"t.maj({json.dumps(etat)}, new Date({json.dumps(maintenant)}));"
        "sortir(plat(t.element));")


# --- Phrase-synthèse : un test par règle -------------------------------------------------------

@sans_node
def test_regle_1_noms_dans_l_ordre_de_la_colonne_groupes_par_heure():
    attentes = [_attente("projet-a", "2026-11-06T22:47:00Z"),
                _attente("projet-b", "2026-11-07T07:58:00Z"),
                _attente("claude-config", "2026-11-07T08:21:00Z")]
    etat = _etat(attentes, [_relance(f"x{i}", None) for i in range(3)], tourne=1, rien=5)
    assert _phrase(etat, "2026-11-07T10:00:00Z") == (
        "projet-a vous attend depuis hier 22:47, projet-b et claude-config depuis ce matin. "
        "3 projets à relancer, 1 qui tourne, 5 au repos.")
    inverse = _etat(list(reversed(attentes)))
    assert _phrase(inverse, "2026-11-07T10:00:00Z") == (
        "claude-config et projet-b vous attendent depuis ce matin, projet-a depuis hier 22:47.")


@sans_node
def test_regle_2_personne_ne_vous_attend():
    assert _phrase(_etat(rien=2), "2026-11-07T10:00:00Z") == "Personne ne vous attend. 2 au repos."
    assert _phrase(_etat(), "2026-11-07T10:00:00Z") == "Personne ne vous attend."


@sans_node
def test_regle_3_plus_ancien_a_relancer_date_ou_omis_sans_dernier_tour():
    relances = [_relance("a", "2026-11-06T21:15:00Z"), _relance("b", "2026-11-07T08:00:00Z"),
                _relance("c", None)]
    etat = _etat([], relances, tourne=3, rien=6)
    assert _phrase(etat, "2026-11-07T10:00:00Z") == (
        "Personne ne vous attend. 3 projets à relancer, le plus ancien depuis hier 21:15 ; "
        "3 tournent, 6 au repos.")
    sans_tour = _etat([], [_relance("c", None), _relance("d", None)], tourne=3, rien=6)
    assert _phrase(sans_tour, "2026-11-07T10:00:00Z") == (
        "Personne ne vous attend. 2 projets à relancer, 3 tournent, 6 au repos.")
    # Quelqu'un attend : le plus ancien à relancer n'est pas daté.
    avec_attente = _etat([_attente("projet-a", "2026-11-07T13:00:00Z")], relances, rien=1)
    assert _phrase(avec_attente, "2026-11-07T15:00:00Z") == (
        "projet-a vous attend depuis 13:00. 3 projets à relancer, 1 au repos.")
    # Plus ancien qu'hier : « depuis le JJ/MM » ; seul à relancer, sans « le plus ancien ».
    seul = _etat([], [_relance("a", "2026-11-04T09:00:00Z")])
    assert _phrase(seul, "2026-11-07T10:00:00Z") == (
        "Personne ne vous attend. 1 projet à relancer, depuis le 04/11.")


@sans_node
def test_regle_4_accords():
    deux = _etat([_attente("a", "2026-11-07T08:00:00Z"), _attente("b", "2026-11-07T09:00:00Z")],
                 [_relance("x", None)], tourne=1, rien=1)
    assert _phrase(deux, "2026-11-07T10:00:00Z") == (
        "a et b vous attendent depuis ce matin. 1 projet à relancer, 1 qui tourne, 1 au repos.")
    trois = _etat([], [_relance(f"x{i}", None) for i in range(2)], tourne=2)
    phrase = _phrase(trois, "2026-11-07T10:00:00Z")
    assert phrase == "Personne ne vous attend. 2 projets à relancer, 2 tournent."
    assert "!" not in phrase


@sans_node
def test_regle_5_trois_noms_au_plus_puis_et_n_autres():
    matin = [_attente(n, f"2026-11-07T0{i}:00:00Z") for i, n in enumerate("abcde", start=1)]
    assert _phrase(_etat(matin), "2026-11-07T10:00:00Z") == (
        "a, b, c et 2 autres vous attendent depuis ce matin.")
    melange = [_attente("a", "2026-11-06T22:00:00Z"), _attente("b", "2026-11-07T08:00:00Z"),
               _attente("c", "2026-11-07T09:00:00Z"), _attente("d", "2026-11-07T14:05:00Z")]
    assert _phrase(_etat(melange), "2026-11-07T15:00:00Z") == (
        "a vous attend depuis hier 22:00, b et c depuis ce matin, et 1 autre depuis 14:05.")
    # Autres d'heures différentes : aucune heure, plutôt qu'un « depuis ce matin » faux pour 14:05.
    divers = matin[:4] + [_attente("e", "2026-11-07T14:05:00Z")]
    assert _phrase(_etat(divers), "2026-11-07T15:00:00Z") == (
        "a, b et c vous attendent depuis ce matin, et 2 autres.")
    trois = _node(
        f"const t = s.creerTete(); t.maj({json.dumps(_etat(matin))},"
        " new Date('2026-11-07T10:00:00Z'));"
        "sortir(plat(t.element));")
    assert [n["x"] for n in _classe(trois, "synthese-nom")] == ["a", "b", "c"]


@sans_node
@pytest.mark.parametrize(("heure", "attendu"), [
    ("11:59", "projet-a vous attend depuis ce matin."),
    ("12:00", "projet-a vous attend depuis 12:00."),
    ("00:00", "projet-a vous attend depuis ce matin."),
    ("14:05", "projet-a vous attend depuis 14:05."),
])
def test_regle_6_depuis_ce_matin_avant_12_h(heure, attendu):
    etat = _etat([_attente("projet-a", f"2026-11-07T{heure}:00Z")])
    assert _phrase(etat, "2026-11-07T18:00:00Z") == attendu


@sans_node
def test_regle_6_hier_matin_garde_son_heure():
    etat = _etat([_attente("projet-a", "2026-11-06T09:30:00Z")])
    assert _phrase(etat, "2026-11-07T18:00:00Z") == "projet-a vous attend depuis hier 09:30."


@sans_node
def test_regle_7_compte_nul_omis():
    etat = _etat([_attente("projet-a", "2026-11-07T13:00:00Z")],
                 [_relance(f"x{i}", None) for i in range(3)], tourne=0, rien=5)
    assert _phrase(etat, "2026-11-07T15:00:00Z") == (
        "projet-a vous attend depuis 13:00. 3 projets à relancer, 5 au repos.")
    assert _phrase(_etat([_attente("projet-a", "2026-11-07T13:00:00Z")], tourne=1),
                   "2026-11-07T15:00:00Z") == "projet-a vous attend depuis 13:00. 1 qui tourne."
    assert _phrase(_etat([_attente("projet-a", None)]),
                   "2026-11-07T15:00:00Z") == "projet-a vous attend."


# --- Noms : accent-texte, textContent, jamais des liens ----------------------------------------

@sans_node
@pytest.mark.parametrize("hostile", ["<img src=x onerror=alert(1)>", "<script>alert(1)</script>"])
def test_nom_hostile_reste_du_texte_inerte(hostile):
    racine = _tete(_etat([_attente(hostile, "2026-11-07T08:00:00Z")]))
    (phrase,) = _classe(racine, "synthese")
    assert phrase["t"] == "p" and "aria-live" not in phrase["a"]
    (nom,) = _classe(phrase, "synthese-nom")
    assert nom["t"] == "span" and nom["x"] == hostile and nom["k"] == []
    noeuds = list(_tous(racine))
    assert not [n for n in noeuds if n["t"] in {"a", "button", "img", "script"}]
    for n in noeuds:
        assert all(not cle.startswith("on") for cle in n["a"])
        assert all(hostile not in v for v in n["a"].values())
    assert sum(hostile in n["x"] for n in noeuds) == 1


def test_css_noms_en_accent_texte():
    css = (WEB / "appli.css").read_text(encoding="utf-8")
    assert re.search(r"\.synthese-nom\s*\{\s*color:\s*var\(--accent-texte\);", css)
    assert re.search(r"\.synthese\s*\{[^}]*overflow-wrap:\s*anywhere", css)


# --- Bloc des stables et barre de répartition --------------------------------------------------

def _comptes_maquette():
    etat = _etat([_attente(f"a{i}", "2026-11-07T08:00:00Z") for i in range(3)],
                 [_relance(f"r{i}", None) for i in range(3)], tourne=1, rien=5,
                 familles={"stable": 4, "pause": 1}, stables=4)
    return etat


@sans_node
def test_bloc_des_stables_et_pourcentage_arrondi():
    racine = _tete(_comptes_maquette())
    (bloc,) = _classe(racine, "bloc-stables")
    assert _textes(bloc) == ["4", " sur 12 projets stables", "33 % des projets suivis"]
    deux_tiers = _tete(_etat(rien=3, familles={"stable": 2, "pause": 1}, stables=2))
    assert _textes(_classe(deux_tiers, "bloc-stables")[0])[2] == "67 % des projets suivis"
    un = _tete(_etat(rien=1, familles={"stable": 1}, stables=1))
    assert _textes(_classe(un, "bloc-stables")[0]) == [
        "1", " sur 1 projet stable", "100 % des projets suivis"]


@sans_node
def test_barre_segments_ordre_largeurs_et_legende():
    etat = _comptes_maquette()
    etat["comptes"]["familles"]["a-classer"] = 0
    racine = _tete(etat)
    (barre,) = _classe(racine, "barre-repartition")
    assert barre["a"]["aria-hidden"] == "true"
    segments = barre["k"]
    assert [s["c"] for s in segments] == [
        "segment segment-attend", "segment segment-relancer", "segment segment-tourne",
        "segment segment-stable", "segment segment-pause"]
    assert [s["a"]["width"] for s in segments] == ["25%", "25%", "8.333%", "33.333%", "8.333%"]
    assert all(s["a"]["aria-hidden"] == "true" for s in segments)
    (legende,) = _classe(racine, "legende-repartition")
    assert legende["t"] == "ul"
    assert legende["a"]["aria-label"] == "Répartition des 12 projets suivis"
    items = ["".join(_textes(li)) for li in legende["k"]]
    assert items == ["Vous attend : 3", "À relancer : 3", "Tourne : 1", "stables : 4",
                     "en pause : 1"]
    assert all(li["t"] == "li" for li in legende["k"])
    masques = [li["k"][2] for li in legende["k"]]
    assert all(m["c"] == "masque" and m["x"] == " :" for m in masques)  # visible « Vous attend 3 »


@sans_node
def test_legende_attend_porte_le_nom_configure():
    etat = {**_comptes_maquette(), "utilisateur": " Camille "}
    racine = _tete(etat)
    items = ["".join(_textes(li)) for li in _classe(racine, "legende-repartition")[0]["k"]]
    assert items[0] == "Attend Camille : 3"
    # phrase-synthèse inchangée : adressée à la personne (« vous attend »)
    assert "vous attend" in "".join(_textes(_classe(racine, "synthese")[0]))


@sans_node
@pytest.mark.parametrize(("valeur", "attendu"), [
    (None, "Vous attend"), ("", "Vous attend"), ("  ", "Vous attend"), (7, "Vous attend"),
    ("Zoë", "Attend Zoë"), ("  Jean  Luc ", "Attend Jean  Luc"),
])
def test_titre_attente(valeur, attendu):
    etat = {} if valeur is None else {"utilisateur": valeur}
    assert _node(f"sortir([s.titreAttente({json.dumps(etat)}), s.titreAttente(null)]);") == [
        attendu, "Vous attend"]


@sans_node
def test_groupe_vide_sans_segment_ni_legende_et_a_classer_en_dernier():
    etat = _etat([], [], tourne=0, rien=3, familles={"stable": 1, "a-classer": 2}, stables=1)
    racine = _tete(etat)
    assert [s["c"] for s in _classe(racine, "barre-repartition")[0]["k"]] == [
        "segment segment-stable", "segment segment-a-classer"]
    assert ["".join(_textes(li)) for li in _classe(racine, "legende-repartition")[0]["k"]] == [
        "stables : 1", "à classer : 2"]
    # Comptes incohérents (suivis > 0, aucun groupe non nul) : ni barre ni légende vide nommée.
    incoherent = _tete(_etat([], [], rien=2, familles={}, stables=0))
    assert not _classe(incoherent, "barre-repartition")
    assert not _classe(incoherent, "legende-repartition")


def test_css_barre_ecart_et_forced_colors():
    css = (WEB / "appli.css").read_text(encoding="utf-8")
    barre = re.search(r"\.barre-repartition\s*\{([^}]*)\}", css).group(1)
    assert "gap: var(--espacement-1)" in barre and "height: 16px" in barre
    assert re.search(r"\.segment\s*\{[^}]*flex: 0 1 auto;[^}]*min-width: 0", css)
    assert re.search(r"\.segment-pause\s*\{[^}]*border: 2px solid var\(--neutre\)", css)
    forcees = css[css.index("@media (forced-colors: active)"):]
    forcees = forcees[:forcees.index("\n}\n")]
    assert re.search(r"\.segment\s*\{[^}]*forced-color-adjust: none;[^}]*background: CanvasText",
                     forcees)
    assert re.search(r"\.segment-pause\s*\{[^}]*border-color: CanvasText", forcees)


# --- Aides repliables ---------------------------------------------------------------------------

@sans_node
def test_aides_fermees_titres_et_contenu():
    racine = _tete(_comptes_maquette())
    aides = _classe(racine, "aide")
    assert [a["t"] for a in aides] == ["details", "details"]
    assert all("open" not in a["a"] for a in aides)
    resumes = [a["k"][0] for a in aides]
    assert [r["t"] for r in resumes] == ["summary", "summary"]
    assert [_textes(r) for r in resumes] == [
        ["Les types d'attente, en clair"], ["Quand un projet est-il stable ?"]]
    assert all(i["a"]["aria-hidden"] == "true" for r in resumes for i in r["k"] if i["t"] == "svg")
    types = _textes(aides[0])
    assert types[1] == (
        "Chaque carte Attend porte un type : il dit ce que la session attend de vous.")
    assert types[2:4] == ["choix", "Trancher entre des options ou valider une proposition."]
    assert ("Fournir une connexion, une clé, un compte, ou activer une ressource "
            "(Ollama, GPU).") in types
    stable = _textes(aides[1])
    assert stable[2:7] == ["Une release publiée", "Aucun commit hors docs/chore depuis la release",
                           "Aucune story ouverte", "Aucune PR ouverte", "CI de main verte"]
    assert stable[-1] == ("Stable, il va dans Rien à faire. Inactif sans être stable, il passe "
                          "dans "
                          "À relancer avec la raison « à stabiliser », suivie du premier critère "
                          "qui manque.")


@sans_node
def test_aides_ouvertes_survivent_aux_relectures_et_au_retour_d_onglet_sans_bouger_le_focus():
    etat = json.dumps(_comptes_maquette())
    sortie = _node(
        "const r = new N('main'); const h = new Date('2026-11-07T10:00:00Z');"
        "acc.rendreAccueil(r, null, h);"
        "const aides = () => { const out = []; const f = (n) => { if (n.className === "
        "'aide aide-types' || n.className === 'aide aide-stable') { out.push(n); }"
        " n.k.forEach(f); }; f(r); return out; };"
        "const [types, stable] = aides(); const fermees = [types.open, stable.open];"
        "types.open = true; const resume = types.k[0]; resume.focus();"
        f"acc.rendreAccueil(r, {etat}, h); acc.rendreAccueil(r, {etat}, h);"  # 30 s, Actualiser, F5
        "while (r.firstChild) { r.removeChild(r.firstChild); }"  # onglet Chantiers puis retour
        f"acc.rendreAccueil(r, {etat}, h);"
        "const [t2, s2] = aides();"
        "sortir({ fermees, meme: t2 === types && s2 === stable, ouvert: t2.open,"
        "  fermee: s2.open === undefined || s2.open === false,"
        "  focus: document.activeElement === resume,"
        "  ordre: r.k.map((n) => n.className) });"
    )
    assert sortie["fermees"] == [None, None] or sortie["fermees"] == [False, False]
    assert sortie["meme"] and sortie["ouvert"] is True and sortie["fermee"]
    assert sortie["focus"]
    # Ordre de lecture et de Tab dans main : titre masqué, tête (synthèse, barre, aides), kanban.
    assert sortie["ordre"] == ["masque", "tete", "kanban"]


@sans_node
def test_aucun_element_focalisable_avant_les_resumes_dans_main():
    racine = _node(
        "const r = new N('main');"
        f"acc.rendreAccueil(r, {json.dumps(_comptes_maquette())},"
        " new Date('2026-11-07T10:00:00Z'));"
        "sortir(plat(r));")
    focalisables = [n["t"] for n in _tous(racine) if n["t"] in {"summary", "button", "a"}
                    or "tabindex" in n["a"]]
    assert focalisables[:2] == ["summary", "summary"]


def test_css_aides_cote_a_cote_selon_la_largeur():
    css = (WEB / "appli.css").read_text(encoding="utf-8")
    assert re.search(r"\.aides\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\);", css)
    moyen = css[css.index("@media (min-width: 47.5em) {\n  .tete-haut"):]
    assert re.search(r"\.aides\s*\{\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);",
                     moyen[:moyen.index("\n}\n")])
    large = css[css.index("@media (min-width: 80em) {\n  .aides"):]
    assert "grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);" in large[:large.index("\n}\n")]
    # Types sur cinq colonnes seulement dès 1280 px (à 1 : 1, une aide fait ~350 px).
    assert "repeat(5" not in moyen[:moyen.index("\n}\n")]
    assert re.search(r"\.aide-types-liste\s*\{\s*grid-template-columns: repeat\(5,",
                     large[:large.index("\n}\n")])
    assert re.search(r"\.aide-resume\s*\{[^}]*min-height: 48px", css)
    synthese = (WEB / "synthese.js").read_text(encoding="utf-8")
    assert ".open" not in synthese  # l'appli ne pose jamais l'état des aides


# --- Aucun projet, chargement lent --------------------------------------------------------------

@sans_node
def test_aucun_projet_remplace_la_synthese_sans_bloc_ni_barre():
    racine = _tete(_etat())
    (phrase,) = _classe(racine, "synthese")
    assert phrase["t"] == "p" and phrase["x"] == AUCUN
    assert not _classe(racine, "bloc-stables") and not _classe(racine, "barre-repartition")
    assert not _classe(racine, "legende-repartition")
    assert len(_classe(racine, "aide")) == 2


@sans_node
def test_chargement_espaces_reserves_puis_donnees_et_aria_busy():
    sortie = _node(
        "const t = s.creerTete(); t.maj(null);"
        "const avant = plat(t.element);"
        f"t.maj({json.dumps(_comptes_maquette())}, new Date('2026-11-07T10:00:00Z'));"
        "const main = new N('main'); s.marquerOccupe(main, true); const occupe = { ...main.a };"
        "s.marquerOccupe(main, false);"
        "sortir({ avant, apres: plat(t.element), occupe, libre: main.a,"
        "  delai: s.DELAI_CHARGEMENT_MS });"
    )
    avant = sortie["avant"]
    reserves = _classe(avant, "reserve")
    assert [r["c"] for r in reserves] == ["reserve reserve-synthese", "reserve reserve-barre"]
    assert all(r["a"]["aria-hidden"] == "true" and r["k"] == [] for r in reserves)
    assert len(_classe(avant, "aide")) == 2
    assert not _classe(sortie["apres"], "reserve") and _classe(sortie["apres"], "synthese")
    assert sortie["occupe"] == {"aria-busy": "true"} and sortie["libre"] == {}
    assert sortie["delai"] == 300


def test_css_reserves_hauteur_fixe_sans_animation_et_app_js_branche_le_delai():
    css = (WEB / "appli.css").read_text(encoding="utf-8")
    for classe in (".reserve-synthese", ".reserve-barre"):
        regle = re.search(re.escape(classe) + r"\s*\{([^}]*)\}", css).group(1)
        assert "height:" in regle and "animation" not in regle
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "chargement = suivreChargement(contenu, rendreVue, window);" in app
    # Toute réponse lève l'attente : données (appliquer) comme erreur du premier chargement.
    appliquer = re.search(r"function appliquer\(donnees\) \{(.*?)\n\}", app, re.DOTALL).group(1)
    assert "chargement.finir();" in appliquer
    lire = re.search(r"async function lireEtat\(\) \{(.*?)\n\}", app, re.DOTALL).group(1)
    echec = lire[lire.index("annoncerLecture = false;\n  if (etat === null)"):]
    assert echec.index("chargement.finir();") < echec.index("if (statut === 0)")


_MINUTEUR = (
    "const file = []; const minuteur = {"
    "  setTimeout(f, d) { file.push({ f, d, vivant: true }); return file.length - 1; },"
    "  clearTimeout(i) { file[i].vivant = false; } };"
    "const tirer = () => { for (const m of file) { if (m.vivant) { m.vivant = false; m.f(); } } };"
)


@sans_node
def test_chargement_lent_puis_reponse_retire_aria_busy_et_les_reserves():
    sortie = _node(
        _MINUTEUR
        + "const main = new N('main'); let rendus = 0;"
        "const c = s.suivreChargement(main, () => { rendus += 1; }, minuteur); c.demarrer();"
        "const avant = { ...main.a }; tirer();"
        "const lent = { a: { ...main.a }, lent: c.lent(), rendus, delai: file[0].d };"
        "c.finir();"
        "sortir({ avant, lent, apres: { a: main.a, lent: c.lent() } });"
    )
    assert sortie["avant"] == {}
    assert sortie["lent"] == {"a": {"aria-busy": "true"}, "lent": True, "rendus": 1, "delai": 300}
    assert sortie["apres"] == {"a": {}, "lent": False}


@sans_node
def test_reponse_en_erreur_avant_300_ms_jamais_occupe():
    # Statut 0, 401, 403 ou 500 au premier chargement : finir() avant le délai, rien ne suit.
    sortie = _node(
        _MINUTEUR
        + "const main = new N('main'); let rendus = 0;"
        "const c = s.suivreChargement(main, () => { rendus += 1; }, minuteur); c.demarrer();"
        "c.finir(); tirer();"
        "sortir({ a: main.a, lent: c.lent(), rendus });"
    )
    assert sortie == {"a": {}, "lent": False, "rendus": 0}
