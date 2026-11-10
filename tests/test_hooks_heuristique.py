# ruff: noqa: F811, F401 - la fixture importée `racine` est reprise comme argument des tests
"""Heuristique de secours dans les hooks `Stop` et `Notification` (sous-processus `-I -S`).

Les tests `*_a_confirmer` reposent sur les fixtures `Notification-*-a-confirmer.json` : forme de
`AskUserQuestion` et de la permission native non observée en session interactive (AD-2). À rouvrir
si la capture interactive de la story 2.1 les contredit.
"""

import uuid

import pytest
from test_hooks_session import HOOKS, HORODATAGE, _journal, _lancer, _lire, _payload, _sans_sortie
from test_hooks_tour import ATTENTE, DEBUT, _attente, _creer, _prompt, _stop, racine

from pilotage.noyau import schemas

NOTIFICATION = HOOKS / "notification.py"
PERMISSION = "Notification-permission-a-confirmer"
QUESTION = "Notification-askuserquestion-a-confirmer"


def _notifier(racine, session, fixture=PERMISSION, **champs):
    payload = _payload(fixture, racine, session, **champs)
    _sans_sortie(_lancer(NOTIFICATION, payload))


def _permission(racine, session):
    _notifier(racine, session, message="Claude needs your permission to use Bash")


# --- une source, un cas ---------------------------------------------------------------------


def test_question_finale_ecrit_une_attente_sans_type(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, "Tout est prêt. Je lance le déploiement ?")
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert list(etat["attente"]) == ["quoi", "depuis", "source"]
    assert etat["attente"]["quoi"] == "Je lance le déploiement ?"
    assert HORODATAGE.fullmatch(etat["attente"]["depuis"])
    schemas.valider("session", etat)
    assert _journal(racine) == []


def test_question_finale_quoi_borne(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, "é" * 500 + " ?")
    assert _lire(chemin)["attente"]["quoi"] == ("é" * 500 + " ?")[:200]


def test_question_finale_quoi_supprime_par_le_filtre(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, "Utiliser la clé sk-abc123 ?")
    etat = _lire(chemin)
    assert etat["statut"] == "attente"  # l'attente est gardée, le *quoi* est vide
    assert etat["attente"]["quoi"] == ""
    assert "sk-abc123" not in chemin.read_text(encoding="utf-8")


def test_question_finale_quoi_vide_si_rien_d_exploitable(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, "Fini.\n\n?")
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert etat["attente"]["quoi"] == ""


def test_stop_sans_question_n_ecrit_rien(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, "Terminé, rien à demander.")
    etat = _lire(chemin)
    assert etat["statut"] == "active"
    assert "attente" not in etat


def test_askuserquestion_a_confirmer(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _notifier(racine, session, QUESTION, message="Quelle base de données ?")
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert list(etat["attente"]) == ["quoi", "depuis", "source"]
    assert etat["attente"]["quoi"] == "Quelle base de données ?"
    schemas.valider("session", etat)


def test_askuserquestion_fixture_telle_quelle_a_confirmer(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _notifier(racine, session, QUESTION)
    assert _lire(chemin)["attente"]["quoi"] == "TEXTE FACTICE (question)"


def test_permission_a_confirmer(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _permission(racine, session)
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert list(etat["attente"]) == ["quoi", "depuis", "source"]
    assert etat["attente"]["quoi"] == "permission demandée : Bash"


def test_permission_quoi_vide_si_outil_introuvable_a_confirmer(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _notifier(racine, session)  # message de la fixture : « TEXTE FACTICE (...) »
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert etat["attente"]["quoi"] == ""


def test_askuserquestion_quoi_supprime_par_le_filtre(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _notifier(racine, session, QUESTION, message="Utiliser ghp_abc123 ?")
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert etat["attente"]["quoi"] == ""
    assert "ghp_abc123" not in chemin.read_text(encoding="utf-8")


def test_notification_d_un_autre_type_sans_effet(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _notifier(racine, session, notification_type="idle_prompt")
    assert _lire(chemin)["statut"] == "active"
    assert "attente" not in _lire(chemin)


# --- précédence : marqueur > AskUserQuestion > permission > question finale ----------------------
# Chemin réel des hooks, chaque ordre d'arrivée. Entre deux événements, aucun prompt de
# l'utilisateur (un
# tour relancé par la fin d'un sous-agent, `<task-notification>`, n'efface rien, A1).


def _question(racine, session):
    _notifier(racine, session, QUESTION, message="Quelle voie ?")


def _question_finale(racine, session):
    _stop(racine, session, "On continue ?")


def _marqueur(racine, session):
    _stop(racine, session, ATTENTE)


SOURCES = {  # du plus au moins prioritaire : (pose, *quoi* attendu)
    "marqueur": (_marqueur, "Quelle option ?"),
    "askuserquestion": (_question, "Quelle voie ?"),
    "permission": (_permission, "permission demandée : Bash"),
    "question": (_question_finale, "On continue ?"),
}
ORDRE = list(SOURCES)


@pytest.mark.parametrize(("premiere", "seconde"), [
    (a, b) for a in ORDRE for b in ORDRE
    if a != b and not (a in ("askuserquestion", "permission") and b in ("marqueur", "question"))
])
def test_precedence_chaque_ordre_d_arrivee(racine, premiere, seconde):
    """La plus prioritaire reste, quel que soit l'ordre (sauf un Stop après un dialogue)."""
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    SOURCES[premiere][0](racine, session)
    SOURCES[seconde][0](racine, session)
    gagnante = min(premiere, seconde, key=ORDRE.index)
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert etat["attente"]["quoi"] == SOURCES[gagnante][1]
    assert etat["attente"].get("source", "marqueur") == gagnante
    schemas.valider("session", etat)


@pytest.mark.parametrize("dialogue", ["askuserquestion", "permission"])
def test_stop_resout_le_dialogue_puis_reevalue_la_question_finale(racine, dialogue):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    SOURCES[dialogue][0](racine, session)
    _question_finale(racine, session)
    attente = _lire(chemin)["attente"]
    assert (attente["quoi"], attente["source"]) == ("On continue ?", "question")


@pytest.mark.parametrize("dialogue", ["askuserquestion", "permission"])
def test_stop_sans_question_efface_le_dialogue(racine, dialogue):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    SOURCES[dialogue][0](racine, session)
    _stop(racine, session, "Terminé.")
    etat = _lire(chemin)
    assert etat["statut"] == "active"
    assert "attente" not in etat


@pytest.mark.parametrize("dialogue", ["askuserquestion", "permission"])
def test_stop_avec_marqueur_remplace_le_dialogue(racine, dialogue):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    SOURCES[dialogue][0](racine, session)
    _marqueur(racine, session)
    attente = _lire(chemin)["attente"]
    assert attente["quoi"] == "Quelle option ?" and "source" not in attente


def test_meme_source_garde_la_premiere(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _permission(racine, session)
    avant = _lire(chemin)["attente"]
    _notifier(racine, session, message="Claude needs your permission to use Edit")
    assert _lire(chemin)["attente"] == avant


def test_question_finale_gardee_par_un_stop_sans_prompt(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _question_finale(racine, session)
    avant = _lire(chemin)["attente"]
    _stop(racine, session, "Terminé.")
    assert _lire(chemin)["attente"] == avant


# --- attente existante, effacement, sous-agent ----------------------------------------------


def test_attente_existante_non_remplacee_par_la_notification(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    avant = _lire(chemin)
    _permission(racine, session)
    assert _lire(chemin) == avant


def test_attente_existante_non_remplacee_par_la_question_finale(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    _stop(racine, session, "Et maintenant ?")
    assert _lire(chemin)["attente"] == {"quoi": "avant", "depuis": DEBUT}


def test_attente_repondue_remplacee_par_la_nouvelle_question(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session, dernier_prompt="2026-01-02T03:04:06Z")
    _stop(racine, session, "Et maintenant ?")
    attente = _lire(chemin)["attente"]
    assert attente["quoi"] == "Et maintenant ?"
    assert attente["depuis"] != DEBUT


def test_la_notification_n_efface_pas_l_attente(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session, dernier_prompt="2026-01-02T03:04:06Z")
    _notifier(racine, session, notification_type="idle_prompt")
    assert _lire(chemin)["attente"]["quoi"] == "avant"


def test_prompt_utilisateur_efface_l_attente_de_secours(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _permission(racine, session)
    _prompt(racine, session)
    etat = _lire(chemin)
    assert "attente" not in etat
    assert etat["statut"] == "active"


def test_sous_agent_sans_effet(racine):
    for lancer in (
        lambda s: _stop(racine, s, "On continue ?", agent_id="a1"),
        lambda s: _notifier(racine, s, agent_id="a1"),
    ):
        session = str(uuid.uuid4())
        chemin = _creer(racine, session)
        avant = chemin.read_text(encoding="utf-8")
        lancer(session)
        assert chemin.read_text(encoding="utf-8") == avant


def test_etat_finie_intact_et_sans_etat_rien_cree(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session, statut="finie")
    avant = chemin.read_text(encoding="utf-8")
    _permission(racine, session)
    _stop(racine, session, "On continue ?")
    assert chemin.read_text(encoding="utf-8") == avant
    autre = str(uuid.uuid4())
    _permission(racine, autre)
    assert not list((racine / "attente" / "etat").rglob(f"{autre}.json"))


def test_notification_payload_illisible_journalisee(racine):
    _sans_sortie(_lancer(NOTIFICATION, b"pas du json"))
    assert len(_journal(racine)) == 1
    assert _journal(racine)[0].endswith("Notification PayloadInvalide")


def test_interrupteur_desactive_le_hook(racine):
    desactive = racine / "installation" / "desactive"
    desactive.parent.mkdir(parents=True, exist_ok=True)
    desactive.write_text("", encoding="utf-8")
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    avant = chemin.read_text(encoding="utf-8")
    _permission(racine, session)
    assert chemin.read_text(encoding="utf-8") == avant
