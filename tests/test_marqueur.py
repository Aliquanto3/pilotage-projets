"""`noyau/marqueur` : grammaire, un test par cas mal formé, jamais d'exception."""

import pytest

from pilotage.noyau import marqueur
from pilotage.noyau.marqueur import AUCUN, lire

ATTENTE = '<!-- pilotage: action=attend-utilisateur | type=choix | quoi="Quelle option ?" -->'


def test_attente_complete():
    assert lire(ATTENTE) == (("choix", "Quelle option ?"), None)


def test_attente_en_fin_de_message_apres_du_texte():
    message = f"Fin du travail.\n\n{ATTENTE}\n\n  \r\n"
    assert lire(message) == (("choix", "Quelle option ?"), None)


def test_marqueur_en_fin_de_ligne_de_texte():
    assert lire(f"Je m'arrête ici. {ATTENTE}").attente == ("choix", "Quelle option ?")


@pytest.mark.parametrize(
    "message",
    [
        f"Exemple :\n\n{ATTENTE}\n\nVoilà comment l'écrire.",  # exemple cité dans la prose
        f"```\n{ATTENTE}\n```",  # exemple dans un bloc de code
        f"{ATTENTE} suivi de texte",
        f"Fin du travail.\n\n{ATTENTE}\nMerci",
    ],
)
def test_marqueur_suivi_de_texte_ignore(message):
    assert lire(message) == AUCUN


def test_seul_le_bloc_final_compte():
    message = (
        '<!-- pilotage: reprise="ancienne" -->\nTexte.\n'
        f'{ATTENTE}\n\n<!-- pilotage: reprise="r" -->'
    )
    assert lire(message) == (("choix", "Quelle option ?"), "r")


@pytest.mark.parametrize("genre", ["choix", "test", "donnees", "acces"])
def test_types_gardes(genre):
    message = f'<!-- pilotage: action=attend-utilisateur | type={genre} | quoi="q" -->'
    assert lire(message).attente == (genre, "q")


@pytest.mark.parametrize("genre", ["decision", "Choix", "CHOIX", "a-qualifier", '""', '"choix "'])
def test_type_inconnu_omis(genre):
    message = f'<!-- pilotage: action=attend-utilisateur | type={genre} | quoi="q" -->'
    assert lire(message).attente == (None, "q")


def test_sans_type():
    assert lire('<!-- pilotage: action=attend-utilisateur | quoi="q" -->').attente == (None, "q")


def test_type_entre_guillemets_accepte():
    message = '<!-- pilotage: action=attend-utilisateur | type="test" | quoi="q" -->'
    assert lire(message).attente == ("test", "q")


def test_quoi_peut_contenir_barre_et_signe_egal():
    message = '<!-- pilotage: action=attend-utilisateur | quoi="a | b=c" -->'
    assert lire(message).attente == (None, "a | b=c")


def test_reprise():
    assert lire('<!-- pilotage: reprise="Reprendre à l\'étape 3" -->') == (
        None, "Reprendre à l'étape 3"
    )


def test_attente_et_reprise_dans_un_meme_marqueur():
    message = '<!-- pilotage: action=attend-utilisateur | quoi="q" | reprise="r" -->'
    assert lire(message) == ((None, "q"), "r")


def test_deux_genres_dans_deux_marqueurs():
    message = f'{ATTENTE}\n<!-- pilotage: reprise="r" -->'
    assert lire(message) == (("choix", "Quelle option ?"), "r")


# --- Cas mal formés de la story ---------------------------------------------------------------


def test_guillemet_non_ferme():
    assert lire('<!-- pilotage: action=attend-utilisateur | quoi="jamais fermé -->') == AUCUN


def test_guillemet_non_ferme_puis_marqueur_valide_apres():
    message = '<!-- pilotage: action=attend-utilisateur | quoi="x -->\n' + ATTENTE
    assert lire(message).attente == ("choix", "Quelle option ?")


@pytest.mark.parametrize("quoi", ['""', '"   "', '"\t"'])
def test_quoi_vide(quoi):
    assert lire(f"<!-- pilotage: action=attend-utilisateur | type=choix | quoi={quoi} -->") == AUCUN


def test_quoi_absent():
    assert lire("<!-- pilotage: action=attend-utilisateur | type=choix -->") == AUCUN


def test_action_inconnue():
    assert lire('<!-- pilotage: action=autre | quoi="q" -->') == AUCUN


def test_champs_inconnus_ignores():
    message = '<!-- pilotage: action=attend-utilisateur | urgence=haute | quoi="q" | x_y="z" -->'
    assert lire(message).attente == (None, "q")


def test_deux_marqueurs_d_attente_le_dernier_l_emporte():
    message = (
        '<!-- pilotage: action=attend-utilisateur | type=test | quoi="premier" -->\n'
        '<!-- pilotage: action=attend-utilisateur | type=acces | quoi="second" -->'
    )
    assert lire(message).attente == ("acces", "second")


def test_dernier_marqueur_vide_ne_masque_pas_le_precedent_valide():
    message = (
        '<!-- pilotage: action=attend-utilisateur | quoi="premier" -->\n'
        '<!-- pilotage: action=attend-utilisateur | quoi="" -->'
    )
    assert lire(message).attente == (None, "premier")


def test_deux_reprises_la_derniere_l_emporte():
    message = '<!-- pilotage: reprise="a" -->\n<!-- pilotage: reprise="b" -->'
    assert lire(message).reprise == "b"


def test_separateur_final_tolere():
    assert lire('<!-- pilotage: action=attend-utilisateur | quoi="q" | -->').attente == (None, "q")


def test_type_sans_valeur_rend_le_marqueur_mal_forme():
    assert lire('<!-- pilotage: action=attend-utilisateur | type= | quoi="q" -->') == AUCUN


def test_champ_repete_dans_un_marqueur_le_dernier_l_emporte():
    assert lire('<!-- pilotage: reprise="a" | reprise="b" -->').reprise == "b"


def test_reprise_vide():
    assert lire('<!-- pilotage: reprise="" -->') == AUCUN


@pytest.mark.parametrize(
    "message",
    [
        "<!-- pilotage: -->",
        "<!-- pilotage: action -->",
        "<!-- pilotage: action= -->",
        '<!-- pilotage: action=attend-utilisateur quoi="q" -->',  # séparateur manquant
        '<!-- pilotage: action=attend-utilisateur | | quoi="q" -->',
        '<!-- pilotage: Action=attend-utilisateur | quoi="q" -->',  # clé en majuscules
        '<!-- pilotage: action=attend-utilisateur | quoi="a"b" -->',
        '<!-- pilotage: action=attend-utilisateur | quoi="q"',  # commentaire non fermé
        '<!-- pilotage: action=attend-utilisateur | quoi="q" ->',
        '<!-- pilotage: action=attend-utilisateur |\nquoi="q" -->',  # sur deux lignes
        '<!--pilotage action=attend-utilisateur | quoi="q" -->',  # deux-points manquant
        '<!-- pilotag: action=attend-utilisateur | quoi="q" -->',
    ],
)
def test_mal_forme_ignore(message):
    assert lire(message) == AUCUN


def test_corps_trop_long_ignore():
    quoi = "x" * (marqueur.BORNE_CORPS + 1)
    assert lire(f'<!-- pilotage: action=attend-utilisateur | quoi="{quoi}" -->') == AUCUN


def test_quoi_long_mais_dans_la_borne_du_corps_est_rendu_brut():
    quoi = "x" * 500  # la troncature à 200 est faite par `texte.nettoyer`, à l'écriture
    message = f'<!-- pilotage: action=attend-utilisateur | quoi="{quoi}" -->'
    assert lire(message).attente == (None, quoi)


def test_marqueur_dans_un_marqueur_non_ferme_ne_bloque_pas():
    message = "<!-- pilotage: " * 500 + ATTENTE
    assert lire(message).attente == ("choix", "Quelle option ?")


# --- Jamais d'exception -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [None, 12, b"<!-- pilotage: reprise=\"r\" -->", ["x"], {"a": 1}, "", "\x00", "\ud800",
     "<!--" * 10000, "<!-- pilotage:" + '"' * 5000, "é" * 100000, "\u202e<!-- pilotage: -->"],
)
def test_ne_leve_jamais(message):
    assert lire(message) == AUCUN


def test_substitut_isole_ignore_le_marqueur():
    # Sinon le *quoi* passerait la lecture puis ferait échouer l'écriture du Stop (schéma).
    message = ('<!-- pilotage: action=attend-utilisateur | quoi="a\ud800b" -->\n'
               '<!-- pilotage: reprise="ok" -->')
    assert lire(message) == marqueur.Marqueurs(None, "ok")


# --- Story 7.2 : `attend-utilisateur`, ancienne valeur lue -------------------------------------


def test_action_attente_renommee_et_alias_d_entree():
    assert marqueur.ACTION_ATTENTE == "attend-utilisateur"
    assert marqueur.ACTION_ATTENTE_ANCIENNE == "attend-anael"
    assert marqueur.ACTIONS_ATTENTE == {"attend-utilisateur", "attend-anael"}


@pytest.mark.parametrize("action", ["attend-utilisateur", "attend-anael"])
def test_ancienne_et_nouvelle_action_lues_pareil(action):
    message = (f'Fin.\n<!-- pilotage: action={action} | type=test | quoi="Lancer X" '
               '| reprise="r" -->')
    assert lire(message) == (("test", "Lancer X"), "r")


def test_ancienne_action_puis_nouvelle_la_derniere_l_emporte():
    message = (
        '<!-- pilotage: action=attend-anael | type=choix | quoi="avant" -->\n'
        '<!-- pilotage: action=attend-utilisateur | type=acces | quoi="après" -->'
    )
    assert lire(message).attente == ("acces", "après")


@pytest.mark.parametrize(
    "action", ["attend-" + "Ana" + "el", "attend-ana\u00ebl", "attend", "attend-autre"]
)
def test_autre_action_proche_ignoree(action):
    assert lire(f'<!-- pilotage: action={action} | quoi="q" -->') == AUCUN
