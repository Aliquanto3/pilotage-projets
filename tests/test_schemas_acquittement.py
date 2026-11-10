"""Story 5.3 : schéma `acquittement` (C2)."""

import pytest

from pilotage.noyau import schemas
from pilotage.noyau.schemas import ErreurValidation

VALIDE = {
    "schema": 1, "id": "20261106T101500Z-0000000a", "projet": "capture-payloads",
    "pc": "pc-essai", "session": "0f8e2c1a-1b2c-4d5e-8f90-123456789abc",
    "heure": "2026-11-06T10:15:00Z",
}


def test_valide_par_le_registre():
    schemas.valider("acquittement", dict(VALIDE))


@pytest.mark.parametrize(
    ("modif", "motif"),
    [
        ({"autre": 1}, "champ inconnu : autre"),
        ({"schema": 2}, "schema 1 attendu"),
        ({"schema": True}, "schema 1 attendu"),
        ({"id": "x"}, "acquittement : id"),
        ({"projet": "A B"}, "acquittement : projet"),
        ({"pc": "PC"}, "acquittement : pc"),
        ({"session": "abc"}, "acquittement : session"),
        ({"heure": "2026-11-06 10:15:00"}, "heure AAAA-MM-JJTHH:MM:SSZ attendue"),
        ({"heure": "2026-02-30T10:15:00Z"}, "heure impossible"),
    ],
)
def test_refus(modif, motif):
    with pytest.raises(ErreurValidation, match=motif):
        schemas.valider("acquittement", {**VALIDE, **modif})


@pytest.mark.parametrize("champ", sorted(VALIDE))
def test_champ_manquant(champ):
    objet = {k: v for k, v in VALIDE.items() if k != champ}
    with pytest.raises(ErreurValidation, match=f"champ manquant : {champ}"):
        schemas.valider("acquittement", objet)


def test_objet_attendu():
    with pytest.raises(ErreurValidation, match="un objet est attendu"):
        schemas.valider("acquittement", [])
