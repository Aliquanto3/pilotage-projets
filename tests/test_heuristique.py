"""Noyau `heuristique` : question finale, notifications, précédence (pur, sans E/S)."""

import pytest

from pilotage.noyau import heuristique as h
from pilotage.noyau.heuristique import Detection


@pytest.mark.parametrize(("message", "attendu"), [
    ("Fait. Quelle option ?", "Quelle option ?"),
    ("Intro.\n\nOn continue ?\n", "On continue ?"),
    ("a\n- **Quoi faire ?**", "Quoi faire ?"),
    ("1. Choix A ?", "Choix A ?"),
    ("3 options ?", "3 options ?"),
    ("Je fais X. Ok ? Oui, vraiment ?", "Oui, vraiment ?"),
    ("Valider ?\n<!-- pilotage: reprise=\"x\" -->", "Valider ?"),
    ("?", ""),
    ("**?**", ""),
])
def test_question_finale(message, attendu):
    assert h.question_finale(message) == attendu


@pytest.mark.parametrize("message", [
    "Fait.", "Voulez-vous ? Non, c'est fini.", "```\nx = 1 ?\n```", "", "   ", None, 12, [],
])
def test_pas_de_question_finale(message):
    assert h.question_finale(message) is None
    assert h.depuis_stop(message) is None


def test_question_finale_bornee_a_la_fin_du_message():
    phrase = h.question_finale("x" * 100_000 + " Fini ?")
    assert phrase.endswith("Fini ?")
    assert len(phrase) == h.BORNE_ANALYSE


def test_depuis_stop():
    assert h.depuis_stop("Ok ?") == Detection(h.QUESTION_FINALE, "Ok ?")


def test_notification_askuserquestion_a_confirmer():
    """Forme supposée par la spine (fixture `-a-confirmer`) : message = texte de la question."""
    assert h.depuis_notification("elicitation_dialog", "  Quelle voie ?\n") == Detection(
        h.ASKUSERQUESTION, "Quelle voie ?"
    )


def test_notification_permission_a_confirmer():
    """Forme supposée (fixture `-a-confirmer`) : « ... permission to use <Outil> »."""
    d = h.depuis_notification("permission_prompt", "Claude needs your permission to use Bash")
    assert d == Detection(h.PERMISSION, "permission demandée : Bash")


def test_permission_sans_outil_reconnaissable_quoi_vide():
    assert h.depuis_notification("permission_prompt", "TEXTE FACTICE") == Detection(
        h.PERMISSION, ""
    )
    assert h.depuis_notification("permission_prompt", None) == Detection(h.PERMISSION, "")


def test_askuserquestion_sans_message_quoi_vide():
    assert h.depuis_notification("elicitation_dialog", None) == Detection(h.ASKUSERQUESTION, "")


@pytest.mark.parametrize("genre", ["idle_prompt", "auth_success", "", None, 3])
def test_autres_notifications_sans_effet(genre):
    assert h.depuis_notification(genre, "Quelle voie ?") is None


def test_detecter_selon_l_evenement():
    assert h.detecter({"hook_event_name": "Stop", "last_assistant_message": "Ok ?"}).source == (
        h.QUESTION_FINALE
    )
    assert h.detecter({"hook_event_name": "Notification", "notification_type": "permission_prompt",
                       "message": "use Edit"}).quoi == "permission demandée : Edit"
    assert h.detecter({"hook_event_name": "SessionEnd"}) is None
    assert h.detecter("x") is None


SOURCES = [h.MARQUEUR, h.ASKUSERQUESTION, h.PERMISSION, h.QUESTION_FINALE]


@pytest.mark.parametrize(("i", "j"), [(i, j) for i in range(4) for j in range(i + 1, 4)])
def test_precedence_par_paire(i, j):
    haut, bas = Detection(SOURCES[i], "haut"), Detection(SOURCES[j], "bas")
    assert h.choisir(haut, bas) is haut
    assert h.choisir(bas, haut) is haut


def test_choisir_ignore_none_et_vide():
    d = Detection(h.PERMISSION, "")
    assert h.choisir(None, d, None) is d
    assert h.choisir() is None
    assert h.choisir(None) is None


@pytest.mark.parametrize("message", [
    "Ouvre https://ex.fr/?",
    "Voir www.ex.fr/page?",
    "Exemple :\n    print(x?)",
    "Exemple :\n\tx = a?",
    "```\nx = a?",
    "Texte.\n~~~py\ny = b ?",
])
def test_url_code_indente_bloc_non_ferme_pas_une_question(message):
    assert h.question_finale(message) is None


@pytest.mark.parametrize(("message", "attendu"), [
    ("```\nx = 1\n```\nOn garde ce code ?", "On garde ce code ?"),
    ("Voir https://ex.fr. Je publie ?", "Je publie ?"),
])
def test_question_apres_code_ou_url(message, attendu):
    assert h.question_finale(message) == attendu


def test_source_de_une_attente_ecrite():
    assert h.source_de({"quoi": "q", "depuis": "d"}) == h.MARQUEUR  # attente de 2.3
    assert h.source_de({"source": "permission"}) == h.PERMISSION
    assert h.source_de({"source": "inconnue"}) == h.MARQUEUR
    assert h.source_de(None) == h.MARQUEUR


def test_sources_du_schema_session():
    from pilotage.noyau.schemas import session

    assert set(h.PRIORITE) == session.SOURCES_ATTENTE
    assert h.MILIEU_DE_TOUR == {h.ASKUSERQUESTION, h.PERMISSION}
