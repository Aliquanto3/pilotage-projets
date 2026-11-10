# ruff: noqa: F401, F811
"""Archivage des sessions et rotation des journaux (story 3.3) : dépôt nu local, `gh` simulé."""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, timedelta

import pytest

from pilotage import chemins
from pilotage.scan import processus
from pilotage.sync import archivage, cycle
from tests.test_hooks_session import (  # fixture `racine` et assistants du test des hooks
    PC as PC_HOOK,
)
from tests.test_hooks_session import (
    START,
    _lancer,
    _lire,
    _payload,
    _sans_sortie,
    racine,
)
from tests.test_hooks_session import _etat as etat_hook
from tests.test_sync_cli import (  # fixtures autouse et partagées
    ETAT_AUTRE_PC,
    INSTANT,
    PC,
    SESSION,
    alertes_sync,
    arbre,
    distant,
    etat,
    g,
    gh,
    github,
    horloge,
    nb_commits,
    nom_propre,
    poser,
    synchro,
    windows,
)

MAINTENANT = INSTANT.astimezone(UTC)
ETAT_PC = f"etat/demo/{PC}/{SESSION}.json"
ARCHIVE = f"archive/{ETAT_PC}"


@pytest.fixture(autouse=True)
def pid_des_etats_absent(monkeypatch):
    """Le pid 1234 des états de test peut exister sur le poste ou la CI : tenu pour absent ; tout
    autre pid passe par la vraie sonde (frontière OS)."""
    reel = processus.pid_present
    monkeypatch.setattr(processus, "pid_present", lambda pid: pid != 1234 and reel(pid))


def iso(delta: timedelta) -> str:
    return (MAINTENANT - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def ancienne(**champs):
    """État dont le dernier tour date de 8 jours."""
    return etat(debut=iso(timedelta(days=9)), dernier_tour=iso(timedelta(days=8)), **champs)


def en_attente():
    return chemins.attente() / ETAT_PC


def archive():
    return chemins.attente() / ARCHIVE


def journal() -> str:
    dossier = chemins.attente() / "journal"
    return "".join(p.read_text("utf-8") for p in sorted(dossier.glob("sync-*.log")))


def test_etape_nommee_apres_le_pull_avant_la_copie():
    noms = [nom for nom, _ in cycle.ETAPES]
    assert noms.index("pull") < noms.index("archivage") < noms.index("copie-attente")


def test_session_de_plus_de_7_jours_archivee_et_retiree_de_donnees(distant, github, gh):
    poser(chemins.attente(), ETAT_PC, etat())
    assert synchro(github) == 0
    assert ETAT_PC in arbre(distant)
    avant = nb_commits(distant)
    contenu = ancienne()
    poser(chemins.attente(), ETAT_PC, contenu)
    assert synchro(github) == 0
    assert not en_attente().exists()
    assert json.loads(archive().read_text("utf-8")) == contenu
    assert not (chemins.donnees() / ETAT_PC).exists()
    assert ETAT_PC not in arbre(distant)
    assert ETAT_AUTRE_PC in arbre(distant)  # l'état d'un autre PC n'est pas touché
    assert nb_commits(distant) == avant + 1
    assert g(["status", "--porcelain"], chemins.donnees()) == ""
    assert "archivage : 1 session(s) archivée(s), 0 journal(aux) supprimé(s)" in journal()
    assert synchro(github) == 0  # cycle suivant : rien à faire, aucun commit
    assert nb_commits(distant) == avant + 1


def test_premier_cycle_archive_sans_jamais_publier(distant, github, gh):
    poser(chemins.attente(), ETAT_PC, ancienne())
    assert synchro(github) == 0
    assert archive().is_file() and not en_attente().exists()
    assert ETAT_PC not in arbre(distant)


def test_la_copie_ignore_archive(distant, github, gh):
    poser(chemins.attente(), ARCHIVE, etat())
    poser(chemins.attente(), ETAT_PC, ancienne())
    assert synchro(github) == 0
    assert not any(chemin.startswith("archive") for chemin in arbre(distant))
    assert not (chemins.donnees() / "archive").exists()
    assert alertes_sync() == []


def test_debut_sert_a_defaut_de_dernier_tour(distant, github, gh):
    poser(chemins.attente(), ETAT_PC, etat(debut=iso(timedelta(days=8))))
    assert synchro(github) == 0
    assert archive().is_file()


def test_dernier_tour_recent_garde_une_vieille_session(distant, github, gh):
    poser(chemins.attente(), ETAT_PC, etat(
        debut=iso(timedelta(days=30)), dernier_tour=iso(timedelta(days=1))))
    assert synchro(github) == 0
    assert en_attente().is_file() and not archive().exists()
    assert ETAT_PC in arbre(distant)


def test_borne_exacte_de_7_jours(tmp_path):
    poser(chemins.attente(), ETAT_PC, etat(dernier_tour=iso(timedelta(days=7))))
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 0)
    assert en_attente().is_file()
    poser(chemins.attente(), ETAT_PC, etat(dernier_tour=iso(timedelta(days=7, seconds=1))))
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 1)  # absent de donnees/
    assert archive().is_file() and not en_attente().exists()


def test_retire_de_donnees_rend_le_relatif_s_il_est_suivi(tmp_path):
    donnees = chemins.donnees()
    poser(donnees, ETAT_PC, ancienne())
    g(["init", "--quiet"], donnees)
    poser(chemins.attente(), ETAT_PC, ancienne())
    # Non suivi par git : retiré, mais pas de relatif (`git add` d'un chemin inconnu échouerait).
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 1)
    assert not (donnees / ETAT_PC).exists()
    poser(donnees, ETAT_PC, ancienne())
    g(["add", "--", ETAT_PC], donnees)
    poser(chemins.attente(), ETAT_PC, ancienne())
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([ETAT_PC], 1)
    assert not (donnees / ETAT_PC).exists()


def test_retrait_de_donnees_impossible_remet_l_etat_en_attente(tmp_path):
    (chemins.donnees() / ETAT_PC).mkdir(parents=True)  # vrai échec d'unlink, sur tous les OS
    contenu = ancienne()
    poser(chemins.attente(), ETAT_PC, contenu)
    messages = []
    assert archivage.archiver_sessions(PC, MAINTENANT, messages.append) == ([], 0)
    assert json.loads(en_attente().read_text("utf-8")) == contenu and not archive().exists()
    assert messages == [
        "archivage : retrait de donnees/ impossible, session laissée au cycle suivant"]
    assert not (chemins.attente() / "verrous" / f"{SESSION}.lock").exists()


def test_etat_recree_par_un_hook_n_est_pas_ecrase_au_retour(tmp_path, monkeypatch):
    (chemins.donnees() / ETAT_PC).mkdir(parents=True)  # vrai échec d'unlink
    poser(chemins.attente(), ETAT_PC, ancienne())
    frais = etat(dernier_tour=iso(timedelta(minutes=1)))
    remplacer = os.replace

    def deplacer_puis_hook(src, dst):  # verrou jugé périmé : un hook recrée l'état
        remplacer(src, dst)
        monkeypatch.setattr(archivage.os, "replace", remplacer)
        poser(chemins.attente(), ETAT_PC, frais)

    monkeypatch.setattr(archivage.os, "replace", deplacer_puis_hook)
    messages = []
    assert archivage.archiver_sessions(PC, MAINTENANT, messages.append) == ([], 1)
    assert json.loads(en_attente().read_text("utf-8")) == frais and archive().is_file()


def test_git_ls_files_lance_hors_verrou(tmp_path, monkeypatch):
    poser(chemins.donnees(), ETAT_PC, ancienne())
    poser(chemins.attente(), ETAT_PC, ancienne())
    verrou = chemins.attente() / "verrous" / f"{SESSION}.lock"
    vus = []
    monkeypatch.setattr(archivage, "_suivi", lambda d, r: vus.append(verrou.exists()) or False)
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 1)
    assert vus == [False]


def test_date_future_jamais_archivee(tmp_path):
    poser(chemins.attente(), ETAT_PC, etat(dernier_tour=iso(timedelta(days=-30))))
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 0)
    assert en_attente().is_file()


def test_tour_ecrit_par_un_hook_avant_le_verrou_l_emporte(tmp_path, monkeypatch):
    poser(chemins.attente(), ETAT_PC, ancienne())
    frais = etat(dernier_tour=iso(timedelta(minutes=1)))
    prendre = archivage._prendre_verrou

    def hook_puis_verrou(session):  # course simulée : le hook écrit entre l'examen et le verrou
        poser(chemins.attente(), ETAT_PC, frais)
        return prendre(session)

    monkeypatch.setattr(archivage, "_prendre_verrou", hook_puis_verrou)
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 0)
    assert json.loads(en_attente().read_text("utf-8")) == frais and not archive().exists()
    assert not (chemins.attente() / "verrous" / f"{SESSION}.lock").exists()


def test_verrou_repris_par_un_autre_n_est_pas_supprime(tmp_path):
    chemin, jeton = archivage._prendre_verrou(SESSION)
    assert archivage._prendre_verrou(SESSION) is None  # tenu
    chemin.write_bytes(b"999 autre")  # jugé périmé et repris par un hook
    archivage._rendre_verrou(chemin, jeton)
    assert chemin.read_bytes() == b"999 autre"


def test_session_d_un_autre_pc_jamais_archivee(tmp_path):
    autre = f"etat/demo/autre-pc/{SESSION}.json"
    poser(chemins.attente(), autre, ancienne(pc="autre-pc"))
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 0)
    assert (chemins.attente() / autre).is_file()


def poser_verrou(age_s=0.0):
    chemin = chemins.attente() / "verrous" / f"{SESSION}.lock"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("1234 aa", encoding="utf-8")
    ancien = time.time() - age_s
    os.utime(chemin, (ancien, ancien))
    return chemin


def test_verrou_de_session_pris_laisse_au_cycle_suivant(distant, github, gh):
    poser(chemins.attente(), ETAT_PC, etat())
    assert synchro(github) == 0
    poser(chemins.attente(), ETAT_PC, ancienne())
    verrou = poser_verrou()
    assert synchro(github) == 0
    assert en_attente().is_file() and not archive().exists()
    assert ETAT_PC in arbre(distant)
    assert verrou.is_file()  # le verrou d'un autre n'est pas touché
    verrou.unlink()
    assert synchro(github) == 0  # cycle suivant : archivée
    assert archive().is_file() and ETAT_PC not in arbre(distant)


def test_verrou_perime_repris_puis_rendu(tmp_path):
    poser(chemins.attente(), ETAT_PC, ancienne())
    verrou = poser_verrou(age_s=archivage.VERROU_PERIME_S + 5)
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 1)
    assert archive().is_file()
    assert not verrou.exists()


def test_verrou_rendu_apres_archivage(tmp_path):
    poser(chemins.attente(), ETAT_PC, ancienne())
    archivage.archiver_sessions(PC, MAINTENANT)
    assert not (chemins.attente() / "verrous" / f"{SESSION}.lock").exists()


@pytest.mark.parametrize("pid_cree", [None, "1", "cree"])
def test_pid_reel_vivant_garde_la_session_quelle_que_soit_son_heure(tmp_path, pid_cree):
    # Tous OS : `pid_cree` null (adaptateur en échec, ou hors Windows) ou différent ne suffit pas.
    if pid_cree == "cree":
        pid_cree = str(processus.heure_creation(os.getpid())) if sys.platform == "win32" else None
    poser(chemins.attente(), ETAT_PC, ancienne(pid=os.getpid(), pid_cree=pid_cree))
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 0)
    assert en_attente().is_file() and not archive().exists()


def test_pid_mort_archive(tmp_path):
    fini = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True, check=True)
    poser(chemins.attente(), ETAT_PC, ancienne(pid=int(fini.stdout), pid_cree=None))
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 1)


@pytest.mark.parametrize("contenu", [
    "pas du json",
    json.dumps(etat(debut="hier", dernier_tour="2020-01-01T00:00:00Z")),
    json.dumps(etat(debut="2020-02-30T00:00:00Z")),  # date impossible
    json.dumps({"schema": 1}),
    "[]",
])
def test_date_ou_fichier_illisible_jamais_archive(tmp_path, contenu):
    poser(chemins.attente(), ETAT_PC, contenu)
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 0)
    assert en_attente().is_file() and not archive().exists()


def test_chemin_et_contenu_divergents_jamais_archives(tmp_path):
    poser(chemins.attente(), ETAT_PC, ancienne(session="0123abcd-0000-4000-8000-0000000000ff"))
    assert archivage.archiver_sessions(PC, MAINTENANT) == ([], 0)
    assert en_attente().is_file()


def test_session_archivee_puis_reprise_recree_l_etat(racine):
    session = "0123abcd-0000-4000-8000-0000000000aa"
    chemin = etat_hook(racine, session)
    poser(chemin.parent, chemin.name, etat(
        projet="capture-payloads", pc=PC_HOOK, session=session, dossier="_sandbox/capture-payloads",
        debut="2026-01-02T03:04:05Z", dernier_tour="2026-01-02T04:00:00Z"))
    assert archivage.archiver_sessions(PC_HOOK, MAINTENANT)[1] == 1
    classee = racine / "attente" / "archive" / "etat" / "capture-payloads" / PC_HOOK
    archive_avant = (classee / chemin.name).read_text("utf-8")
    assert not chemin.exists()
    _sans_sortie(_lancer(START, _payload("SessionStart-resume", racine, session)))
    neuf = _lire(chemin)
    assert neuf["statut"] == "active"
    assert neuf["debut"] != "2026-01-02T03:04:05Z"  # état neuf, l'archive n'est pas relue
    assert "dernier_tour" not in neuf
    assert (classee / chemin.name).read_text("utf-8") == archive_avant


def poser_journaux(*noms):
    dossier = chemins.attente() / "journal"
    dossier.mkdir(parents=True, exist_ok=True)
    for nom in noms:
        (dossier / nom).write_text("x\n", encoding="utf-8")
    return dossier


def test_rotation_des_journaux_de_plus_de_12_mois(tmp_path):
    dossier = poser_journaux(
        "sync-2025-10.log", "sync-2025-11.log", "sync-2026-11.log", "serveur-2024-01.log",
        "hooks-2025-01.log", "notes.log", "sync-2025-13.log", "sync-2025-10.txt", "sync.log",
    )
    assert archivage.faire_tourner_journaux(INSTANT) == 3  # sync-2025-10, serveur-2024, hooks-2025
    assert sorted(p.name for p in dossier.iterdir()) == [
        "notes.log", "sync-2025-10.txt", "sync-2025-11.log", "sync-2025-13.log",
        "sync-2026-11.log", "sync.log",
    ]


def test_rotation_sans_dossier_de_journaux(tmp_path):
    assert archivage.faire_tourner_journaux(INSTANT) == 0


def test_cycle_supprime_les_vieux_journaux_et_le_note(distant, github, gh):
    dossier = poser_journaux("sync-2025-01.log", "sync-2025-11.log")
    assert synchro(github) == 0
    assert not (dossier / "sync-2025-01.log").exists()
    assert (dossier / "sync-2025-11.log").is_file()
    assert "archivage : 0 session(s) archivée(s), 1 journal(aux) supprimé(s)" in journal()


def test_rien_a_faire_ne_journalise_rien(distant, github, gh):
    assert synchro(github) == 0
    assert "archivage" not in journal()
