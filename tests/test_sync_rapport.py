# ruff: noqa: F401, F811
"""Étape `rapport` de `sync` (story 9.3, FR46) : rapport de la semaine ISO précédente."""

from datetime import datetime
from pathlib import Path

import pytest

from pilotage import chemins
from pilotage.noyau import alertes as catalogue
from pilotage.rapport import generation
from pilotage.sync import cycle
from tests.test_sync_cli import (  # fixtures autouse et partagées
    INSTANT,
    alertes_sync,
    distant,
    gh,
    github,
    horloge,
    nom_propre,
    synchro,
)

PRECEDENTE = "2026-W44"  # INSTANT : vendredi 2026-11-06, semaine 45


def journal():
    chemin = chemins.journal_sync(f"{INSTANT:%Y-%m}")
    return chemin.read_text("utf-8").splitlines() if chemin.exists() else []


def poser_rapports(*semaines):
    chemins.rapports().mkdir(parents=True, exist_ok=True)
    for s in semaines:
        chemins.rapport_semaine(s).write_text("ancien", encoding="utf-8")


def test_premier_cycle_ecrit_le_rapport_de_la_semaine_precedente(distant, github, gh):
    assert synchro(github) == 0
    page = chemins.rapport_semaine(PRECEDENTE)
    assert page.is_file()
    assert PRECEDENTE in page.read_text("utf-8")
    assert [p.name for p in chemins.rapports().iterdir()] == ["semaine-2026-W44.html"]
    assert catalogue.RAPPORT_NON_GENERE not in dict(alertes_sync())


def test_cycle_suivant_ne_lit_ni_ne_recalcule(distant, github, gh, monkeypatch):
    poser_rapports(PRECEDENTE)

    def interdit(*args, **kwargs):
        raise AssertionError("rapport recalculé")

    monkeypatch.setattr(generation, "generer", interdit)
    assert synchro(github) == 0
    assert chemins.rapport_semaine(PRECEDENTE).read_text("utf-8") == "ancien"
    assert catalogue.RAPPORT_NON_GENERE not in dict(alertes_sync())
    assert journal() == []


def test_erreur_alerte_journal_fixe_et_etapes_suivantes(distant, github, gh, monkeypatch):
    def panne(*args, **kwargs):
        raise RuntimeError("secret chemin-prive")

    vrai = generation.generer
    monkeypatch.setattr(generation, "generer", panne)
    assert synchro(github) == 0  # commit et push ont eu lieu après l'étape
    assert (catalogue.RAPPORT_NON_GENERE,
            "Rapport de la semaine non généré : nouvel essai au prochain cycle") in alertes_sync()
    assert journal() == [f"{INSTANT:%Y-%m-%d %H:%M} rapport : non généré (RuntimeError)"]
    assert not chemins.rapport_semaine(PRECEDENTE).exists()
    monkeypatch.setattr(generation, "generer", vrai)  # cycle suivant réussi : l'alerte est levée
    assert synchro(github) == 0
    assert catalogue.RAPPORT_NON_GENERE not in dict(alertes_sync())
    assert chemins.rapport_semaine(PRECEDENTE).is_file()


def semaines(n):
    return [f"2025-W{i:02d}" for i in range(1, n + 1)]


def test_retention_garde_les_douze_plus_recents_par_nom():
    poser_rapports(*semaines(14))
    chemins.rapport_semaine("2024-W52").write_text("x", encoding="utf-8")  # nom ancien, mtime neuf
    (chemins.rapports() / "semaine-2025-W05.html.tmp").write_text("t", encoding="utf-8")
    generation.appliquer_retention()
    restes = sorted(p.name for p in chemins.rapports().iterdir() if p.suffix == ".html")
    assert restes == [f"semaine-2025-W{i:02d}.html" for i in range(3, 15)]
    assert (chemins.rapports() / "semaine-2025-W05.html.tmp").exists()  # .tmp ignoré


def test_retention_ne_supprime_jamais_un_fichier_etranger():
    poser_rapports(*semaines(13))
    for nom in ("notes.html", "semaine-2025-W1.html", "semaine-2025-W01.htm", "semaine-x.html"):
        (chemins.rapports() / nom).write_text("a", encoding="utf-8")
    (chemins.rapports() / "semaine-2020-W01.html").mkdir()  # dossier au nom conforme
    generation.appliquer_retention()
    noms = {p.name for p in chemins.rapports().iterdir()}
    assert {"notes.html", "semaine-2025-W1.html", "semaine-2025-W01.htm", "semaine-x.html"} <= noms
    assert "semaine-2025-W01.html" not in noms
    assert "semaine-2025-W02.html" in noms


def test_etape_ecrit_puis_applique_la_retention(distant, github, gh):
    poser_rapports(*semaines(12))  # douze anciens + le nouveau : le plus ancien part
    assert synchro(github) == 0
    noms = sorted(p.name for p in chemins.rapports().iterdir())
    assert len(noms) == 12
    assert "semaine-2025-W01.html" not in noms
    assert "semaine-2026-W44.html" in noms


@pytest.mark.parametrize(
    ("instant", "attendue"),
    [
        (datetime(2027, 1, 4, 10, 0), "2026-W53"),  # lundi W01 2027 : la précédente est W53
        (datetime(2025, 12, 29, 10, 0), "2025-W52"),  # lundi W01 2026
        (datetime(2026, 1, 5, 10, 0), "2026-W01"),
        (datetime(2026, 12, 31, 12, 0), "2026-W52"),
    ],
)
def test_changement_d_annee(distant, github, gh, monkeypatch, instant, attendue):
    local = instant.astimezone()
    monkeypatch.setattr(cycle, "_maintenant", lambda: local)
    assert synchro(github) == 0
    assert chemins.rapport_semaine(attendue).is_file()


def test_retention_sans_dossier():
    assert not chemins.rapports().exists()
    assert generation.appliquer_retention() == 0


DEBLOQUE = Path.unlink


def verrouiller(monkeypatch, *noms):
    """Simule un fichier ouvert ailleurs (Windows) : `unlink` refusé pour ces noms."""
    vrai = Path.unlink

    def unlink(self, *args, **kwargs):
        if self.name in noms:
            raise PermissionError("verrouillé")
        return vrai(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)


def test_retention_un_fichier_verrouille_n_arrete_pas_les_autres(monkeypatch):
    poser_rapports(*semaines(15))
    verrouiller(monkeypatch, "semaine-2025-W01.html")
    assert generation.appliquer_retention() == 1
    noms = {p.name for p in chemins.rapports().iterdir()}
    assert "semaine-2025-W01.html" in noms
    assert not {"semaine-2025-W02.html", "semaine-2025-W03.html"} & noms


def test_retention_en_echec_ni_alerte_ni_non_genere_et_reprise(distant, github, gh, monkeypatch):
    poser_rapports(*semaines(12))
    verrouiller(monkeypatch, "semaine-2025-W01.html")
    assert synchro(github) == 0
    assert chemins.rapport_semaine(PRECEDENTE).is_file()
    assert catalogue.RAPPORT_NON_GENERE not in dict(alertes_sync())
    assert journal() == [f"{INSTANT:%Y-%m-%d %H:%M} rapport : rétention incomplète (1 fichier(s))"]
    monkeypatch.setattr(Path, "unlink", DEBLOQUE)  # fichier libéré
    assert synchro(github) == 0  # rapport présent : la rétention est quand même reprise
    assert not chemins.rapport_semaine("2025-W01").exists()
    assert len(list(chemins.rapports().iterdir())) == 12
