"""Le vrai `pilotage/web/` servi par le serveur local, avec la CSP d'AD-15 (story 4.4)."""

import http.client
import threading

import pytest

from pilotage import chemins
from pilotage.serveur.appli import CSP, ServeurPilotage

WEB = chemins.racine_web()


@pytest.fixture(scope="module")
def serveur():
    serveur = ServeurPilotage(0, WEB)
    fil = threading.Thread(target=serveur.serve_forever, args=(0.02,), daemon=True)
    fil.start()
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def _get(serveur, cible):
    connexion = http.client.HTTPConnection("127.0.0.1", serveur.port, timeout=5)
    connexion.request("GET", cible, headers={"Host": f"127.0.0.1:{serveur.port}"})
    reponse = connexion.getresponse()
    corps = reponse.read()
    connexion.close()
    return reponse, corps


def test_csp_stricte_sans_inline_ni_eval():
    assert CSP == (
        "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'"
    )
    assert "unsafe" not in CSP and "style-src" not in CSP  # style-src hérite de default-src


def test_racine_sert_index_avec_csp(serveur):
    reponse, corps = _get(serveur, "/")
    assert reponse.status == 200
    assert reponse.getheader("Content-Type") == "text/html; charset=utf-8"
    assert reponse.getheader("Content-Security-Policy") == CSP
    assert reponse.getheader("X-Content-Type-Options") == "nosniff"
    assert corps == (WEB / "index.html").read_bytes()


@pytest.mark.parametrize(
    "fichier", sorted(p.name for p in WEB.glob("*.js")) + ["appli.css", "charte.css",
                                                           "charte-base.css", "polices.css",
                                                           "favicon.svg"],
)
def test_modules_et_feuilles_servis_avec_le_bon_type(serveur, fichier):
    attendu = {
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
    }[(WEB / fichier).suffix]
    reponse, corps = _get(serveur, f"/{fichier}")
    assert reponse.status == 200
    assert reponse.getheader("Content-Type") == attendu
    assert reponse.getheader("Content-Security-Policy") == CSP
    assert corps == (WEB / fichier).read_bytes()


def test_polices_woff2_servies(serveur):
    polices = sorted((WEB / "polices").glob("*.woff2"))
    assert polices
    reponse, _ = _get(serveur, f"/polices/{polices[0].name}")
    assert reponse.status == 200
    assert reponse.getheader("Content-Type") == "font/woff2"


def test_page_sans_jeton_ne_donne_aucune_donnee(serveur):
    reponse, corps = _get(serveur, "/api/etat")
    assert reponse.status == 401
    assert serveur.jeton.encode() not in corps
