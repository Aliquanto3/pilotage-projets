"""Garde « pas de fenêtre console » : tout enfant console de `pilotage/` reçoit l'option commune."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from pilotage import chemins
from pilotage.scan import faits_gh
from pilotage.sync import depot

RACINE = Path(__file__).resolve().parent.parent / "pilotage"
APPELS = {"run", "Popen", "check_output", "call", "check_call"}
# (fichier relatif à `pilotage/`, fonction englobante) : lancements volontairement sans l'option.
LISTE_BLANCHE = {
    # Python enfant détaché : DETACHED_PROCESS (aucune console), incompatible avec CREATE_NO_WINDOW.
    ("hooks/_commun.py", "_lancer_detache"),
    # Alias `popen = subprocess.Popen` (frontière remplacée par les tests) : ses drapeaux
    # (CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP) sont vérifiés par `test_serveur_enfants`.
    ("serveur/enfants.py", "<module>"),
}


def _est_option_commune(mot) -> bool:
    valeur = mot.value
    return (
        mot.arg is None
        and isinstance(valeur, ast.Call)
        and isinstance(valeur.func, ast.Attribute)
        and valeur.func.attr == "options_sans_fenetre"
    )


def _fautes_appel(appel: ast.Call) -> str | None:
    commune = any(_est_option_commune(m) for m in appel.keywords)
    if not commune:
        return "sans options_sans_fenetre()"
    if any(m.arg == "creationflags" for m in appel.keywords):
        return "creationflags en double (TypeError sous Windows)"
    return None


def _appels_fautifs(racine: Path) -> list[str]:
    """Toute référence à un lanceur de `subprocess` (appel, alias, import direct ou renommé)."""
    fautes = []
    for fichier in sorted(racine.rglob("*.py")):
        relatif = fichier.relative_to(racine).as_posix()
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        englobante = {}
        for fonction in ast.walk(arbre):
            if isinstance(fonction, ast.FunctionDef | ast.AsyncFunctionDef):
                for noeud in ast.walk(fonction):
                    englobante.setdefault(id(noeud), fonction.name)  # walk : externe d'abord
        modules = {a.asname or a.name for n in ast.walk(arbre) if isinstance(n, ast.Import)
                   for a in n.names if a.name == "subprocess"}
        appeles = {id(n.func) for n in ast.walk(arbre) if isinstance(n, ast.Call)}
        for noeud in ast.walk(arbre):
            if (relatif, englobante.get(id(noeud), "<module>")) in LISTE_BLANCHE:
                continue
            if isinstance(noeud, ast.ImportFrom) and noeud.module == "subprocess":
                fautes += [f"{relatif}:{noeud.lineno} from subprocess import {a.name}"
                           for a in noeud.names if a.name in APPELS | {"*"}]
            elif (isinstance(noeud, ast.Attribute) and noeud.attr in APPELS
                  and isinstance(noeud.value, ast.Name) and noeud.value.id in modules):
                nom = f"{relatif}:{noeud.lineno} subprocess.{noeud.attr}"
                if id(noeud) not in appeles:
                    fautes.append(f"{nom} référencé sans être appelé (alias)")
        for noeud in ast.walk(arbre):
            if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)):
                continue
            f = noeud.func
            if not (f.attr in APPELS and isinstance(f.value, ast.Name) and f.value.id in modules):
                continue
            if (relatif, englobante.get(id(noeud), "<module>")) in LISTE_BLANCHE:
                continue
            faute = _fautes_appel(noeud)
            if faute:
                fautes.append(f"{relatif}:{noeud.lineno} subprocess.{f.attr} {faute}")
    return fautes


def test_aucun_appel_subprocess_sans_option():
    assert _appels_fautifs(RACINE) == []


def test_garde_detecte_un_appel_nu(tmp_path):
    (tmp_path / "x.py").write_text(
        "import subprocess\ndef f():\n    subprocess.run(['git'])\n", encoding="utf-8"
    )
    assert _appels_fautifs(tmp_path) == ["x.py:3 subprocess.run sans options_sans_fenetre()"]


def test_garde_detecte_alias_imports_et_module(tmp_path):
    (tmp_path / "x.py").write_text(
        "import subprocess as sp\nfrom subprocess import run\nimport subprocess\n"
        "p = subprocess.Popen\nsubprocess.run(['x'])\ndef f():\n    sp.run(['git'])\n"
        "    subprocess.run(['git'], creationflags=1, **chemins.options_sans_fenetre())\n",
        encoding="utf-8",
    )
    fautes = _appels_fautifs(tmp_path)
    assert [f.split(" ")[0] for f in fautes] == ["x.py:2", "x.py:4", "x.py:5", "x.py:7", "x.py:8"]
    assert "en double" in fautes[-1]


def test_garde_accepte_l_option(tmp_path):
    (tmp_path / "x.py").write_text(
        "import subprocess\nfrom pilotage import chemins\ndef f():\n"
        "    subprocess.run(['git'], **chemins.options_sans_fenetre())\n",
        encoding="utf-8",
    )
    assert _appels_fautifs(tmp_path) == []


def test_option_windows_et_ailleurs():
    assert chemins.options_sans_fenetre("nt") == {"creationflags": 0x08000000}
    assert chemins.options_sans_fenetre("posix") == {}


class _Resultat:
    returncode = 0
    stdout = ""
    stderr = ""


@pytest.mark.parametrize("appel", ["git", "gh"])
def test_git_et_gh_passent_l_option(monkeypatch, appel):
    recus = []

    def faux_run(*args, **kwargs):
        recus.append(kwargs)
        return _Resultat()

    monkeypatch.setattr(subprocess, "run", faux_run)
    if appel == "git":
        depot.git(["--version"])
    else:
        faits_gh.executeur_gh(["--version"], 5.0)
    assert recus[0].get("creationflags") == chemins.options_sans_fenetre().get("creationflags")
    assert ("creationflags" in recus[0]) == (sys.platform == "win32")


@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW : Windows seulement")
def test_constante_windows_conforme():
    assert chemins.CREATE_NO_WINDOW == subprocess.CREATE_NO_WINDOW


# Script lancé par `pythonw` (sans console) : lance un enfant console qui rapporte s'il a une
# fenêtre de console (`GetConsoleWindow` non nul), avec ou sans l'option commune.
_SCRIPT_PYTHONW = """
import subprocess, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from pilotage import chemins
code = "import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())"
sortie = {}
for nom, options in (("sans", chemins.options_sans_fenetre()), ("avec", {})):
    r = subprocess.run([sys.argv[2], "-c", code], capture_output=True, text=True, **options)
    sortie[nom] = r.stdout.strip()
Path(sys.argv[3]).write_text(sortie["sans"] + "," + sortie["avec"], encoding="utf-8")
"""


@pytest.mark.skipif(sys.platform != "win32", reason="consoles Windows seulement")
def test_pythonw_enfant_sans_console_avec_option(tmp_path):
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pytest.skip("pythonw.exe introuvable")
    script = tmp_path / "essai.py"
    script.write_text(_SCRIPT_PYTHONW, encoding="utf-8")
    resultat = tmp_path / "resultat.txt"
    racine = str(RACINE.parent)
    subprocess.run(
        [str(pythonw), "-I", str(script), racine, sys.executable, str(resultat)],
        check=True, timeout=60, **chemins.options_sans_fenetre(),
    )
    sans, avec = resultat.read_text(encoding="utf-8").split(",")
    assert sans == "0"  # avec l'option : aucune fenêtre de console
    assert avec != "0"  # témoin : sans l'option, pythonw fait ouvrir une console
