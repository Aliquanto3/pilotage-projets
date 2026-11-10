"""Identifiants sûrs : formes d'AD-9, jointure lexicale du noyau, jointure sûre sur disque."""

import os
import subprocess
import sys

import pytest

from pilotage import chemins
from pilotage.noyau import ids
from pilotage.noyau.ids import ErreurId

UUID = "123e4567-e89b-12d3-a456-426614174000"
HORS_FORME = [
    "'; calc; '", "$(calc)", '"x"', "a'b", "a\nb", "a\n", "..", "a/b", "a\\b", "a:b", "a\x00b",
    "", " ", "a b",
]


@pytest.mark.parametrize("valeur", ["a", "pilotage-projets", "x.y_z-1", ".a", "console", "a" * 100])
def test_projet_valide(valeur):
    assert ids.valider_projet(valeur) == valeur


@pytest.mark.parametrize(
    "valeur",
    [*HORS_FORME, ".", "A", "é", "a" * 101, "٣", "..a", "a..", "a..b", "pilotage.", "nul", "con",
     "aux.x", "com1", "lpt9.json"],
)
def test_projet_refuse(valeur):
    with pytest.raises(ErreurId):
        ids.valider_projet(valeur)


@pytest.mark.parametrize("valeur", ["a", "pc-1", "x" * 32, "0"])
def test_pc_valide(valeur):
    assert ids.valider_pc(valeur) == valeur


@pytest.mark.parametrize(
    "valeur", [*HORS_FORME, "a.b", "a_b", "PC", "x" * 33, "nul", "prn", "com3"]
)
def test_pc_refuse(valeur):
    with pytest.raises(ErreurId):
        ids.valider_pc(valeur)


def test_session_valide():
    assert ids.valider_session(UUID) == UUID


@pytest.mark.parametrize(
    "valeur",
    [*HORS_FORME, UUID.upper(), UUID.replace("-", ""), UUID + "0", UUID[:-1], "{" + UUID + "}",
     UUID[:-1] + "g", UUID + "\n"],
)
def test_session_refuse(valeur):
    with pytest.raises(ErreurId):
        ids.valider_session(valeur)


def test_id_valide():
    assert ids.valider_id("20261106T123456Z-0a1b2c3d") == "20261106T123456Z-0a1b2c3d"


@pytest.mark.parametrize(
    "valeur",
    [*HORS_FORME, "20261106T123456Z-0A1B2C3D", "20261106T123456Z-0a1b2c3",
     "20261106T123456Z-0a1b2c3de",
     "20261106T123456-0a1b2c3d", "20261106123456Z-0a1b2c3d", "20261306T123456Z-0a1b2c3d",
     "20261106T256100Z-0a1b2c3d", "20261106T123456Z-0a1b2c3d\n"],
)
def test_id_refuse(valeur):
    with pytest.raises(ErreurId):
        ids.valider_id(valeur)


@pytest.mark.parametrize("valider", [ids.valider_projet, ids.valider_pc, ids.valider_session,
                                     ids.valider_id, ids.valider_segment])
@pytest.mark.parametrize("valeur", [None, 1, b"abc", ["a"]])
def test_type_non_texte_refuse(valider, valeur):
    with pytest.raises(ErreurId, match="chaîne"):
        valider(valeur)


def test_message_d_erreur_borne_la_valeur():
    with pytest.raises(ErreurId) as exc:
        ids.valider_pc("x" * 500)
    assert len(str(exc.value)) < 200


@pytest.mark.parametrize("valider", [ids.valider_projet, ids.valider_pc, ids.valider_session,
                                     ids.valider_id, ids.valider_segment])
def test_message_d_erreur_ne_recopie_pas_la_valeur(valider):
    with pytest.raises(ErreurId) as exc:
        valider("ghp_SECRETjeton/../x")
    assert "SECRET" not in str(exc.value)


@pytest.mark.parametrize(
    "segments", [("a",), ("a", "b.json"), ("etat", "pilotage-projets.json")]
)
def test_joindre_valide(segments):
    assert ids.joindre(*segments) == "/".join(segments)


@pytest.mark.parametrize(
    "segment",
    ["", ".", "..", "../x", "a/b", "/abs", "a\\b", "\\\\hote\\partage", "C:", "C:\\x", "a:b",
     "a\x00", "a..b", "a/../b", "a.", "a ", "nul", "NUL.json", "con.txt", "com1", "lpt1.x",
     "aux .json"],
)
def test_joindre_refuse_segment(segment):
    with pytest.raises(ErreurId):
        ids.joindre("ok", segment)


def test_joindre_sans_segment_refuse():
    with pytest.raises(ErreurId, match="sans segment"):
        ids.joindre()


# --- jointure sûre sur disque (chemins.joindre_sous) ---


def test_joindre_sous_rend_le_chemin_resolu(tmp_path):
    attendu = tmp_path.resolve() / "etat" / "p.json"
    assert chemins.joindre_sous(tmp_path, "etat", "p.json") == attendu


@pytest.mark.parametrize("segment", ["..", "../x", "/etc", "C:\\x", "a\\..\\b"])
def test_joindre_sous_refuse_traversee_lexicale(tmp_path, segment):
    with pytest.raises(ErreurId):
        chemins.joindre_sous(tmp_path, "etat", segment)


def _lien_vers(cible, lien):
    """Crée un lien de dossier ; jonction sous Windows (sans droits admin). False si impossible."""
    try:
        if sys.platform == "win32":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(lien), str(cible)],
                               capture_output=True, check=False)
            return r.returncode == 0
        os.symlink(cible, lien, target_is_directory=True)
        return True
    except OSError:
        return False


def test_joindre_sous_refuse_lien_qui_sort_de_la_racine(tmp_path):
    racine = tmp_path / "racine"
    dehors = tmp_path / "dehors"
    racine.mkdir()
    dehors.mkdir()
    if not _lien_vers(dehors, racine / "lien"):
        pytest.skip("création de lien ou de jonction impossible sur ce poste")
    with pytest.raises(ErreurId, match="hors de sa racine"):
        chemins.joindre_sous(racine, "lien", "x.json")


def test_joindre_sous_accepte_lien_qui_reste_sous_la_racine(tmp_path):
    (tmp_path / "vrai").mkdir()
    if not _lien_vers(tmp_path / "vrai", tmp_path / "lien"):
        pytest.skip("création de lien ou de jonction impossible sur ce poste")
    assert chemins.joindre_sous(tmp_path, "lien", "x") == tmp_path.resolve() / "vrai" / "x"


@pytest.mark.parametrize(
    ("relatif", "cle"),
    [
        ("Mon-Depot", "mon-depot"),
        ("_worktrees\\Pilotage-1-3\\", "_worktrees/pilotage-1-3"),
        ("a/B/", "a/b"),
        ("Straße", "strasse"),
        ("deja/normal", "deja/normal"),
    ],
)
def test_cle_dossier(relatif, cle):
    assert ids.cle_dossier(relatif) == cle
    assert ids.cle_dossier(cle) == cle


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("PC-Moi", "pc-moi"),
        ("PC_X", "pc-x"),
        ("Bureau  Joël", "bureau-jo-l"),
        ("--pc--", "pc"),
        ("a" * 31 + "-b", "a" * 31),  # coupé à 32 puis bord `-` retiré
        ("A" * 40, "a" * 32),
    ],
)
def test_normaliser_pc(brut, attendu):
    assert ids.normaliser_pc(brut) == attendu


@pytest.mark.parametrize("brut", ["", "__", "CON", "é"])
def test_normaliser_pc_refuse(brut):
    with pytest.raises(ids.ErreurId):
        ids.normaliser_pc(brut)
