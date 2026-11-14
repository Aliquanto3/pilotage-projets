"""Story 8.1 : `hooks.note.derniere_note`, choix de la dernière note de reprise (racine isolée)."""

import json
import os

import pytest

from pilotage import chemins
from pilotage.hooks import _commun, note

PROJET = "projet-n"
PC = "pc-ici"
AUTRE = "pc-la"
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
S3 = "33333333-3333-4333-8333-333333333333"
COURANTE = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


@pytest.fixture
def ctx(racine_locale_isolee):
    return _commun.Contexte(
        projet=PROJET, pc=PC, session=COURANTE, dossier="projet-n",
        cwd=str(racine_locale_isolee / "github" / "projet-n"),
    )


def _etat(session, pc=PC, projet=PROJET, **champs) -> dict:
    objet = {
        "schema": 1, "projet": projet, "pc": pc, "session": session, "pid": 4,
        "pid_cree": None, "dossier": "projet-n", "branche": "main",
        "debut": "2026-11-10T08:00:00Z", "statut": "finie", "fin": "2026-11-10T09:00:00Z",
    }
    objet.update(champs)
    return {cle: valeur for cle, valeur in objet.items() if valeur is not None or cle == "pid_cree"}


def _dossier(pc=PC, ou="attente", projet=PROJET):
    racine = chemins.attente() if ou == "attente" else chemins.donnees()
    dossier = racine / "etat" / projet / pc
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def _deposer(objet, pc=PC, ou="attente", nom=None, mtime=None, brut=None):
    chemin = _dossier(pc, ou) / (nom or f"{objet['session']}.json")
    if brut is None:
        brut = json.dumps(objet, ensure_ascii=False).encode("utf-8")
    chemin.write_bytes(brut)
    if mtime is not None:
        os.utime(chemin, (mtime, mtime))
    return chemin


def _journal() -> list[str]:
    dossier = chemins.attente() / "journal"
    if not dossier.exists():
        return []
    return [
        ligne.split(" ", 1)[1]
        for fichier in sorted(dossier.glob("hooks-*.log"))
        for ligne in fichier.read_text(encoding="utf-8").splitlines()
    ]


# --- Choix de la note ---------------------------------------------------------------------


def test_aucun_etat_aucune_note(ctx):
    assert note.derniere_note(ctx) is None
    assert _journal() == []


def test_note_d_un_autre_pc_plus_recente(ctx):
    _deposer(_etat(S1, reprise="N1 hier", dernier_tour="2026-11-13T18:00:00Z"))
    _deposer(_etat(S2, pc=AUTRE, reprise="N2 ce matin", dernier_tour="2026-11-14T07:30:00Z"),
             pc=AUTRE, ou="donnees")
    assert note.derniere_note(ctx) == note.NoteRetenue(
        AUTRE, S2, "2026-11-14T07:30:00Z", "N2 ce matin"
    )
    assert _journal() == []


def test_note_de_ce_pc_plus_recente(ctx):
    _deposer(_etat(S1, reprise="N1", dernier_tour="2026-11-14T10:00:00Z"))
    _deposer(_etat(S2, pc=AUTRE, reprise="N2", dernier_tour="2026-11-14T07:30:00Z"),
             pc=AUTRE, ou="donnees")
    assert note.derniere_note(ctx) == note.NoteRetenue(PC, S1, "2026-11-14T10:00:00Z", "N1")


def test_session_courante_comprise(ctx):
    _deposer(_etat(S1, reprise="ancienne", dernier_tour="2026-11-13T10:00:00Z"))
    _deposer(_etat(COURANTE, reprise="la mienne", dernier_tour="2026-11-14T10:00:00Z",
                   statut="active", fin=None))
    assert note.derniere_note(ctx).session == COURANTE
    assert note.derniere_note(ctx).texte == "la mienne"


def test_debut_quand_pas_de_dernier_tour(ctx):
    _deposer(_etat(S1, reprise="par tour", dernier_tour="2026-11-12T10:00:00Z"))
    _deposer(_etat(S2, reprise="par début", debut="2026-11-13T10:00:00Z",
                   fin="2026-11-13T11:00:00Z"))
    assert note.derniere_note(ctx) == note.NoteRetenue(
        PC, S2, "2026-11-13T10:00:00Z", "par début"
    )


def test_egalite_departagee_par_session(ctx):
    heure = "2026-11-14T10:00:00Z"
    _deposer(_etat(S3, reprise="trois", dernier_tour=heure))
    _deposer(_etat(S1, reprise="un", dernier_tour=heure))
    _deposer(_etat(S2, reprise="deux", dernier_tour=heure))
    assert note.derniere_note(ctx).session == S1


def test_etat_sans_note_ignore(ctx):
    _deposer(_etat(S1, reprise="la note", dernier_tour="2026-11-13T10:00:00Z"))
    _deposer(_etat(S2, dernier_tour="2026-11-14T10:00:00Z"))
    _deposer(_etat(S3, reprise="   ", dernier_tour="2026-11-14T11:00:00Z"))
    assert note.derniere_note(ctx).session == S1


def test_ce_pc_lu_dans_attente_seulement(ctx):
    """M5 : une copie de ce PC dans `donnees/` n'est pas lue (elle peut être en retard)."""
    _deposer(_etat(S1, reprise="copie poussée", dernier_tour="2026-11-14T10:00:00Z"),
             ou="donnees")
    assert note.derniere_note(ctx) is None


def test_racine_github_normalisee(ctx):
    racine = str(chemins.racine_github())
    heure = "2026-11-14T10:00:00Z"
    _deposer(_etat(S1, reprise=f"voir {racine}\\projet-n\\x.md", dernier_tour=heure))
    assert note.derniere_note(ctx).texte == "voir {{RACINE_GITHUB}}\\projet-n\\x.md"


# --- Filtre rejoué ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "suspecte", ["jeton ghp_abcdefghijklmnop", "clé AKIAABCDEFGHIJKLMNOP", "Bearer abc", "s​k-x"]
)
def test_note_suspecte_ecartee_au_profit_de_la_suivante(ctx, suspecte):
    _deposer(_etat(S1, reprise="saine", dernier_tour="2026-11-13T10:00:00Z"))
    _deposer(_etat(S2, pc=AUTRE, reprise=suspecte, dernier_tour="2026-11-14T10:00:00Z"),
             pc=AUTRE, ou="donnees")
    retenue = note.derniere_note(ctx)
    assert (retenue.session, retenue.texte) == (S1, "saine")


def test_note_suspecte_seule_aucune_note(ctx):
    _deposer(_etat(S1, reprise="ghp_secret", dernier_tour="2026-11-14T10:00:00Z"))
    assert note.derniere_note(ctx) is None
    assert _journal() == []


# --- États invalides ------------------------------------------------------------------------


VALIDE = _etat(S1, reprise="valide", dernier_tour="2026-11-10T10:00:00Z")


def _recent(**champs):
    return _etat(S2, reprise="piège", dernier_tour="2026-11-14T10:00:00Z", **champs)


@pytest.mark.parametrize(
    "fabrique",
    [
        pytest.param(lambda: {"brut": b'{"schema": 1, "projet": '}, id="json-tronque"),
        pytest.param(lambda: {"objet": {**_recent(), "inconnu": 1}}, id="schema-faux"),
        pytest.param(lambda: {"objet": _recent(projet="autre-projet")}, id="projet-autre"),
        pytest.param(lambda: {"objet": _recent(pc=AUTRE)}, id="pc-autre"),
        pytest.param(lambda: {"objet": _recent(), "nom": f"{S3}.json"}, id="nom-autre"),
        pytest.param(
            lambda: {"brut": b"\xef\xbb\xbf" + json.dumps(_recent()).encode()}, id="bom"
        ),
        pytest.param(lambda: {"brut": b"\xff" + json.dumps(_recent()).encode()}, id="non-utf8"),
        pytest.param(lambda: {"objet": {**_recent(), "reprise": 42}}, id="reprise-non-chaine"),
        pytest.param(lambda: {"objet": {**_recent(), "reprise": "x" * 301}}, id="reprise-longue"),
        pytest.param(lambda: {"brut": b"[" * 30_000 + b"]" * 30_000}, id="imbrication"),
        pytest.param(
            lambda: {"brut": json.dumps({**_recent(), "branche": "b" * 200}).encode()
                     + b" " * (1024 * 1024)},
            id="un-mio",
        ),
    ],
)
def test_etat_invalide_ignore(ctx, fabrique):
    _deposer(VALIDE)
    piege = fabrique()
    _deposer(piege.get("objet", _recent()), nom=piege.get("nom"), brut=piege.get("brut"))
    retenue = note.derniere_note(ctx)
    assert (retenue.session, retenue.texte) == (S1, "valide")
    assert _journal() == []


def test_etat_juste_sous_64_kio_lu(ctx):
    brut = json.dumps(_recent()).encode()
    brut += b" " * (note.BORNE_ETAT_OCTETS - len(brut))
    assert len(brut) == note.BORNE_ETAT_OCTETS
    _deposer(_recent(), brut=brut)
    assert note.derniere_note(ctx).session == S2
    _deposer(_recent(), brut=brut + b" ")
    assert note.derniere_note(ctx) is None


def test_pc_au_nom_invalide_ignore(ctx):
    dossier = chemins.donnees() / "etat" / PROJET / "PC_Invalide"
    dossier.mkdir(parents=True)
    objet = _etat(S2, pc="PC_Invalide", reprise="piège", dernier_tour="2026-11-14T10:00:00Z")
    (dossier / f"{S2}.json").write_text(json.dumps(objet), encoding="utf-8")
    assert note.derniere_note(ctx) is None
    assert _journal() == []


def test_fichiers_hors_convention_ignores(ctx):
    dossier = _dossier()
    (dossier / "sous-dossier.json").mkdir()
    (dossier / f"{S1}.json.tmp").write_text(json.dumps(VALIDE), encoding="utf-8")
    (chemins.donnees() / "etat" / PROJET).mkdir(parents=True)
    (chemins.donnees() / "etat" / PROJET / "fichier-pas-dossier").write_text("x")
    assert note.derniere_note(ctx) is None


def test_dossiers_absents(ctx):
    (chemins.attente()).mkdir(parents=True, exist_ok=True)
    assert note.derniere_note(ctx) is None
    assert _journal() == []


def test_autres_projets_non_lus(ctx):
    autre = chemins.attente() / "etat" / "autre-projet" / PC
    autre.mkdir(parents=True)
    objet = _etat(S1, projet="autre-projet", reprise="pas ici", dernier_tour="2026-11-14T10:00:00Z")
    (autre / f"{S1}.json").write_text(json.dumps(objet), encoding="utf-8")
    assert note.derniere_note(ctx) is None


# --- Borne de lecture -----------------------------------------------------------------------


def test_au_plus_vingt_fichiers_les_plus_recents_par_mtime(ctx, monkeypatch):
    """Le 21e fichier par `mtime` n'est pas ouvert, même s'il porte la note la plus récente."""
    ouverts = []
    vrai_open = open

    def compter(chemin, *args, **kwargs):  # frontière : système de fichiers
        ouverts.append(os.path.basename(str(chemin)))
        return vrai_open(chemin, *args, **kwargs)

    sessions = [f"{i:08x}-0000-4000-8000-000000000000" for i in range(25)]
    for i, session in enumerate(sessions):
        objet = _etat(session, dernier_tour=f"2026-11-01T{i:02d}:00:00Z",
                      reprise=f"note {i}" if i == 0 else None)
        _deposer(objet, mtime=1_700_000_000 + (1000 if i == 0 else 10 * i))
    # La note la plus récente par `dernier_tour` est sur l'état le plus ancien par `mtime`.
    _deposer(_etat(sessions[0], dernier_tour="2026-11-14T00:00:00Z", reprise="cachée"),
             mtime=1_600_000_000)
    monkeypatch.setattr("builtins.open", compter)
    assert note.derniere_note(ctx) is None
    assert len(ouverts) == note.MAX_ETATS_LUS == 20
    assert f"{sessions[0]}.json" not in ouverts
    assert sorted(ouverts) == sorted(f"{s}.json" for s in sessions[5:])


# --- Erreurs imprévues --------------------------------------------------------------------


def test_erreur_imprevue_journalisee_sans_contenu(ctx, monkeypatch):
    _deposer(_etat(S1, reprise="note secrète du projet", dernier_tour="2026-11-14T10:00:00Z"))

    def lever(_dossier):  # frontière : système de fichiers
        raise RuntimeError("note secrète du projet")

    vrai_scandir = os.scandir
    monkeypatch.setattr(os, "scandir", lever)
    assert note.derniere_note(ctx) is None
    monkeypatch.setattr(os, "scandir", vrai_scandir)  # pas `undo` : il retirerait l'isolement
    lignes = _journal()
    assert lignes == ["SessionStart RuntimeError"]
    assert all("secrète" not in ligne for ligne in lignes)
    for fichier in (chemins.attente() / "journal").iterdir():
        assert "secrète" not in fichier.read_text(encoding="utf-8")


def test_dossier_illisible_ignore_sans_journal(ctx, monkeypatch):
    _deposer(_etat(S1, reprise="x", dernier_tour="2026-11-14T10:00:00Z"))

    def refuser(_dossier):  # frontière : système de fichiers
        raise PermissionError(13, "refusé")

    monkeypatch.setattr(os, "scandir", refuser)
    assert note.derniere_note(ctx) is None
    assert _journal() == []

