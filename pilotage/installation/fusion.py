"""Fusion ciblée des hooks du pilotage dans `settings.json` (AD-7).

1. retirer les entrées du pilotage (marque d'appartenance, voir `est_du_pilotage`) ;
2. retirer les groupes vidés par ce retrait ;
3. ajouter les groupes de `hooks-pilotage.json`, jetons substitués.

Écriture en JSON `indent=2`, `ensure_ascii=False`, ordre des clés conservé, UTF-8 sans BOM, LF :
deux exécutions donnent les mêmes octets. Un fichier illisible n'est jamais écrasé ; un fichier
existant est copié en `.avant-pilotage-<AAAAMMJJ-HHMMSS>` avant toute écriture.
"""

import copy
import json
import os
import re
import shlex
from collections.abc import Callable, Collection
from datetime import datetime
from pathlib import Path

from pilotage import chemins

JETON_PYTHON = "{{PYTHON_PILOTAGE}}"
JETON_RACINE = "{{RACINE_PILOTAGE}}"
EVENEMENTS = ("SessionStart", "UserPromptSubmit", "Stop", "Notification", "SessionEnd")
NOM_MODELE = "hooks-pilotage.json"
SUFFIXE_COPIE = ".avant-pilotage-"
BOM = b"\xef\xbb\xbf"


class ErreurInstallation(ValueError):
    """Fichier illisible, modèle invalide ou chemin refusé : rien n'est écrit."""


def chemin_modele() -> Path:
    """`hooks-pilotage.json` à la racine du runtime (code, jamais redirigé)."""
    return Path(__file__).resolve().parents[2] / NOM_MODELE


def settings_par_defaut() -> Path:
    """`~/.claude/settings.json` ; `<racine>/claude/settings.json` sous `PILOTAGE_RACINE_LOCALE`.

    Calcul local : `chemins.py` est hors du périmètre de la story (contrat C1).
    """
    surcharge = os.environ.get(chemins.VARIABLE_RACINE, "")
    if surcharge:
        return Path(os.path.abspath(surcharge)) / "claude" / "settings.json"
    return Path.home() / ".claude" / "settings.json"


def python_par_defaut(racine: Path) -> Path:
    """Interpréteur de l'environnement installé sous `racine` (`uv sync`, story 2.8)."""
    if os.name == "nt":
        return racine / ".venv" / "Scripts" / "python.exe"
    return racine / ".venv" / "bin" / "python"


def normaliser(chemin: str) -> str:
    """Forme comparée par la marque : `..` et `//` résolus, nom court 8.3 et lien suivis
    (`realpath` sur la partie existante), `\\` → `/`, `casefold()`, sans `/` final."""
    try:
        chemin = os.path.realpath(os.path.normpath(chemin))
    except (OSError, ValueError):
        chemin = os.path.normpath(chemin)
    return chemin.replace("\\", "/").casefold().rstrip("/")


def _sans_doublon(paires: list[tuple[str, object]]) -> dict[str, object]:
    objet: dict[str, object] = {}
    for cle, valeur in paires:
        if cle in objet:
            raise ErreurInstallation(f"clé JSON en double : {cle!r}")
        objet[cle] = valeur
    return objet


def lire_json(chemin: Path, bom_accepte: bool = False) -> dict | None:
    """Lit un objet JSON en UTF-8 strict sans BOM ; absent : `None`. Lève `ErreurInstallation`.

    `bom_accepte` : BOM UTF-8 ignoré (`config.json`, comme `chemins.lire_config`).
    """
    try:
        octets = chemin.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ErreurInstallation(f"{chemin} : illisible ({exc.strerror or exc})") from None
    if octets.startswith(BOM) and bom_accepte:
        octets = octets[len(BOM):]
    elif octets.startswith(BOM):
        raise ErreurInstallation(f"{chemin} : BOM UTF-8 inattendu")
    try:
        texte = octets.decode("utf-8")
    except UnicodeDecodeError:
        raise ErreurInstallation(f"{chemin} : encodage non UTF-8") from None
    try:
        donnees = json.loads(texte, object_pairs_hook=_sans_doublon)
    except json.JSONDecodeError as exc:
        raise ErreurInstallation(f"{chemin} : JSON invalide ({exc.msg})") from None
    except ErreurInstallation as exc:
        raise ErreurInstallation(f"{chemin} : {exc}") from None
    if not isinstance(donnees, dict):
        raise ErreurInstallation(f"{chemin} : un objet JSON est attendu à la racine")
    return donnees


_INTERPRETE = re.compile(r"(python[w]?(\d+(\.\d+)*t?)?|py)(\.exe)?")
# options de l'interpréteur suivies d'un argument séparé (`-X utf8`, `-W ignore`)
_OPTIONS_A_ARGUMENT = {"-X", "-W"}


def _scripts(entree: object) -> list[str]:
    """Chemins candidats de l'entrée (le script lancé).

    Forme exec : premier `args` qui n'est pas une option (`-I`, `-S`). Forme shell (sans
    `args`, ancienne installation) : `command` lui-même s'il nomme un `.py`, sinon le premier
    mot non option qui suit un interpréteur Python (`python`, `pythonw`, `py`, `python3.13`),
    et seulement s'il nomme un `.py` : un argument quelconque d'un outil tiers ne compte pas.
    Les options `-X`/`-W` sautent leur argument ; le script doit être le dernier mot.
    """
    if not isinstance(entree, dict):
        return []
    args = entree.get("args")
    if isinstance(args, list):
        for arg in args:
            if not isinstance(arg, str):
                return []
            if not arg.startswith("-"):
                return [arg]
        return []
    commande = entree.get("command")
    if args is not None or not isinstance(commande, str):
        return []
    try:
        mots = [m.strip("\"'") for m in shlex.split(commande, posix=False)]
    except ValueError:
        return []
    if not mots:
        return []
    if mots[0].casefold().endswith(".py"):
        return [mots[0]] if len(mots) == 1 else []
    interprete = mots[0].replace("\\", "/").rsplit("/", 1)[-1].casefold()
    if not _INTERPRETE.fullmatch(interprete):
        return []
    i = 1
    while i < len(mots) and mots[i].startswith("-"):
        i += 2 if mots[i] in _OPTIONS_A_ARGUMENT else 1
    # le script doit être le dernier mot : une commande chaînée (`&&`, `|`, `>`) reste tierce
    if i == len(mots) - 1 and mots[i].casefold().endswith(".py"):
        return [mots[i]]
    return []


def est_du_pilotage(entree: object, racine: str) -> bool:
    """Vrai si un script de l'entrée est sous `<racine>/pilotage/hooks/` (chemins normalisés)."""
    prefixe = normaliser(racine) + "/pilotage/hooks/"
    # chemin relatif : `realpath` le résoudrait contre le dossier courant, jamais du pilotage
    return any(
        os.path.isabs(s) and normaliser(s).startswith(prefixe) for s in _scripts(entree)
    )


# `sauver` : script sous un dossier `pilotage/hooks/` quelconque (installé, clone de dev, autre
# racine), toute graphie de barre et toute casse ; l'installation garde la règle stricte.
_HOOKS_PILOTAGE = re.compile(r"(^|/)pilotage/+hooks/", re.IGNORECASE)


def est_hook_pilotage_quelconque(entree: object) -> bool:
    """Vrai si un script de l'entrée est sous un chemin `*/pilotage/hooks/` (toute racine)."""
    return any(_HOOKS_PILOTAGE.search(s.replace("\\", "/")) for s in _scripts(entree))


def controler_modele(modele: object) -> None:
    """Exactement une entrée exec par événement suivi, sans matcher ; lève `ErreurInstallation`."""
    if not isinstance(modele, dict) or list(modele) != ["hooks"]:
        raise ErreurInstallation("modèle : un objet {'hooks': …} est attendu")
    hooks = modele["hooks"]
    if not isinstance(hooks, dict) or list(hooks) != list(EVENEMENTS):
        raise ErreurInstallation(f"modèle : événements attendus {list(EVENEMENTS)}")
    for evenement, groupes in hooks.items():
        if not isinstance(groupes, list) or len(groupes) != 1:
            raise ErreurInstallation(f"modèle : un seul groupe attendu pour {evenement}")
        groupe = groupes[0]
        if not isinstance(groupe, dict) or list(groupe) != ["hooks"]:
            raise ErreurInstallation(f"modèle : groupe sans matcher attendu pour {evenement}")
        entrees = groupe["hooks"]
        if not isinstance(entrees, list) or len(entrees) != 1:
            raise ErreurInstallation(f"modèle : une seule entrée attendue pour {evenement}")
        entree = entrees[0]
        args = entree.get("args") if isinstance(entree, dict) else None
        if (
            not isinstance(entree, dict)
            or entree.get("type") != "command"
            or entree.get("command") != JETON_PYTHON
            or not isinstance(args, list)
            or len(args) != 3
            or args[:2] != ["-I", "-S"]
            or not isinstance(args[2], str)
            or not args[2].startswith(JETON_RACINE + "/pilotage/hooks/")
            or not args[2].endswith(".py")
        ):
            raise ErreurInstallation(f"modèle : entrée exec invalide pour {evenement}")


def valider_chemin(nom: str, chemin: str) -> str:
    """Chemin absolu, sans guillemet ni saut de ligne ni jeton ; rendu avec des `/`."""
    if not chemin or any(c in chemin for c in "\"\r\n") or "{{" in chemin or "}}" in chemin:
        raise ErreurInstallation(f"{nom} refusé : {chemin!r}")
    if not os.path.isabs(chemin):
        raise ErreurInstallation(f"{nom} refusé, chemin absolu attendu : {chemin!r}")
    return chemin.replace("\\", "/").rstrip("/")


def _substituer(valeur: object, jetons: dict[str, str]) -> object:
    if isinstance(valeur, str):
        for jeton, remplacement in jetons.items():
            valeur = valeur.replace(jeton, remplacement)
        if "{{" in valeur or "}}" in valeur:
            raise ErreurInstallation(f"jeton non substitué : {valeur!r}")
        return valeur
    if isinstance(valeur, list):
        return [_substituer(v, jetons) for v in valeur]
    if isinstance(valeur, dict):
        return {cle: _substituer(v, jetons) for cle, v in valeur.items()}
    return valeur


def _retirer(
    resultat: dict,
    racine: str,
    garder: Collection[str] = (),
    retirer: Callable[[object], bool] | None = None,
) -> dict:
    """Retire de `resultat` (modifié sur place) les entrées du pilotage et les groupes vidés.

    Un événement vidé par ce retrait est retiré, sauf s'il est dans `garder` ; un groupe ou un
    événement déjà vide à l'origine est conservé. `retirer` : prédicat ajouté à la marque.
    """
    hooks = resultat.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ErreurInstallation("'hooks' doit être un objet")
    for evenement in list(hooks):
        groupes = hooks[evenement]
        if not isinstance(groupes, list):
            raise ErreurInstallation(f"'hooks.{evenement}' doit être une liste")
        gardes = []
        for groupe in groupes:
            if not isinstance(groupe, dict) or not isinstance(groupe.get("hooks"), list):
                raise ErreurInstallation(f"'hooks.{evenement}' : groupe mal formé")
            entrees = [
                e for e in groupe["hooks"]
                if not est_du_pilotage(e, racine) and not (retirer and retirer(e))
            ]
            if len(entrees) == len(groupe["hooks"]):
                gardes.append(groupe)
            elif entrees:
                groupe["hooks"] = entrees
                gardes.append(groupe)
        if groupes and not gardes and evenement not in garder:
            del hooks[evenement]
        else:
            hooks[evenement] = gardes
    return hooks


def sans_pilotage(settings: dict, racine: str) -> dict:
    """Rend un nouveau `settings` sans aucune entrée du pilotage (`sauver`, AD-7).

    Retire aussi tout hook sous un `*/pilotage/hooks/` d'une autre racine (clone de dev) : jamais
    versionné. Une clé `hooks` absente à l'origine reste absente.
    """
    racine = valider_chemin("racine", racine)
    resultat = copy.deepcopy(settings)
    avait_hooks = "hooks" in resultat
    _retirer(resultat, racine, retirer=est_hook_pilotage_quelconque)
    if not avait_hooks:
        del resultat["hooks"]
    return resultat


def fusionner(settings: dict | None, modele: dict, python: str, racine: str) -> dict:
    """Rend un nouveau `settings` : entrées du pilotage remplacées, tout le reste conservé."""
    controler_modele(modele)
    python = valider_chemin("python", python)
    racine = valider_chemin("racine", racine)
    groupes_pilotage = _substituer(
        modele["hooks"], {JETON_PYTHON: python, JETON_RACINE: racine}
    )
    resultat = copy.deepcopy(settings) if settings is not None else {}
    hooks = _retirer(resultat, racine, garder=groupes_pilotage)
    for evenement, groupes in groupes_pilotage.items():
        hooks.setdefault(evenement, []).extend(groupes)
    return resultat


def serialiser(settings: dict) -> bytes:
    """JSON `indent=2`, `ensure_ascii=False`, ordre conservé, UTF-8 sans BOM, LF final."""
    try:
        texte = json.dumps(settings, indent=2, ensure_ascii=False, allow_nan=False)
        return (texte + "\n").encode("utf-8")
    except ValueError as exc:  # NaN, Infinity (`1e400`), surrogate isolé : JSON non valide
        raise ErreurInstallation(f"valeur non représentable en JSON ({exc})") from None


def _copier(cible: Path, octets: bytes, horodatage: str) -> Path:
    """Copie exclusive (`xb`) : n'écrase jamais une copie existante (suffixe `-2`, `-3`…)."""
    base = f"{cible.name}{SUFFIXE_COPIE}{horodatage}"
    for rang in range(1, 1000):
        copie = cible.with_name(base if rang == 1 else f"{base}-{rang}")
        try:
            with open(copie, "xb") as fichier:
                fichier.write(octets)
                fichier.flush()
                os.fsync(fichier.fileno())
        except FileExistsError:
            continue
        return copie
    raise ErreurInstallation(f"{cible} : trop de copies {base}")


def installer(
    cible: Path,
    python: str,
    racine: str,
    modele: Path | None = None,
    maintenant: Callable[[], datetime] = datetime.now,
    depuis: Path | None = None,
) -> tuple[bool, Path | None]:
    """Fusionne le modèle dans `cible`. Rend (fichier écrit ?, copie de sauvegarde ou `None`).

    `depuis` : base lue dans ce fichier (réglages du dépôt, `restaurer`) au lieu de `cible`.
    Rien n'est écrit si le résultat est identique à l'octet au fichier existant.
    """
    cible = Path(cible)
    if cible.is_symlink():  # lien (dotfiles) : écrire sa cible, ne pas remplacer le lien
        cible = Path(os.path.realpath(cible))
    if not os.path.isfile(python):
        raise ErreurInstallation(f"python introuvable : {python!r}")
    chemin = modele or chemin_modele()
    contenu_modele = lire_json(chemin)
    if contenu_modele is None:
        raise ErreurInstallation(f"{chemin} : modèle absent")
    try:
        avant = cible.read_bytes()
    except FileNotFoundError:
        avant = None
    except OSError as exc:
        raise ErreurInstallation(f"{cible} : illisible ({exc.strerror or exc})") from None
    if depuis is not None:
        settings = lire_json(Path(depuis))
        if settings is None:
            raise ErreurInstallation(f"{depuis} : réglages source absents")
    else:
        settings = lire_json(cible) if avant is not None else None
    apres = serialiser(fusionner(settings, contenu_modele, python, racine))
    if apres == avant:
        return False, None
    copie = None
    if avant is not None:
        copie = _copier(cible, avant, maintenant().strftime("%Y%m%d-%H%M%S"))
    chemins.ecrire_atomique(cible, apres.decode("utf-8"))
    return True, copie


def exporter_sans_pilotage(source: Path, sortie: Path, racine: str) -> None:
    """Écrit dans `sortie` les réglages de `source` sans les entrées du pilotage (`sauver`)."""
    settings = lire_json(Path(source))
    if settings is None:
        raise ErreurInstallation(f"{source} : absent")
    octets = serialiser(sans_pilotage(settings, racine))
    chemins.ecrire_atomique(Path(sortie), octets.decode("utf-8"))


def valider_identite(
    proprietaire: str | None = None,
    depot_donnees: str | None = None,
    utilisateur: str | None = None,
) -> dict[str, str]:
    """Clés d'identité GitHub fournies (story 7.1), validées ; `ErreurInstallation` sinon.

    Une valeur `None` n'est pas rendue : celle de `config.json` est alors conservée.
    """
    identite: dict[str, str] = {}
    if proprietaire is not None:
        if not chemins.est_login_github(proprietaire):
            raise ErreurInstallation(f"propriétaire GitHub invalide : {proprietaire!r}")
        identite["proprietaire_github"] = proprietaire
    if depot_donnees is not None:
        if not chemins.est_depot_github(depot_donnees):
            raise ErreurInstallation(
                f"dépôt de données invalide (propriétaire/nom attendu) : {depot_donnees!r}"
            )
        identite["depot_donnees"] = depot_donnees
    if utilisateur is not None:
        nom = chemins.utilisateur_valide(utilisateur)
        if nom is None:
            raise ErreurInstallation(
                f"utilisateur invalide ({chemins.BORNE_UTILISATEUR} caractères au plus, "
                "lettres, chiffres, espace et - ' . ’ seulement)"
            )
        identite["utilisateur"] = nom
    return identite


def preparer_config(
    chemin: Path,
    python: str,
    racine_github: str,
    proprietaire: str | None = None,
    depot_donnees: str | None = None,
    utilisateur: str | None = None,
) -> bytes | None:
    """`config.json` avec `python`, `pythonw`, `racine_github` et `port` (s'il manque).

    `proprietaire`, `depot_donnees` et `utilisateur` fournis : écrits (`proprietaire_github`,
    `depot_donnees`, `utilisateur`) après validation ; absents, la valeur présente est gardée.
    Les autres clés sont gardées, dans leur ordre. Rend les octets à écrire, ou `None` si le
    fichier est déjà à jour. N'écrit rien (validation avant la fusion).
    """
    chemin = Path(chemin)
    python = valider_chemin("python", python)
    racine_github = valider_chemin("racine GitHub", racine_github)
    identite = valider_identite(proprietaire, depot_donnees, utilisateur)
    config = lire_json(chemin, bom_accepte=True)  # réécrit sans BOM
    try:
        avant = chemin.read_bytes() if config is not None else None
    except OSError as exc:
        raise ErreurInstallation(f"{chemin} : illisible ({exc.strerror or exc})") from None
    config = dict(config or {})
    dossier, nom = python.rsplit("/", 1)
    nom_w = re.sub(r"^python", "pythonw", nom, flags=re.IGNORECASE)
    config["python"] = python
    config["pythonw"] = f"{dossier}/{nom_w}"
    config["racine_github"] = racine_github
    config.setdefault("port", chemins.PORT_PAR_DEFAUT)
    config.update(identite)
    apres = serialiser(config)
    return None if apres == avant else apres


def ecrire_config(chemin: Path, python: str, racine_github: str) -> bool:
    """Écrit `config.json` (voir `preparer_config`). Rend vrai si le fichier a été écrit."""
    apres = preparer_config(chemin, python, racine_github)
    if apres is None:
        return False
    chemins.ecrire_atomique(Path(chemin), apres.decode("utf-8"))
    return True
