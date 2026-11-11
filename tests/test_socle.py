"""Arborescence, version, CI et charte posées par la story 1.1."""

import re
import tomllib

from tests.test_imports import RACINE_DEPOT

WEB = RACINE_DEPOT / "pilotage" / "web"


def test_arborescence_structural_seed():
    for relatif in [
        "lancer.py", "pilotage/chemins.py", "pilotage/noyau", "pilotage/noyau/schemas",
        "pilotage/hooks", "pilotage/scan/cli.py", "pilotage/sync/cli.py",
        "pilotage/serveur/cli.py", "pilotage/installation/cli.py", "pilotage/web", "outils",
        "tests",
    ]:
        assert (RACINE_DEPOT / relatif).exists(), relatif


def test_version_et_pyproject():
    assert (RACINE_DEPOT / "VERSION").read_text(encoding="utf-8") == "0.4.0\n"
    projet = tomllib.loads((RACINE_DEPOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert projet["project"]["version"] == "0.4.0"
    assert projet["project"]["requires-python"] == ">=3.14,<3.15"
    assert projet["project"]["dependencies"] == []
    assert projet["dependency-groups"]["outils"] == ["pyyaml==6.0.3"]
    assert all("==" in d for d in projet["dependency-groups"]["dev"])
    assert (RACINE_DEPOT / ".python-version").read_text(encoding="utf-8").strip() == "3.14"
    assert (RACINE_DEPOT / "uv.lock").exists()


def test_ci_sur_main_seulement():
    ci = (RACINE_DEPOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in ci
    assert ci.count("branches: [main]") == 2
    assert "donnees" not in ci
    assert "uv run ruff check ." in ci
    assert "uv run pytest -q --tb=short" in ci
    assert re.search(r"astral-sh/setup-uv@[0-9a-f]{40}", ci)


def test_charte_posee_sans_cdn():
    polices = sorted(p.name for p in (WEB / "polices").glob("*.woff2"))
    assert polices == [
        "atkinson-hyperlegible-latin-400-normal.woff2",
        "atkinson-hyperlegible-latin-700-normal.woff2",
        "jetbrains-mono-latin-400-normal.woff2",
        "sora-latin-600-normal.woff2",
    ]
    assert "--police-titres" in (WEB / "charte.css").read_text(encoding="utf-8")
    declarees = re.findall(r'url\("([^"]+)"\)', (WEB / "polices.css").read_text(encoding="utf-8"))
    assert sorted(d.removeprefix("polices/") for d in declarees) == polices
    for fichier in WEB.rglob("*"):
        if fichier.suffix in {".css", ".html", ".js", ".svg"}:
            texte = fichier.read_text(encoding="utf-8")
            assert not re.search(r"https?://(?!www\.w3\.org/)", texte), fichier


def test_charte_2_1_0_jetons_et_contours():
    css = (WEB / "charte.css").read_text(encoding="utf-8")
    assert css.splitlines()[0].endswith("(version 2.1.0). */")
    sombre = css.split("@media (prefers-color-scheme: light)")[0]
    clair = css.split('[data-theme="light"] {')[1].split("}")[0]
    # Les quatre blocs de jetons : :root, sombre explicite, clair par média, clair explicite.
    assert len(re.findall(r"--trait-fort: #[0-9A-Fa-f]{6};", css)) == 4
    assert css.count("--halo:") == 4
    assert css.count("--cat-4:") == 4
    assert "--cat-4: #E58FB8;" in sombre
    assert "--cat-4: #B83A75;" in clair
    appli = (WEB / "appli.css").read_text(encoding="utf-8")
    actif = re.search(r"\.btn2 \{[^}]*border: [^;]*var\(--trait-fort\)", appli)
    assert actif
    champs = re.search(r"input,\s*select,\s*textarea \{([^}]*)\}", appli).group(1)
    assert "border: var(--trait-largeur) solid var(--trait-fort)" in champs
    inactif = re.search(r"input:disabled,[^{]*\.btn2:disabled \{([^}]*)\}", appli).group(1)
    assert "border-color: var(--trait)" in inactif
    assert "solid var(--neutre)" not in appli.split(".btn1")[0]
    # [aria-disabled] (barre.js) doit venir après .btn2 : même spécificité, l'ordre tranche.
    assert appli.index('[aria-disabled="true"] {') > appli.index(".btn2 {")
    assert "border-color: var(--trait)" in appli.split('[aria-disabled="true"] {')[1].split("}")[0]
