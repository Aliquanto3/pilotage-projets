"""Garde-fou commun : aucun test n'écrit dans les vrais dossiers ni ne joint GitHub (NFR15).

Deux niveaux (incident du 2026-11-06, story 5.1 : un appel à `undo` du monkeypatch a retiré
l'isolement et un cycle `sync` réel a poussé vers le vrai dépôt) :
- session : `os.environ` isolé pour toute la session (racine locale, profil, `gh` sans compte,
  proxy HTTPS local fermé, et `GIT_CONFIG_COUNT` qui détourne `https://github.com/` vers un chemin
  local inexistant, en plus de toute config git qu'un test pose avec `GIT_CONFIG_GLOBAL`) ; un test
  qui retire l'isolement de sa fonction retombe sur celui-ci, jamais sur le vrai profil ;
- fonction : isolement propre à chaque test, puis gardes qui font échouer le test si la racine
  locale sort du dossier temporaire de pytest, si un clone `donnees` vise (URL effective)
  github.com, ou si une variable de session a été retirée sans monkeypatch (rétablie aussitôt).
"""

import os
import subprocess
from pathlib import Path

import pytest

from pilotage import chemins

_JETONS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
_PROXY_FERME = "http://127.0.0.1:9"  # port « discard » : toute requête HTTPS échoue localement
_SESSION: dict[str, str] = {}  # variables de session, vérifiées après chaque test
# Identité GitHub neutre (story 7.1) : aucun test ne vise le vrai propriétaire ni son dépôt.
PROPRIETAIRE_TEST = "proprio-test"
DEPOT_DONNEES_TEST = "proprio-test/donnees-test"
UTILISATEUR_TEST = "Personne Test"


def _profil(racine: Path) -> dict[str, str]:
    profil = racine / "profil"
    return {
        "USERPROFILE": str(profil),
        "HOME": str(profil),
        "HOMEDRIVE": profil.drive,
        "HOMEPATH": str(profil)[len(profil.drive):],
        "LOCALAPPDATA": str(profil / "AppData" / "Local"),
        chemins.VARIABLE_RACINE: str(racine / "racine"),
        chemins.VARIABLE_PROPRIETAIRE: PROPRIETAIRE_TEST,
        chemins.VARIABLE_DEPOT_DONNEES: DEPOT_DONNEES_TEST,
        chemins.VARIABLE_UTILISATEUR: UTILISATEUR_TEST,
    }


def retablir_session() -> list[str]:
    """Rétablit les variables de session retirées ou changées hors monkeypatch ; rend leurs noms."""
    changees = [cle for cle, valeur in _SESSION.items() if os.environ.get(cle) != valeur]
    changees += [cle for cle in _JETONS if cle in os.environ]
    for cle in changees:
        if cle in _SESSION:
            os.environ[cle] = _SESSION[cle]
        else:
            os.environ.pop(cle, None)
    return changees


@pytest.fixture(name="retablir_session")
def _fixture_retablir_session():
    """`retablir_session` de l'instance de ce module chargée par pytest (tests de la garde)."""
    return retablir_session


@pytest.fixture(scope="session", autouse=True)
def isolement_session(tmp_path_factory):
    """`os.environ` isolé pour toute la session, rétabli à la fin."""
    base = tmp_path_factory.mktemp("session")
    bloque = (base / "reseau-interdit").as_uri() + "/"
    config = base / "gitconfig"
    config.write_text(
        "[user]\n\tname = Test\n\temail = test@example.invalid\n[commit]\n\tgpgsign = false\n",
        encoding="utf-8",
    )
    cle_url = f"url.{bloque}.insteadOf"
    valeurs = {
        **_profil(base),
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
        # Portée « commande » : s'ajoute à la config d'un test (préfixe le plus long gagnant).
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": cle_url,
        "GIT_CONFIG_VALUE_0": "https://github.com/",
        "GIT_CONFIG_KEY_1": cle_url,
        "GIT_CONFIG_VALUE_1": "git@github.com:",
        # `gh` sans compte (le jeton du trousseau Windows reste lisible par `gh auth token`,
        # mais les commandes refusent sans hosts.yml) ; le proxy fermé coupe toute requête.
        "GH_CONFIG_DIR": str(base / "gh"),
        "HTTPS_PROXY": _PROXY_FERME,
        "https_proxy": _PROXY_FERME,
        "NO_PROXY": "localhost,127.0.0.1,::1",
        "no_proxy": "localhost,127.0.0.1,::1",
    }
    anciennes = {cle: os.environ.get(cle) for cle in (*valeurs, *_JETONS)}
    os.environ.update(valeurs)
    for cle in _JETONS:
        os.environ.pop(cle, None)
    _SESSION.clear()
    _SESSION.update({c: v for c, v in valeurs.items() if c not in _profil(base)})
    yield base
    _SESSION.clear()
    for cle, valeur in anciennes.items():
        if valeur is None:
            os.environ.pop(cle, None)
        else:
            os.environ[cle] = valeur


@pytest.fixture(autouse=True)
def garde_session(isolement_session):
    """Après le monkeypatch du test (installé après cette garde, retiré avant) : les variables
    de session sont intactes, sinon rétablies et le test échoue."""
    yield
    changees = retablir_session()
    if changees:
        pytest.fail(f"isolement de session modifié hors monkeypatch : {sorted(changees)}")


@pytest.fixture(autouse=True)
def racine_locale_isolee(garde_session, tmp_path, monkeypatch, isolement_session):
    """Pose `PILOTAGE_RACINE_LOCALE` sous `tmp_path`, l'identité GitHub neutre, et isole le
    profil utilisateur.

    `USERPROFILE`, `HOME`, `HOMEDRIVE`/`HOMEPATH` et `LOCALAPPDATA` pointent aussi sous
    `tmp_path` : un test qui retire `PILOTAGE_RACINE_LOCALE` reste hors de `~/.claude/`.
    """
    for cle, valeur in _profil(tmp_path).items():
        monkeypatch.setenv(cle, valeur)
    return tmp_path / "racine"


def _sous(chemin: Path, base: Path) -> bool:
    try:
        Path(chemin).resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


@pytest.fixture(autouse=True)
def garde_isolement(racine_locale_isolee, tmp_path_factory):
    """Échoue si, après le test, la racine locale sort du dossier temporaire de pytest ou si le
    clone `donnees` a une URL distante effective (après `insteadOf`) sur github.com."""
    yield
    base = tmp_path_factory.getbasetemp()
    try:
        racine = chemins.racine_locale()
    except chemins.ErreurConfiguration:  # config.json invalide laissée par le test : défaut
        racine = Path(os.environ.get("LOCALAPPDATA", "")) / "pilotage-projets"
    assert _sous(racine, base), f"racine locale hors du dossier de test : {racine}"
    donnees = racine / "donnees"
    if (donnees / ".git").exists():
        urls = [
            subprocess.run(
                ["git", "-C", str(donnees), *args],
                capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
            ).stdout
            for args in (["ls-remote", "--get-url", "origin"],
                         ["remote", "get-url", "--push", "origin"])
        ]
        assert not any("github.com" in u for u in urls), f"clone de test relié à GitHub : {urls}"
