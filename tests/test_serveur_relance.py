"""Relance de `sync` après une mutation, cycle occupé (story 5.2, M2) : minuteur et `Popen`
simulés, aucune attente réelle."""

import pytest

from pilotage import chemins
from pilotage.scan import verrou as impl
from pilotage.serveur import enfants, relance
from tests.test_serveur_enfants import FauxProcessus, attendre


class FauxMinuteur:
    def __init__(self, delai, fonction):
        self.delai, self.fonction = delai, fonction
        self.demarre = self.annule = False

    def start(self):
        self.demarre = True

    def cancel(self):
        self.annule = True

    def declencher(self):
        self.fonction()


@pytest.fixture(autouse=True)
def isole(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPUTERNAME", "PC-Test")
    monkeypatch.setenv(impl.VARIABLE_NOM, rf"Local\pilotage-test-rel-{abs(hash(str(tmp_path)))}")
    enfants.reinitialiser()
    relance.reinitialiser()
    yield
    relance.reinitialiser()
    enfants.reinitialiser()


@pytest.fixture
def minuteurs(monkeypatch):
    crees = []

    def faux(delai, fonction):
        minuteur = FauxMinuteur(delai, fonction)
        crees.append(minuteur)
        return minuteur

    monkeypatch.setattr(relance, "minuteur", faux)
    return crees


@pytest.fixture
def lances(monkeypatch):
    appels = []

    def faux(commande, **options):
        processus = FauxProcessus()
        appels.append((commande, processus))
        return processus

    monkeypatch.setattr(enfants, "popen", faux)
    yield appels
    for _, processus in appels:
        processus.finir(0)
    attendre(lambda: enfants._etat[0] is None, delai=2)


def finir(lances, code):
    lances[-1][1].finir(code)
    assert attendre(lambda: enfants._etat[0] is None)


def test_cycle_libre_lance_sync_sans_relance(lances, minuteurs):
    assert relance.demander() == "lance"
    ((commande, _),) = lances
    assert commande[-1] == "sync"
    finir(lances, 0)
    assert minuteurs == []
    assert relance.etat() == {"en_file": False, "tentatives": 0, "arrete": False, "abandons": 0}


def test_enfant_occupe_relance_cinq_fois_de_2_a_30_s_puis_abandon(lances, minuteurs):
    operation = chemins.operations() / "20261106T101500Z-0a1b2c3d.json"
    operation.parent.mkdir(parents=True)
    operation.write_text("{}", "utf-8")
    assert relance.demander() == "lance"
    for numero in range(5):
        finir(lances, enfants.CODE_OCCUPE)
        assert attendre(lambda n=numero: len(minuteurs) == n + 1)
        assert minuteurs[-1].demarre and relance.etat()["en_file"]
        minuteurs[-1].declencher()
        assert len(lances) == numero + 2
    assert [m.delai for m in minuteurs] == [2, 4, 8, 16, 30]
    finir(lances, enfants.CODE_OCCUPE)
    assert attendre(lambda: relance.etat()["abandons"] == 1)
    assert len(minuteurs) == 5 and len(lances) == 6
    assert relance.etat()["en_file"] is False
    assert operation.exists()  # laissée au cycle planifié
    journal = chemins.journal_enfants(enfants._maintenant()[:7]).read_text("utf-8")
    assert "relance de sync abandonnée" in journal


def test_mutex_externe_une_seule_relance_en_file(lances, minuteurs):
    with impl.Verrou():
        assert relance.demander() == "en_file"
        assert relance.demander() == "en_file"
        assert [m.delai for m in minuteurs] == [2]
        assert lances == []
        minuteurs[0].declencher()  # toujours occupé : reprogrammée, plus longue
        assert [m.delai for m in minuteurs] == [2, 4]
        assert lances == []
    minuteurs[1].declencher()
    assert len(lances) == 1
    finir(lances, 0)
    assert attendre(lambda: relance.etat()["tentatives"] == 0)  # enfant fini : remis à zéro
    assert len(minuteurs) == 2


def test_enfant_de_l_appli_en_cours_relance_apres(lances, minuteurs):
    assert enfants.lancer("sync") == "lance"  # bouton Sync
    assert relance.demander() == "en_file"
    assert len(lances) == 1
    finir(lances, 0)
    minuteurs[0].declencher()
    assert len(lances) == 2


def test_echec_de_l_enfant_ne_relance_pas(lances, minuteurs):
    with impl.Verrou():
        relance.demander()  # tentative 1 en file
    minuteurs[0].declencher()
    finir(lances, 1)
    assert attendre(lambda: relance.etat()["tentatives"] == 0)
    assert len(minuteurs) == 1


def test_arreter_annule_la_relance_et_refuse_les_suivantes(lances, minuteurs):
    with impl.Verrou():
        assert relance.demander() == "en_file"
        relance.arreter()
        assert minuteurs[0].annule
        assert relance.demander() == "abandon"
    minuteurs[0].declencher()  # un minuteur déjà parti ne relance rien
    assert lances == [] and len(minuteurs) == 1


def test_popen_impossible_abandon_sans_relance(monkeypatch, minuteurs):
    def refuse(commande, **options):
        raise OSError("refusé")

    monkeypatch.setattr(enfants, "popen", refuse)
    assert relance.demander() == "abandon"
    assert minuteurs == []


def test_minuteur_reel_en_fil_demon():
    appels = []
    minuteur = relance._minuteur_reel(30, lambda: appels.append(1))
    assert minuteur.daemon is True and minuteur.interval == 30
    minuteur.cancel()
    assert appels == []


def test_post_pendant_la_serie_ne_remet_pas_le_compteur_a_zero(lances, minuteurs, monkeypatch):
    fins = []
    fin = relance._fin
    monkeypatch.setattr(relance, "_fin", lambda dernier: (fin(dernier), fins.append(1)))
    assert relance.demander() == "lance"
    for numero in range(5):
        assert relance.demander() == "en_file"  # POST pendant l'enfant : cycle occupé
        assert len(minuteurs) == numero + 1
        finir(lances, enfants.CODE_OCCUPE)
        assert attendre(lambda n=numero: len(fins) == n + 1)
        minuteurs[-1].declencher()
        assert len(lances) == numero + 2
    assert [m.delai for m in minuteurs] == [2, 4, 8, 16, 30]
    assert relance.demander() == "abandon"  # borne de 5 tenue malgré les POST
    assert relance.etat()["abandons"] == 1 and relance.etat()["tentatives"] == 0


def test_popen_impossible_journalise(monkeypatch, minuteurs):
    monkeypatch.setattr(enfants, "popen", lambda c, **o: (_ for _ in ()).throw(OSError("refusé")))
    assert relance.demander() == "abandon"
    journal = chemins.journal_enfants(enfants._maintenant()[:7]).read_text("utf-8")
    assert "sync non lancée (OSError)" in journal


def test_rappel_de_fin_en_echec_journalise(lances):
    def rappel(dernier):
        raise RuntimeError("rappel cassé")

    assert enfants.lancer("sync", a_la_fin=rappel) == "lance"
    lances[-1][1].finir(0)
    chemin = chemins.journal_enfants(enfants._maintenant()[:7])
    assert attendre(lambda: chemin.exists()
                    and "rappel de fin de sync en échec" in chemin.read_text("utf-8"))
