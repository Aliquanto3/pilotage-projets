# ruff: noqa: F401, F811
"""Reprise du cycle `sync` sur erreur (story 3.2) : dépôt nu local, `gh` simulé, aucun GitHub."""

import subprocess
import sys

import pytest

from pilotage import chemins
from pilotage.scan import verrou as impl
from pilotage.sync import cli, cycle, depot
from tests.test_imports import RACINE_DEPOT
from tests.test_sync_cli import (  # fixtures autouse et partagées
    ENFANT,
    ETAT_AUTRE_PC,
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

ETAT_PC = f"etat/demo/{PC}/{SESSION}.json"
DEPOSE = f"instantanes/{PC}.json"


class Tue(BaseException):
    """Arrêt brutal simulé : ni `Exception`, donc rien ne l'attrape dans le cycle."""


def journal() -> str:
    dossier = chemins.attente() / "journal"
    return "".join(p.read_text("utf-8") for p in sorted(dossier.glob("sync-*.log"))) if (
        dossier.is_dir()) else ""


def autre_clone(distant, tmp_path, nom="autre"):
    clone = tmp_path / nom
    g(["clone", "--quiet", "--branch", "donnees", str(distant), str(clone)])
    return clone


def pousser_depuis(clone, relatif, texte):
    g(["pull", "--quiet", "--rebase", "origin", "donnees"], clone)
    poser(clone, relatif, texte)
    g(["add", "--", relatif], clone)
    g(["commit", "--quiet", "-m", f"autre: {texte.strip()}"], clone)
    g(["push", "--quiet", "origin", "donnees"], clone)


def propre(donnees):
    """Arbre propre : rien de modifié ni de non suivi, sur `donnees`, aucun rebase."""
    assert g(["status", "--porcelain"], donnees) == ""
    assert g(["symbolic-ref", "--short", "HEAD"], donnees).strip() == "donnees"
    assert not depot.rebase_en_cours(donnees)
    assert not any((donnees / ".git" / nom).exists() for nom in depot.VERROUS)


def stashs(donnees) -> list[str]:
    return [ligne for ligne in g(["stash", "list"], donnees).splitlines() if ligne]


def test_etapes_dont_la_reprise_en_premier():
    noms = [nom for nom, _ in cycle.ETAPES]
    assert noms[0] == "reprise"
    assert len(noms) == 12


@pytest.mark.parametrize("etape", [nom for nom, _ in cycle.ETAPES])
def test_cycle_tue_a_chaque_etape_puis_cycle_normal(distant, github, gh, monkeypatch, etape):
    poser(chemins.attente(), ETAT_PC, etat())
    reelles = list(cycle.ETAPES)

    def tuer(nom, fonction):
        def jouer(ctx):
            fonction(ctx)
            if nom == etape:
                raise Tue
        return jouer

    monkeypatch.setattr(cycle, "ETAPES", [(n, tuer(n, f)) for n, f in reelles])
    with pytest.raises(Tue):
        synchro(github)
    assert impl.occupe() is False  # le `finally` du CLI a rendu le mutex
    monkeypatch.setattr(cycle, "ETAPES", reelles)
    assert synchro(github) == 0
    assert alertes_sync() == []
    assert {ETAT_PC, DEPOSE} <= arbre(distant)
    assert ETAT_AUTRE_PC in arbre(distant)
    assert nb_commits(distant) == 2  # graine + un seul commit etat(pc-test)
    propre(chemins.donnees())
    assert synchro(github) == 0
    assert nb_commits(distant) == 2


def test_conflit_de_rebase_abandonne_alerte_code_1(distant, github, gh, tmp_path):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    poser(donnees, DEPOSE, "local\n")  # commit local non poussé, en conflit avec le distant
    g(["add", "--", DEPOSE], donnees)
    g(["commit", "--quiet", "-m", "local"], donnees)
    pousser_depuis(autre_clone(distant, tmp_path), DEPOSE, "distant\n")
    avant = nb_commits(distant)
    assert synchro(github) == 1
    assert alertes_sync() == [
        ("sync-conflit",
         "Synchro abandonnée à 09:05 : conflit de rebase."
         " Nouvel essai au prochain cycle.")
    ]
    propre(donnees)
    assert g(["log", "-1", "--format=%s"], donnees).strip() == "local"  # commit local conservé
    assert nb_commits(distant) == avant  # rien poussé


def test_reprise_d_un_rebase_laisse_en_cours(distant, github, gh, tmp_path):
    poser(chemins.attente(), ETAT_PC, etat())
    assert synchro(github) == 0
    donnees = chemins.donnees()
    # Commit local en conflit, puis un rebase tué en plein conflit (rebase-merge/ présent).
    poser(donnees, DEPOSE, "local\n")
    g(["add", "--", DEPOSE], donnees)
    g(["commit", "--quiet", "-m", "etat(pc-test): local"], donnees)
    pousser_depuis(autre_clone(distant, tmp_path), DEPOSE, "distant\n")
    g(["fetch", "--quiet", "origin", "donnees"], donnees)
    assert depot.git(["rebase", "origin/donnees"], donnees).returncode != 0
    assert depot.rebase_en_cours(donnees)
    poser(donnees, "fichier-non-suivi.txt", "x\n")
    assert synchro(github) == 1  # le conflit se reproduit au pull : abandonné proprement
    assert "reprise : rebase abandonné" in journal()
    assert "fichiers non suivis supprimés" in journal()
    assert alertes_sync() == [
        ("sync-conflit",
         "Synchro abandonnée à 09:05 : conflit de rebase."
         " Nouvel essai au prochain cycle.")
    ]
    propre(donnees)
    assert not (donnees / "fichier-non-suivi.txt").exists()


def test_reprise_remet_l_arbre_propre_sauf_projets_yaml(distant, github, gh):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    poser(donnees, DEPOSE, "sale\n")  # fichier suivi modifié (non commité)
    poser(donnees, "projets.yaml", "schema: 1\n# note de l'utilisateur\n")
    poser(donnees, "nouveau.json", "{}\n")
    g(["add", "--", "nouveau.json"], donnees)  # indexé, non suivi par HEAD
    assert synchro(github) == 0
    assert "fichiers suivis rétablis" in journal()
    assert "nouveau.json" not in arbre(distant)
    assert "note de l'utilisateur" in (donnees / "projets.yaml").read_text("utf-8")
    assert "note de l'utilisateur" in g(["--git-dir", str(distant), "show", "donnees:projets.yaml"])
    assert "sale" not in g(["--git-dir", str(distant), "show", f"donnees:{DEPOSE}"])


@pytest.mark.parametrize("detache", [True, False])
def test_head_detache_ou_autre_branche_remis_sur_donnees(distant, github, gh, detache):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    if detache:
        g(["checkout", "--quiet", "--detach"], donnees)
    else:
        g(["checkout", "--quiet", "-b", "autre"], donnees)
    assert synchro(github) == 0
    propre(donnees)
    assert "HEAD remis sur donnees" in journal()


def test_head_avec_commit_propre_hors_de_donnees_refuse(distant, github, gh):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    g(["checkout", "--quiet", "-b", "autre"], donnees)
    poser(donnees, "perdu.txt", "x\n")
    g(["add", "--", "perdu.txt"], donnees)
    g(["commit", "--quiet", "-m", "propre"], donnees)
    assert synchro(github) == 1
    assert alertes_sync() == [("sync-echec", "Synchro en échec à l'étape reprise")]
    assert g(["symbolic-ref", "--short", "HEAD"], donnees).strip() == "autre"
    assert (donnees / "perdu.txt").exists()


def test_reprise_sans_rien_a_faire_ne_journalise_pas(distant, github, gh):
    assert synchro(github) == 0
    assert synchro(github) == 0
    assert journal() == ""


@windows
def test_mutex_abandonne_journalise_la_reprise(distant, github, gh):
    enfant = subprocess.Popen(
        [sys.executable, "-c", ENFANT], cwd=RACINE_DEPOT, stdout=subprocess.PIPE, text=True
    )
    try:
        assert enfant.stdout.readline().strip() == "acquis"
        poignee = impl._noyau().CreateMutexW(None, False, impl.nom())  # garde l'objet en vie
        enfant.kill()
        enfant.wait()
        try:
            assert synchro(github) == 0
        finally:
            impl._noyau().CloseHandle(poignee)
    finally:
        enfant.kill()
        enfant.wait()
    assert journal() == "2026-11-06 09:05 reprise : mutex abandonné\n"


def pousseur_concurrent(distant, tmp_path, fois):
    """Étape `push` qui précède chaque push réel d'un push d'un autre PC (`fois` fois)."""
    autre = autre_clone(distant, tmp_path)
    reelle = dict(cycle.ETAPES)["push"]
    compte = []

    def push(ctx):
        if len(compte) < fois:
            compte.append(1)
            pousser_depuis(autre, f"instantanes/autre-{len(compte)}.json", f"{len(compte)}\n")
        reelle(ctx)

    return [(n, push if n == "push" else f) for n, f in cycle.ETAPES], compte


def test_non_fast_forward_un_seul_nouvel_essai_reussi(distant, github, gh, tmp_path, monkeypatch):
    poser(chemins.attente(), ETAT_PC, etat())
    etapes, compte = pousseur_concurrent(distant, tmp_path, 1)
    monkeypatch.setattr(cycle, "ETAPES", etapes)
    assert synchro(github) == 0
    assert alertes_sync() == []
    assert len(gh.appels) == 4  # contrôles isPrivate rejoués avec le cycle complet
    assert {ETAT_PC, DEPOSE, "instantanes/autre-1.json"} <= arbre(distant)
    assert nb_commits(distant) == 3  # graine, autre PC, un seul commit etat(pc-test)
    assert "nouvel essai" in journal()


def test_non_fast_forward_deux_fois_abandonne_avec_alerte(
    distant, github, gh, tmp_path, monkeypatch
):
    poser(chemins.attente(), ETAT_PC, etat())
    etapes, compte = pousseur_concurrent(distant, tmp_path, 5)
    monkeypatch.setattr(cycle, "ETAPES", etapes)
    assert synchro(github) == 1
    assert len(compte) == 2  # un seul nouvel essai
    assert len(gh.appels) == 4
    assert alertes_sync() == [
        ("sync-push-refuse",
         "Synchro abandonnée à 09:05 : push refusé (non-fast-forward)."
         " Nouvel essai au prochain cycle.")
    ]
    assert ETAT_PC not in arbre(distant)  # jamais de force
    assert g(["log", "-1", "--format=%s"], chemins.donnees()).startswith("etat(pc-test)")
    propre(chemins.donnees())


def test_non_fast_forward_non_confondu_avec_un_refus_du_distant(distant, github, gh):
    crochet = distant / "hooks" / "pre-receive"
    crochet.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
    crochet.chmod(0o755)
    poser(chemins.attente(), ETAT_PC, etat())
    assert synchro(github) == 1
    assert len(gh.appels) == 2  # pas de nouvel essai
    assert alertes_sync() == [("sync-echec", "Synchro en échec à l'étape push")]


def test_cycle_ne_laisse_aucun_stash(distant, github, gh):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    poser(donnees, "projets.yaml", "schema: 1\n# note\n")
    assert synchro(github) == 0
    assert stashs(donnees) == []


def test_reprise_garde_un_projets_yaml_non_suivi(tmp_path):
    donnees = tmp_path / "donnees"
    g(["init", "--quiet", "-b", "donnees", str(donnees)])
    g(["config", "user.email", "t@t"], donnees)
    g(["config", "user.name", "t"], donnees)
    poser(donnees, DEPOSE, "{}\n")
    g(["add", "--", DEPOSE], donnees)
    g(["commit", "--quiet", "-m", "graine"], donnees)
    poser(donnees, "projets.yaml", "schema: 1\n# jamais commité\n")
    poser(donnees, "sous/x.txt", "x\n")
    assert depot.reprendre(donnees) == ["fichiers non suivis supprimés"]
    assert "jamais commité" in (donnees / "projets.yaml").read_text("utf-8")
    assert not (donnees / "sous").exists()
    assert depot.reprendre(donnees) == []  # projets.yaml seul : rien à faire


def test_verrous_orphelins_retires_si_aucun_git_actif(distant, github, gh, monkeypatch):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    for nom in depot.VERROUS:
        (donnees / ".git" / nom).write_text("", "utf-8")
    monkeypatch.setattr(depot, "git_actif", lambda: False)  # frontière : liste des processus
    poser(chemins.attente(), ETAT_PC, etat())
    assert synchro(github) == 0
    assert "verrous git orphelins retirés" in journal()
    assert ETAT_PC in arbre(distant)
    propre(donnees)


def test_verrou_garde_si_un_git_tourne(distant, github, gh, monkeypatch):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    verrou = donnees / ".git" / "index.lock"
    verrou.write_text("", "utf-8")
    monkeypatch.setattr(depot, "git_actif", lambda: True)
    assert synchro(github) == 1  # `reset` bute sur le verrou : échec, rien de forcé
    assert alertes_sync() == [("sync-echec", "Synchro en échec à l'étape reprise")]
    assert verrou.exists()


def test_git_actif_rend_un_booleen():
    assert isinstance(depot.git_actif(), bool)


def test_refus_hors_de_donnees_avant_toute_operation_destructive(distant, github, gh):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    g(["checkout", "--quiet", "-b", "autre"], donnees)
    poser(donnees, "propre.txt", "x\n")
    g(["add", "--", "propre.txt"], donnees)
    g(["commit", "--quiet", "-m", "propre"], donnees)
    poser(donnees, "propre.txt", "édité\n")  # suivi modifié
    poser(donnees, "brouillon.txt", "y\n")  # non suivi
    assert synchro(github) == 1
    assert alertes_sync() == [("sync-echec", "Synchro en échec à l'étape reprise")]
    assert (donnees / "propre.txt").read_text("utf-8") == "édité\n"
    assert (donnees / "brouillon.txt").exists()


def conflit_projets_yaml(distant, tmp_path, donnees):
    """`projets.yaml` édité dans le clone sans commit, et modifié autrement sur le distant."""
    pousser_depuis(autre_clone(distant, tmp_path), "projets.yaml", "schema: 1\ndistant: 1\n")
    poser(donnees, "projets.yaml", "schema: 1\nlocal: 1\n")


def test_autostash_en_conflit_abandonne_sans_marqueurs(distant, github, gh, tmp_path):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    conflit_projets_yaml(distant, tmp_path, donnees)
    avant = nb_commits(distant)
    assert synchro(github) == 1
    assert alertes_sync() == [(
        "sync-conflit",
        "Synchro abandonnée à 09:05 : modifications locales en conflit, gardées dans le stash."
        " Nouvel essai au prochain cycle.",
    )]
    assert nb_commits(distant) == avant
    assert "<<<<<<<" not in (donnees / "projets.yaml").read_text("utf-8")
    assert len(stashs(donnees)) == 1  # modification locale conservée, tracée au journal
    sha = g(["rev-parse", "refs/stash"], donnees).strip()
    assert f"gardées dans le stash {sha}" in journal()
    assert "local: 1" in g(["show", "refs/stash:projets.yaml"], donnees)
    assert synchro(github) == 0  # cycle suivant : repart propre, sans marqueurs
    assert "<<<<<<<" not in g(["--git-dir", str(distant), "show", "donnees:projets.yaml"])
    assert len(stashs(donnees)) == 1


def test_reprise_d_un_autostash_laisse_en_conflit(distant, github, gh, tmp_path):
    assert synchro(github) == 0
    donnees = chemins.donnees()
    conflit_projets_yaml(distant, tmp_path, donnees)
    # Cycle tué juste après un pull dont l'autostash est en conflit.
    g(["pull", "--quiet", "--rebase", "--autostash", "origin", "donnees"], donnees)
    assert g(["diff", "--name-only", "--diff-filter=U"], donnees).strip() == "projets.yaml"
    assert synchro(github) == 0
    assert "conflit d'autostash annulé" in journal()
    assert "<<<<<<<" not in g(["--git-dir", str(distant), "show", "donnees:projets.yaml"])
    assert len(stashs(donnees)) == 1
    propre(donnees)


def test_autostash_en_conflit_modifie_supprime_ne_bloque_pas(distant, github, gh, tmp_path):
    """`projets.yaml` édité dans le clone, supprimé sur le distant : sans fichier dans `HEAD`,
    la remise à `HEAD` le retire ; le cycle suivant repart, la copie reste dans le stash."""
    assert synchro(github) == 0
    donnees = chemins.donnees()
    autre = autre_clone(distant, tmp_path)
    pousser_depuis(autre, "projets.yaml", "schema: 1\nv: 2\n")
    assert synchro(github) == 0
    g(["rm", "--quiet", "projets.yaml"], autre)
    g(["commit", "--quiet", "-m", "autre: suppression"], autre)
    g(["push", "--quiet", "origin", "donnees"], autre)
    poser(donnees, "projets.yaml", "schema: 1\nlocal: 1\n")
    assert synchro(github) == 1
    assert alertes_sync()[0][0] == "sync-conflit"
    assert not (donnees / "projets.yaml").exists()
    assert "local: 1" in g(["show", "refs/stash:projets.yaml"], donnees)
    assert synchro(github) == 0
    assert len(stashs(donnees)) == 1
    propre(donnees)
