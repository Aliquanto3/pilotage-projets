"""Périmètre de sécurité du serveur local (story 4.1, AD-14, AD-15, `securite.md`)."""

import http.client
import json
import socket
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from pilotage import chemins
from pilotage.serveur import appli, routes
from pilotage.serveur.appli import CSP, ServeurPilotage
from pilotage.serveur.routes import Reponse, Route

METHODES = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")


def _echo(parametres, corps):
    return Reponse(200, donnees={"parametres": parametres, "corps": corps.decode("utf-8")})


def _plante(parametres, corps):
    raise RuntimeError("secret interne")


# Une route livrée par méthode, plus une route à paramètre et une qui lève.
TABLE_TEST = tuple(
    Route(methode, f"/api/r-{methode.lower()}", _echo) for methode in METHODES
) + (
    Route("GET", "/api/elem/<id>", _echo),
    Route("GET", "/api/plante", _plante),
    Route("POST", "/api/pas-livree"),
)


@pytest.fixture
def racine_web(tmp_path):
    web = tmp_path / "web"
    (web / "polices").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (web / "appli.js").write_text("export const x = 1;", encoding="utf-8")
    (web / "polices" / "p.woff2").write_bytes(b"wOF2")
    (tmp_path / "secret.txt").write_text("SECRET-HORS-RACINE", encoding="utf-8")
    return web


def _demarrer(racine_web, table=TABLE_TEST):
    serveur = ServeurPilotage(0, racine_web, table)
    fil = threading.Thread(target=serveur.serve_forever, args=(0.02,), daemon=True)
    fil.start()
    return serveur


@pytest.fixture
def serveur(racine_web):
    serveur = _demarrer(racine_web)
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def requete(serveur, methode, cible, entetes=None, corps=None, jeton=None, hote=None):
    """Requête brute ; `hote` remplace l'en-tête `Host` (liste : plusieurs en-têtes)."""
    connexion = http.client.HTTPConnection("127.0.0.1", serveur.port, timeout=5)
    connexion.putrequest(methode, cible, skip_host=True, skip_accept_encoding=True)
    hotes = hote if isinstance(hote, list) else [hote or f"127.0.0.1:{serveur.port}"]
    for valeur in hotes:
        connexion.putheader("Host", valeur)
    if jeton is not None:
        connexion.putheader("Authorization", f"Bearer {jeton}")
    for nom, valeur in (entetes or {}).items():
        connexion.putheader(nom, valeur)
    if corps is not None:
        connexion.putheader("Content-Length", str(len(corps)))
    connexion.endheaders(corps)
    reponse = connexion.getresponse()
    contenu = reponse.read()
    connexion.close()
    return reponse, contenu


def _json(contenu):
    return json.loads(contenu.decode("utf-8"))


def _verifier_entetes_api(reponse):
    assert reponse.getheader("Content-Type") == "application/json"
    assert reponse.getheader("X-Content-Type-Options") == "nosniff"
    assert reponse.getheader("Cache-Control") == "no-store"


# --- Écoute ----------------------------------------------------------------------------------


def test_ecoute_sur_127_0_0_1_sans_reutilisation(serveur):
    assert serveur.server_address[0] == "127.0.0.1"
    assert ServeurPilotage.allow_reuse_address is False
    assert serveur.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0


@pytest.mark.skipif(sys.platform != "win32", reason="SO_EXCLUSIVEADDRUSE : Windows seulement")
def test_port_exclusif_sous_windows(serveur, racine_web):
    assert serveur.socket.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE) == 1
    with pytest.raises(OSError):
        ServeurPilotage(serveur.port, racine_web)
    intrus = socket.socket()
    intrus.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        with pytest.raises(OSError):
            intrus.bind(("127.0.0.1", serveur.port))
    finally:
        intrus.close()


def _adresse_non_locale():
    """Adresse IPv4 de l'interface sortante, sans DNS ni paquet émis (UDP non connecté)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sonde:
            sonde.connect(("192.0.2.1", 9))  # TEST-NET-1 : aucun trafic, choix de route seul
            adresse = sonde.getsockname()[0]
    except OSError:
        return None
    return None if adresse.startswith("127.") or adresse == "0.0.0.0" else adresse


def test_injoignable_par_une_autre_adresse(serveur):
    adresse = _adresse_non_locale()
    if adresse is None:
        pytest.skip("aucune adresse non locale")
    with pytest.raises(OSError):
        socket.create_connection((adresse, serveur.port), timeout=3).close()


def test_jeton_aleatoire_par_lancement(racine_web):
    premier = ServeurPilotage(0, racine_web)
    second = ServeurPilotage(0, racine_web)
    try:
        assert premier.jeton != second.jeton
        assert len(premier.jeton) >= 43  # 32 octets en base64url : 256 bits
        assert premier.url() == f"http://127.0.0.1:{premier.port}/#{premier.jeton}"
    finally:
        premier.server_close()
        second.server_close()


# --- Matrice M10 ------------------------------------------------------------------------------


@pytest.mark.parametrize("methode", METHODES)
@pytest.mark.parametrize("avec_jeton", [True, False])
@pytest.mark.parametrize("cas", ["permise", "non_permise", "inconnue"])
def test_matrice_api(serveur, methode, avec_jeton, cas):
    autre = "POST" if methode == "GET" else "GET"
    cible = {
        "permise": f"/api/r-{methode.lower()}",
        "non_permise": f"/api/r-{autre.lower()}",
        "inconnue": "/api/inconnue",
    }[cas]
    reponse, contenu = requete(
        serveur, methode, cible, jeton=serveur.jeton if avec_jeton else None
    )
    _verifier_entetes_api(reponse)
    attendu = 401 if not avec_jeton else {"permise": 200, "non_permise": 405, "inconnue": 404}[cas]
    assert reponse.status == attendu
    if attendu == 405:
        assert reponse.getheader("Allow") == autre
    else:
        assert reponse.getheader("Allow") is None
    if attendu == 401:
        assert reponse.getheader("WWW-Authenticate") == "Bearer"
    if methode == "HEAD":
        assert contenu == b""
    else:
        corps = _json(contenu)
        assert corps["ok"] is (attendu == 200)
        if attendu == 200:
            assert corps == {"ok": True, "donnees": {"parametres": {}, "corps": ""}}
        else:
            assert set(corps) == {"ok", "erreur"}


@pytest.mark.parametrize("methode", METHODES)
@pytest.mark.parametrize("avec_jeton", [True, False])
@pytest.mark.parametrize("cas", ["fichier", "inconnu"])
def test_matrice_statiques(serveur, methode, avec_jeton, cas):
    cible = "/appli.js" if cas == "fichier" else "/absent.js"
    reponse, contenu = requete(
        serveur, methode, cible, jeton=serveur.jeton if avec_jeton else None
    )
    assert reponse.getheader("Content-Security-Policy") == CSP
    assert reponse.getheader("X-Content-Type-Options") == "nosniff"
    if cas == "inconnu":
        assert reponse.status == 404
    elif methode in ("GET", "HEAD"):
        assert reponse.status == 200
        assert reponse.getheader("Content-Type") == "text/javascript; charset=utf-8"
        assert contenu == (b"" if methode == "HEAD" else b"export const x = 1;")
    else:
        assert reponse.status == 405
        assert reponse.getheader("Allow") == "GET, HEAD"


@pytest.mark.parametrize("methode", ["PROPFIND", "TRACE", "CONNECT", "FOO"])
def test_methode_quelconque_jamais_501(serveur, methode):
    reponse, _ = requete(serveur, methode, "/api/r-get", jeton=serveur.jeton)
    assert reponse.status == 405
    assert reponse.getheader("Allow") == "GET"
    reponse, _ = requete(serveur, methode, "/api/r-get")
    assert reponse.status == 401
    reponse, _ = requete(serveur, methode, "/appli.js")
    assert reponse.status == 405


def test_route_a_parametre(serveur):
    reponse, contenu = requete(serveur, "GET", "/api/elem/a%20b", jeton=serveur.jeton)
    assert reponse.status == 200
    assert _json(contenu)["donnees"]["parametres"] == {"id": "a b"}
    reponse, _ = requete(serveur, "GET", "/api/elem/", jeton=serveur.jeton)
    assert reponse.status == 404


def test_route_pas_livree_rend_404(serveur):
    for methode in ("POST", "GET"):
        reponse, _ = requete(serveur, methode, "/api/pas-livree", jeton=serveur.jeton)
        assert reponse.status == 404
        assert reponse.getheader("Allow") is None


def test_prefixe_api_insensible_a_la_casse(serveur):
    reponse, _ = requete(serveur, "GET", "/API/r-get")
    assert reponse.status == 401
    reponse, _ = requete(serveur, "GET", "/%61pi/r-get")
    assert reponse.status == 401


# --- Host, Origin, jeton -------------------------------------------------------------------


@pytest.mark.parametrize(
    "hote", ["evil.example", "evil.example:{port}", "127.0.0.1", "127.0.0.1:1", "[::1]:{port}",
             "127.0.0.1:{port}.evil.example", ""],
)
@pytest.mark.parametrize("cible", ["/api/r-get", "/appli.js", "/api/inconnue"])
def test_host_etranger_403(serveur, hote, cible):
    reponse, _ = requete(
        serveur, "GET", cible, jeton=serveur.jeton, hote=hote.format(port=serveur.port) or " "
    )
    assert reponse.status == 403


def test_host_double_403(serveur):
    p = serveur.port
    reponse, _ = requete(serveur, "GET", "/appli.js", hote=[f"127.0.0.1:{p}", "evil.example"])
    assert reponse.status == 403


@pytest.mark.parametrize("hote", ["127.0.0.1:{port}", "localhost:{port}", "LOCALHOST:{port}"])
def test_host_permis(serveur, hote):
    reponse, _ = requete(serveur, "GET", "/api/r-get", jeton=serveur.jeton,
                         hote=hote.format(port=serveur.port))
    assert reponse.status == 200


def test_host_controle_avant_jeton(serveur):
    reponse, contenu = requete(serveur, "GET", "/api/r-get", hote="evil.example")
    assert reponse.status == 403
    _verifier_entetes_api(reponse)
    assert _json(contenu) == {"ok": False, "erreur": "hôte refusé"}


@pytest.mark.parametrize(
    "origine", ["http://evil.example", "null", "https://127.0.0.1:{port}",
                "http://127.0.0.1:{port}/", "http://127.0.0.1:1"],
)
@pytest.mark.parametrize("cible", ["/api/r-get", "/appli.js"])
def test_origin_etranger_403(serveur, origine, cible):
    reponse, _ = requete(serveur, "GET", cible, jeton=serveur.jeton,
                         entetes={"Origin": origine.format(port=serveur.port)})
    assert reponse.status == 403


@pytest.mark.parametrize("origine", ["http://127.0.0.1:{port}", "http://localhost:{port}"])
def test_origin_de_l_appli_permis(serveur, origine):
    reponse, _ = requete(serveur, "POST", "/api/r-post", jeton=serveur.jeton,
                         entetes={"Origin": origine.format(port=serveur.port)})
    assert reponse.status == 200


def test_origin_controle_avant_jeton(serveur):
    reponse, _ = requete(serveur, "POST", "/api/r-post",
                         entetes={"Origin": "http://evil.example"})
    assert reponse.status == 403


def test_jeton_controle_avant_routage(serveur):
    reponse, _ = requete(serveur, "GET", "/api/inconnue")
    assert reponse.status == 401


@pytest.mark.parametrize(
    "valeur", ["", "Bearer", "Bearer ", "bearer {jeton}", "Basic {jeton}", "Bearer {jeton} ",
               "Bearer {jeton}x", "Bearer \xe9"],
)
def test_jeton_mal_forme_401(serveur, valeur):
    connexion = http.client.HTTPConnection("127.0.0.1", serveur.port, timeout=5)
    connexion.putrequest("GET", "/api/r-get")
    connexion.putheader("Authorization", valeur.format(jeton=serveur.jeton))
    connexion.endheaders()
    reponse = connexion.getresponse()
    reponse.read()
    connexion.close()
    assert reponse.status == 401


def test_jeton_double_401(serveur):
    connexion = http.client.HTTPConnection("127.0.0.1", serveur.port, timeout=5)
    connexion.putrequest("GET", "/api/r-get")
    connexion.putheader("Authorization", f"Bearer {serveur.jeton}")
    connexion.putheader("Authorization", f"Bearer {serveur.jeton}")
    connexion.endheaders()
    reponse = connexion.getresponse()
    reponse.read()
    connexion.close()
    assert reponse.status == 401


def test_jeton_d_un_lancement_precedent_401(racine_web):
    premier = _demarrer(racine_web)
    ancien = premier.jeton
    premier.shutdown()
    premier.server_close()
    second = _demarrer(racine_web)
    try:
        reponse, contenu = requete(second, "GET", "/api/r-get", jeton=ancien)
        assert reponse.status == 401
        assert _json(contenu) == {"ok": False, "erreur": "jeton absent ou invalide"}
        reponse, _ = requete(second, "GET", "/api/r-get", jeton=second.jeton)
        assert reponse.status == 200
    finally:
        second.shutdown()
        second.server_close()


def test_jeton_en_query_refuse(serveur):
    reponse, _ = requete(serveur, "GET", f"/api/r-get?jeton={serveur.jeton}")
    assert reponse.status == 401


# --- Réponses /api/ ---------------------------------------------------------------------------


def test_corps_post_transmis(serveur):
    reponse, contenu = requete(serveur, "POST", "/api/r-post", jeton=serveur.jeton,
                               corps='{"a": "é"}'.encode())
    assert reponse.status == 200
    assert _json(contenu)["donnees"]["corps"] == '{"a": "é"}'


def test_corps_trop_grand_413(serveur):
    connexion = http.client.HTTPConnection("127.0.0.1", serveur.port, timeout=5)
    connexion.putrequest("POST", "/api/r-post")
    connexion.putheader("Authorization", f"Bearer {serveur.jeton}")
    connexion.putheader("Content-Length", str(appli.TAILLE_MAX_CORPS + 1))
    connexion.endheaders()
    reponse = connexion.getresponse()
    contenu = reponse.read()
    connexion.close()
    assert reponse.status == 413
    _verifier_entetes_api(reponse)
    assert _json(contenu) == {"ok": False, "erreur": "corps trop grand"}


@pytest.mark.parametrize(
    "entete",
    [("Content-Length", "abc"), ("Content-Length", chr(0xB2)), ("Content-Length", "-1"),
     ("Content-Length", "1e3"), ("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "")],
)
def test_corps_mal_annonce_400(serveur, entete):
    reponse, contenu = requete(serveur, "POST", "/api/r-post", jeton=serveur.jeton,
                               entetes=dict([entete]))
    assert reponse.status == 400
    assert _json(contenu)["ok"] is False


def _brut(serveur, donnees, delai=5):
    with socket.create_connection(("127.0.0.1", serveur.port), timeout=delai) as brut:
        brut.sendall(donnees)
        brut.shutdown(socket.SHUT_WR)
        recu = b""
        while morceau := brut.recv(4096):
            recu += morceau
    return recu


FIN = chr(13) + chr(10)  # CRLF


def _post_brut(serveur, longueur, corps=b""):
    lignes = ["POST /api/r-post HTTP/1.1", f"Host: 127.0.0.1:{serveur.port}",
              f"Authorization: Bearer {serveur.jeton}", f"Content-Length: {longueur}", "", ""]
    return FIN.join(lignes).encode("latin-1") + corps


def test_longueur_demesuree_413_sans_lecture(serveur):
    recu = _brut(serveur, _post_brut(serveur, "9" * 5000))
    assert recu.startswith(b"HTTP/1.0 413")


def test_longueur_a_zeros_de_tete_acceptee(serveur):
    recu = _brut(serveur, _post_brut(serveur, "0000000000002", b"ok"))
    assert recu.startswith(b"HTTP/1.0 200")
    assert b'"corps": "ok"' in recu


def test_corps_tronque_400(serveur):
    recu = _brut(serveur, _post_brut(serveur, 10, b"abc"))
    assert recu.startswith(b"HTTP/1.0 400")
    assert b"corps incomplet" in recu


def test_connexion_muette_coupee_apres_delai(racine_web, monkeypatch):
    monkeypatch.setattr(appli.Requete, "timeout", 0.3)
    serveur = _demarrer(racine_web)
    try:
        with socket.create_connection(("127.0.0.1", serveur.port), timeout=5) as brut:
            assert brut.recv(4096) == b""  # fermée par le serveur, sans requête reçue
        with socket.create_connection(("127.0.0.1", serveur.port), timeout=5) as brut:
            brut.sendall(_post_brut(serveur, 10, b"abc"))  # corps annoncé jamais complété
            assert brut.recv(4096).startswith(b"HTTP/1.0 408")
    finally:
        serveur.shutdown()
        serveur.server_close()


def test_erreur_du_gestionnaire_500_sans_detail(serveur):
    reponse, contenu = requete(serveur, "GET", "/api/plante", jeton=serveur.jeton)
    assert reponse.status == 500
    _verifier_entetes_api(reponse)
    assert _json(contenu) == {"ok": False, "erreur": "erreur interne"}
    journal = next((chemins.attente() / "journal").glob("serveur-*.log")).read_text("utf-8")
    assert "RuntimeError" in journal
    assert "secret interne" not in journal


def test_requete_mal_formee_sans_html(serveur):
    with socket.create_connection(("127.0.0.1", serveur.port), timeout=5) as brut:
        entetes = b"".join(b"X-%d: v\r\n" % i for i in range(150))
        brut.sendall(b"GET / HTTP/1.1\r\n" + entetes + b"\r\n")
        recu = brut.recv(4096)
    assert recu.startswith(b"HTTP/1.0 431")
    assert CSP.encode() in recu
    assert b"<html" not in recu.lower()


# --- Table des routes -----------------------------------------------------------------------


def test_table_fermee_d_ad14():
    assert {(r.methode, r.motif) for r in routes.TABLE} == {
        ("GET", "/api/etat"), ("GET", "/api/brief/<id>"), ("GET", "/api/sessions/<projet>"),
        ("GET", "/api/operations"), ("POST", "/api/scan"), ("POST", "/api/sync"),
        ("POST", "/api/reprise"), ("POST", "/api/message"), ("POST", "/api/projets"),
    }
    assert len(routes.TABLE) == len({(r.methode, r.motif) for r in routes.TABLE})


VALEURS = {"<id>": "20261106T101500Z-0a1b2c3d", "<projet>": "demo"}


def _cible(route):
    return "/" + "/".join(VALEURS.get(s, "x") if s.startswith("<") else s for s in route.segments)


@pytest.mark.parametrize("route", routes.TABLE, ids=lambda r: f"{r.methode} {r.motif}")
def test_route_api_jeton_et_hote_puis_404_si_non_livree(racine_web, route):
    serveur = _demarrer(racine_web, routes.TABLE)
    try:
        assert route.motif.startswith("/api/")
        assert requete(serveur, route.methode, _cible(route))[0].status == 401
        assert requete(serveur, route.methode, _cible(route), hote="evil.example")[0].status == 403
        if route.gestionnaire is None:
            reponse, _ = requete(serveur, route.methode, _cible(route), jeton=serveur.jeton)
            assert reponse.status == 404
    finally:
        serveur.shutdown()
        serveur.server_close()


@pytest.mark.parametrize("route", routes.TABLE, ids=lambda r: f"{r.methode} {r.motif}")
def test_chaque_route_passe_par_verifier_requete(racine_web, route):
    """Toute route de la table, livrée ou à venir, n'atteint son gestionnaire qu'après M10."""
    appels = []

    def espion(parametres, corps):
        appels.append(parametres)
        return Reponse(200, donnees="ok")

    table = tuple(replace(r, gestionnaire=espion) for r in routes.TABLE)
    serveur = _demarrer(racine_web, table)
    try:
        cible = _cible(route)
        refus = [
            requete(serveur, route.methode, cible, hote="evil.example", jeton=serveur.jeton),
            requete(serveur, route.methode, cible, jeton=serveur.jeton,
                    entetes={"Origin": "http://evil.example"}),
            requete(serveur, route.methode, cible),
            requete(serveur, route.methode, cible, jeton="perime"),
        ]
        assert [r.status for r, _ in refus] == [403, 403, 401, 401]
        assert appels == []
        autre = "POST" if route.methode == "GET" else "GET"
        reponse, _ = requete(serveur, autre, cible, jeton=serveur.jeton)
        assert reponse.status == 405
        assert reponse.getheader("Allow") == route.methode
        assert appels == []
        reponse, _ = requete(serveur, route.methode, cible, jeton=serveur.jeton)
        assert reponse.status == 200
        assert len(appels) == 1
    finally:
        serveur.shutdown()
        serveur.server_close()


# --- Statiques ------------------------------------------------------------------------------


def test_racine_sert_index_avec_csp(serveur):
    reponse, contenu = requete(serveur, "GET", "/")
    assert reponse.status == 200
    assert reponse.getheader("Content-Security-Policy") == CSP
    assert reponse.getheader("Content-Type") == "text/html; charset=utf-8"
    assert serveur.jeton.encode() not in contenu


def test_racine_404_sans_index(racine_web):
    (racine_web / "index.html").unlink()
    serveur = _demarrer(racine_web)
    try:
        reponse, _ = requete(serveur, "GET", "/")
        assert reponse.status == 404
        assert reponse.getheader("Content-Security-Policy") == CSP
    finally:
        serveur.shutdown()
        serveur.server_close()


@pytest.mark.parametrize(
    "cible",
    ["/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/..%5csecret.txt",
     "/polices/../../secret.txt", "/polices/%2e%2e/%2e%2e/secret.txt", "/C:/Windows/win.ini",
     "/%00index.html", "/polices", "/polices/", "//secret.txt", "http://evil/secret.txt"],
)
def test_traversee_et_listage_refuses(serveur, cible):
    reponse, contenu = requete(serveur, "GET", cible)
    assert reponse.status in (400, 404)
    assert b"SECRET-HORS-RACINE" not in contenu
    assert b"p.woff2" not in contenu


def test_sous_dossier_servi(serveur):
    reponse, contenu = requete(serveur, "GET", "/polices/p.woff2")
    assert reponse.status == 200
    assert reponse.getheader("Content-Type") == "font/woff2"
    assert contenu == b"wOF2"


def test_vrais_statiques_sans_jeton_ni_donnee(racine_locale_isolee):
    """Chaque fichier de `pilotage/web/` est servi sans jeton, sans le jeton ni donnée de projet."""
    marqueur = "projet-marqueur-4-1"
    etat = chemins.attente() / "etat" / marqueur
    etat.mkdir(parents=True)
    (etat / "session.json").write_text(json.dumps({"projet": marqueur}), encoding="utf-8")
    racine = chemins.racine_web()
    fichiers = [f for f in racine.rglob("*") if f.is_file()]
    assert fichiers
    serveur = _demarrer(racine)
    try:
        for fichier in fichiers:
            cible = "/" + fichier.relative_to(racine).as_posix()
            reponse, contenu = requete(serveur, "GET", cible)
            assert reponse.status == 200, cible
            assert reponse.getheader("Content-Security-Policy") == CSP
            assert contenu == fichier.read_bytes()
            assert serveur.jeton.encode() not in contenu
            assert marqueur.encode() not in contenu
    finally:
        serveur.shutdown()
        serveur.server_close()


# --- Journal --------------------------------------------------------------------------------


def test_journal_sans_jeton_ni_authorization(serveur):
    requete(serveur, "GET", "/api/r-get", jeton=serveur.jeton)
    requete(serveur, "GET", "/api/r-get", jeton="perime")
    requete(serveur, "GET", f"/api/inconnue?x={serveur.jeton}", jeton=serveur.jeton)
    with socket.create_connection(("127.0.0.1", serveur.port), timeout=5) as brut:
        hote = f"Host: 127.0.0.1:{serveur.port}".encode()
        brut.sendall(b"GET /appli.js\x01 HTTP/1.1\r\n" + hote + b"\r\n\r\n")
        brut.recv(4096)
    fichiers = list((chemins.attente() / "journal").glob("serveur-*.log"))
    assert len(fichiers) == 1
    assert Path(fichiers[0]).name.startswith("serveur-") and len(fichiers[0].stem) == 15
    journal = fichiers[0].read_text(encoding="utf-8")
    assert '"GET /api/r-get HTTP/1.1" 200' in journal
    assert '"GET /api/r-get HTTP/1.1" 401' in journal
    assert serveur.jeton not in journal
    assert "Authorization" not in journal
    assert "Bearer" not in journal
    assert "\x01" not in journal
