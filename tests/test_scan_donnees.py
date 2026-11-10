"""Tests de `scan.donnees` et du scan assemblé sur plusieurs PC (story 3.4)."""

import json

import pytest

from pilotage import chemins
from pilotage.noyau import schemas
from pilotage.scan import cli, donnees, faits_gh
from tests.test_faits_gh import faux_gh
from tests.test_inventaire import faux_depot
from tests.test_scan_cli import nom_propre  # noqa: F401 (fixture autouse du mutex)
from tests.test_scan_sessions import SID, etat

DEPOT = {
    "tag": "v1.0.0", "commits": {}, "prs_ouvertes": 0, "ci": "verte", "topics": [],
    "stories_ouvertes": 0, "sprint_status": "present", "run": "aucun",
}


def ecrire(relatif, objet):
    chemin = chemins.donnees() / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet), "utf-8")


def instantane_distant(pc, genere, projets):
    objet = {"schema": 1, "genere_a": genere, "projets": projets}
    schemas.valider("instantane", objet)
    ecrire(f"instantanes/{pc}.json", objet)
    return objet


def etat_distant(pc="pc-b", projet="demo", session=SID, **champs):
    objet = {
        "schema": 1, "projet": projet, "pc": pc, "session": session, "pid": 77,
        "pid_cree": None, "dossier": projet, "branche": "main",
        "debut": "2026-11-06T08:00:00Z", "statut": "active", **champs,
    }
    schemas.valider("session", objet)
    ecrire(f"etat/{projet}/{pc}/{session}.json", objet)
    return objet


# --- lecture de donnees/ ---


def test_lit_les_autres_pc_et_ignore_ce_pc():
    instantane_distant("pc-b", "2026-11-06T10:00:00Z", {"demo": {"faits_depot": None,
                                                                 "sessions_vivantes": []}})
    instantane_distant("pc-a", "2026-11-06T10:00:00Z", {})
    etat_distant("pc-b")
    etat_distant("pc-a", session="0a1b2c3d-0000-4000-8000-000000000002")
    instantanes, etats, alertes = donnees.lire_autres_pcs("pc-a")
    assert list(instantanes) == ["pc-b"]
    assert {pc: {p: [s["session"] for s in v] for p, v in d.items()} for pc, d in etats.items()} \
        == {"pc-b": {"demo": [SID]}}
    assert alertes == []


def test_donnees_absent_rien_a_lire_sans_alerte():
    assert donnees.lire_autres_pcs("pc-a") == ({}, {}, [])


def test_instantane_de_schema_plus_recent_ignore_avec_alerte_de_lecture():
    ecrire("instantanes/pc-b.json", {"schema": 2, "genere_a": "x", "projets": 5})
    instantanes, _, alertes = donnees.lire_autres_pcs("pc-a")
    assert instantanes == {}
    assert alertes == [{
        "code": "donnees-version-recente",
        "message": (
            "Fichiers de pc-b ignorés : version plus récente. "
            "Mettez à jour pilotage-projets sur ce PC."
        ),
        "params": {"pc": "pc-b", "quelle": "plus récente"},
    }]


@pytest.mark.parametrize(
    "version, suite",
    [
        (0, "version inconnue."),
        (-3, "version inconnue."),
        (7, "version plus récente. Mettez à jour pilotage-projets sur ce PC."),
    ],
)
def test_message_de_version_juste_selon_le_schema(version, suite):
    ecrire("instantanes/pc-b.json", {"schema": version, "genere_a": "x", "projets": {}})
    _, _, alertes = donnees.lire_autres_pcs("pc-a")
    assert [a["message"] for a in alertes] == [f"Fichiers de pc-b ignorés : {suite}"]


def test_date_calendaire_impossible_d_un_autre_pc_ignoree_sans_masquer_les_autres():
    ecrire("instantanes/pc-b.json", {"schema": 1, "genere_a": "2026-99-99T00:00:00Z", "projets": {
        "demo": {"faits_depot": dict(DEPOT, tag="v9.9.9"), "sessions_vivantes": []}}})
    ecrire("instantanes/pc-c.json", {"schema": 1, "genere_a": "2026-11-06T10:00:00Z", "projets": {
        "demo": {"faits_depot": DEPOT, "sessions_vivantes": []}}})
    instantanes, _, alertes = donnees.lire_autres_pcs("pc-a")
    assert list(instantanes) == ["pc-c"]
    assert [a["code"] for a in alertes] == ["donnees-illisibles"]


def test_etat_de_schema_inconnu_ignore_une_alerte_par_pc():
    for n in (2, 3):
        ecrire(f"etat/demo/pc-c/0a1b2c3d-0000-4000-8000-00000000000{n}.json", {"schema": n + 8})
    etat_distant("pc-b")
    _, etats, alertes = donnees.lire_autres_pcs("pc-a")
    assert list(etats) == ["pc-b"]
    assert [a["message"] for a in alertes] == [
        "Fichiers de pc-c ignorés : version plus récente. Mettez à jour pilotage-projets sur ce PC."
    ]


def test_fichier_illisible_ou_invalide_ou_hors_de_sa_place_alerte_fixe():
    (chemins.donnees() / "instantanes").mkdir(parents=True)
    (chemins.donnees() / "instantanes" / "pc-b.json").write_text("{pas du json", "utf-8")
    ecrire("instantanes/pc-c.json", {"schema": 1, "genere_a": "hier", "projets": {}})  # invalide
    ecrire("instantanes/PC Mauvais.json", {})  # nom de PC invalide
    objet = etat_distant("pc-d")
    ecrire("etat/demo/pc-e/" + f"{SID}.json", objet)  # pc du contenu différent du dossier
    instantanes, etats, alertes = donnees.lire_autres_pcs("pc-a")
    assert (instantanes, list(etats)) == ({}, ["pc-d"])
    assert alertes == [{
        "code": "donnees-illisibles", "message": "Fichier de donnees/ illisible ignoré",
    }]


# --- scan bout en bout ---


@pytest.fixture
def github(tmp_path):
    racine = tmp_path / "github"
    faux_depot(racine / "demo", url="https://github.com/Proprio-Test/demo.git")
    return racine


def scanner(github):
    return cli.main(["--racine-github", str(github), "--pc", "pc-a"])


def test_tableau_assemble_les_pc_fraicheur_et_pas_clone_ici(github, monkeypatch):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh(release=None))
    instantane_distant("pc-b", "2026-11-06T10:00:00Z", {
        "ailleurs": {"faits_depot": DEPOT, "sessions_vivantes": []},
        "demo": {"faits_depot": DEPOT, "sessions_vivantes": []},
    })
    assert scanner(github) == 0
    texte = chemins.tableau().read_text("utf-8")
    # depot de demo : le plus récent qui les contient = le scan du jour (pc-a), pas pc-b
    ailleurs = next(lg for lg in texte.splitlines() if lg.startswith("- **ailleurs**"))
    assert ailleurs.startswith(
        "- **ailleurs** : à classer · pas cloné ici · dépôt vu par pc-b le 06/11 "
    )
    assert ailleurs.endswith(" · phase : — · chantier : —")
    demo = next(lg for lg in texte.splitlines() if lg.startswith("- **demo**"))
    assert demo.startswith("- **demo** : run non terminé")
    assert "dépôt vu par" not in demo  # faits de ce PC : pas d'origine affichée
    assert "## Fraîcheur des PC" in texte
    fin = texte.split("## Fraîcheur des PC")[1].splitlines()
    assert [ligne for ligne in fin if ligne.startswith("- ")][0].startswith("- pc-a (ce PC) :")
    assert [ligne for ligne in fin if ligne.startswith("- ")][1].startswith(
        "- pc-b : instantané du 06/11 ")
    assert "Alertes de lecture" not in texte


def test_alerte_de_lecture_dans_le_tableau_jamais_dans_alertes_json(github, monkeypatch):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    ecrire("instantanes/pc-b.json", {"schema": 9})
    assert scanner(github) == 0
    texte = chemins.tableau().read_text("utf-8")
    assert "## Alertes de lecture\n\n- Fichiers de pc-b ignorés : version plus récente. " in texte
    assert json.loads(chemins.alertes_json().read_text("utf-8")) == {"schema": 1, "alertes": []}


def test_le_pc_courant_se_lit_dans_attente_pas_dans_donnees(github, monkeypatch):
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    etat(session=SID, pc="pc-a", fin="2026-11-06T09:00:00Z", statut="finie")
    # une copie périmée de ce PC dans donnees/ (session sans fin) est ignorée
    etat_distant("pc-a", session="0a1b2c3d-0000-4000-8000-000000000002")
    instantane_distant("pc-a", "2026-11-06T10:00:00Z", {})
    assert scanner(github) == 0
    texte = chemins.tableau().read_text("utf-8")
    assert "arrêtée" not in texte
    assert "sans nouvelles" not in texte


def test_session_d_un_autre_pc_cite_par_un_instantane_recent_tourne(github, monkeypatch):
    from datetime import UTC, datetime
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    maintenant = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    instantane_distant("pc-b", maintenant, {
        "demo": {"faits_depot": DEPOT, "sessions_vivantes": [SID]},
    })
    etat_distant("pc-b")
    assert scanner(github) == 0
    assert "- **demo** : tourne sur pc-b, session 0a1b2c3d" in chemins.tableau().read_text("utf-8")
