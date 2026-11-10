"""Clone `donnees/` : commandes git et contrôle du dépôt privé (story 3.1, AD-4, AD-5 §4).

Toute commande git passe par `git(...)` : tableau d'arguments, sans shell, sans invite
(`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`), avec un délai. Seul `sync` en lance dans
`donnees/` (M13). Le contrôle `isPrivate` est en échec fermé : toute réponse autre que
`{"isPrivate": true}` pour le dépôt de données vaut refus. Ce dépôt (`login/nom`) est lu dans
`config.json` (`chemins.depot_donnees()`, story 7.1) une fois par cycle, jamais à l'import :
absent ou invalide, `chemins.ConfigurationGithubAbsente` est levée avant tout appel git ou gh.
"""

import json
import os
import re
import subprocess
from pathlib import Path

from pilotage import chemins
from pilotage.scan import faits_gh

BRANCHE = "donnees"
DELAI_GIT_S = 120.0
DELAI_GH_S = 30.0
# Formes d'URL admises pour `origin` : HTTPS, SSH court et SSH long de github.com.
_URL = re.compile(
    r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<depot>[^/\s]+/[^/\s]+?)(?:\.git)?/?",
    re.IGNORECASE,
)


class ErreurGit(Exception):
    """Commande git en échec ou clone invalide (le message ne contient aucune sortie git)."""


class ConflitRebase(ErreurGit):
    """Le `pull --rebase` a conflit ; le rebase a été abandonné."""


class ConflitAutostash(ErreurGit):
    """Modifications locales réappliquées en conflit après le pull ; gardées dans le stash."""

    def __init__(self, stash: str) -> None:
        super().__init__("autostash en conflit")
        self.stash = stash  # empreinte du stash (hexadécimal) ou ""


class NonFastForward(ErreurGit):
    """Le push est refusé parce que le distant a avancé."""


class DepotNonPrive(Exception):
    """`origin` ne désigne pas le dépôt privé, ou `isPrivate` n'est pas confirmé."""


def depot_attendu() -> str:
    """`login/nom` du dépôt de données configuré ; `chemins.ConfigurationGithubAbsente` sinon."""
    return chemins.depot_donnees()


def url_distant(attendu: str | None = None) -> str:
    """URL HTTPS du dépôt de données (`attendu`, sinon celui configuré)."""
    return f"https://github.com/{attendu or depot_attendu()}.git"


def git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Lance `git <args>` sans shell ni invite ; `ErreurGit` si git manque ou dépasse le délai."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        return subprocess.run(  # noqa: S603 (tableau d'arguments, pas de shell)
            ["git", *args],  # noqa: S607
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DELAI_GIT_S,
            check=False,
            stdin=subprocess.DEVNULL,
            **chemins.options_sans_fenetre(),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ErreurGit(f"git {args[0]} indisponible ou trop lent") from None


def git_ok(args: list[str], cwd: Path | None = None) -> str:
    """`git <args>` qui doit réussir ; rend la sortie standard."""
    resultat = git(args, cwd)
    if resultat.returncode != 0:
        raise ErreurGit(f"git {args[0]} a échoué")
    return resultat.stdout


def depot_de_url(url: str) -> str | None:
    """`propriétaire/nom` d'une URL github.com admise, sinon None."""
    correspondance = _URL.fullmatch(url.strip())
    return correspondance.group("depot") if correspondance else None


def verifier_url(url: str, attendu: str | None = None) -> None:
    """Lève `DepotNonPrive` si `url` ne désigne pas le dépôt de données (`attendu`, sinon celui
    configuré) sur github.com."""
    attendu = attendu or depot_attendu()
    depot = depot_de_url(url)
    if depot is None or depot.casefold() != attendu.casefold():
        raise DepotNonPrive("origin ne désigne pas le dépôt attendu")


def _lignes(resultat: subprocess.CompletedProcess, commande: str) -> list[str]:
    if resultat.returncode != 0:
        raise ErreurGit(f"git {commande} a échoué")
    return [ligne.strip() for ligne in resultat.stdout.splitlines() if ligne.strip()]


def urls_origine(donnees: Path) -> list[str]:
    """URL de `origin` telles que git les utilise, et leurs formes brutes.

    `git remote get-url --all [--push]` applique `insteadOf` et `pushInsteadOf` (configs du
    clone, globale et système) : ce sont ces URL effectives que pull et push contactent. Les URL
    brutes `url` et `pushurl` sont contrôlées aussi. Un échec de git lève `ErreurGit`.
    """
    urls: list[str] = []
    for cle in ("remote.origin.url", "remote.origin.pushurl"):
        resultat = git(["config", "--get-all", cle], donnees)
        if resultat.returncode == 0:
            urls += _lignes(resultat, "config")
        elif resultat.returncode != 1:  # 1 : clé absente
            raise ErreurGit("git config a échoué")
    if not urls:
        return []
    for options in (["--all"], ["--all", "--push"]):
        urls += _lignes(git(["remote", "get-url", *options, "origin"], donnees), "remote")
    return urls


def url_clone(donnees: Path, attendu: str | None = None) -> list[str]:
    """`url_distant()` et l'URL que `cloner` contactera après réécriture `insteadOf`.

    Lancé du même dossier que `cloner` (parent de `donnees/`), donc avec la même configuration.
    """
    donnees.parent.mkdir(parents=True, exist_ok=True)
    distant = url_distant(attendu)
    resultat = git(["ls-remote", "--get-url", distant], donnees.parent)
    return [distant, *_lignes(resultat, "ls-remote")]


def _executeur(args: list[str], delai: float) -> subprocess.CompletedProcess:
    return faits_gh.executeur_gh(args, delai)  # résolu à l'appel : substituable en test


def est_prive(attendu: str | None = None) -> bool:
    """Vrai seulement si `gh` répond `{"isPrivate": true}` pour le dépôt (échec fermé)."""
    depot = attendu or depot_attendu()
    try:
        resultat = _executeur(["repo", "view", depot, "--json", "isPrivate"], DELAI_GH_S)
    except faits_gh.ErreurGh:
        return False
    if resultat.returncode != 0:
        return False
    try:
        objet = json.loads(resultat.stdout or "")
    except ValueError:
        return False
    return isinstance(objet, dict) and objet.get("isPrivate") is True


def controler_prive(donnees: Path, attendu: str | None = None) -> None:
    """Contrôle d'AD-5 §4 (étapes 1 et 9) : URL brutes et effectives de `origin`
    (ou de `url_distant()` sans clone), puis `gh`.

    Lève `DepotNonPrive` en cas de doute ; chaque URL doit désigner le dépôt privé.
    Dépôt non configuré : `chemins.ConfigurationGithubAbsente`, avant toute commande git ou gh.
    Le dépôt est lu une seule fois (ou fourni par `attendu`) : URL et `isPrivate` portent sur la
    même valeur, même si `config.json` change pendant le contrôle.
    """
    attendu = attendu or depot_attendu()
    urls = urls_origine(donnees) if est_clone(donnees) else url_clone(donnees, attendu)
    if not urls:
        raise DepotNonPrive("origin absent")
    for url in urls:
        verifier_url(url, attendu)
    if not est_prive(attendu):
        raise DepotNonPrive("isPrivate non confirmé")


def est_clone(donnees: Path) -> bool:
    """Vrai si `donnees/` porte son propre `.git` (le clone n'est pas encore vérifié)."""
    return (donnees / ".git").is_dir()


def verifier_racine(donnees: Path) -> None:
    """`donnees/` est la racine de son clone, sinon `ErreurGit`.

    Évite qu'une commande git agisse sur un dépôt parent qui contiendrait `donnees/`.
    """
    racine = git_ok(["rev-parse", "--show-toplevel"], donnees).strip()
    if Path(racine).resolve() != donnees.resolve():
        raise ErreurGit("donnees/ n'est pas la racine de son clone")


def verifier_clone(donnees: Path) -> None:
    """Le clone est à la racine de `donnees/` et sur la branche `donnees`, sinon `ErreurGit`."""
    verifier_racine(donnees)
    if git_ok(["symbolic-ref", "--short", "HEAD"], donnees).strip() != BRANCHE:
        raise ErreurGit("donnees/ n'est pas sur la branche donnees")


def cloner(donnees: Path, attendu: str | None = None) -> None:
    """Clone mono-branche de `donnees` dans `donnees/` (absent ou vide), depuis `attendu` (le
    dépôt contrôlé par `controler_prive`), sinon le dépôt configuré."""
    if donnees.exists() and any(donnees.iterdir()):
        raise ErreurGit("donnees/ existe sans être un clone")
    distant = url_distant(attendu)
    donnees.parent.mkdir(parents=True, exist_ok=True)
    git_ok(["clone", "--quiet", "--single-branch", "--branch", BRANCHE, distant,
            str(donnees)], donnees.parent)


def tirer(donnees: Path) -> None:
    """`git pull --rebase --autostash` de la branche `donnees`.

    Rebase laissé en cours par un échec : `git rebase --abort` puis `ConflitRebase`. Autostash
    réappliqué en conflit (git sort alors 0) : les fichiers en conflit sont remis à `HEAD`
    (jamais de marqueurs de conflit commités), les modifications locales restent dans le stash
    que git a gardé, puis `ConflitAutostash`.
    """
    resultat = git(
        ["pull", "--quiet", "--rebase", "--autostash", "origin", BRANCHE], donnees
    )
    if resultat.returncode == 0:
        conflits = _non_fusionnes(donnees)
        if conflits:
            stash = git(["rev-parse", "--quiet", "--verify", "refs/stash"], donnees).stdout.strip()
            _remettre_a_head(donnees, conflits)
            git_ok(["reset", "--quiet"], donnees)
            raise ConflitAutostash(stash if re.fullmatch(r"[0-9a-f]{40,64}", stash) else "")
        return
    if rebase_en_cours(donnees):
        git_ok(["rebase", "--abort"], donnees)
        raise ConflitRebase("conflit de rebase")
    raise ErreurGit("git pull a échoué")


def rebase_en_cours(donnees: Path) -> bool:
    return any((donnees / ".git" / nom).is_dir() for nom in ("rebase-merge", "rebase-apply"))


def _non_fusionnes(donnees: Path) -> list[str]:
    sortie = git_ok(["diff", "--name-only", "--diff-filter=U", "-z"], donnees)
    return sorted({p for p in sortie.split("\0") if p})


def _remettre_a_head(donnees: Path, conflits: list[str]) -> None:
    """Remet des fichiers en conflit à leur état de `HEAD` ; absents de `HEAD` (conflit
    modifié/supprimé), ils sont retirés de l'index et de l'arbre (le stash en garde la copie)."""
    git_ok(["reset", "--quiet", "--", *conflits], donnees)
    sortie = git_ok(["ls-tree", "-z", "--name-only", "HEAD", "--", *conflits], donnees)
    suivis = set(sortie.split("\0"))
    presents = [c for c in conflits if c in suivis]
    if presents:
        git_ok(["checkout", "--quiet", "HEAD", "--", *presents], donnees)
    for chemin in conflits:
        if chemin not in suivis:
            (donnees / chemin).unlink(missing_ok=True)


VERROUS = ("index.lock", "HEAD.lock")


def git_actif() -> bool:
    """Vrai si un processus git tourne sur ce PC, ou en cas de doute (échec fermé).

    Sans moyen portable de savoir sur quel dépôt il agit, tout git en cours compte.
    """
    if os.name == "nt":
        commande = ["tasklist", "/FI", "IMAGENAME eq git.exe", "/FO", "CSV", "/NH"]
    else:
        commande = ["ps", "-A", "-o", "comm="]
    try:
        resultat = subprocess.run(  # noqa: S603 (tableau d'arguments, pas de shell)
            commande, capture_output=True, text=True, errors="replace", timeout=30,
            check=False, stdin=subprocess.DEVNULL, **chemins.options_sans_fenetre(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    if resultat.returncode != 0:
        return True
    if os.name == "nt":
        return "git.exe" in resultat.stdout.casefold()
    return any(
        Path(ligne.strip()).name in {"git", "git-remote-https"}
        for ligne in resultat.stdout.splitlines()
    )


def _retirer_verrous(donnees: Path) -> bool:
    """Retire `.git/index.lock` et `HEAD.lock` laissés par un git tué, sous le mutex et seulement
    si aucun git ne tourne ; rend vrai si un verrou a été retiré."""
    presents = [donnees / ".git" / nom for nom in VERROUS if (donnees / ".git" / nom).is_file()]
    if not presents or git_actif():
        return False
    for verrou in presents:
        verrou.unlink(missing_ok=True)
    return True


def reprendre(donnees: Path) -> list[str]:
    """Rétablit un arbre propre sur `donnees` après un cycle interrompu (AD-5 §1, M3, H3).

    À appeler sous le mutex. Dans l'ordre : verrous git orphelins retirés, `git rebase --abort`
    si un rebase est en cours (ce qui rend aussi l'autostash), contrôle de HEAD (détaché ou sur
    une autre branche : refus s'il porte des commits absents de `donnees`, **avant** toute
    opération destructive), conflit d'autostash annulé si le stash le garde, index vidé, fichiers
    suivis remis à `HEAD` et fichiers non suivis supprimés, sauf `projets.yaml` (édité à la main,
    AD-3), puis HEAD remis sur `donnees`. Un commit local non poussé est conservé. Rend les
    actions faites (textes fixes, pour le journal).
    """
    actions: list[str] = []
    if _retirer_verrous(donnees):
        actions.append("verrous git orphelins retirés")
    if rebase_en_cours(donnees):
        git_ok(["rebase", "--abort"], donnees)
        actions.append("rebase abandonné")
    branche = git(["symbolic-ref", "--short", "-q", "HEAD"], donnees)
    ailleurs = branche.returncode != 0 or branche.stdout.strip() != BRANCHE
    if ailleurs:
        if git(["rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCHE}"], donnees).returncode:
            raise ErreurGit("branche donnees absente du clone")
        if git(["merge-base", "--is-ancestor", "HEAD", BRANCHE], donnees).returncode != 0:
            raise ErreurGit("HEAD hors de donnees avec des commits propres")
    conflits = _non_fusionnes(donnees)
    if conflits:
        if git(["rev-parse", "--quiet", "--verify", "refs/stash"], donnees).returncode != 0:
            raise ErreurGit("conflit non résolu sans stash")  # rien n'en garde une copie
        _remettre_a_head(donnees, conflits)
        actions.append("conflit d'autostash annulé (modifications gardées dans le stash)")
    git_ok(["reset", "--quiet"], donnees)
    modifies = git_ok(["diff", "--name-only", "-z", "HEAD"], donnees).split("\0")
    modifies = [p for p in modifies if p and p != "projets.yaml"]
    if modifies:
        git_ok(["checkout", "--quiet", "HEAD", "--", *modifies], donnees)
        actions.append("fichiers suivis rétablis")
    non_suivis = git_ok(["ls-files", "--others", "--exclude-standard", "-z"], donnees).split("\0")
    if any(p and p != "projets.yaml" for p in non_suivis):
        git_ok(["clean", "--quiet", "-fd", "-e", "/projets.yaml"], donnees)
        actions.append("fichiers non suivis supprimés")
    if ailleurs:
        git_ok(["checkout", "--quiet", BRANCHE], donnees)
        actions.append("HEAD remis sur donnees")
    return actions


def commiter(donnees: Path, relatifs: list[str], message: str) -> bool:
    """Index vidé, `git add` des seuls `relatifs`, commit s'il y a un changement indexé.

    Rend vrai si un commit a été créé. Jamais `git add -A` ni `.`.
    """
    git_ok(["reset", "--quiet"], donnees)
    if relatifs:
        git_ok(["add", "--", *relatifs], donnees)
    if git(["diff", "--cached", "--quiet"], donnees).returncode == 0:
        return False
    git_ok(["commit", "--quiet", "-m", message], donnees)
    return True


def pousser(donnees: Path) -> None:
    """`git push origin donnees`, sans force ; `NonFastForward` si le distant a avancé.

    Le refus est reconnu sans lire le texte de git (traduit) : après un échec, `fetch` puis
    `origin/donnees` qui n'est pas ancêtre de `HEAD`.
    """
    if git(["push", "--quiet", "origin", BRANCHE], donnees).returncode == 0:
        return
    if git(["fetch", "--quiet", "origin", BRANCHE], donnees).returncode == 0:
        distant = f"refs/remotes/origin/{BRANCHE}"
        if git(["merge-base", "--is-ancestor", distant, "HEAD"], donnees).returncode == 1:
            raise NonFastForward("push refusé : le distant a avancé")
    raise ErreurGit("git push a échoué")
