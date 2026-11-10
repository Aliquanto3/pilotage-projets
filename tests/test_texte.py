"""Texte libre : filtre de secrets, séquence de `nettoyer`, normalisation de la racine, bornes."""

import pytest

from pilotage.noyau import texte
from pilotage.noyau.texte import ErreurTexte, nettoyer

MOTIFS = ["sk-", "ghp_", "gho_", "ghu_", "ghs_", "github_pat_", "AKIA", "-----BEGIN", "Bearer",
          "KEY=", "sk_live_", "sk_test_", "xoxb-", "xoxp-", "glpat-", "hf_", "TOKEN=", "SECRET=",
          "PASSWORD="]


# Contournements relevés par le second avis de la story 2.3 : rendus `sk-` / `ghp_` à l'affichage.
@pytest.mark.parametrize("deguise", [
    "s̸k-ABCDEF0123456789",  # combinant (Mn)
    "sḱ-ABCDEF",  # accent combinant
    "sk️-ABCDEF",  # sélecteur de variante
    "sk‐-ABCDEF",  # trait d'union Unicode (Pd)
    "&#115;k-ABCDEF",  # entité HTML
    "&amp;#115;k-ABCDEF",  # entité doublement échappée
    "ghp\\_ABCDEF",  # échappement Markdown
    "API_KEY = abc",  # blancs autour de `=`
    "hf_ABCDEFabcdef",  # jeton Hugging Face
])
def test_contournements_supprimes(deguise):
    assert nettoyer(f"avant {deguise} après", 200) == ""


@pytest.mark.parametrize("sain", [
    "Créer la PR de l’étape 3 — après relecture", "café-crème", "tests_unitaires",
    "Lien &amp; texte", "Choisir la suite ?",
])
def test_texte_sain_garde(sain):
    assert nettoyer(sain, 200) == sain


def test_motifs_attendus():
    assert list(texte.MOTIFS_SECRETS) == MOTIFS


@pytest.mark.parametrize("motif", MOTIFS)
@pytest.mark.parametrize("variante", [str, str.lower, str.upper])
def test_motif_supprime_entierement(motif, variante):
    secret = variante(motif)
    assert nettoyer(f"avant {secret}abc123 après", 100) == ""
    assert nettoyer(secret, 100) == ""


def test_texte_sain_conserve():
    assert nettoyer("Corriger le bug du scan", 200) == "Corriger le bug du scan"


def test_troncature_en_points_de_code():
    assert nettoyer("é" * 10, 4) == "éééé"
    assert nettoyer("😀" * 10, 3) == "😀😀😀"
    assert nettoyer("abc", 0) == ""
    assert nettoyer("abc", 3) == "abc"


@pytest.mark.parametrize("motif", MOTIFS)
def test_motif_a_cheval_sur_la_borne(motif):
    # Le motif commence avant la borne et finit après : le texte entier part, pas de reste tronqué.
    borne = 10
    brut = "x" * (borne - 2) + motif + "zzzz"
    assert nettoyer(brut, borne) == ""


@pytest.mark.parametrize("motif", MOTIFS)
def test_motif_apres_la_borne_est_supprime_aussi(motif):
    assert nettoyer("x" * 10 + motif, 10) == ""


def test_motif_complet_juste_avant_la_borne_supprime():
    assert nettoyer("ab AKIA", 7) == ""
    assert nettoyer("ab AKI", 6) == "ab AKI"


def test_borne_invalide():
    for borne in (-1, True, 1.5, "3"):
        with pytest.raises(ErreurTexte, match="borne"):
            nettoyer("a", borne)
    with pytest.raises(ErreurTexte, match="chaîne"):
        nettoyer(None, 3)


# --- normalisation de la racine GitHub ---

RACINE = "C:\\Users\\Moi\\Documents\\GitHub"


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("C:\\Users\\Moi\\Documents\\GitHub\\p\\x.py", "{{RACINE_GITHUB}}\\p\\x.py"),
        ("C:/Users/Moi/Documents/GitHub/p/x.py", "{{RACINE_GITHUB}}/p/x.py"),
        ("c:\\users\\moi\\documents\\github\\p", "{{RACINE_GITHUB}}\\p"),
        ("C:\\Users\\Moi\\Documents\\GitHub", "{{RACINE_GITHUB}}"),
        ("voir 'C:\\Users\\Moi\\Documents\\GitHub\\p' et C:/Users/Moi/Documents/GitHub.",
         "voir '{{RACINE_GITHUB}}\\p' et {{RACINE_GITHUB}}."),
        ("C:\\Users\\Moi\\Documents\\GitHubAutre\\p", "C:\\Users\\Moi\\Documents\\GitHubAutre\\p"),
        ("D:\\Users\\Moi\\Documents\\GitHub\\p", "D:\\Users\\Moi\\Documents\\GitHub\\p"),
        ("sans chemin", "sans chemin"),
    ],
)
def test_normaliser_racine_windows(brut, attendu):
    assert texte.normaliser_racine(brut, RACINE) == attendu


@pytest.mark.parametrize(
    "racine", ["C:/Users/Moi/Documents/GitHub/", "c:\\Users\\Moi\\Documents\\GitHub\\"]
)
def test_normaliser_racine_variantes_de_la_racine(racine):
    assert texte.normaliser_racine("C:\\Users\\Moi\\Documents\\GitHub\\p", racine) == (
        "{{RACINE_GITHUB}}\\p"
    )


def test_normaliser_racine_posix():
    racine = "/home/moi/GitHub"
    assert texte.normaliser_racine("/home/moi/GitHub/p/x", racine) == "{{RACINE_GITHUB}}/p/x"
    assert texte.normaliser_racine("/autre/home/moi/GitHub/p", racine) == "/autre/home/moi/GitHub/p"


def test_normaliser_racine_vide():
    with pytest.raises(ErreurTexte, match="racine"):
        texte.normaliser_racine("x", "")


def test_nettoyer_normalise_avant_de_tronquer():
    brut = "C:\\Users\\Moi\\Documents\\GitHub\\p"
    assert nettoyer(brut, 100, RACINE) == "{{RACINE_GITHUB}}\\p"
    assert nettoyer(brut, 100) == brut


# --- bornes ---


def test_bornes_constantes():
    assert (texte.BORNE_QUOI, texte.BORNE_NOTE, texte.BORNE_MESSAGE_OCTETS) == (200, 300, 2048)


@pytest.mark.parametrize("valider", [texte.valider_quoi, texte.valider_note])
@pytest.mark.parametrize("caractere", ["a", "é", "😀", "👨‍👩‍👧"[0]])
def test_borne_points_de_code_a_la_limite(valider, caractere):
    borne = texte.BORNE_QUOI if valider is texte.valider_quoi else texte.BORNE_NOTE
    assert valider(caractere * borne) == caractere * borne
    with pytest.raises(ErreurTexte, match=f"{borne + 1} points de code"):
        valider(caractere * (borne + 1))


def test_borne_compte_les_points_de_code_et_non_les_graphemes():
    famille = "👨‍👩‍👧"  # 5 points de code
    assert len(famille) == 5
    assert texte.valider_quoi(famille * 40) == famille * 40
    with pytest.raises(ErreurTexte):
        texte.valider_quoi(famille * 40 + "a")


def test_validateur_ne_tronque_pas():
    with pytest.raises(ErreurTexte):
        texte.valider_note("a" * 301)


def test_message_octets_a_la_limite():
    assert texte.valider_message("a" * 2048) == "a" * 2048
    assert texte.valider_message("😀" * 512) == "😀" * 512  # 4 octets chacun
    assert texte.valider_message("é" * 1024) == "é" * 1024  # 2 octets chacun
    with pytest.raises(ErreurTexte, match="2049 octets"):
        texte.valider_message("a" * 2049)
    with pytest.raises(ErreurTexte, match="2050 octets"):
        texte.valider_message("é" * 1024 + "ab")
    with pytest.raises(ErreurTexte):
        texte.valider_message("😀" * 512 + "a")


@pytest.mark.parametrize("valider", [texte.valider_quoi, texte.valider_note, texte.valider_message])
def test_borne_type_non_texte(valider):
    with pytest.raises(ErreurTexte, match="chaîne"):
        valider(12)


@pytest.mark.parametrize(
    "brut",
    ["s\u200bk-abc", "\uff53\uff4b\uff0dabc", "gh\u00adp_abc", "\ufeffAKIA123", "Bea\u2060rer x"],
)
def test_contournement_unicode_detecte(brut):
    assert nettoyer(brut, 100) == ""


def test_texte_garde_tel_quel_hors_secret():
    brut = "\uff21 caf\u00e9 \u200b ok"
    assert nettoyer(brut, 100) == brut


@pytest.mark.parametrize("valider", [texte.valider_quoi,
                                     texte.valider_note, texte.valider_message])
def test_substitut_isole_refuse(valider):
    with pytest.raises(ErreurTexte, match="substitut"):
        valider("a" + chr(0xD800) + "b")


# --- Story 7.2 : règle unique du nom affiché ---------------------------------------------------


@pytest.mark.parametrize(("brut", "attendu"), [
    ("Joël", "Joël"), ("Joe\u0308l", "Joël"), ("Nguye\u0302\u0303n", "Nguyễn"),
    ("  Jean-Luc   O’Neil ", "Jean-Luc O’Neil"), ("M. Durand", "M. Durand"), ("李小龍", "李小龍"),
    ("देवनागरी", "देवनागरी"), ("a" * 64, "a" * 64),
])
def test_nom_affiche_admis(brut, attendu):
    assert texte.nom_affiche(brut) == attendu


@pytest.mark.parametrize("brut", [
    None, 3, "", "  ", "a" * 65, "# X", "**gras**", "<b>", "x`y", "a|b", "[x](y)", "a/b", "a&b",
    "deux\nlignes", "tab\tulation", "invisible\u200b", "sk-abc",
])
def test_nom_affiche_refuse(brut):
    assert texte.nom_affiche(brut) == ""
