"""Scan et synchro lancés par le serveur, état `cycle` (story 4.3, AD-5 §3, AD-14, M2)."""

import json
import subprocess
import sys
import threading
import time

import pytest

from pilotage import chemins
from pilotage.scan import verrou as impl
from pilotage.serveur import cli, enfants, routes
from tests.test_serveur import _demarrer, _json, requete
from tests.test_serveur_lancement import _lancer, _port_libre


class FauxProcessus:
    """Enfant simulé : `wait` attend `finir(code)`."""

    pid = 0

    def __init__(self):
        self._fini = threading.Event()
        self.code = 0

    def wait(self, timeout=None):
        self._fini.wait(10)
        return self.code

    def poll(self):
        return self.code if self._fini.is_set() else None

    def kill(self):
        self.finir(-9)

    def finir(self, code):
        self.code = code
        self._fini.set()


@pytest.fixture(autouse=True)
def isole(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPUTERNAME", "PC-Test")
    nom = rf"Local\pilotage-test-enfants-{abs(hash(str(tmp_path)))}"
    monkeypatch.setenv(impl.VARIABLE_NOM, nom)
    enfants.reinitialiser()
    yield
    enfants.reinitialiser()


@pytest.fixture
def lances(monkeypatch):
    """Faux `Popen` : enregistre (commande, options) et rend un `FauxProcessus`."""
    appels = []

    def faux(commande, **options):
        processus = FauxProcessus()
        appels.append((commande, options, processus))
        return processus

    monkeypatch.setattr(enfants, "popen", faux)
    yield appels
    for _, _, processus in appels:
        processus.finir(0)
    attendre(lambda: enfants._etat[0] is None, delai=2)  # le fil a noté la fin avant `isole`


@pytest.fixture
def serveur(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    serveur = _demarrer(web, routes.TABLE)
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def poster(serveur, type_):
    reponse, contenu = requete(serveur, "POST", f"/api/{type_}", jeton=serveur.jeton)
    return reponse.status, _json(contenu)


def attendre(condition, delai=5):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.mark.parametrize("type_", ["scan", "sync"])
def test_post_lance_un_enfant_en_tableau_sans_attendre(serveur, lances, type_):
    statut, objet = poster(serveur, type_)
    assert statut == 202
    assert objet["donnees"] == {"type": type_, "etat": "lance"}
    ((commande, options, _),) = lances
    lancer = str(chemins.racine_installation() / "lancer.py")
    assert commande == [sys.executable, "-I", lancer, type_]
    assert options["shell"] is False
    assert options["stdin"] == options["stdout"] == subprocess.DEVNULL
    assert options["cwd"] == str(chemins.racine_installation())
    journal = options["stderr"]  # sortie d'erreur gardée pour comprendre un `echec`
    assert journal.closed  # le serveur ne garde pas le descripteur
    assert journal.name == str(chemins.journal_enfants(enfants._maintenant()[:7]))
    assert f"{type_} lancé" in open(journal.name, encoding="utf-8").read()
    if sys.platform == "win32":
        assert options["creationflags"] == 0x08000000 | 0x00000200
    assert enfants.lire_cycle() == {
        "en_cours": True, "type": type_, "origine": "appli", "dernier": None,
    }


def test_sans_jeton_rien_n_est_lance(serveur, lances):
    reponse, _ = requete(serveur, "POST", "/api/sync")
    assert reponse.status == 401
    assert lances == []


def test_deuxieme_action_pendant_un_enfant_rien_de_lance(serveur, lances):
    assert poster(serveur, "scan")[0] == 202
    statut, objet = poster(serveur, "sync")
    assert statut == 409
    assert objet["erreur"] == "déjà en cours"
    assert objet["donnees"] == {"type": "sync", "etat": "deja_en_cours"}
    assert len(lances) == 1


def test_deux_post_simultanes_un_seul_enfant(monkeypatch):
    appels = []
    depart = threading.Barrier(2)

    def lent(commande, **options):
        time.sleep(0.2)  # laisse l'autre fil arriver avant la fin du Popen
        appels.append(commande)
        return FauxProcessus()

    monkeypatch.setattr(enfants, "popen", lent)
    issues = []

    def tirer():
        depart.wait()
        issues.append(enfants.lancer("sync"))

    fils = [threading.Thread(target=tirer) for _ in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(5)
    assert sorted(issues) == ["deja_en_cours", "lance"]
    assert len(appels) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="mutex : Windows seulement")
def test_cycle_externe_tient_le_mutex_rien_n_est_lance(serveur, lances):
    with impl.Verrou():
        statut, objet = poster(serveur, "sync")
        assert (statut, objet["erreur"]) == (409, "déjà en cours")
        assert enfants.lire_cycle() == {
            "en_cours": True, "type": None, "origine": "externe", "dernier": None,
        }
    assert lances == []
    assert enfants.lire_cycle()["en_cours"] is False


@pytest.mark.parametrize(
    ("code", "resultat"), [(0, "fait"), (3, "deja_en_cours"), (1, "echec"), (2, "echec"),
                           (-1, "echec")],
)
def test_resultat_selon_le_code_de_sortie(lances, code, resultat):
    assert enfants.lancer("scan") == "lance"
    lances[0][2].finir(code)
    assert attendre(lambda: not enfants.lire_cycle()["en_cours"])
    cycle = enfants.lire_cycle()
    assert cycle["dernier"]["type"] == "scan"
    assert cycle["dernier"]["resultat"] == resultat
    assert cycle["dernier"]["fin"].endswith("Z") and len(cycle["dernier"]["fin"]) == 20
    assert (cycle["en_cours"], cycle["type"], cycle["origine"]) == (False, None, None)
    assert enfants.lancer("sync") == "lance"  # l'enfant fini libère la place


def test_etat_porte_le_cycle(serveur, lances):
    chemins.racine_github().mkdir(parents=True, exist_ok=True)
    assert _json(requete(serveur, "GET", "/api/etat", jeton=serveur.jeton)[1])["donnees"][
        "cycle"] == enfants.CYCLE_NEUTRE
    poster(serveur, "sync")
    cycle = _json(requete(serveur, "GET", "/api/etat", jeton=serveur.jeton)[1])["donnees"]["cycle"]
    assert (cycle["en_cours"], cycle["type"], cycle["origine"]) == (True, "sync", "appli")
    lances[0][2].finir(0)
    assert attendre(lambda: enfants.lire_cycle()["dernier"] is not None)
    cycle = _json(requete(serveur, "GET", "/api/etat", jeton=serveur.jeton)[1])["donnees"]["cycle"]
    assert cycle["en_cours"] is False and cycle["dernier"]["resultat"] == "fait"


def test_popen_impossible_500_et_rien_note(serveur, monkeypatch):
    def echoue(commande, **options):
        raise FileNotFoundError("python")

    monkeypatch.setattr(enfants, "popen", echoue)
    statut, objet = poster(serveur, "scan")
    assert (statut, objet["erreur"]) == (500, "lancement impossible")
    assert enfants.lire_cycle()["en_cours"] is False


def test_type_inconnu_refuse(lances):
    with pytest.raises(ValueError):
        enfants.lancer("reprise")
    assert lances == []


def test_appli_lance_une_synchro_au_demarrage(tmp_path, lances):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    constats = {}

    def pret(serveur):
        constats["lances"] = [c[-1] for c, _, _ in lances]
        threading.Timer(0, serveur.shutdown).start()

    assert _lancer(web, [], pret) == 0  # réessai : course connue entre `_port_libre` et bind
    assert constats["lances"] == ["sync"]


def test_appli_demarre_si_la_synchro_ne_peut_pas_partir(tmp_path, monkeypatch, capsys):
    def echoue(commande, **options):
        raise FileNotFoundError(2, "introuvable")

    monkeypatch.setattr(enfants, "popen", echoue)
    web = tmp_path / "web"
    web.mkdir()
    servi = []

    def pret(serveur):
        servi.append(serveur.port)
        threading.Timer(0, serveur.shutdown).start()

    assert _lancer(web, [], pret) == 0
    assert servi
    assert "synchro non lancée (introuvable)" in capsys.readouterr().err
    assert enfants.lire_cycle()["en_cours"] is False


def test_appli_sans_sync_ne_lance_rien(tmp_path, lances):
    web = tmp_path / "web"
    web.mkdir()

    def pret(serveur):
        threading.Timer(0, serveur.shutdown).start()

    argv = ["--port", str(_port_libre()), "--sans-sync"]
    assert cli.main(argv, navigateur=lambda url: None, pret=pret, racine_web=web) == 0
    assert lances == []


def test_fil_refuse_libere_la_place_et_tue_l_enfant(lances, monkeypatch):
    class FilRefuse:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    vrai = threading.Thread
    monkeypatch.setattr(enfants.threading, "Thread", FilRefuse)
    with pytest.raises(RuntimeError):
        enfants.lancer("sync")
    monkeypatch.setattr(enfants.threading, "Thread", vrai)  # jamais undo() : isolement
    assert lances[0][2].poll() is not None  # enfant tué
    assert enfants.lire_cycle()["en_cours"] is False


def test_erreur_autre_qu_oserror_500_sans_trace(serveur, monkeypatch):
    def echoue(commande, **options):  # erreur imprévue : ni type ni message dans la réponse
        raise RuntimeError("JSON interne")

    monkeypatch.setattr(enfants, "popen", echoue)
    statut, objet = poster(serveur, "sync")
    assert (statut, objet["erreur"]) == (500, "lancement impossible")
    assert "JSON" not in str(objet)
    assert enfants.lire_cycle()["en_cours"] is False


def test_lecture_du_cycle_n_attend_pas_un_popen_lent(monkeypatch):
    entre, sortie = threading.Event(), threading.Event()

    def lent(commande, **options):
        entre.set()
        sortie.wait(5)
        return FauxProcessus()

    monkeypatch.setattr(enfants, "popen", lent)
    fil = threading.Thread(target=enfants.lancer, args=("sync",))
    fil.start()
    try:
        assert entre.wait(5)
        debut = time.monotonic()
        cycle = enfants.lire_cycle()
        assert time.monotonic() - debut < 0.5
        assert (cycle["en_cours"], cycle["type"], cycle["origine"]) == (True, "sync", "appli")
    finally:
        sortie.set()
        fil.join(5)
    assert enfants.lancer("scan") == "deja_en_cours"  # M2 : l'enfant lancé garde la place


def test_enfant_qui_ne_finit_jamais_est_tue_apres_le_delai(monkeypatch):
    """Vrai processus (un `sleep`, jamais `lancer.py`) : `taskkill /T` ou terminate l'arrête."""
    lances = []

    def dormeur(commande, **options):
        options.pop("cwd")
        processus = subprocess.Popen(
            [sys.executable, "-I", "-c", "import time; time.sleep(120)"], **options)
        lances.append(processus)
        return processus

    monkeypatch.setattr(enfants, "popen", dormeur)
    monkeypatch.setattr(enfants, "DELAI_ENFANT", 0.5)
    assert enfants.lancer("sync") == "lance"
    assert attendre(lambda: not enfants.lire_cycle()["en_cours"], delai=30)
    dernier = enfants.lire_cycle()["dernier"]
    assert (dernier["resultat"], dernier["cause"]) == ("echec", "delai")
    assert lances[0].poll() is not None


def _config(monkeypatch, **cles):
    monkeypatch.delenv("PILOTAGE_RACINE_LOCALE")
    chemin = chemins.chemin_config()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(cles), encoding="utf-8")


@pytest.mark.parametrize("cle", ["python", "racine_installation"])
def test_python_et_racine_relatifs_de_config_refuses(monkeypatch, lances, cle):
    _config(monkeypatch, **{cle: "relatif"})
    with pytest.raises(chemins.ErreurConfiguration, match=f"'{cle}' doit être un chemin absolu"):
        enfants.lancer("scan")
    assert lances == []
    assert enfants.lire_cycle()["en_cours"] is False


def test_python_absolu_de_config_utilise(tmp_path, monkeypatch, lances):
    python = str(tmp_path / "py" / "python.exe")
    _config(monkeypatch, python=python)
    assert enfants.lancer("sync") == "lance"
    assert lances[0][0][0] == python


def test_journal_trop_gros_repart_a_zero(lances, monkeypatch):
    monkeypatch.setattr(enfants, "TAILLE_MAX_JOURNAL", 10)
    chemin = chemins.journal_enfants(enfants._maintenant()[:7])
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("x" * 100, encoding="utf-8")
    assert enfants.lancer("sync") == "lance"
    assert "x" not in chemin.read_text(encoding="utf-8")


def test_route_config_relative_500_avec_cause(serveur, monkeypatch, lances):
    _config(monkeypatch, python="relatif")
    statut, objet = poster(serveur, "scan")
    assert statut == 500 and objet["erreur"].startswith("lancement impossible : ")
    assert "'python' doit être un chemin absolu" in objet["erreur"]
    assert lances == []
