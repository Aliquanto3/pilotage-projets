"""Catalogue des alertes de `sync` (M8, story 3.6) et validateur `alertes`."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pilotage.noyau import alertes, schemas

PARIS_HIVER = timezone(timedelta(hours=1))


def _fichier(*liste):
    return {"schema": 1, "alertes": list(liste)}


@pytest.mark.parametrize(
    ("code", "params", "attendu"),
    [
        ("depot-public", {}, "Envoi refusé : le dépôt de données n'est pas privé."),
        (
            "depot-non-configure",
            {},
            "Synchro arrêtée : dépôt de données non configuré. Renseignez depot_donnees "
            "(propriétaire/nom) dans config.json ou relancez l'installation.",
        ),
        ("sync-echec", {"etape": "push"}, "Synchro en échec à l'étape push"),
        ("fichiers-ignores", {}, "Fichiers locaux illisibles ou invalides : non copiés"),
        (
            "sync-conflit",
            {"instant": "2026-11-06T08:05:00Z", "motif": "rebase"},
            "Synchro abandonnée à 09:05 : conflit de rebase. Nouvel essai au prochain cycle.",
        ),
        (
            "sync-conflit",
            {"instant": "2026-11-06T23:30:59Z", "motif": "autostash"},
            "Synchro abandonnée à 00:30 : modifications locales en conflit, gardées dans le stash."
            " Nouvel essai au prochain cycle.",
        ),
        (
            "sync-push-refuse",
            {"instant": "2026-11-06T08:05:00Z", "motif": "non-fast-forward"},
            "Synchro abandonnée à 09:05 : push refusé (non-fast-forward)."
            " Nouvel essai au prochain cycle.",
        ),
    ],
)
def test_un_texte_par_code(code, params, attendu):
    alerte = {"source": "sync", "code": code, "params": params}
    schemas.valider("alertes", _fichier(alerte))
    assert alertes.texte(alerte, PARIS_HIVER) == attendu


def test_heure_dans_le_fuseau_recu():
    alerte = {"source": "sync", "code": "sync-conflit",
              "params": {"instant": "2026-11-06T08:05:00Z", "motif": "rebase"}}
    assert alertes.texte(alerte, UTC).startswith("Synchro abandonnée à 08:05 ")


def test_instant_utc_a_la_seconde():
    moment = datetime(2026, 11, 6, 9, 5, 7, 999, tzinfo=PARIS_HIVER)
    assert alertes.instant(moment) == "2026-11-06T08:05:07Z"


def test_forme_message_toleree_en_lecture():
    ancienne = {"source": "scan", "code": "scan-echec", "message": "Scan en échec"}
    schemas.valider("alertes", _fichier(ancienne))
    assert alertes.texte(ancienne, UTC) == "Scan en échec"


@pytest.mark.parametrize(
    "alerte",
    [
        {"source": "sync", "code": "sync-echec", "params": {}},
        {"source": "sync", "code": "sync-echec", "params": {"etape": "Push !"}},
        {"source": "sync", "code": "sync-echec", "params": {"etape": 3}},
        {"source": "sync", "code": "sync-echec", "params": {"etape": "push", "en_plus": "x"}},
        {"source": "sync", "code": "depot-public", "params": []},
        {"source": "sync", "code": "sync-conflit",
         "params": {"instant": "2026-11-06 08:05", "motif": "rebase"}},
        {"source": "sync", "code": "sync-conflit",
         "params": {"instant": "2026-11-06T08:05:00Z", "motif": "non-fast-forward"}},
        {"source": "sync", "code": "depot-public", "params": {}, "message": "x"},
    ],
)
def test_params_hors_catalogue_refuses(alerte):
    with pytest.raises(schemas.ErreurValidation):
        schemas.valider("alertes", _fichier(alerte))


def test_verifier_refuse_des_params_inexacts():
    with pytest.raises(alertes.AlerteInconnue, match="invalide"):
        alertes.verifier("sync-echec", {"etape": "Push !"})
    alertes.verifier("code-d-une-version-plus-recente", {"n": 1})  # code sans règle : toléré


@pytest.mark.parametrize(
    ("alerte", "attendu"),
    [
        ({"source": "sync", "code": "inconnu", "params": {}}, "inconnu"),
        ({"source": "sync", "code": "sync-echec", "params": {"etape": "Push !"}},
         "sync-echec"),
        ({"source": "sync", "code": "sync-conflit",
          "params": {"instant": "2026-11-06T08:05:00Z", "motif": "non-fast-forward"}},
         "sync-conflit"),
    ],
)
def test_texte_ne_leve_jamais(alerte, attendu):
    """Une alerte que le validateur refuserait reste lisible (serveur, tableau) : repli sur le
    code, jamais d'exception à l'affichage."""
    assert alertes.texte(alerte, UTC) == attendu


def test_texte_sans_fuseau_rend_l_heure_locale():
    alerte = {"code": "sync-conflit",
              "params": {"instant": "2026-11-06T08:05:00Z", "motif": "rebase"}}
    local = datetime(2026, 11, 6, 8, 5, tzinfo=UTC).astimezone()
    assert alertes.texte(alerte) == (
        f"Synchro abandonnée à {local:%H:%M} : conflit de rebase. Nouvel essai au prochain cycle."
    )


@pytest.mark.parametrize("instant", ["0001-01-01T00:00:00Z", "9999-12-31T23:59:59Z"])
@pytest.mark.parametrize("fuseau", [None, timezone(timedelta(hours=14)), "Europe/Paris"])
def test_texte_ne_leve_jamais_instant_extreme_ou_fuseau_invalide(instant, fuseau):
    """Instant admis par le validateur mais hors de la plage du fuseau, ou fuseau qui n'est pas
    un `tzinfo` : repli sur le message puis le code, sans exception (serveur, tableau)."""
    alerte = {"code": "sync-conflit", "params": {"instant": instant, "motif": "rebase"},
              "message": "ancien texte"}
    texte = alertes.texte(alerte, fuseau)  # ne lève pas
    assert texte == "ancien texte" or texte.startswith("Synchro abandonnée à ")
