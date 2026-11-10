import pytest

from pilotage.noyau import schemas
from pilotage.noyau.schemas import ErreurValidation, SchemaInconnu


def test_registre_en_1_3():
    assert sorted(schemas.REGISTRE) == [
        "acquittement", "alertes", "instantane", "message", "operation", "projets", "session",
        "table_dossiers",
    ]


def test_nom_inconnu_erreur_claire():
    motif = (r"^schéma inconnu : 'etat' \(connus : acquittement, alertes, instantane, message, "
             r"operation, projets, session, table_dossiers\)$")
    with pytest.raises(SchemaInconnu, match=motif):
        schemas.valider("etat", {})


def test_valider_delegue_et_propage(monkeypatch):
    vus: list[object] = []

    def refuser(objet: object) -> None:
        vus.append(objet)
        raise ErreurValidation("champ inconnu : x")

    monkeypatch.setitem(schemas.REGISTRE, "essai", refuser)
    with pytest.raises(ErreurValidation, match="champ inconnu : x"):
        schemas.valider("essai", {"x": 1})
    assert vus == [{"x": 1}]
    motif = (r"\(connus : acquittement, alertes, essai, instantane, message, operation, "
             r"projets, session, table_dossiers\)")
    with pytest.raises(SchemaInconnu, match=motif):
        schemas.valider("autre", {})
