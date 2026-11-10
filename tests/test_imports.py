"""Test AST du graphe des imports entre couches (ARCHITECTURE-SPINE, Design Paradigm)."""

import ast
import sys
from pathlib import Path

import pytest

RACINE_DEPOT = Path(__file__).resolve().parent.parent

# Couches de `pilotage/` qu'une couche peut importer (la sienne comprise).
PILOTAGE_AUTORISE: dict[str, set[str]] = {
    "racine": set(),
    "noyau": {"noyau"},
    "chemins": {"noyau", "chemins"},
    "hooks": {"noyau", "chemins", "hooks"},
    "scan": {"noyau", "chemins", "scan"},
    "sync": {"noyau", "chemins", "scan", "sync"},
    "serveur": {"noyau", "chemins", "sync", "serveur"},
    "installation": {"noyau", "chemins", "installation"},
    "lancer": {"noyau", "chemins", "scan", "sync", "serveur", "installation"},
}
# Paquets tiers permis (PyYAML : outils seulement).
TIERS_AUTORISES: dict[str, set[str]] = {"scan": {"yaml"}, "sync": {"yaml"}, "serveur": {"yaml"}}
# Noyau : liste blanche de la bibliothèque standard (calcul pur, sans E/S, processus ni réseau).
# Une story qui a besoin d'un autre module pur l'ajoute ici, avec son motif.
STDLIB_NOYAU: set[str] = {
    "__future__", "abc", "base64", "bisect", "collections", "copy", "dataclasses", "datetime",
    "decimal", "difflib", "enum", "fractions", "functools", "hashlib", "heapq", "hmac",
    "html", "itertools", "json", "math", "numbers", "operator", "re", "secrets", "statistics",
    "string", "textwrap", "types", "typing", "unicodedata", "uuid",
}
# Autres couches : liste noire (processus et réseau interdits à `chemins`).
STDLIB_INTERDITE: dict[str, set[str]] = {
    "chemins": {"subprocess", "socket", "http", "urllib", "asyncio", "multiprocessing"},
}
COUCHES_PAQUETS = {"noyau", "hooks", "scan", "sync", "serveur", "installation"}


def _couche_du_fichier(relatif: Path) -> str | None:
    parties = relatif.parts
    if parties == ("lancer.py",):
        return "lancer"
    if parties == ("pilotage", "__init__.py"):
        return "racine"
    if parties == ("pilotage", "chemins.py"):
        return "chemins"
    if len(parties) >= 3 and parties[1] in COUCHES_PAQUETS:
        return parties[1]
    return None


def _nom_module(relatif: Path) -> str:
    parties = list(relatif.with_suffix("").parts)
    if parties[-1] == "__init__":
        parties.pop()
    return ".".join(parties)


def _couche_importee(nom: str) -> str:
    parties = nom.split(".")
    if len(parties) == 1:
        return "racine"
    return parties[1] if parties[1] in COUCHES_PAQUETS | {"chemins"} else "racine"


def _imports(arbre: ast.AST, module: str, est_paquet: bool) -> list[tuple[int, str]]:
    trouves: list[tuple[int, str]] = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            trouves += [(noeud.lineno, alias.name) for alias in noeud.names]
        elif isinstance(noeud, ast.ImportFrom):
            if noeud.level:
                paquet = module.split(".") if est_paquet else module.split(".")[:-1]
                paquet = paquet[: len(paquet) - (noeud.level - 1)]
                base = ".".join(paquet + ([noeud.module] if noeud.module else []))
            else:
                base = noeud.module or ""
            if base.split(".")[0] == "pilotage":
                trouves += [
                    (noeud.lineno, base if a.name == "*" else f"{base}.{a.name}")
                    for a in noeud.names
                ]
            else:
                trouves.append((noeud.lineno, base))
    return trouves


def violations(racine: Path) -> list[str]:
    """Liste les imports hors graphe sous `racine` (qui contient `pilotage/` et `lancer.py`)."""
    fichiers = sorted((racine / "pilotage").rglob("*.py"))
    if (racine / "lancer.py").exists():
        fichiers.append(racine / "lancer.py")
    erreurs: list[str] = []
    for fichier in fichiers:
        relatif = fichier.relative_to(racine)
        module = _nom_module(relatif)
        couche = _couche_du_fichier(relatif)
        if couche is None:
            erreurs.append(f"{module} ({relatif.as_posix()}) : fichier Python hors des couches")
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for ligne, nom in _imports(arbre, module, fichier.name == "__init__.py"):
            haut = nom.split(".")[0]
            ou = f"{module} ({relatif.as_posix()}:{ligne}) importe {nom}"
            if haut == "pilotage":
                cible = _couche_importee(nom)
                if cible != "racine" and cible not in PILOTAGE_AUTORISE[couche]:
                    erreurs.append(f"{ou} : couche {couche} -> {cible} hors du graphe")
            elif haut in sys.stdlib_module_names or haut == "__future__":
                if (couche == "noyau" and haut not in STDLIB_NOYAU) or haut in (
                    STDLIB_INTERDITE.get(couche, set())
                ):
                    erreurs.append(f"{ou} : module interdit dans la couche {couche}")
            elif haut not in TIERS_AUTORISES.get(couche, set()):
                erreurs.append(f"{ou} : paquet tiers interdit dans la couche {couche}")
    return erreurs


def test_graphe_des_imports_respecte():
    assert violations(RACINE_DEPOT) == []


def test_web_sans_python():
    assert list((RACINE_DEPOT / "pilotage" / "web").rglob("*.py")) == []


def _imports_au_chargement(arbre: ast.AST) -> list[str]:
    """Imports exécutés au chargement du module (hors corps de fonction), même sous try/if."""
    noms: list[str] = []
    a_voir = [arbre]
    while a_voir:
        noeud = a_voir.pop()
        if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(noeud, ast.Import):
            noms += [a.name for a in noeud.names]
        elif isinstance(noeud, ast.ImportFrom):
            noms.append("." * noeud.level + (noeud.module or ""))
        a_voir.extend(ast.iter_child_nodes(noeud))
    return sorted(noms)


def test_lancer_importe_ses_couches_tardivement():
    arbre = ast.parse((RACINE_DEPOT / "lancer.py").read_text(encoding="utf-8"))
    noms = _imports_au_chargement(arbre)
    assert [n for n in noms if n.startswith(("pilotage", "."))] == []


def test_import_sous_try_au_chargement_detecte():
    source = (
        "try:\n    import pilotage.scan.cli\nexcept ImportError:\n    pass\n"
        "if True:\n    from pilotage.sync import cli\n"
        "def f():\n    import pilotage.serveur\n"
    )
    assert _imports_au_chargement(ast.parse(source)) == ["pilotage.scan.cli", "pilotage.sync"]


def _depot_factice(racine: Path, fichiers: dict[str, str]) -> Path:
    for relatif, contenu in fichiers.items():
        chemin = racine / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    return racine


@pytest.mark.parametrize(
    ("relatif", "source", "attendu"),
    [
        ("pilotage/noyau/ids.py", "import os\n", "pilotage.noyau.ids (pilotage/noyau/ids.py:1) "
         "importe os : module interdit dans la couche noyau"),
        ("pilotage/noyau/ids.py", "\n\nimport subprocess\n",
         "pilotage.noyau.ids (pilotage/noyau/ids.py:3) importe subprocess"),
        ("pilotage/noyau/ids.py", "from pilotage import chemins\n",
         "importe pilotage.chemins : couche noyau -> chemins hors du graphe"),
        ("pilotage/noyau/ids.py", "from .. import chemins\n",
         "importe pilotage.chemins : couche noyau -> chemins hors du graphe"),
        ("pilotage/noyau/ids.py", "import zipfile\n", "importe zipfile : module interdit"),
        ("pilotage/noyau/ids.py", "import builtins\n", "importe builtins : module interdit"),
        ("pilotage/hooks/stop.py", "import yaml\n",
         "pilotage.hooks.stop (pilotage/hooks/stop.py:1) importe yaml : paquet tiers interdit"),
        ("pilotage/hooks/stop.py", "from pilotage.scan import cli\n",
         "couche hooks -> scan hors du graphe"),
        ("pilotage/scan/cli.py", "import pilotage.sync.cycle\n",
         "couche scan -> sync hors du graphe"),
        ("pilotage/serveur/http.py", "from pilotage.scan.cli import main\n",
         "couche serveur -> scan hors du graphe"),
        ("pilotage/installation/fusion.py", "import yaml\n", "paquet tiers interdit"),
        ("lancer.py", "def f():\n    from pilotage.hooks import stop\n",
         "lancer (lancer.py:2) importe pilotage.hooks.stop : couche lancer -> hooks"),
        ("pilotage/web/x.py", "", "pilotage.web.x (pilotage/web/x.py) : fichier Python hors"),
        ("pilotage/divers.py", "", "fichier Python hors des couches"),
    ],
)
def test_violation_detectee(tmp_path, relatif, source, attendu):
    racine = _depot_factice(tmp_path / "depot", {relatif: source})
    erreurs = violations(racine)
    assert len(erreurs) == 1, erreurs
    assert attendu in erreurs[0]


def test_imports_permis_acceptes(tmp_path):
    racine = _depot_factice(
        tmp_path / "depot",
        {
            "pilotage/noyau/ids.py": "import re\nfrom . import schemas\n",
            "pilotage/chemins.py": "import os, json\nfrom pilotage.noyau import ids\n",
            "pilotage/hooks/stop.py": "import subprocess\nfrom pilotage import chemins\n",
            "pilotage/sync/cycle.py": "import yaml\nfrom pilotage.scan import cli\n",
            "pilotage/serveur/http.py": "from ..sync import cycle\nimport pilotage\n",
            "lancer.py": "def f():\n    from pilotage.installation.cli import main\n",
        },
    )
    assert violations(racine) == []
