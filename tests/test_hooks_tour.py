# ruff: noqa: F811, F401 - la fixture importée `racine` est reprise comme argument des tests
"""Hooks Stop et UserPromptSubmit en vrai sous-processus (`-I -S`), sous une racine isolée."""

import json
import os
import re
import threading
import time
import uuid

import pytest
from test_hooks_session import (
    DOSSIER,
    HOOKS,
    HORODATAGE,
    PC,
    _depot,
    _etat,
    _journal,
    _lancer,
    _lire,
    _payload,
    _sans_sortie,
    _verrou,
    racine,
)

from pilotage.noyau import schemas

STOP = HOOKS / "stop.py"
PROMPT = HOOKS / "prompt.py"
ATTENTE = '<!-- pilotage: action=attend-utilisateur | type=choix | quoi="Quelle option ?" -->'
DEBUT = "2026-01-02T03:04:05Z"
EN_ATTENTE = {"quoi": "avant", "depuis": DEBUT}


def _creer(racine, session, **champs):
    chemin = _etat(racine, session)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    etat = {
        "schema": 1, "projet": "capture-payloads", "pc": PC, "session": session, "pid": 1,
        "pid_cree": "1", "dossier": DOSSIER, "branche": "main", "debut": DEBUT,
        "statut": "active",
    }
    etat.update(champs)
    chemin.write_text(json.dumps(etat), encoding="utf-8")
    return chemin


def _attente(racine, session, **champs):
    return _creer(racine, session, statut="attente", attente=dict(EN_ATTENTE), **champs)


def _attente_repondue(racine, session):
    """Attente datée d'un prompt de l'utilisateur (seul cas où un Stop sans marqueur l'efface)."""
    return _attente(racine, session, dernier_prompt="2026-01-02T03:04:06Z")


def _stop(racine, session, message, **champs):
    payload = _payload("Stop-session", racine, session, last_assistant_message=message, **champs)
    _sans_sortie(_lancer(STOP, payload))


def _prompt(racine, session, **champs):
    payload = _payload("UserPromptSubmit-saisie", racine, session, **champs)
    _sans_sortie(_lancer(PROMPT, payload))


# --- Stop -------------------------------------------------------------------------------------


def test_stop_pose_l_attente(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, f"Bonjour\n{ATTENTE}")
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert list(etat["attente"]) == ["type", "quoi", "depuis"]
    assert etat["attente"]["type"] == "choix"
    assert etat["attente"]["quoi"] == "Quelle option ?"
    assert HORODATAGE.fullmatch(etat["attente"]["depuis"])
    assert etat["dernier_tour"] == etat["attente"]["depuis"]
    assert etat["debut"] == DEBUT
    schemas.valider("session", etat)
    assert _journal(racine) == []


def test_stop_type_inconnu_omis(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session,
          '<!-- pilotage: action=attend-utilisateur | type=decision | quoi="q" -->')
    assert list(_lire(chemin)["attente"]) == ["quoi", "depuis"]


def test_stop_quoi_borne_a_200_points_de_code(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, f'<!-- pilotage: action=attend-utilisateur | quoi="{"é" * 500}" -->')
    assert _lire(chemin)["attente"]["quoi"] == "é" * 200


def test_stop_quoi_normalise_la_racine(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    cible = racine / "github" / "projet-b" / "x.py"
    _stop(racine, session, f'<!-- pilotage: action=attend-utilisateur | quoi="Voir {cible}" -->')
    reste = str(cible)[len(str(racine / "github")):]
    assert _lire(chemin)["attente"]["quoi"] == "Voir {{RACINE_GITHUB}}" + reste


def test_stop_quoi_suspect_supprime_mais_attente_gardee(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, '<!-- pilotage: action=attend-utilisateur | quoi="la clé sk-abc123" -->')
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert etat["attente"]["quoi"] == ""
    assert "sk-abc123" not in chemin.read_text(encoding="utf-8")


def test_stop_secret_present_avant_la_troncature_supprime(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    quoi = "a" * 250 + " ghp_x"  # le motif tombe au-delà de 200 : le premier filtre le voit
    _stop(racine, session, f'<!-- pilotage: action=attend-utilisateur | quoi="{quoi}" -->')
    assert _lire(chemin)["attente"]["quoi"] == ""


def test_stop_sans_marqueur_efface_l_attente(racine):
    session = str(uuid.uuid4())
    chemin = _attente_repondue(racine, session)
    _stop(racine, session, "Fini, rien à demander.")
    etat = _lire(chemin)
    assert "attente" not in etat
    assert etat["statut"] == "active"
    assert HORODATAGE.fullmatch(etat["dernier_tour"])


def test_stop_marqueur_mal_forme_efface_l_attente(racine):
    session = str(uuid.uuid4())
    chemin = _attente_repondue(racine, session)
    _stop(racine, session, '<!-- pilotage: action=attend-utilisateur | quoi="ouvert -->')
    assert "attente" not in _lire(chemin)


def test_stop_sans_marqueur_garde_l_attente_sans_reponse_utilisateur(racine):
    # Fin d'un sous-agent : le prompt `<task-notification>` est ignoré, puis Claude répond sans
    # marqueur. La question de l'utilisateur reste posée (A1).
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    payload = _payload("UserPromptSubmit-task-notification", racine, session)
    _sans_sortie(_lancer(PROMPT, payload))
    _stop(racine, session, "Le sous-agent a fini.")
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert etat["attente"] == EN_ATTENTE
    assert HORODATAGE.fullmatch(etat["dernier_tour"])


def test_stop_sans_marqueur_garde_l_attente_posee_a_la_seconde_du_prompt(racine):
    # Prompt de l'utilisateur puis question à la même seconde : un tour suivant sans marqueur
    # la garde.
    session = str(uuid.uuid4())
    chemin = _creer(racine, session, statut="attente", dernier_prompt=DEBUT,
                    attente={"quoi": "Quelle option ?", "depuis": DEBUT})
    _stop(racine, session, "Le sous-agent a fini.")
    assert _lire(chemin)["statut"] == "attente"


def test_stop_meme_attente_reemise_garde_depuis(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session, statut="attente",
                    attente={"type": "choix", "quoi": "Quelle option ?", "depuis": DEBUT})
    _stop(racine, session, ATTENTE)
    assert _lire(chemin)["attente"]["depuis"] == DEBUT


def test_stop_nouvelle_attente_remplace_l_ancienne(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    _stop(racine, session, ATTENTE)
    etat = _lire(chemin)
    assert etat["attente"]["quoi"] == "Quelle option ?"
    assert etat["attente"]["depuis"] != DEBUT


def test_stop_reprise(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, '<!-- pilotage: reprise="' + "é" * 400 + '" -->')
    etat = _lire(chemin)
    assert etat["reprise"] == "é" * 300
    assert etat["statut"] == "active"
    assert "attente" not in etat


def test_stop_reprise_suspecte_supprimee_meme_l_ancienne(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session, reprise="ancienne note")
    _stop(racine, session, '<!-- pilotage: reprise="token Bearer abc" -->')
    assert "reprise" not in _lire(chemin)
    assert "Bearer" not in chemin.read_text(encoding="utf-8")


def test_stop_sans_marqueur_de_reprise_garde_la_note(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session, reprise="à garder")
    _stop(racine, session, "rien")
    assert _lire(chemin)["reprise"] == "à garder"


def test_stop_attente_et_reprise_ensemble(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, f'{ATTENTE}\n<!-- pilotage: reprise="r" -->')
    etat = _lire(chemin)
    assert (etat["statut"], etat["reprise"]) == ("attente", "r")


def test_stop_ne_lit_jamais_transcript_path(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    transcript = racine / "transcript.jsonl"
    transcript.write_text(json.dumps({"message": ATTENTE}) + "\n", encoding="utf-8")
    _stop(racine, session, "Rien ici.", transcript_path=str(transcript))
    assert "attente" not in _lire(chemin)
    # un transcript inexistant ne provoque aucune erreur : le fichier n'est pas ouvert
    _stop(racine, session, "Rien ici.", transcript_path=str(racine / "absent" / "x.jsonl"))
    assert _journal(racine) == []


def test_stop_ignore_les_autres_champs_du_payload(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    payload = _payload(
        "Stop-session", racine, session, last_assistant_message="Rien", prompt=ATTENTE,
        background_tasks=[{"resultat": ATTENTE}], tool_response=ATTENTE,
    )
    _sans_sortie(_lancer(STOP, payload))
    assert "attente" not in _lire(chemin)


def test_stop_message_absent_ou_non_texte(racine):
    session = str(uuid.uuid4())
    chemin = _attente_repondue(racine, session)
    payload = _payload("Stop-session", racine, session)
    del payload["last_assistant_message"]
    _sans_sortie(_lancer(STOP, payload))
    assert "attente" not in _lire(chemin)
    _stop(racine, session, ["liste"])
    assert _journal(racine) == []


def test_stop_sans_etat_ne_cree_rien(racine):
    _stop(racine, str(uuid.uuid4()), ATTENTE)
    assert not (racine / "attente").exists()


def test_stop_sous_agent_sans_effet(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    avant = chemin.read_bytes()
    _stop(racine, session, ATTENTE, agent_id="agent-0001")
    assert chemin.read_bytes() == avant


def test_stop_ne_touche_pas_un_etat_fini(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session, statut="finie", fin="2026-01-02T04:00:00Z")
    avant = chemin.read_bytes()
    _stop(racine, session, ATTENTE)
    assert chemin.read_bytes() == avant


def test_stop_retrouve_l_etat_si_le_cwd_a_change(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _depot(racine / "github" / "ailleurs", "main")
    payload = _payload("Stop-session", racine, session, last_assistant_message=ATTENTE)
    payload["cwd"] = str(racine / "github" / "ailleurs")
    _sans_sortie(_lancer(STOP, payload))
    assert _lire(chemin)["statut"] == "attente"


def test_stop_verrou_tenu_un_seul_essai(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    avant = chemin.read_bytes()
    _verrou(racine, session)
    _stop(racine, session, ATTENTE)
    assert chemin.read_bytes() == avant
    assert _journal(racine) == ["Stop VerrouOccupe"]


def test_stop_etat_invalide_laisse_intact(racine):
    session = str(uuid.uuid4())
    chemin = _etat(racine, session)
    chemin.parent.mkdir(parents=True)
    chemin.write_text("{pas du json", encoding="utf-8")
    _stop(racine, session, ATTENTE)
    assert chemin.read_text(encoding="utf-8") == "{pas du json"


# --- UserPromptSubmit -------------------------------------------------------------------------


def test_prompt_efface_l_attente(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session, statut="attente", attente=dict(EN_ATTENTE), reprise="r")
    _prompt(racine, session)
    etat = _lire(chemin)
    assert "attente" not in etat
    assert etat["statut"] == "active"
    assert HORODATAGE.fullmatch(etat["dernier_prompt"])
    assert etat["reprise"] == "r"
    schemas.valider("session", etat)
    assert _journal(racine) == []


def test_prompt_n_ecrit_jamais_le_texte(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _prompt(racine, session, prompt="CONFIDENTIEL-xyz sk-secret " + "p" * 5000)
    brut = chemin.read_text(encoding="utf-8")
    assert "CONFIDENTIEL" not in brut and "secret" not in brut
    assert HORODATAGE.fullmatch(_lire(chemin)["dernier_prompt"])
    fichiers = [f for f in (racine / "attente").rglob("*") if f.is_file()]
    assert all("CONFIDENTIEL" not in f.read_text(encoding="utf-8", errors="replace")
               for f in fichiers)


def test_prompt_task_notification_sans_effet(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    avant = chemin.read_bytes()
    payload = _payload("UserPromptSubmit-task-notification", racine, session)
    _sans_sortie(_lancer(PROMPT, payload))
    assert chemin.read_bytes() == avant
    assert not (racine / "attente" / "verrous").exists()


@pytest.mark.parametrize("debut", [" ", "\n", "\ufeff"])
def test_prompt_task_notification_apres_blancs_sans_effet(racine, debut):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    avant = chemin.read_bytes()
    _prompt(racine, session, prompt=debut + "<task-notification>fini</task-notification>")
    assert chemin.read_bytes() == avant


def test_prompt_contenant_task_notification_plus_loin_agit(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    _prompt(racine, session, prompt="voir <task-notification> plus bas")
    assert _lire(chemin)["statut"] == "active"


def test_prompt_sous_agent_sans_effet(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    avant = chemin.read_bytes()
    _prompt(racine, session, agent_id="agent-0001")
    assert chemin.read_bytes() == avant


def test_prompt_sans_etat_ne_cree_rien(racine):
    _prompt(racine, str(uuid.uuid4()))
    assert not (racine / "attente").exists()


def test_prompt_ne_touche_pas_un_etat_fini(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session, statut="finie", fin="2026-01-02T04:00:00Z")
    avant = chemin.read_bytes()
    _prompt(racine, session)
    assert chemin.read_bytes() == avant


def test_prompt_reessaie_le_verrou(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    verrou = _verrou(racine, session)

    def liberer():
        time.sleep(0.03)  # libéré pendant le deuxième essai de 20 ms
        os.unlink(verrou)

    fil = threading.Thread(target=liberer)
    fil.start()
    _prompt(racine, session)
    fil.join()
    assert _lire(chemin)["statut"] == "active"
    assert _journal(racine) == []


def test_prompt_verrou_tenu_au_dela_des_essais(racine):
    session = str(uuid.uuid4())
    chemin = _attente(racine, session)
    avant = chemin.read_bytes()
    _verrou(racine, session)
    _prompt(racine, session)
    assert chemin.read_bytes() == avant
    assert _journal(racine) == ["UserPromptSubmit VerrouOccupe"]


@pytest.mark.parametrize("hook", [STOP, PROMPT])
def test_payload_invalide(racine, hook):
    _sans_sortie(_lancer(hook, b"{pas du json"))
    assert re.fullmatch(r"(Stop|UserPromptSubmit) PayloadInvalide", _journal(racine)[0])
    assert len(_journal(racine)) == 1


@pytest.mark.parametrize("hook", [STOP, PROMPT])
def test_desactive(racine, hook):
    interrupteur = racine / "installation" / "desactive"
    interrupteur.parent.mkdir(parents=True, exist_ok=True)
    interrupteur.write_bytes(b"")
    _sans_sortie(_lancer(hook, b"{pas du json"))
    assert not (racine / "attente").exists()


def test_cycle_complet(racine):
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, ATTENTE)
    assert _lire(chemin)["statut"] == "attente"
    _prompt(racine, session)
    assert _lire(chemin)["statut"] == "active"
    _stop(racine, session, "Terminé.")
    assert _lire(chemin)["statut"] == "active"


def test_stop_ancien_marqueur_alias_pose_l_attente(racine):
    # Session ouverte avant la story 7.2 : sa règle injectée porte encore `attend-anael`.
    session = str(uuid.uuid4())
    chemin = _creer(racine, session)
    _stop(racine, session, '<!-- pilotage: action=attend-anael | type=choix | quoi="Ancien" -->')
    etat = _lire(chemin)
    assert etat["statut"] == "attente"
    assert (etat["attente"]["type"], etat["attente"]["quoi"]) == ("choix", "Ancien")
    assert "action" not in etat["attente"]  # le nom de l'action n'est jamais écrit
    schemas.valider("session", etat)
