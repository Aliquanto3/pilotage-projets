"""`POST /api/rapport` (story 9.4) : génération de la semaine en cours, ouverture par un faux
navigateur, verrou, erreurs fixes, matrice de refus alignée sur `/api/scan`."""

import http.client
import json
import socket
import threading
from datetime import UTC, datetime

import pytest

from pilotage import chemins
from pilotage.serveur import cli, rapport, routes
from pilotage.serveur.appli import ServeurPilotage

MAINTENANT = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)  # samedi : 2026-W46 sous tout fuseau
SEMAINE = "2026-W46"
SUCCES = {"ok": True, "donnees": {"type": "rapport", "etat": "ouvert", "semaine": SEMAINE}}


class FauxNavigateur:
    def __init__(self, rendu=True, leve=False):
        self.uris: list[str] = []
        self.rendu, self.leve = rendu, leve

    def __call__(self, uri):
        self.uris.append(uri)
        if self.leve:
            raise OSError("aucun navigateur")
        return self.rendu


@pytest.fixture(autouse=True)
def module_neuf():
    chemins.racine_github().mkdir(parents=True, exist_ok=True)
    rapport.reinitialiser()
    yield
    rapport.reinitialiser()
    if rapport._verrou.locked():
        rapport._verrou.release()


@pytest.fixture
def navigateur():
    faux = FauxNavigateur()
    rapport.configurer(faux, lambda: MAINTENANT)
    return faux


@pytest.fixture
def serveur(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    serveur = ServeurPilotage(0, web, routes.TABLE)
    threading.Thread(target=serveur.serve_forever, args=(0.02,), daemon=True).start()
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def requete(serveur, methode, cible, *, jeton=True, corps=None, hote=None, entetes=None):
    connexion = http.client.HTTPConnection("127.0.0.1", serveur.port, timeout=10)
    connexion.putrequest(methode, cible, skip_host=True, skip_accept_encoding=True)
    connexion.putheader("Host", hote or f"127.0.0.1:{serveur.port}")
    if jeton is True:
        connexion.putheader("Authorization", f"Bearer {serveur.jeton}")
    elif jeton:
        connexion.putheader("Authorization", f"Bearer {jeton}")
    for nom, valeur in (entetes or {}).items():
        connexion.putheader(nom, valeur)
    if corps is not None:
        connexion.putheader("Content-Length", str(len(corps)))
    connexion.endheaders(corps)
    reponse = connexion.getresponse()
    contenu = reponse.read()
    connexion.close()
    return reponse.status, (json.loads(contenu) if contenu else None)


def page():
    return chemins.rapport_semaine(SEMAINE)


# --- Succès ---------------------------------------------------------------------------------


def test_succes_genere_la_semaine_courante_et_ouvre_son_uri(serveur, navigateur):
    statut, corps = requete(serveur, "POST", "/api/rapport")
    assert (statut, corps) == (200, SUCCES)
    assert page().is_file()
    assert "<title>Semaine 2026-W46</title>" in page().read_text(encoding="utf-8")
    assert navigateur.uris == [page().resolve().as_uri()]
    assert navigateur.uris[0].startswith("file:")
    brut = json.dumps(corps, ensure_ascii=False)
    assert ":\\" not in brut and "/" not in brut and "rapports" not in brut


def test_semaine_en_heure_locale_par_defaut_sans_horloge(serveur):
    faux = FauxNavigateur()
    rapport.configurer(faux)
    avant = datetime.now(UTC)
    statut, corps = requete(serveur, "POST", "/api/rapport")
    attendues = {
        f"{a}-W{n:02d}" for a, n, _ in (avant.astimezone().isocalendar(),
                                        datetime.now(UTC).astimezone().isocalendar())
    }
    assert statut == 200
    assert corps["donnees"]["semaine"] in attendues
    assert faux.uris == [chemins.rapport_semaine(corps["donnees"]["semaine"]).resolve().as_uri()]


def test_page_reecrite_au_second_clic(serveur, navigateur):
    assert requete(serveur, "POST", "/api/rapport") == (200, SUCCES)
    page().write_text("ancienne", encoding="utf-8")
    assert requete(serveur, "POST", "/api/rapport") == (200, SUCCES)
    assert page().read_text(encoding="utf-8").startswith("<!doctype html>")
    assert len(navigateur.uris) == 2


# --- Refus ----------------------------------------------------------------------------------


def _cas_de_refus(serveur, cible, methode="POST"):
    return [
        requete(serveur, methode, cible + "?x=1"),
        requete(serveur, methode, cible, jeton=False),
        requete(serveur, methode, cible, jeton="perime"),
        requete(serveur, methode, cible, hote="evil.example"),
        requete(serveur, methode, cible, entetes={"Origin": "http://evil.example"}),
        requete(serveur, "GET", cible),
    ]


def test_matrice_de_refus_identique_a_scan_rien_genere(serveur, navigateur):
    refus_rapport = _cas_de_refus(serveur, "/api/rapport")
    refus_scan = _cas_de_refus(serveur, "/api/scan")
    assert [s for s, _ in refus_rapport] == [400, 401, 401, 403, 403, 405]
    assert refus_rapport == refus_scan
    assert refus_rapport[0][1] == {"ok": False, "erreur": "paramètre refusé"}
    assert navigateur.uris == []
    assert not chemins.rapports().exists()


@pytest.mark.parametrize("corps", [b"{}", b" ", b'{"semaine": "2020-W01"}'])
def test_corps_non_vide_400_rien_genere(serveur, navigateur, corps):
    statut, reponse = requete(serveur, "POST", "/api/rapport", corps=corps)
    assert (statut, reponse) == (400, {"ok": False, "erreur": "corps refusé"})
    assert navigateur.uris == []
    assert not chemins.rapports().exists()


def test_corps_vide_annonce_accepte(serveur, navigateur):
    assert requete(serveur, "POST", "/api/rapport", corps=b"") == (200, SUCCES)


# --- Verrou ---------------------------------------------------------------------------------


def test_verrou_pris_409_puis_succes_apres_liberation(serveur, navigateur):
    assert rapport._verrou.acquire(blocking=False)
    try:
        statut, corps = requete(serveur, "POST", "/api/rapport")
    finally:
        rapport._verrou.release()
    assert (statut, corps) == (409, {
        "ok": False, "donnees": {"type": "rapport", "etat": "deja_en_cours"},
        "erreur": "déjà en cours",
    })
    assert navigateur.uris == []
    assert not chemins.rapports().exists()
    assert requete(serveur, "POST", "/api/rapport") == (200, SUCCES)


def test_autres_routes_servies_pendant_la_generation(serveur):
    entre, sortie = threading.Event(), threading.Event()

    def bloquant(uri):
        entre.set()
        assert sortie.wait(10)
        return True

    rapport.configurer(bloquant, lambda: MAINTENANT)
    premier = {}
    fil = threading.Thread(target=lambda: premier.update(r=requete(serveur, "POST",
                                                                   "/api/rapport")))
    fil.start()
    try:
        assert entre.wait(10)
        assert requete(serveur, "GET", "/api/etat")[0] == 200
        assert requete(serveur, "POST", "/api/rapport")[0] == 409
    finally:
        sortie.set()
        fil.join(10)
    assert premier["r"] == (200, SUCCES)
    assert not rapport._verrou.locked()


# --- Erreurs --------------------------------------------------------------------------------


def test_erreur_de_generation_500_fixe_puis_verrou_rendu(serveur, navigateur):
    chemins.rapports().parent.mkdir(parents=True, exist_ok=True)
    chemins.rapports().write_text("un fichier à la place du dossier", encoding="utf-8")
    statut, corps = requete(serveur, "POST", "/api/rapport")
    assert (statut, corps) == (500, {"ok": False, "erreur": "rapport impossible"})
    assert navigateur.uris == []
    assert not rapport._verrou.locked()
    chemins.rapports().unlink()
    assert requete(serveur, "POST", "/api/rapport") == (200, SUCCES)


@pytest.mark.parametrize("faux", [FauxNavigateur(rendu=False), FauxNavigateur(leve=True)],
                         ids=["rend-false", "leve"])
def test_navigateur_en_echec_500_page_ecrite(serveur, faux):
    rapport.configurer(faux, lambda: MAINTENANT)
    statut, corps = requete(serveur, "POST", "/api/rapport")
    assert (statut, corps) == (500, {"ok": False, "erreur": "page générée, ouverture impossible"})
    assert page().is_file()
    assert faux.uris == [page().resolve().as_uri()]
    assert not rapport._verrou.locked()


@pytest.mark.parametrize("rendu", [None, "", 0])
def test_navigateur_sans_bool_false_vaut_succes(serveur, rendu):
    rapport.configurer(FauxNavigateur(rendu=rendu), lambda: MAINTENANT)
    assert requete(serveur, "POST", "/api/rapport") == (200, SUCCES)


# --- Câblage par `lancer.py appli` ----------------------------------------------------------


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_cli_configure_le_navigateur_du_rapport(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    ouvertes, constats = [], {}

    def pret(serveur):
        def verifier():
            try:
                constats["rapport"] = requete(serveur, "POST", "/api/rapport")
            finally:
                serveur.shutdown()

        threading.Thread(target=verifier, daemon=True).start()

    for _ in range(3):
        code = cli.main(["--port", str(_port_libre()), "--sans-sync"],
                        navigateur=ouvertes.append, pret=pret, racine_web=web)
        if code != 1:
            break
    assert code == 0
    statut, corps = constats["rapport"]
    assert statut == 200
    semaine = corps["donnees"]["semaine"]
    assert ouvertes[0].startswith("http://127.0.0.1:")
    assert ouvertes[1:] == [chemins.rapport_semaine(semaine).resolve().as_uri()]
