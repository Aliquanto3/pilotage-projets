"""Seule source des chemins de pilotage-projets, et écriture atomique.

- `PILOTAGE_RACINE_LOCALE` posée (tests) : tout est redirigé sous cette racine
  (`attente/`, `donnees/`, `table-dossiers.json`, `installation/`), `config.json` n'est pas lu.
- Sinon : `~/.claude/pilotage/config.json`, clés facultatives `racine_locale`
  (défaut `%LOCALAPPDATA%\\pilotage-projets`), `racine_installation` (défaut
  `~/.claude/pilotage`), `racine_github` (défaut `~/Documents/GitHub`), et `attente`,
  `donnees`, `table_dossiers` pour un chemin précis, `python` et `pythonw` (interpréteurs
  installés, écrits par `restaurer`), et `port` (entier, port du serveur local,
  défaut `PORT_PAR_DEFAUT`).
- Toute clé de chemin doit être absolue après `~` développé (`expanduser`, appliqué à toutes les
  clés par `lire_config`, qui rend le chemin développé) ; sinon `ErreurConfiguration`. `~user`
  est refusé : seul `~`, `~/` ou `~\\` est accepté en tête.
- Sous `PILOTAGE_RACINE_LOCALE`, la racine GitHub devient `<racine>/github`.
- Interrupteur des hooks : `~/.claude/pilotage/desactive` (à côté de `config.json`).
- `PILOTAGE_PYTHONW` (sous `PILOTAGE_RACINE_LOCALE` seulement) : interpréteur des lancements
  détachés des hooks (tests, banc) ; absente, aucun lancement.
- Identité GitHub (story 7.1), clés texte de `config.json` écrites à l'installation :
  `proprietaire_github` (login), `depot_donnees` (`login/nom` du dépôt privé de la branche
  `donnees`), `utilisateur` (nom affiché, facultatif). Sous `PILOTAGE_RACINE_LOCALE` :
  variables `PILOTAGE_PROPRIETAIRE_GITHUB`, `PILOTAGE_DEPOT_DONNEES`, `PILOTAGE_UTILISATEUR`.
  Jamais de valeur par défaut pour les deux premières : `ConfigurationGithubAbsente` sinon.
"""

import json
import os
import re
from pathlib import Path

from pilotage.noyau import ids
from pilotage.noyau import texte as noyau_texte

VARIABLE_RACINE = "PILOTAGE_RACINE_LOCALE"
# Sous `PILOTAGE_RACINE_LOCALE` seulement : interpréteur des lancements détachés (tests, banc).
VARIABLE_PYTHONW = "PILOTAGE_PYTHONW"
VARIABLE_PROPRIETAIRE = "PILOTAGE_PROPRIETAIRE_GITHUB"
VARIABLE_DEPOT_DONNEES = "PILOTAGE_DEPOT_DONNEES"
VARIABLE_UTILISATEUR = "PILOTAGE_UTILISATEUR"
NOM_CONFIG = "config.json"
# Clés texte (non chemins) de `config.json`, validées par leur accesseur.
CLES_TEXTE = ("proprietaire_github", "depot_donnees", "utilisateur")
# Login GitHub : alphanumérique et tirets, 39 caractères au plus, pas de tiret en tête ni en fin.
_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_NOM_DEPOT = re.compile(r"[A-Za-z0-9._-]{1,100}")
BORNE_UTILISATEUR = noyau_texte.BORNE_NOM_AFFICHE  # points de code
CLES_CONFIG = frozenset(
    {"racine_locale", "racine_installation", "racine_github", "attente", "donnees",
     "table_dossiers", "python", "pythonw"}
)
NOM_DESACTIVE = "desactive"
# Windows : un enfant console lancé par un processus sans console (`pythonw`, hooks détachés)
# ouvre sinon une fenêtre visible ; `CREATE_NO_WINDOW` l'en empêche.
CREATE_NO_WINDOW = 0x08000000


def options_sans_fenetre(systeme: str = os.name) -> dict:
    """Option de lancement sans fenêtre, à passer en `**` à `subprocess`.

    Vide hors Windows. `serveur/enfants.py` combine `CREATE_NO_WINDOW` à la main avec
    `CREATE_NEW_PROCESS_GROUP`. Ne se combine pas avec `DETACHED_PROCESS` (voir `hooks/_commun`).
    """
    return {"creationflags": CREATE_NO_WINDOW} if systeme == "nt" else {}

# Port du serveur local (`lancer.py appli`) quand `config.json` n'a pas de clé `port`.
PORT_PAR_DEFAUT = 47615


class ErreurConfiguration(ValueError):
    """`config.json` illisible ou mal formé."""


class ConfigurationGithubAbsente(ErreurConfiguration):
    """`proprietaire_github` ou `depot_donnees` absent, vide ou mal formé."""


def _racine_surchargee() -> Path | None:
    valeur = os.environ.get(VARIABLE_RACINE, "")
    return Path(os.path.abspath(valeur)) if valeur else None


def _installation_par_defaut() -> Path:
    return Path.home() / ".claude" / "pilotage"


def chemin_config() -> Path:
    """Emplacement de `config.json` (sous la racine d'installation)."""
    racine = _racine_surchargee()
    if racine is not None:
        return racine / "installation" / NOM_CONFIG
    return _installation_par_defaut() / NOM_CONFIG


def lire_config() -> dict[str, str | int]:
    """Lit `config.json` ; absent : `{}`. Sous `PILOTAGE_RACINE_LOCALE` : `{}` toujours.

    Les clés de chemin sont des chaînes non vides ; `port` est un entier de 1 à 65535.
    """
    if _racine_surchargee() is not None:
        return {}
    chemin = chemin_config()
    try:
        # `utf-8-sig` : accepte le BOM qu'écrit `Set-Content -Encoding utf8` de PowerShell 5.1.
        texte = chemin.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError:
        raise ErreurConfiguration(f"{chemin} : encodage non UTF-8") from None
    except OSError as exc:
        raise ErreurConfiguration(f"{chemin} : illisible ({exc.strerror or exc})") from None
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as exc:
        raise ErreurConfiguration(f"{chemin} : JSON invalide ({exc.msg})") from None
    if not isinstance(donnees, dict):
        raise ErreurConfiguration(f"{chemin} : un objet JSON est attendu")
    config: dict[str, str | int] = {}
    if "port" in donnees:
        port = donnees["port"]
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ErreurConfiguration(f"{chemin} : 'port' doit être un entier de 1 à 65535")
        config["port"] = port
    for cle in CLES_CONFIG & donnees.keys():
        valeur = donnees[cle]
        if not isinstance(valeur, str) or not valeur:
            raise ErreurConfiguration(f"{chemin} : {cle!r} doit être un chemin non vide")
        if valeur.startswith("~") and valeur != "~" and valeur[1] not in "/\\":
            # `~bob` viserait le profil d'un autre utilisateur (faute de frappe) : refusé.
            raise ErreurConfiguration(
                f"{chemin} : {cle!r} : seul `~` ou `~/` est accepté en tête (reçu {valeur!r})"
            )
        expanse = Path(valeur).expanduser()
        if not expanse.is_absolute():
            # Un hook a pour cwd le projet ouvert : un chemin relatif y écrirait l'état (ou y
            # lancerait un exécutable). `C:foo` et `\foo` ne sont pas absolus sous Windows.
            raise ErreurConfiguration(
                f"{chemin} : {cle!r} doit être un chemin absolu (reçu {valeur!r})"
            )
        config[cle] = str(expanse) if valeur.startswith("~") else valeur
    for cle in CLES_TEXTE:
        # Gardées brutes : validées par leur accesseur (une valeur fausse ne casse pas les hooks).
        if isinstance(donnees.get(cle), str):
            config[cle] = donnees[cle]
    return config


def racine_locale() -> Path:
    """Racine des données locales du PC (`%LOCALAPPDATA%\\pilotage-projets` par défaut)."""
    racine = _racine_surchargee()
    if racine is not None:
        return racine
    valeur = _chemin_de_config("racine_locale")
    return Path(valeur) if valeur else _racine_locale_par_defaut()


def _chemin_de_config(cle: str) -> str | None:
    """Valeur de la clé de chemin `cle` de `config.json`, ou `None` si absente."""
    valeur = lire_config().get(cle)
    return valeur if isinstance(valeur, str) and valeur else None


def _racine_locale_par_defaut() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "pilotage-projets"


def attente_de_secours() -> Path:
    """`attente/` par défaut, sans lire `config.json` (journal des hooks si elle est invalide)."""
    racine = _racine_surchargee()
    return (racine if racine is not None else _racine_locale_par_defaut()) / "attente"


def racine_installation() -> Path:
    """Racine du runtime installé (`~/.claude/pilotage` par défaut)."""
    racine = _racine_surchargee()
    if racine is not None:
        return racine / "installation"
    valeur = _chemin_de_config("racine_installation")
    return Path(valeur) if valeur else _installation_par_defaut()


def fichier_desactive() -> Path:
    """Interrupteur des hooks, à côté de `config.json` : son existence coupe tous les hooks.

    Ne lit pas `config.json` (le hook vérifie ce fichier avant toute lecture).
    """
    return chemin_config().parent / NOM_DESACTIVE


def racine_surchargee() -> bool:
    """`PILOTAGE_RACINE_LOCALE` posée (tests, banc)."""
    return _racine_surchargee() is not None


def pythonw() -> str | None:
    """Interpréteur sans console des lancements détachés (AD-6), ou `None` s'il n'est pas connu.

    Clé `pythonw` de `config.json` ; sous `PILOTAGE_RACINE_LOCALE`, variable `PILOTAGE_PYTHONW`.
    """
    if _racine_surchargee() is not None:
        return os.environ.get(VARIABLE_PYTHONW) or None
    return _chemin_de_config("pythonw")


def est_login_github(valeur: object) -> bool:
    """Login GitHub valide : `[A-Za-z0-9-]`, 39 caractères au plus, sans tiret en tête ni en fin."""
    return isinstance(valeur, str) and _LOGIN.fullmatch(valeur) is not None


def est_depot_github(valeur: object) -> bool:
    """`login/nom` valide : nom en `[A-Za-z0-9._-]`, sans `..`, ni `.git` final, ni `-` en tête."""
    if not isinstance(valeur, str) or valeur.count("/") != 1:
        return False
    login, nom = valeur.split("/")
    return (
        est_login_github(login)
        and _NOM_DEPOT.fullmatch(nom) is not None
        and nom not in (".", "..")
        and ".." not in nom
        and not nom.startswith("-")
        and not nom.casefold().endswith(".git")
    )


def utilisateur_valide(valeur: object) -> str | None:
    """Nom affiché admis, sous sa forme normalisée (`noyau.texte.nom_affiche`), sinon None.

    Une seule règle pour l'installation, le web, `TABLEAU.md` et le préambule injecté dans Claude.
    """
    return noyau_texte.nom_affiche(valeur) or None


def _valeur_texte(cle: str, variable: str) -> object:
    if _racine_surchargee() is not None:
        return os.environ.get(variable)
    return lire_config().get(cle)


def proprietaire_github() -> str:
    """Login GitHub des projets suivis (`proprietaire_github`) ; `ConfigurationGithubAbsente`
    s'il est absent, vide ou mal formé (jamais de valeur par défaut)."""
    valeur = _valeur_texte("proprietaire_github", VARIABLE_PROPRIETAIRE)
    if not est_login_github(valeur):
        raise ConfigurationGithubAbsente(
            "'proprietaire_github' absent ou invalide dans config.json : relancez l'installation"
        )
    return valeur


def depot_donnees() -> str:
    """Dépôt privé `login/nom` de la branche `donnees` (`depot_donnees`) ;
    `ConfigurationGithubAbsente` s'il est absent, vide ou mal formé."""
    valeur = _valeur_texte("depot_donnees", VARIABLE_DEPOT_DONNEES)
    if not est_depot_github(valeur):
        raise ConfigurationGithubAbsente(
            "'depot_donnees' absent ou invalide dans config.json : relancez l'installation"
        )
    return valeur


def utilisateur() -> str:
    """Nom affiché de la personne (`utilisateur`) ; absent ou invalide : `""`, sans exception."""
    try:
        valeur = _valeur_texte("utilisateur", VARIABLE_UTILISATEUR)
    except ErreurConfiguration:
        return ""
    return utilisateur_valide(valeur) or ""


def racine_github() -> Path:
    """Racine des dépôts (`~/Documents/GitHub` par défaut, clé `racine_github` de la config).

    Sous `PILOTAGE_RACINE_LOCALE` : `<racine>/github`.
    """
    racine = _racine_surchargee()
    if racine is not None:
        return racine / "github"
    valeur = _chemin_de_config("racine_github")
    return Path(valeur) if valeur else Path.home() / "Documents" / "GitHub"


def _sous_racine(cle: str, nom: str) -> Path:
    racine = _racine_surchargee()
    if racine is not None:
        return racine / nom
    valeur = _chemin_de_config(cle)
    return Path(valeur) if valeur else racine_locale() / nom


def attente() -> Path:
    """Dossier `attente/` : écritures locales du PC, jamais poussées telles quelles."""
    return _sous_racine("attente", "attente")


def donnees() -> Path:
    """Clone local de la branche `donnees`."""
    return _sous_racine("donnees", "donnees")


def table_dossiers() -> Path:
    """Fichier `table-dossiers.json` écrit par le scan."""
    return _sous_racine("table_dossiers", "table-dossiers.json")


def joindre_sous(racine: Path | str, *segments: str) -> Path:
    """Joint des segments validés par le noyau sous `racine` ; refuse toute sortie de la racine.

    Les segments passent par `noyau.ids.joindre` (lexical), puis le chemin est résolu (liens et
    jonctions suivis) et doit rester sous la racine résolue. Lève `ErreurId` sinon.
    """
    relatif = ids.joindre(*segments)
    base = Path(racine).resolve()
    cible = (base / relatif).resolve()
    if cible != base and base not in cible.parents:
        raise ids.ErreurId(f"chemin hors de sa racine : {relatif!r}")
    return cible


def ecrire_atomique(chemin: Path, contenu: str) -> None:
    """Écrit `contenu` en UTF-8 sans BOM, fins de ligne inchangées : `.tmp` puis `os.replace`.

    Crée le dossier parent au besoin. En cas d'échec, le `.tmp` est supprimé et l'erreur remonte.
    """
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(f"{chemin.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        with open(temporaire, "w", encoding="utf-8", newline="") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.replace(temporaire, chemin)
    except BaseException:
        temporaire.unlink(missing_ok=True)
        raise


def alertes_json() -> Path:
    """Fichier `attente/alertes.json` : alertes rangées par source (AD-5 §9)."""
    return attente() / "alertes.json"


def operations() -> Path:
    """Dossier `attente/operations/` : opérations déposées par le serveur (AD-3, AD-5 §7)."""
    return attente() / "operations"


def briefs() -> Path:
    """Briefs de reprise écrits par le serveur (story 5.4) : local, jamais poussé."""
    return attente() / "briefs"


def instantanes() -> Path:
    """Dossier `attente/instantanes/` : un fichier `<pc>.json` par PC (ici, celui de ce PC)."""
    return attente() / "instantanes"


def tableau() -> Path:
    """`TABLEAU.md` à la racine locale : export lisible du scan, jamais poussé."""
    return racine_locale() / "TABLEAU.md"


def port_serveur() -> int:
    """Port du serveur local : clé `port` de `config.json`, sinon `PORT_PAR_DEFAUT`."""
    port = lire_config().get("port")
    return port if isinstance(port, int) else PORT_PAR_DEFAUT


def appli_pid() -> Path:
    """Fichier `attente/appli.pid` : pid et heure de création de l'instance de l'appli."""
    return attente() / "appli.pid"


def sync_demande() -> Path:
    """Fichier `attente/sync-demande` : synchro demandée par un hook pendant un cycle (M2)."""
    return attente() / "sync-demande"


def journal_sync(mois: str) -> Path:
    """Journal de `sync` `attente/journal/sync-AAAA-MM.log` (`mois` = `AAAA-MM`)."""
    return attente() / "journal" / f"sync-{mois}.log"


def journal_serveur(mois: str) -> Path:
    """Journal du serveur local `attente/journal/serveur-AAAA-MM.log` (`mois` = `AAAA-MM`)."""
    return attente() / "journal" / f"serveur-{mois}.log"


def journal_enfants(mois: str) -> Path:
    """Sortie d'erreur des scans et synchros de l'appli `attente/journal/enfants-AAAA-MM.log`.

    Nom en `[a-z]+-AAAA-MM.log` : la rotation de `sync.archivage` le couvre.
    """
    return attente() / "journal" / f"enfants-{mois}.log"


def racine_web() -> Path:
    """Dossier `pilotage/web/` des fichiers statiques (code du dépôt, jamais redirigé)."""
    return Path(__file__).resolve().parent / "web"


def sessions_claude() -> Path:
    """`~/.claude/sessions/` de Claude Code (lu seul) ; test : `claude-sessions`."""
    racine = _racine_surchargee()
    if racine is not None:
        return racine / "claude-sessions"
    return Path.home() / ".claude" / "sessions"


# --- Boîte aux lettres (story 5.3) ---------------------------------------------------------


def boite_attente() -> Path:
    """Dossier `attente/boite/` : acquittements `<projet>/<id>.lu.<pc>` écrits par les hooks."""
    return attente() / "boite"


def boite_donnees() -> Path:
    """Dossier `donnees/boite/` : messages `<projet>/<id>.json` (et acquittements recopiés)."""
    return donnees() / "boite"



def creer_exclusif(chemin: Path, contenu: str) -> bool:
    """Crée `chemin` (`O_CREAT|O_EXCL`) et y écrit `contenu` en UTF-8 d'un seul `write`, sans
    `fsync` ; rend `False` s'il existe déjà (jamais écrasé). Pour un petit fichier dont la seule
    présence compte et dont la perte sur coupure est sans gravité (acquittement : le message est
    remis à nouveau) ; `.tmp`, `os.replace` et `fsync` coûtaient ~15 ms à `SessionStart` (NFR1).
    """
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    drapeaux = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        descripteur = os.open(chemin, drapeaux, 0o600)
    except FileExistsError:
        return False
    try:
        os.write(descripteur, contenu.encode("utf-8"))
    finally:
        os.close(descripteur)
    return True
