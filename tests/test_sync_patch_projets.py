"""Patch ciblé du texte de `projets.yaml` (story 5.1, M7) : commentaires et ordre conservés."""

import pytest

from pilotage.scan import inventaire
from pilotage.sync import patch_projets
from pilotage.sync.patch_projets import PatchImpossible, appliquer

COMMENTE = """\
# projets.yaml de l'utilisateur : ne pas réordonner
schema: 1
chantiers:
  Pilotage:   # chantier principal
    projets:
      - pilotage-projets  # le tableau de bord
      - projet-a
  Recherche:
    projets:
      - projet-b
dependances:
  - "pilotage-projets ← projet-a"
exclus:
  - vieux-depot   # abandonné
pauses:
  projet-b:
    revue: 2026-12-01  # après le bench
# fin
"""


def lire(texte):
    config, recent, alertes = inventaire.analyser_projets(texte)
    assert alertes == [] and not recent
    return config


def test_valeurs_et_projection():
    config = lire(COMMENTE)
    assert patch_projets.valeurs(config, "projet-b") == {
        "chantier": "Recherche", "exclu": False, "pause": "2026-12-01"
    }
    assert patch_projets.valeurs(config, "vieux-depot") == {
        "chantier": None, "exclu": True, "pause": None
    }
    assert patch_projets.valeurs(config, "inconnu") == patch_projets.DEFAUT
    assert sorted(patch_projets.projection(config)["projets"]) == [
        "pilotage-projets", "projet-a", "projet-b", "vieux-depot"
    ]


def test_pause_posee_dans_un_bloc_existant():
    resultat = appliquer(COMMENTE, "projet-a", "pause", None, "2027-01-15")
    assert resultat == COMMENTE.replace(
        "    revue: 2026-12-01  # après le bench\n",
        "    revue: 2026-12-01  # après le bench\n  projet-a:\n    revue: 2027-01-15\n",
    )
    assert patch_projets.valeurs(lire(resultat), "projet-a")["pause"] == "2027-01-15"


def test_date_de_pause_remplacee_commentaire_garde():
    resultat = appliquer(COMMENTE, "projet-b", "pause", "2026-12-01", "2027-02-01")
    assert resultat == COMMENTE.replace("revue: 2026-12-01  #", "revue: 2027-02-01  #")


def test_pause_levee_retire_le_bloc_seulement():
    resultat = appliquer(COMMENTE, "projet-b", "pause", "2026-12-01", None)
    assert resultat == COMMENTE.replace(
        "  projet-b:\n    revue: 2026-12-01  # après le bench\n", ""
    )
    assert lire(resultat)["pauses"] is None  # `pauses:` vide se lit comme vide


def test_exclusion_ajoutee_puis_retiree():
    ajoute = appliquer(COMMENTE, "projet-b2", "exclu", False, True)
    assert ajoute == COMMENTE.replace(
        "  - vieux-depot   # abandonné\n", "  - vieux-depot   # abandonné\n  - projet-b2\n"
    )
    retire = appliquer(COMMENTE, "vieux-depot", "exclu", True, False)
    assert retire == COMMENTE.replace("  - vieux-depot   # abandonné\n", "")


def test_chantier_change_de_liste():
    resultat = appliquer(COMMENTE, "projet-a", "chantier", "Pilotage", "Recherche")
    assert resultat == COMMENTE.replace("      - projet-a\n", "").replace(
        "      - projet-b\n", "      - projet-b\n      - projet-a\n"
    )


def test_rattachement_d_un_projet_a_classer_et_retrait():
    rattache = appliquer(COMMENTE, "nouveau", "chantier", None, "Pilotage")
    assert "      - projet-a\n      - nouveau\n  Recherche:" in rattache
    detache = appliquer(COMMENTE, "projet-b", "chantier", "Recherche", None)
    assert detache == COMMENTE.replace("      - projet-b\n", "")
    assert lire(detache)["chantiers"]["Recherche"] == {"projets": None}


def test_cles_absentes_creees_en_fin_de_fichier():
    texte = "schema: 1  # minimal\n"
    assert appliquer(texte, "demo", "exclu", False, True) == texte + "exclus:\n  - demo\n"
    assert appliquer(texte, "demo", "pause", None, "2026-12-01") == (
        texte + "pauses:\n  demo:\n    revue: 2026-12-01\n"
    )
    sans_fin = "schema: 1"
    assert appliquer(sans_fin, "demo", "exclu", False, True) == "schema: 1\nexclus:\n  - demo\n"


def test_cle_vide_remplie_sous_la_cle():
    texte = "schema: 1\nexclus:   # rien\npauses:\n# fin\n"
    assert appliquer(texte, "demo", "exclu", False, True) == (
        "schema: 1\nexclus:   # rien\n  - demo\npauses:\n# fin\n"
    )
    assert appliquer(texte, "demo", "pause", None, "2026-12-01") == (
        "schema: 1\nexclus:   # rien\npauses:\n  demo:\n    revue: 2026-12-01\n# fin\n"
    )
    explicite = "schema: 1\nexclus: ~\n"
    assert appliquer(explicite, "demo", "exclu", False, True) == "schema: 1\nexclus: [demo]\n"


def test_listes_en_flux_sur_une_ligne():
    texte = "schema: 1\nexclus: [a, 'b']  # liste\n"
    assert appliquer(texte, "c", "exclu", False, True) == (
        "schema: 1\nexclus: [a, 'b', c]  # liste\n"
    )
    assert appliquer(texte, "a", "exclu", True, False) == "schema: 1\nexclus: ['b']  # liste\n"
    pauses = "schema: 1\npauses: {a: {revue: 2026-01-01}, b: {revue: 2026-02-02}}\n"
    assert appliquer(pauses, "a", "pause", "2026-01-01", None) == (
        "schema: 1\npauses: {b: {revue: 2026-02-02}}\n"
    )
    assert appliquer(pauses, "b", "pause", "2026-02-02", "2026-03-03") == (
        "schema: 1\npauses: {a: {revue: 2026-01-01}, b: {revue: 2026-03-03}}\n"
    )


def test_nom_ambigu_rendu_entre_apostrophes():
    resultat = appliquer("schema: 1\n", "null", "exclu", False, True)
    assert resultat == "schema: 1\nexclus:\n  - 'null'\n"
    assert lire(resultat)["exclus"] == ["null"]
    assert appliquer("schema: 1\n", "1.5", "exclu", False, True).endswith("  - '1.5'\n")


def test_fins_de_ligne_crlf_conservees():
    texte = COMMENTE.replace("\n", "\r\n")
    resultat = appliquer(texte, "projet-b2", "exclu", False, True)
    assert resultat == texte.replace(
        "  - vieux-depot   # abandonné\r\n", "  - vieux-depot   # abandonné\r\n  - projet-b2\r\n"
    )
    assert "\n" not in resultat.replace("\r\n", "")


@pytest.mark.parametrize("texte, projet, champ, courant, voulu", [
    # chantier voulu absent, ou sans liste
    (COMMENTE, "projet-b", "chantier", "Recherche", "Inconnu"),
    ("schema: 1\nchantiers:\n  A:\n", "x", "chantier", None, "A"),
    ("schema: 1\nchantiers:\n  A: {}\n", "x", "chantier", None, "A"),
    # liste en flux sur plusieurs lignes
    ("schema: 1\nexclus: [a,\n  b]\n", "c", "exclu", False, True),
    # élément introuvable, ou en double
    ("schema: 1\nexclus:\n  - a\n  - b\n", "z", "exclu", True, False),
    ("schema: 1\nexclus:\n  - a\n  - a\n", "a", "exclu", True, False),
    # pauses en flux non vide pour un nouveau projet
    ("schema: 1\npauses: {a: {revue: 2026-01-01}}\n", "b", "pause", None, "2026-02-02"),
    # racine en flux
    ("{schema: 1, exclus: [a]}\n", "b", "exclu", False, True),
    # YAML invalide
    ("schema: [\n", "b", "exclu", False, True),
])
def test_patch_impossible(texte, projet, champ, courant, voulu):
    with pytest.raises(PatchImpossible):
        appliquer(texte, projet, champ, courant, voulu)


def test_scalaire_de_liste_sur_plusieurs_lignes_impossible():
    texte = "schema: 1\nexclus:\n  - \"a\n    b\"\n"
    with pytest.raises(PatchImpossible):
        appliquer(texte, "a b", "exclu", True, False)
