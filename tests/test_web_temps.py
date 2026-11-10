"""Logique pure de `pilotage/web/temps.js` (story 4.4, UX-DR5, UX-DR20), exécutée par node.

Sauté si `node` n'est pas installé (échec si `PILOTAGE_EXIGER_NODE=1`, posé en CI) : la règle
n'est écrite qu'en JS, jamais dupliquée ici.
"""

import json
import os
import shutil
import subprocess

import pytest

from pilotage import chemins

NODE = shutil.which("node")
# En CI, `PILOTAGE_EXIGER_NODE=1` : node absent fait échouer au lieu de sauter.
if NODE is None and os.environ.get("PILOTAGE_EXIGER_NODE") == "1":
    raise RuntimeError("node absent alors que PILOTAGE_EXIGER_NODE=1")
pytestmark = pytest.mark.skipif(NODE is None, reason="node absent")

MAINTENANT = "2026-11-06T10:00:00Z"


def _evaluer(expression: str):
    """Évalue `expression` (modules de temps.js importés sous `t`) en fuseau UTC."""
    url = (chemins.racine_web() / "temps.js").as_uri()
    script = (
        f"const t = await import({json.dumps(url)});"
        f"const maintenant = new Date({json.dumps(MAINTENANT)});"
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    sortie = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
        env={**os.environ, "TZ": "UTC"},
    )
    return json.loads(sortie.stdout)


def _etiquette(genere_a):
    ligne = json.dumps({"pc": "pc-bureau", "genere_a": genere_a})
    return _evaluer(f"t.etiquetteFraicheur({ligne}, maintenant)")


def test_fuseau_utc_force():
    assert _evaluer("new Date(0).getHours()") == 0


@pytest.mark.parametrize(
    ("genere_a", "texte", "vieux"),
    [
        ("2026-11-06T09:48:00Z", "pc-bureau · il y a 12 min", False),
        ("2026-11-06T09:59:30Z", "pc-bureau · à l'instant", False),
        ("2026-11-06T09:59:00Z", "pc-bureau · il y a 1 min", False),
        ("2026-11-06T09:15:00Z", "pc-bureau · il y a 45 min", False),
        ("2026-11-06T09:14:59Z", "pc-bureau · sans nouvelles depuis 09:14", True),
        ("2026-11-06T08:12:00Z", "pc-bureau · sans nouvelles depuis 08:12", True),
        ("2026-11-05T23:10:00Z", "pc-bureau · sans nouvelles depuis hier 23:10", True),
        ("2026-11-04T23:10:00Z", "pc-bureau · sans nouvelles depuis 04/11", True),
        ("2026-11-06T10:05:00Z", "pc-bureau · à l'instant", False),
        (None, "pc-bureau · aucun instantané", True),
        ("pas une date", "pc-bureau · aucun instantané", True),
    ],
)
def test_etiquette_fraicheur(genere_a, texte, vieux):
    assert _etiquette(genere_a) == {"texte": texte, "vieux": vieux}


@pytest.mark.parametrize(
    ("instant", "attendu"),
    [
        ("2026-11-06T00:00:00Z", "00:00"),
        ("2026-11-06T09:05:00Z", "09:05"),
        ("2026-11-05T00:00:00Z", "hier 00:00"),
        ("2026-11-04T23:59:00Z", "04/11"),
        ("2026-01-02T12:00:00Z", "02/01"),
    ],
)
def test_heure_courte(instant, attendu):
    assert _evaluer(f"t.heureCourte(new Date({json.dumps(instant)}), maintenant)") == attendu


def test_heure_courte_changement_de_mois():
    expression = 't.heureCourte(new Date("2026-10-31T22:00:00Z"), new Date("2026-11-01T08:00:00Z"))'
    assert _evaluer(expression) == "hier 22:00"


def test_seuil_aligne_sur_le_noyau():
    from pilotage.noyau import assemblage

    seuil = _evaluer("t.SEUIL_SANS_NOUVELLES_MIN")
    assert seuil * 60 == assemblage.FRAICHEUR_MAX.total_seconds()


@pytest.mark.parametrize(
    "module", sorted(p.name for p in chemins.racine_web().glob("*.js")), ids=str
)
def test_module_es_syntaxe_valide(module):
    """Chaque module se compile comme module ES (`node --check`), sans être exécuté."""
    chemin = chemins.racine_web() / module
    sortie = subprocess.run(
        [NODE, "--input-type=module", "--check"],
        input=chemin.read_text(encoding="utf-8"),
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert sortie.returncode == 0, sortie.stderr


# --- Story 4.11 : formes de la durée d'une attente vieillissante (maintenant : 06/11 10:00 UTC) --

@pytest.mark.parametrize(("debut", "sans_nouvelles", "attendu"), [
    ("2026-11-06T02:00:00Z", False, "depuis plus de 8 h"),  # 8 h pile
    ("2026-11-05T23:37:00Z", False, "depuis plus de 10 h"),  # 10 h 23, arrondi inférieur
    ("2026-11-05T10:00:00Z", False, "depuis plus de 24 h"),  # 24 h pile
    ("2026-11-05T09:59:00Z", False, "depuis hier 09:59"),  # au-delà de 24 h : la veille
    ("2026-11-03T22:47:00Z", False, "depuis le 03/11"),  # avant la veille
    ("2026-11-05T22:47:00Z", True, "depuis hier 22:47"),  # PC sans nouvelles : heure seule
    ("2026-11-06T01:00:00Z", True, "depuis 01:00"),
    ("2026-11-06T05:00:00Z", False, "depuis 05:00"),  # sous 8 h (horloges décalées)
])
def test_depuis_vieillissante(debut, sans_nouvelles, attendu):
    js = "true" if sans_nouvelles else "false"
    assert _evaluer(
        f"t.depuisVieillissante(new Date({json.dumps(debut)}), maintenant, {js})") == attendu


@pytest.mark.parametrize(("debut", "attendu"), [
    ("2026-11-06T09:05:00Z", "depuis 09:05"),
    ("2026-11-05T09:05:00Z", "depuis hier 09:05"),
    ("2026-11-01T09:05:00Z", "depuis le 01/11"),
])
def test_depuis_court(debut, attendu):
    assert _evaluer(f"t.depuisCourt(new Date({json.dumps(debut)}), maintenant)") == attendu
