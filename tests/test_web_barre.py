"""Barre du haut (story 9.4) sous node, faux DOM `tests/faux_dom.mjs` : bouton « Rapport de la
semaine » après Sync, `majRapport` indépendant de `majOccupe`, textes de `texteRapport`.

Sauté sans `node` (échec si `PILOTAGE_EXIGER_NODE=1`).
"""

import json

import pytest

from tests.test_web_tiroir import executer, sans_node, url

ENTETE = (
    f"const B = await import({json.dumps(url('barre.js'))});\n"
    "const sortir = (v) => process.stdout.write(JSON.stringify(v));\n"
    "const appels = [];\n"
    "const barre = B.construireBarre({ onglet: (n) => appels.push(`onglet:${n}`),"
    " actualiser: () => appels.push('actualiser'), scan: () => appels.push('scan'),"
    " sync: () => appels.push('sync'), rapport: () => appels.push('rapport') });\n"
    "const boutons = parClasse(barre.element, 'btn2');\n"
    "const etats = () => boutons.map((b) => b.getAttribute('aria-disabled'));\n"
)
INJOIGNABLE = "Serveur local injoignable. Relancez l'appli par lancer.py."


def _barre(corps: str):
    return executer(corps, ENTETE)


@sans_node
def test_bouton_rapport_apres_sync_bouton_secondaire():
    sortie = _barre(
        "sortir({ libelles: boutons.map(texte), types: boutons.map((b) => b.type),"
        " classes: boutons.map((b) => b.className) });")
    assert sortie["libelles"] == ["Actualiser", "Scan", "Sync", "Rapport de la semaine"]
    assert sortie["types"] == ["button"] * 4
    assert sortie["classes"] == ["btn2"] * 4


@sans_node
def test_clic_appelle_rappel_rapport_sauf_si_desactive():
    sortie = _barre(
        "const r = boutons[3];"
        "r.click();"
        "barre.majRapport(true);"
        "r.click();"
        "const pendant = r.getAttribute('aria-disabled');"
        "barre.majRapport(false);"
        "r.click();"
        "sortir({ appels, pendant, apres: r.getAttribute('aria-disabled') });")
    assert sortie == {"appels": ["rapport", "rapport"], "pendant": "true", "apres": None}


@sans_node
def test_maj_rapport_et_maj_occupe_independants():
    sortie = _barre(
        "const a = etats();"
        "barre.majOccupe(true); const b = etats();"
        "barre.majRapport(true); const c = etats();"
        "barre.majOccupe(false); const d = etats();"
        "barre.majRapport(false); const e = etats();"
        "sortir([a, b, c, d, e]);")
    assert sortie == [
        [None, None, None, None],
        [None, "true", "true", None],
        [None, "true", "true", "true"],
        [None, None, None, "true"],
        [None, None, None, None],
    ]


def _texte(statut, corps):
    return executer(
        f"sortir(B.texteRapport({json.dumps(statut)}, {json.dumps(corps)}));",
        f"const B = await import({json.dumps(url('barre.js'))});\n"
        "const sortir = (v) => process.stdout.write(JSON.stringify(v));\n",
    )


def _succes(semaine):
    return {"ok": True, "donnees": {"type": "rapport", "etat": "ouvert", "semaine": semaine}}


@sans_node
def test_texte_succes_avec_semaine():
    assert _texte(200, _succes("2026-W46")) == {
        "annonce": "Rapport de la semaine 2026-W46 ouvert dans le navigateur."}


@sans_node
@pytest.mark.parametrize("semaine", [
    "2026-W4", "26-W46", "2026-w46", "2026-W46\n", " 2026-W46", "<b>2026-W46</b>",
    "C:\\rapports", 202646, None,
])
def test_texte_succes_semaine_invalide_non_affichee(semaine):
    assert _texte(200, _succes(semaine)) == {
        "annonce": "Rapport de la semaine ouvert dans le navigateur."}


@sans_node
@pytest.mark.parametrize("corps", [None, {}, {"donnees": None}, {"donnees": "x"}])
def test_texte_succes_corps_inattendu(corps):
    assert _texte(200, corps) == {"annonce": "Rapport de la semaine ouvert dans le navigateur."}


@sans_node
def test_texte_deja_en_cours():
    corps = {"ok": False, "donnees": {"type": "rapport", "etat": "deja_en_cours"},
             "erreur": "déjà en cours"}
    assert _texte(409, corps) == {"annonce": "Un rapport est déjà en cours."}


@sans_node
@pytest.mark.parametrize(("statut", "corps", "attendu"), [
    (500, {"ok": False, "erreur": "rapport impossible"}, "rapport impossible"),
    (500, {"ok": False, "erreur": "page générée, ouverture impossible"},
     "page générée, ouverture impossible"),
    (400, {"ok": False, "erreur": "corps refusé"}, "corps refusé"),
    (500, None, "Erreur du serveur local."),
    (502, {"erreur": ""}, "Erreur du serveur local."),
    (500, {"erreur": 3}, "Erreur du serveur local."),
    (0, None, INJOIGNABLE),
])
def test_texte_erreurs(statut, corps, attendu):
    assert _texte(statut, corps) == {"erreur": attendu}
