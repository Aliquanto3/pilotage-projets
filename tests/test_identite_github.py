"""Accesseurs d'identité GitHub de `chemins` (story 7.1) : config.json et variables de test."""

import json

import pytest

from pilotage import chemins


@pytest.fixture
def config(monkeypatch, tmp_path):
    """`config.json` réellement lu : `PILOTAGE_RACINE_LOCALE` retirée, profil sous `tmp_path`."""
    monkeypatch.delenv(chemins.VARIABLE_RACINE)
    chemin = chemins.chemin_config()
    assert chemin.is_relative_to(tmp_path)
    chemin.parent.mkdir(parents=True, exist_ok=True)

    def ecrire(objet):
        chemin.write_text(json.dumps(objet), encoding="utf-8")

    return ecrire


def test_valeurs_de_test_neutres():
    assert chemins.proprietaire_github() == "proprio-test"
    assert chemins.depot_donnees() == "proprio-test/donnees-test"
    assert chemins.utilisateur() == "Personne Test"


def test_lues_dans_config_json(config, monkeypatch):
    # Variables de test ignorées hors `PILOTAGE_RACINE_LOCALE` : seule la config compte.
    monkeypatch.setenv(chemins.VARIABLE_PROPRIETAIRE, "ignore")
    config({"proprietaire_github": "Proprio-X", "depot_donnees": "Proprio-X/donnees.v2",
            "utilisateur": "Anaïs"})
    assert chemins.proprietaire_github() == "Proprio-X"  # casse gardée telle quelle
    assert chemins.depot_donnees() == "Proprio-X/donnees.v2"
    assert chemins.utilisateur() == "Anaïs"


@pytest.mark.parametrize("accesseur", [chemins.proprietaire_github, chemins.depot_donnees])
def test_absent_leve_sans_defaut(config, accesseur):
    config({"port": 50000})
    with pytest.raises(chemins.ConfigurationGithubAbsente):
        accesseur()
    assert issubclass(chemins.ConfigurationGithubAbsente, chemins.ErreurConfiguration)


def test_config_json_absent_leve(monkeypatch):
    monkeypatch.delenv(chemins.VARIABLE_RACINE)
    assert not chemins.chemin_config().exists()
    with pytest.raises(chemins.ConfigurationGithubAbsente, match="'depot_donnees' absent"):
        chemins.depot_donnees()
    assert chemins.utilisateur() == ""


@pytest.mark.parametrize("valeur", ["", 3, None, ["a"], "-a", "a-", "a_b", "a.b", "a" * 40,
                                    "a/b", " a"])
def test_proprietaire_invalide_dans_config(config, valeur):
    config({"proprietaire_github": valeur})
    with pytest.raises(chemins.ConfigurationGithubAbsente, match="'proprietaire_github'"):
        chemins.proprietaire_github()


@pytest.mark.parametrize("valeur", ["", 3, "a", "a/", "/b", "a/b/c", "-a/b", "a/-b", "a/b.git",
                                    "a/b.GIT", "a/..", "a/.", "a/x..y", "a/b c", "a/é",
                                    "a/" + "n" * 101, "a\\b"])
def test_depot_invalide_dans_config(config, valeur):
    config({"depot_donnees": valeur})
    with pytest.raises(chemins.ConfigurationGithubAbsente, match="'depot_donnees'"):
        chemins.depot_donnees()


@pytest.mark.parametrize("valeur", ["a", "A-1", "a" * 39, "x-y-z"])
def test_proprietaire_valide(monkeypatch, valeur):
    monkeypatch.setenv(chemins.VARIABLE_PROPRIETAIRE, valeur)
    assert chemins.proprietaire_github() == valeur


@pytest.mark.parametrize("valeur", ["a/b", "A-1/.b_c-d", "a/" + "n" * 100, "a/b.gitx"])
def test_depot_valide(monkeypatch, valeur):
    monkeypatch.setenv(chemins.VARIABLE_DEPOT_DONNEES, valeur)
    assert chemins.depot_donnees() == valeur


@pytest.mark.parametrize(("variable", "accesseur"), [
    (chemins.VARIABLE_PROPRIETAIRE, chemins.proprietaire_github),
    (chemins.VARIABLE_DEPOT_DONNEES, chemins.depot_donnees),
])
def test_variable_absente_ou_vide_leve(monkeypatch, variable, accesseur):
    monkeypatch.delenv(variable)
    with pytest.raises(chemins.ConfigurationGithubAbsente):
        accesseur()
    monkeypatch.setenv(variable, "")
    with pytest.raises(chemins.ConfigurationGithubAbsente):
        accesseur()


@pytest.mark.parametrize(("valeur", "attendu"), [
    ("  Joël  ", "Joël"),
    ("u" * 64, "u" * 64),
    ("u" * 65, ""),
    ("", ""),
    ("   ", ""),
    ("deux\nlignes", ""),
    ("retour\rchariot", ""),
    ("bip\x07", ""),
    ("invisible​", ""),
    ("sep ligne", ""),
    ("sk-abc", ""),
    ("Joe\u0308l", "Joël"),  # NFD recomposé (story 7.2)
    ("Nguye\u0302\u0303n", "Nguyễn"),
    ("# X", ""), ("Bob*", ""), ("a|b", ""), ("<b>", ""), ("x`y", ""), ("[x](y)", ""),
])
def test_utilisateur_invalide_traite_comme_absent(monkeypatch, valeur, attendu):
    monkeypatch.setenv(chemins.VARIABLE_UTILISATEUR, valeur)
    assert chemins.utilisateur() == attendu


def test_utilisateur_absent_ou_config_illisible(config, monkeypatch):
    config({"utilisateur": 12})
    assert chemins.utilisateur() == ""
    chemins.chemin_config().write_text("{pas du json", encoding="utf-8")
    assert chemins.utilisateur() == ""  # jamais d'exception
    with pytest.raises(chemins.ErreurConfiguration):
        chemins.depot_donnees()


def test_cle_invalide_ne_casse_pas_les_autres_lectures(config):
    config({"depot_donnees": "-invalide", "port": 50000})
    assert chemins.port_serveur() == 50000
    assert chemins.lire_config()["depot_donnees"] == "-invalide"  # brute, validée à l'accès


def test_utilisateur_nul_dans_config_traite_comme_absent(config):
    config({"utilisateur": "nul\x00"})  # impossible en variable d'environnement
    assert chemins.utilisateur() == ""


@pytest.mark.parametrize(("brut", "nom"), [
    ("Joe\u0308l", "Joël"), ("# X", ""), ("Bob (admin)", ""), ("  Zoë  ", "Zoë"),
])
def test_nom_identique_sur_les_trois_surfaces(monkeypatch, brut, nom):
    """Web (`/api/etat` rend `chemins.utilisateur()`), `TABLEAU.md` et préambule : même nom ou,
    tous ensemble, la formulation neutre (story 7.2, revue)."""
    from pilotage.noyau import cadrage, etat

    monkeypatch.setenv(chemins.VARIABLE_UTILISATEUR, brut)
    web = chemins.utilisateur()
    assert web == nom
    assert etat.libelle_action(etat.ATTEND, web) == (f"Attend {nom}" if nom else "Vous attend")
    preambule = cadrage.preambule("0" * 32, web)
    de = f"de {nom}" if nom else "de l'utilisateur"
    assert preambule.startswith(f"## Messages {de} (pilotage-projets)\n")
    assert cadrage.nom_sur(brut, "0" * 32) == nom  # noyau : même règle sur le nom brut
