"""Story 2.5 : la règle du marqueur injectée par `SessionStart`, et elle seule, sur stdout."""

import json
import re
import uuid

import pytest
from test_hooks_session import (
    DEPOT,
    HOOKS,
    START,
    _etat,
    _journal,
    _lancer,
    _payload,
    racine,  # noqa: F401 - fixture
    sortie_regle,
)

from pilotage.hooks import cycle
from pilotage.noyau import marqueur

REGLE = DEPOT / "regle-marqueur.md"
FIXTURES_START = [
    "SessionStart-startup", "SessionStart-resume", "SessionStart-clear-a-confirmer",
    "SessionStart-compact-a-confirmer",
]


def _installer(base, contenu: bytes) -> None:
    (base / "installation" / "regle-marqueur.md").write_bytes(contenu)


def _vide(resultat, nom: str = "") -> None:
    assert (resultat.returncode, resultat.stdout, resultat.stderr) == (0, b"", b""), nom


def _contexte_emis(resultat) -> str:
    assert resultat.returncode == 0
    assert resultat.stderr == b""
    objet = json.loads(resultat.stdout.decode("utf-8"))  # un seul objet JSON, rien d'autre
    assert list(objet) == ["hookSpecificOutput"]
    sortie = objet["hookSpecificOutput"]
    assert list(sortie) == ["hookEventName", "additionalContext"]
    assert sortie["hookEventName"] == "SessionStart"
    return sortie["additionalContext"]


# --- Émission ----------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", FIXTURES_START)
def test_regle_emise_pour_chaque_source(racine, fixture):  # noqa: F811
    resultat = _lancer(START, _payload(fixture, racine))
    assert resultat.stdout == sortie_regle()
    assert _contexte_emis(resultat) == REGLE.read_text(encoding="utf-8")
    assert _journal(racine) == []


def test_regle_emise_a_la_reprise_d_un_etat_existant(racine):  # noqa: F811
    session = str(uuid.uuid4())
    for _ in range(2):
        resultat = _lancer(START, _payload("SessionStart-startup", racine, session))
        assert resultat.stdout == sortie_regle()
    assert _etat(racine, session).exists()


def test_rien_pour_un_sous_agent(racine):  # noqa: F811
    payload = _payload("SessionStart-startup", racine, agent_id="a1", agent_type="Explore")
    _vide(_lancer(START, payload))
    assert _journal(racine) == []


def test_rien_pour_un_dossier_non_suivi(racine):  # noqa: F811
    payload = _payload("SessionStart-startup", racine)
    payload["cwd"] = str(racine / "github" / "inconnu")
    _vide(_lancer(START, payload))
    assert _journal(racine) == []


def test_regle_emise_meme_si_l_etat_ne_s_ecrit_pas(racine):  # noqa: F811
    prelude = "import os\ndef _x(*a, **k):\n    raise OSError(28, 'plein')\nos.replace = _x\n"
    resultat = _lancer(START, _payload("SessionStart-startup", racine), prelude)
    assert resultat.stdout == sortie_regle()
    assert _journal(racine) == ["SessionStart OSError:ENOSPC"]


# --- Règle absente, illisible, trop longue ------------------------------------------------


def test_regle_absente_rien_emis_rien_journalise(racine):  # noqa: F811
    # Report 2.7 : tant que l'installation ne copie pas la règle, l'absence est le cas courant.
    (racine / "installation" / "regle-marqueur.md").unlink()
    for _ in range(2):
        _vide(_lancer(START, _payload("SessionStart-startup", racine)))
    assert _journal(racine) == []


def test_regle_avec_bom_emise_sans_bom(racine):  # noqa: F811
    _installer(racine, "﻿règle".encode())
    resultat = _lancer(START, _payload("SessionStart-startup", racine))
    assert _contexte_emis(resultat) == "règle"


def test_la_regle_recopiee_en_entier_n_est_pas_un_marqueur():
    # Second avis 1 : ses exemples sont suivis de texte, donc ignorés s'ils sont recopiés.
    texte = REGLE.read_text(encoding="utf-8")
    assert marqueur.lire(texte) == marqueur.AUCUN
    assert marqueur.lire(f"Voici la règle :\n\n{texte}\nC'est tout.") == marqueur.AUCUN


def test_regle_illisible_dossier(racine):  # noqa: F811
    chemin = racine / "installation" / "regle-marqueur.md"
    chemin.unlink()
    chemin.mkdir()
    _vide(_lancer(START, _payload("SessionStart-startup", racine)))
    journal = _journal(racine)
    assert len(journal) == 1 and journal[0].startswith("SessionStart ")


def test_regle_non_utf8_rien_emis(racine):  # noqa: F811
    _installer(racine, b"r\xe8gle en latin-1")
    _vide(_lancer(START, _payload("SessionStart-startup", racine)))
    assert _journal(racine) == ["SessionStart UnicodeDecodeError"]


def test_regle_trop_longue_rien_emis(racine):  # noqa: F811
    _installer(racine, b"a" * (cycle.BORNE_REGLE + 1))
    _vide(_lancer(START, _payload("SessionStart-startup", racine)))
    assert _journal(racine) == ["SessionStart ValueError"]


def test_regle_a_la_borne_emise(racine):  # noqa: F811
    _installer(racine, b"a" * cycle.BORNE_REGLE)
    resultat = _lancer(START, _payload("SessionStart-startup", racine))
    assert _contexte_emis(resultat) == "a" * cycle.BORNE_REGLE


def test_regle_vide_rien_emis_sans_erreur(racine):  # noqa: F811
    _installer(racine, b" \n")
    _vide(_lancer(START, _payload("SessionStart-startup", racine)))
    assert _journal(racine) == []


# --- Aucun autre hook n'écrit sur stdout --------------------------------------------------


def _points_d_entree() -> dict[str, object]:
    """Événement -> script de `pilotage/hooks/` qui le déclare (`EVENEMENT = "..."`)."""
    trouves = {}
    for fichier in sorted(HOOKS.glob("*.py")):
        if fichier.name.startswith("_"):
            continue
        trouve = re.search(r'^EVENEMENT = "(.+)"', fichier.read_text("utf-8"), re.M)
        if trouve:
            trouves[trouve.group(1)] = fichier
    return trouves


def test_les_points_d_entree_connus_sont_enumeres():
    assert {"SessionStart", "SessionEnd", "UserPromptSubmit", "Stop"} <= set(_points_d_entree())


def test_seul_session_start_ecrit_sur_stdout(racine):  # noqa: F811
    payloads = {
        "UserPromptSubmit": "UserPromptSubmit-saisie",
        "Stop": "Stop-session",
        "SessionEnd": "SessionEnd-other",
        "Notification": "Notification-permission-a-confirmer",
    }
    marqueur_attente = '<!-- pilotage: action=attend-utilisateur | quoi="Choisir" -->'
    inconnus = []
    for evenement, hook in _points_d_entree().items():
        if evenement == "SessionStart":
            continue
        if evenement not in payloads:
            inconnus.append(evenement)
            continue
        session = str(uuid.uuid4())
        _lancer(START, _payload("SessionStart-startup", racine, session))
        payload = _payload(payloads[evenement], racine, session)
        if evenement == "Stop":
            payload["last_assistant_message"] = marqueur_attente
        _vide(_lancer(hook, payload), hook.name)
        _vide(_lancer(hook, b"{pas du json"), hook.name)
        _vide(_lancer(hook, _payload(payloads[evenement], racine, agent_id="a1")), hook.name)
    assert inconnus == [], f"payload de test à ajouter pour {inconnus}"


# --- Texte de la règle -------------------------------------------------------------------


def _exemples() -> list[str]:
    return [
        ligne for ligne in REGLE.read_text(encoding="utf-8").splitlines()
        if ligne.startswith("<!-- pilotage:")
    ]


def test_exemples_de_la_regle_reconnus_par_le_parseur():
    exemples = _exemples()
    assert len(exemples) == 2
    attente = marqueur.lire(exemples[0])
    assert attente.attente == ("choix", "Choisir entre la voie A et la voie B")
    assert attente.reprise is None
    reprise = marqueur.lire(exemples[1])
    assert reprise.attente is None
    assert reprise.reprise == "Étape 3 sur 5 faite ; reste à écrire les tests"


def test_la_regle_decrit_ce_que_le_parseur_accepte():
    texte = REGLE.read_text(encoding="utf-8")
    for genre in marqueur.TYPES:
        assert f"`{genre}`" in texte
    assert marqueur.ACTION_ATTENTE in texte
    assert marqueur.ACTION_ATTENTE_ANCIENNE not in texte  # alias lu, jamais enseigné
    assert "200 caractères" in texte and "300 caractères" in texte
    assert all(len(e) < marqueur.BORNE_CORPS for e in _exemples())


def test_la_regle_est_bornee_et_en_utf8():
    brut = REGLE.read_bytes()
    assert len(brut) <= cycle.BORNE_REGLE
    assert not brut.startswith(b"\xef\xbb\xbf") and b"\r" not in brut
    brut.decode("utf-8")


# --- Aucun CLAUDE.md ne porte la règle ---------------------------------------------------


def test_aucun_claude_md_ne_contient_la_regle():
    titre = REGLE.read_text(encoding="utf-8").splitlines()[0]
    phrases = [titre, *_exemples(), "<!-- pilotage:"]
    fichiers = [
        f for f in DEPOT.rglob("CLAUDE.md")
        if not {".venv", ".git", "node_modules"} & set(f.relative_to(DEPOT).parts)
    ]
    assert DEPOT / "CLAUDE.md" in fichiers
    for fichier in fichiers:
        contenu = fichier.read_text(encoding="utf-8")
        for phrase in phrases:
            assert phrase not in contenu, f"{fichier} contient la règle ({phrase!r})"
