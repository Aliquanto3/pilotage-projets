"""Mutex `Local\\pilotage-projets-sync` : prise sans attente, sonde, deux processus réels."""

import subprocess
import sys
import textwrap

import pytest

from pilotage.scan import verrou as impl
from pilotage.sync import verrou as facade
from tests.test_imports import RACINE_DEPOT

windows = pytest.mark.skipif(sys.platform != "win32", reason="mutex nommé Windows")


@pytest.fixture(autouse=True)
def nom_propre(monkeypatch, tmp_path):
    monkeypatch.setenv(impl.VARIABLE_NOM, f"Local\\pilotage-test-{abs(hash(str(tmp_path)))}")


def test_nom_par_defaut_et_surcharge(monkeypatch):
    monkeypatch.delenv(impl.VARIABLE_NOM)
    assert impl.nom() == "Local\\pilotage-projets-sync"
    monkeypatch.setenv(impl.VARIABLE_NOM, "Local\\autre")
    assert impl.nom() == "Local\\autre"


def test_facade_expose_la_meme_implementation():
    assert facade.Verrou is impl.Verrou
    assert facade.occupe is impl.occupe


@windows
def test_prise_liberation_et_sonde_sans_prise():
    assert facade.occupe() is False
    with facade.Verrou() as v:
        assert v.acquis and not v.abandonne
        assert facade.occupe() is True
        assert facade.occupe() is True  # la sonde n'a rien pris ni rendu
    assert facade.occupe() is False
    with facade.Verrou() as v2:  # la sonde n'a rien retenu : une nouvelle prise réussit
        assert v2.acquis


ENFANT = textwrap.dedent(
    """
    import time
    from pilotage.sync.verrou import Verrou
    v = Verrou().__enter__()
    print("acquis" if v.acquis else "non", flush=True)
    time.sleep(60)
    """
)


@windows
def test_autre_processus_tient_puis_proprietaire_tue_est_abandonne():
    enfant = subprocess.Popen(
        [sys.executable, "-c", ENFANT], cwd=RACINE_DEPOT, stdout=subprocess.PIPE, text=True
    )
    try:
        assert enfant.stdout.readline().strip() == "acquis"
        assert facade.occupe() is True
        with facade.Verrou() as v:
            assert v.acquis is False
        # Une poignée ouverte garde l'objet en vie quand le propriétaire meurt (sans elle,
        # Windows détruit le mutex et il n'y a rien d'abandonné).
        k = impl._noyau()
        poignee = k.CreateMutexW(None, False, impl.nom())
        enfant.kill()
        enfant.wait()
        try:
            with facade.Verrou() as v:
                assert v.acquis is True
                assert v.abandonne is True  # WAIT_ABANDONED compté comme acquis
        finally:
            k.CloseHandle(poignee)
    finally:
        enfant.kill()
        enfant.wait()
