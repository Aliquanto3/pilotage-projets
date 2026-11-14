"""Story 9.1 : synthèse de la semaine (pure) et lecture de l'historique git de `donnees/`."""

import ast
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pilotage import chemins
from pilotage.noyau import etat, texte
from pilotage.rapport import lecture
from pilotage.rapport.semaine import (
    INDISPONIBLE,
    SANS_COMPARAISON,
    bornes_semaine,
    synthese_semaine,
)

FUSEAU = timezone(timedelta(hours=1))
SEMAINE = "2026-W46"  # lundi 2026-11-09 au dimanche 15
MAINTENANT = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
RACINE_RAPPORT = Path(__file__).resolve().parent.parent / "pilotage" / "rapport"
SESSION_1 = "11111111-1111-4111-8111-111111111111"
SESSION_2 = "22222222-2222-4222-8222-222222222222"
SESSION_3 = "33333333-3333-4333-8333-333333333333"
SECRET = "ghp_" + "a" * 30


def depot(**champs):
    base = {
        "tag": "v1.0.0", "commits": {"docs": 2}, "prs_ouvertes": 0, "ci": "verte",
        "topics": ["status-dev"], "stories_ouvertes": 0, "sprint_status": "present",
        "run": "aucun",
    }
    return {**base, **champs}


def faits(**champs):
    base = {"categorie": "classé", "chantier": None, "pause": None, "attente": None,
            "depot": depot(), "sessions": [], "clone_ici": True, "pcs": ["pc-a"],
            "depot_de": None}
    return {**base, **champs}


def attente(quoi="Choisir la base", depuis="2026-11-10T12:00:00Z", type_="choix"):
    return {"origine": "marqueur", "type": type_, "quoi": quoi, "depuis": depuis, "pc": "pc-a"}


def entree(fin, debut=None, **en_plus):
    return {"faits": fin, "debut": debut, "sessions": [], "alertes": [], "exclus": [],
            "fuseau": FUSEAU, **en_plus}


def synth(ent, maintenant=MAINTENANT):
    return synthese_semaine(ent, SEMAINE, maintenant)


def session(sid, pc="pc-a", projet="alpha", debut="2026-11-10T08:00:00Z", **champs):
    return {"projet": projet, "pc": pc, "session": sid, "debut": debut, **champs}


def jeu_complet():
    fin = {
        "alpha": faits(attente=attente(), depot=depot(tag="v1.1.0", topics=["status-test"])),
        "beta": faits(depot=depot(commits={"feat": 3}), pcs=["pc-b"], depot_de={"pc": "pc-b"}),
        "gamma": faits(),
        "delta": faits(depot=None),
    }
    debut = {
        "alpha": faits(),
        "beta": faits(),
        "gamma": faits(),
        "delta": faits(),
    }
    sessions = [
        session(SESSION_1, dernier_tour="2026-11-11T09:00:00Z"),
        session(SESSION_2, debut="2026-11-12T08:00:00Z", fin="2026-11-12T10:00:00Z"),
        session(SESSION_3, pc="pc-b", projet="beta", debut="2026-11-13T08:00:00Z"),
        session("44444444-4444-4444-8444-444444444444", debut="2026-11-01T08:00:00Z",
                dernier_tour="2026-11-03T08:00:00Z"),  # avant la semaine
    ]
    alertes = [{"code": "scan-echec", "params": {}, "message": "Scan en échec"}]
    return entree(fin, debut, sessions=sessions, alertes=alertes)


def test_bornes_de_semaine_iso():
    debut, fin = bornes_semaine(SEMAINE, FUSEAU)
    assert debut == datetime(2026, 11, 9, tzinfo=FUSEAU)
    assert fin == datetime(2026, 11, 16, tzinfo=FUSEAU)
    assert bornes_semaine("2026-W53", FUSEAU)[0] == datetime(2026, 12, 28, tzinfo=FUSEAU)


@pytest.mark.parametrize("mauvaise", ["2026-46", "2026-W5", "2027-W53", "2026-W00", "", None])
def test_semaine_invalide(mauvaise):
    with pytest.raises(ValueError, match="semaine ISO"):
        bornes_semaine(mauvaise, FUSEAU)


def test_maintenant_naif_refuse():
    with pytest.raises(ValueError, match="fuseau"):
        synth(jeu_complet(), datetime(2026, 11, 14, 12, 0))


def test_synthese_complete():
    s = synth(jeu_complet())
    assert (s.semaine, s.comparaison) == (SEMAINE, True)
    assert s.debut == "2026-11-09T00:00:00+01:00" and s.fin == "2026-11-16T00:00:00+01:00"
    assert s.comptes_debut == {
        "attend-utilisateur": 0, "a-relancer": 0, "tourne": 0, "rien-a-faire": 4,
        "indisponibles": 0,
    }
    assert s.comptes_fin == {
        "attend-utilisateur": 1, "a-relancer": 2, "tourne": 0, "rien-a-faire": 1,
        "indisponibles": 1,
    }
    assert s.alertes == ("Scan en échec",)


def test_changements_avant_apres_et_code_de_raison():
    s = synth(jeu_complet())
    assert [(c["projet"], c["avant"], c["apres"]) for c in s.changements] == [
        ("alpha", "rien-a-faire", "attend-utilisateur"),
        ("beta", "rien-a-faire", "a-relancer"),
        ("delta", "rien-a-faire", "a-relancer"),
    ]
    codes = {c["projet"]: c["code"] for c in s.changements}
    assert codes == {"alpha": "attend-utilisateur", "beta": "a-stabiliser",
                     "delta": "faits-absents"}


def test_attentes_projet_type_quoi_age():
    s = synth(jeu_complet())
    assert s.attentes == (
        {"projet": "alpha", "type": "choix", "quoi": "Choisir la base", "age_jours": 4},
    )


def test_livraisons_release_et_phase():
    s = synth(jeu_complet())
    assert s.livraisons == (
        {"projet": "alpha", "type": "release", "tag": "v1.1.0", "avant": "v1.0.0"},
        {"projet": "alpha", "type": "phase", "avant": ["status-dev"], "apres": ["status-test"]},
    )


def test_sessions_par_projet_et_par_pc():
    s = synth(jeu_complet())
    assert s.sessions == (
        {"projet": "alpha", "pc": "pc-a", "nombre": 2, "premiere": "2026-11-10T08:00:00Z",
         "derniere": "2026-11-12T10:00:00Z"},
        {"projet": "beta", "pc": "pc-b", "nombre": 1, "premiere": "2026-11-13T08:00:00Z",
         "derniere": "2026-11-13T08:00:00Z"},
    )


def test_session_doublon_compte_une_fois():
    ent = jeu_complet()
    ent["sessions"] = ent["sessions"] + [dict(ent["sessions"][0])]
    assert synth(ent).sessions[0]["nombre"] == 2


def test_session_a_la_borne():
    ent = entree({"alpha": faits()}, sessions=[
        session(SESSION_1, debut="2026-11-08T23:00:00Z", dernier_tour="2026-11-08T23:00:00Z"),
        session(SESSION_2, debut="2026-11-08T22:59:59Z", dernier_tour="2026-11-08T23:00:00Z"),
        session(SESSION_3, debut="2026-11-15T23:00:00Z"),  # lundi 00:00 local suivant : exclue
    ])
    # début de semaine = 2026-11-08T23:00:00Z ; fin = 2026-11-15T23:00:00Z
    assert synth(ent).sessions[0]["nombre"] == 2
    assert len(synth(ent).sessions) == 1


def test_meme_entree_meme_synthese_et_tri_action_puis_nom():
    ent = jeu_complet()
    inverse = {**ent, "faits": dict(reversed(list(ent["faits"].items()))),
               "sessions": list(reversed(ent["sessions"]))}
    assert synth(ent) == synth(ent) == synth(inverse)
    classement = [(p["action"], p["nom"]) for p in synth(ent).projets]
    assert classement == [
        ("attend-utilisateur", "alpha"), ("a-relancer", "beta"), ("a-relancer", "delta"),
        ("rien-a-faire", "gamma"),
    ]
    ordre = [etat.ACTIONS.index(a) for a, _ in classement]
    assert ordre == sorted(ordre)


def test_projet_exclu_absent():
    ent = jeu_complet()
    ent["exclus"] = ["alpha", "beta"]
    s = synth(ent)
    assert [p["nom"] for p in s.projets] == ["delta", "gamma"]
    assert sum(s.comptes_fin[a] for a in etat.ACTIONS) == 2
    assert s.attentes == () and s.livraisons == () and s.changements[0]["projet"] == "delta"
    assert s.sessions == ()


def test_faits_manquants_indisponibles_jamais_stables():
    s = synth(jeu_complet())
    delta = next(p for p in s.projets if p["nom"] == "delta")
    assert delta == {"nom": "delta", "action": "a-relancer", "raison": "faits-absents",
                     "indisponible": True}
    assert s.comptes_fin["indisponibles"] == 1
    assert s.comptes_fin["rien-a-faire"] == 1  # gamma seul
    assert INDISPONIBLE == "faits indisponibles"


def test_depot_mal_type_jamais_stable():
    ent = entree({"x": faits(depot=depot(prs_ouvertes="2"))})
    assert synth(ent).projets[0]["indisponible"] is True


def test_sans_etat_de_debut_pas_de_comparaison_et_le_reste_est_calcule():
    ent = jeu_complet()
    ent["debut"] = None
    s = synth(ent)
    assert s.comparaison is False and SANS_COMPARAISON == "pas de point de comparaison"
    assert (s.comptes_debut, s.changements, s.livraisons) == (None, (), ())
    assert s.comptes_fin["attend-utilisateur"] == 1
    assert len(s.attentes) == 1 and len(s.sessions) == 2 and s.alertes == ("Scan en échec",)


def test_quoi_filtre_et_borne():
    secret = entree({"a": faits(attente=attente(quoi=f"Coller {SECRET} ici"))})
    assert synth(secret).attentes[0]["quoi"] == ""
    long = entree({"a": faits(attente=attente(quoi="é" * 500))})
    assert synth(long).attentes[0]["quoi"] == "é" * texte.BORNE_QUOI


def test_ni_note_ni_prompt_ni_titre_ni_message_dans_la_synthese():
    interdits = ["NOTE-REPRISE-X", "PROMPT-X", "TITRE-PR-X", "MESSAGE-COMMIT-X"]
    ent = jeu_complet()
    ent["sessions"][0].update(dernier_prompt=interdits[1], reprise={"note": interdits[0]})
    ent["faits"]["alpha"]["depot"].update(titre_pr=interdits[2], message_commit=interdits[3])
    ent["faits"]["alpha"]["sessions"] = [{**ent["sessions"][0], "attente": {
        "quoi": "ok", "depuis": "2026-11-10T08:00:00Z"}}]
    rendu = repr(synth(ent))
    assert not [m for m in interdits if m in rendu]


def test_aucune_action_calculee_hors_de_calculer_action():
    """Test d'import : les modules du rapport n'empruntent à `noyau.etat` que l'assemblage."""
    permis = {"assembler", "ACTIONS", "ATTEND"}
    interdits_noyau = {"heuristique", "faits", "cadrage", "marqueur"}
    for fichier in RACINE_RAPPORT.glob("*.py"):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            if isinstance(n, ast.ImportFrom) and n.module == "pilotage.noyau.etat":
                assert {a.name for a in n.names} <= permis, fichier.name
            if isinstance(n, ast.ImportFrom) and n.module == "pilotage.noyau":
                assert not {a.name for a in n.names} & interdits_noyau, fichier.name
            if isinstance(n, ast.Name | ast.Attribute):
                nom = n.id if isinstance(n, ast.Name) else n.attr
                assert nom not in {"critere_manquant", "_verdict", "calculer_action_"}, nom
    sources = (RACINE_RAPPORT / "semaine.py").read_text(encoding="utf-8")
    assert "etat.assembler(" in sources  # seule voie vers `calculer_action`


def test_semaine_sans_entree_sortie_ni_processus():
    arbre = ast.parse((RACINE_RAPPORT / "semaine.py").read_text(encoding="utf-8"))
    importes = {
        (n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
        for n in ast.walk(arbre) if isinstance(n, ast.Import | ast.ImportFrom)
        for a in getattr(n, "names", [])
    }
    assert not importes & {"os", "subprocess", "pathlib", "socket", "json", "shutil", "chemins"}


# --- lecture : historique git de donnees/ -------------------------------------------------

def _git(depot_git, *args, quand=None):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_CONFIG_COUNT": "0"}
    if quand:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = quand
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=depot_git, env=env, check=True, capture_output=True, stdin=subprocess.DEVNULL,
    )


def _instantane(tag, topics=("status-dev",), genere="2026-11-05T10:00:00Z"):
    return {"schema": 1, "genere_a": genere, "projets": {"alpha": {
        "faits_depot": depot(tag=tag, topics=list(topics)), "sessions_vivantes": []}}}


def _commit(dossier, tag, quand, nom="pc-a"):
    cible = dossier / "instantanes" / f"{nom}.json"
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(json.dumps(_instantane(tag)), encoding="utf-8")
    _git(dossier, "add", "-A")
    _git(dossier, "commit", "-m", f"instantané {tag}", quand=quand)


@pytest.fixture
def depot_donnees(monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "pc-local")
    dossier = chemins.donnees()
    dossier.mkdir(parents=True)
    chemins.racine_github().mkdir(parents=True, exist_ok=True)
    _git(dossier, "init", "-q")
    return dossier


def test_etat_de_debut_dernier_commit_avant_le_lundi_local(depot_donnees):
    # lundi 2026-11-09 00:00 local ; le fuseau local du poste fixe l'instant exact
    lundi = datetime(2026, 11, 9).astimezone()
    avant = (lundi - timedelta(seconds=5)).isoformat()
    _commit(depot_donnees, "v0.9.0", (lundi - timedelta(days=3)).isoformat())
    _commit(depot_donnees, "v1.0.0", avant)
    _commit(depot_donnees, "v1.1.0", lundi.isoformat())  # pile au lundi : pas « avant »
    _commit(depot_donnees, "v1.2.0", (lundi + timedelta(days=2)).isoformat())
    entree_ = lecture.lire_entree(SEMAINE, MAINTENANT)
    assert entree_["debut"]["alpha"]["depot"]["tag"] == "v1.0.0"
    assert entree_["faits"]["alpha"]["depot"]["tag"] == "v1.2.0"
    s = synthese_semaine(entree_, SEMAINE, MAINTENANT)
    assert s.comparaison is True
    assert s.livraisons[0] == {"projet": "alpha", "type": "release", "tag": "v1.2.0",
                               "avant": "v1.0.0"}


def test_semaine_finie_etat_de_fin_au_dernier_commit_avant_le_lundi_suivant(depot_donnees):
    suivant = datetime(2026, 11, 16).astimezone()
    _commit(depot_donnees, "v1.0.0", (suivant - timedelta(days=8)).isoformat())
    _commit(depot_donnees, "v1.1.0", (suivant - timedelta(days=1)).isoformat())
    _commit(depot_donnees, "v2.0.0", (suivant + timedelta(days=4)).isoformat())
    apres = datetime(2026, 11, 25, tzinfo=UTC)
    entree_ = lecture.lire_entree(SEMAINE, apres)
    assert entree_["faits"]["alpha"]["depot"]["tag"] == "v1.1.0"
    assert entree_["debut"]["alpha"]["depot"]["tag"] == "v1.0.0"


def test_pas_de_commit_avant_le_lundi_pas_de_comparaison(depot_donnees):
    lundi = datetime(2026, 11, 9).astimezone()
    _commit(depot_donnees, "v1.0.0", (lundi + timedelta(days=1)).isoformat())
    entree_ = lecture.lire_entree(SEMAINE, MAINTENANT)
    assert entree_["debut"] is None
    assert synthese_semaine(entree_, SEMAINE, MAINTENANT).comparaison is False


def test_donnees_sans_depot_git_pas_de_comparaison(monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "pc-local")
    chemins.donnees().mkdir(parents=True)
    chemins.racine_github().mkdir(parents=True, exist_ok=True)
    assert lecture.lire_entree(SEMAINE, MAINTENANT)["debut"] is None


def test_donnees_absent_pas_de_comparaison(monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "pc-local")
    chemins.racine_github().mkdir(parents=True, exist_ok=True)
    assert lecture.lire_entree(SEMAINE, MAINTENANT)["debut"] is None


def test_git_en_erreur_pas_de_comparaison(depot_donnees):
    lundi = datetime(2026, 11, 9).astimezone()
    _commit(depot_donnees, "v1.0.0", (lundi - timedelta(days=1)).isoformat())
    assert lecture.commit_avant(depot_donnees, lundi) is not None
    (depot_donnees / ".git" / "HEAD").unlink()  # dépôt corrompu : git répond une erreur
    assert lecture.commit_avant(depot_donnees, lundi) is None
    assert lecture.lire_entree(SEMAINE, MAINTENANT)["debut"] is None


def test_fichier_invalide_a_un_commit_ignore(depot_donnees):
    lundi = datetime(2026, 11, 9).astimezone()
    (depot_donnees / "instantanes").mkdir()
    (depot_donnees / "instantanes" / "pc-a.json").write_text("{pas du json", encoding="utf-8")
    _git(depot_donnees, "add", "-A")
    _git(depot_donnees, "commit", "-m", "x", quand=(lundi - timedelta(days=1)).isoformat())
    assert lecture.lire_entree(SEMAINE, MAINTENANT)["debut"] is None


def test_sessions_archivees_et_exclus_lus(depot_donnees):
    archive = chemins.attente() / "archive" / "etat" / "alpha" / "pc-local"
    archive.mkdir(parents=True)
    ancien = {
        "schema": 1, "projet": "alpha", "pc": "pc-local", "session": SESSION_1, "pid": 5,
        "pid_cree": None, "dossier": "alpha", "branche": None,
        "debut": "2026-11-10T08:00:00Z", "statut": "finie", "fin": "2026-11-10T09:00:00Z",
    }
    (archive / f"{SESSION_1}.json").write_text(json.dumps(ancien), encoding="utf-8")
    (archive / "illisible.json").write_text("{", encoding="utf-8")
    entree_ = lecture.lire_entree(SEMAINE, MAINTENANT)
    s = synthese_semaine(entree_, SEMAINE, MAINTENANT)
    assert [(x["projet"], x["pc"], x["nombre"]) for x in s.sessions] == [("alpha", "pc-local", 1)]


# --- changement d'heure (revue, passe 1) ------------------------------------------------------

class _Paris2026(lecture.FuseauLocal):
    """Règle de Paris en 2026 à la place de celle du poste : +01:00, puis +02:00 du 29 mars
    01:00Z au 25 octobre 01:00Z. Seules les deux questions posées au système sont remplacées."""

    ETE = (datetime(2026, 3, 29, 1), datetime(2026, 10, 25, 1))  # UTC naïf

    def _decalage_utc(self, naif_utc):
        return timedelta(hours=2 if self.ETE[0] <= naif_utc < self.ETE[1] else 1)

    def _decalage(self, naif):
        # heure locale : l'heure sautée (02:00-03:00 le 29 mars) prend l'ancien décalage ;
        # l'heure répétée (02:00-03:00 le 25 octobre) prend l'heure d'été sauf si fold=1
        if datetime(2026, 3, 29, 2) <= naif < datetime(2026, 10, 25, 2):
            return timedelta(hours=2)
        if datetime(2026, 10, 25, 2) <= naif < datetime(2026, 10, 25, 3) and not naif.fold:
            return timedelta(hours=2)
        return timedelta(hours=1)


@pytest.mark.parametrize(("semaine", "avant", "apres"), [
    ("2026-W13", "+01:00", "+02:00"),  # passage à l'heure d'été le dimanche 29 mars
    ("2026-W43", "+02:00", "+01:00"),  # passage à l'heure d'hiver le dimanche 25 octobre
])
def test_bornes_d_une_semaine_de_changement_d_heure(semaine, avant, apres):
    debut, fin = bornes_semaine(semaine, _Paris2026())
    assert debut.isoformat().endswith(avant) and fin.isoformat().endswith(apres)
    assert (fin - debut.astimezone(UTC)) == timedelta(days=7, hours=int(avant[2]) - int(apres[2]))


def test_session_du_lundi_suivant_hors_de_la_semaine_de_changement_d_heure():
    # lundi 30 mars 00:30 heure d'été = 2026-03-29T22:30Z : semaine W14, pas W13
    tardive = session(SESSION_1, debut="2026-03-29T22:30:00Z")
    dimanche = session(SESSION_2, debut="2026-03-29T21:30:00Z")  # dimanche 23:30 locale
    ent = entree({"alpha": faits()}, sessions=[tardive, dimanche], fuseau=_Paris2026())
    s = synthese_semaine(ent, "2026-W13", datetime(2026, 4, 2, tzinfo=UTC))
    assert [(x["nombre"], x["premiere"]) for x in s.sessions] == [(1, "2026-03-29T21:30:00Z")]


def test_fuseau_local_convertit_chaque_instant_avec_sa_regle():
    paris = _Paris2026()
    for instant in (datetime(2026, 3, 29, 0, 59, tzinfo=UTC), datetime(2026, 3, 29, 1, tzinfo=UTC),
                    datetime(2026, 10, 25, 0, 30, tzinfo=UTC),
                    datetime(2026, 10, 25, 1, 30, tzinfo=UTC)):
        local = instant.astimezone(paris)
        assert local.astimezone(UTC) == instant  # aller-retour exact, heure répétée comprise
    assert datetime(2026, 10, 25, 0, 30, tzinfo=UTC).astimezone(paris).isoformat() \
        == "2026-10-25T02:30:00+02:00"
    assert datetime(2026, 10, 25, 1, 30, tzinfo=UTC).astimezone(paris).isoformat() \
        == "2026-10-25T02:30:00+01:00"


def test_fuseau_local_suit_le_systeme_sur_chaque_borne():
    for semaine in ("2026-W13", "2026-W43"):
        for borne in bornes_semaine(semaine, lecture.FuseauLocal()):
            naif = borne.replace(tzinfo=None)
            assert borne.utcoffset() == naif.astimezone().utcoffset()
            assert borne.astimezone(UTC).astimezone(lecture.FuseauLocal()) == borne


def test_synthese_nomme_l_approximation_des_livraisons():
    assert "ne datent pas les tags" in synth(jeu_complet()).note_livraisons


def test_arete_rapport_scan_bornee_a_la_lecture():
    """`rapport → scan` sert à lire les faits : `semaine.py` n'importe que le noyau."""
    arbre = ast.parse((RACINE_RAPPORT / "semaine.py").read_text(encoding="utf-8"))
    modules = {n.module for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(arbre) if isinstance(n, ast.Import) for a in n.names}
    assert {m for m in modules if m.startswith("pilotage")} <= {"pilotage.noyau"} | {
        m for m in modules if m.startswith("pilotage.noyau.")}
