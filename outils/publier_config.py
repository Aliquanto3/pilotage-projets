"""Publie un tag de pilotage-projets dans `claude-config/claude/pilotage/` (AD-8, story 2.8).

`uv run python outils/publier_config.py <tag> --vers <claude-config> [--depot <source>]`

Les fichiers sont lus dans le tag par `git archive`, jamais dans la copie de travail. La cible est
remplacée en miroir (fichiers obsolètes supprimés). Rien n'est commité.
Codes : 0 (publié), 1 (refus : rien écrit), 2 (usage).
"""

import argparse
import io
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

RUNTIME = (
    "pilotage",
    "lancer.py",
    "pyproject.toml",
    "uv.lock",
    "VERSION",
    "hooks-pilotage.json",
    "regle-marqueur.md",
)
EXCLUS_DOSSIERS = {"__pycache__", ".venv"}
TAG_SEMVER = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
DEPOT_PAR_DEFAUT = Path(__file__).resolve().parents[1]
SOUS_DOSSIER = Path("claude") / "pilotage"


class Refus(Exception):
    """Publication refusée : rien n'est écrit."""


def _git(depot: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(depot), *args], capture_output=True, check=False
    )


def _controler_propre(depot: Path, nom: str) -> None:
    resultat = _git(depot, "status", "--porcelain")
    if resultat.returncode != 0:
        raise Refus(f"{nom} : {depot} n'est pas un dépôt git")
    if resultat.stdout.strip():
        raise Refus(f"{nom} : copie de travail sale ({depot}), commiter ou remiser d'abord")


def _exclu(nom: str) -> bool:
    parties = nom.split("/")
    return any(p in EXCLUS_DOSSIERS for p in parties) or nom.endswith(".pyc")


def lire_tag(depot: Path, tag: str) -> dict[str, bytes]:
    """Fichiers du runtime dans `tag` : chemin relatif (`/`) → contenu. Lève `Refus`."""
    if not TAG_SEMVER.fullmatch(tag):
        raise Refus(f"tag non SemVer : {tag!r} (forme attendue : v1.2.3)")
    if _git(depot, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}").returncode != 0:
        raise Refus(f"tag absent de {depot} : {tag}")
    # octets du dépôt, sans conversion CRLF propre au poste (`core.autocrlf`)
    archive = _git(
        depot, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
        "archive", "--format=tar", f"refs/tags/{tag}", "--", *RUNTIME,
    )
    if archive.returncode != 0:
        message = archive.stderr.decode("utf-8", "replace").strip()
        raise Refus(f"git archive {tag} a échoué : {message}")
    fichiers: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        for membre in tar.getmembers():
            if not membre.isfile() or _exclu(membre.name):
                continue
            if membre.name.startswith("/") or ".." in membre.name.split("/"):
                raise Refus(f"chemin refusé dans l'archive : {membre.name!r}")
            contenu = tar.extractfile(membre)
            fichiers[membre.name] = contenu.read() if contenu else b""
    for attendu in RUNTIME:
        if not any(n == attendu or n.startswith(attendu + "/") for n in fichiers):
            raise Refus(f"{attendu} absent du tag {tag}")
    version = fichiers["VERSION"].decode("utf-8", "replace").strip()
    if version != tag[1:]:
        raise Refus(f"VERSION du tag ({version!r}) différent du tag {tag}")
    return fichiers


def publier(tag: str, vers: Path, depot: Path = DEPOT_PAR_DEFAUT) -> Path:
    """Copie en miroir le runtime de `tag` vers `<vers>/claude/pilotage/`. Rend la cible."""
    vers = Path(vers).resolve()
    depot = Path(depot).resolve()
    if not (vers / "sync.ps1").is_file():
        raise Refus(f"{vers} n'est pas un claude-config (sync.ps1 absent)")
    _controler_propre(depot, "source")
    _controler_propre(vers, "claude-config")
    fichiers = lire_tag(depot, tag)
    cible = vers / SOUS_DOSSIER
    with tempfile.TemporaryDirectory(dir=vers) as temporaire:
        preparation = Path(temporaire) / "pilotage"
        for nom, contenu in fichiers.items():
            chemin = preparation.joinpath(*nom.split("/"))
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(contenu)
        # ancienne cible déplacée à côté (même volume) puis remise si le remplacement échoue :
        # jamais de `claude/pilotage` à moitié supprimé
        ancienne = Path(temporaire) / "ancienne"
        cible.parent.mkdir(parents=True, exist_ok=True)
        if cible.exists():
            cible.replace(ancienne)
        try:
            preparation.replace(cible)
        except OSError:
            if ancienne.exists():
                ancienne.replace(cible)
            raise
    return cible


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="publier_config.py", description=__doc__.split("\n")[0])
    parser.add_argument("tag", help="tag SemVer de pilotage-projets (ex. v0.1.0)")
    parser.add_argument("--vers", required=True, help="dépôt claude-config (obligatoire)")
    parser.add_argument("--depot", default=str(DEPOT_PAR_DEFAUT), help="dépôt pilotage-projets")
    ns = parser.parse_args(argv)
    try:
        cible = publier(ns.tag, Path(ns.vers), Path(ns.depot))
    except Refus as exc:
        print(f"publier_config.py : {exc} ; rien n'a été écrit", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"publier_config.py : écriture impossible ({exc})", file=sys.stderr)
        return 1
    nombre = sum(1 for f in cible.rglob("*") if f.is_file())
    print(f"{ns.tag} publié dans {cible} ({nombre} fichiers) ; à commiter dans claude-config")
    return 0


if __name__ == "__main__":
    sys.exit(main())
