"""`POST /api/message` et `POST /api/projets` : opérations déposées dans `attente/operations/`
(story 5.2, AD-9, AD-14, M10, M12, `docs/securite.md`).

Le corps (JSON strict, champs fermés) devient une opération du schéma `operation` (5.1), avec un
id généré ici. Avant toute écriture : identifiants validés (AD-9), projet présent dans l'état
chargé et dans `projets.yaml` ou `table-dossiers.json`, PC visé connu par un instantané, message
borné à 2 048 octets UTF-8 et sans motif de secret. L'opération est écrite par création seule
(jamais d'écrasement, jamais `donnees/`), puis `sync` est demandée (`relance`). Tout refus rend
400 sans rien écrire.
"""

import json
import os
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from pilotage import chemins
from pilotage.noyau import ids, schemas, texte
from pilotage.noyau.schemas import operation
from pilotage.serveur import relance
from pilotage.serveur.routes import Reponse
from pilotage.sync import lecture

CHAMPS_MESSAGE = (frozenset({"projet", "texte"}), frozenset({"pc"}))
CHAMPS_PROJETS = (frozenset({"projet", "patch"}), frozenset())
ESSAIS_ID = 3

ERREUR_CORPS = "Corps JSON invalide."
ERREUR_PROJET = "Projet inconnu."
ERREUR_PC = "PC inconnu."
ERREUR_VIDE = "Le message est vide."
ERREUR_TAILLE = f"Le message dépasse {texte.BORNE_MESSAGE_OCTETS:,} octets UTF-8.".replace(",", " ")
ERREUR_SECRET = "Le message contient ce qui ressemble à un secret."
ERREUR_CARACTERE = "Le message contient un caractère invalide (substitut UTF-16 isolé)."
ERREUR_CHANTIER = "Chantier inconnu."
ERREUR_ECRITURE = "Opération non enregistrée, réessayez."


class Refus(Exception):
    """Requête refusée (400) avant toute écriture."""


class Indisponible(Exception):
    """Écriture de l'opération impossible (503) : rien de visible n'est laissé."""


def _sans_doublon(paires: list[tuple[str, object]]) -> dict:
    objet: dict = {}
    for cle, valeur in paires:
        if cle in objet:
            raise Refus(ERREUR_CORPS)
        objet[cle] = valeur
    return objet


def _constante(nom: str) -> object:
    raise Refus(ERREUR_CORPS)  # NaN, Infinity


def lire_corps(corps: bytes, champs: tuple[frozenset, frozenset]) -> dict:
    """Objet JSON aux champs fermés : obligatoires `champs[0]`, facultatifs `champs[1]`."""
    try:
        objet = json.loads(
            corps.decode("utf-8"), object_pairs_hook=_sans_doublon, parse_constant=_constante
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Refus(ERREUR_CORPS) from None
    if not isinstance(objet, dict):
        raise Refus(ERREUR_CORPS)
    obligatoires, facultatifs = champs
    inconnus = sorted(objet.keys() - obligatoires - facultatifs)
    if inconnus:
        raise Refus(f"Champ inconnu : {', '.join(inconnus)}.")
    manquants = sorted(obligatoires - objet.keys())
    if manquants:
        raise Refus(f"Champ manquant : {', '.join(manquants)}.")
    return objet


def _identifiant(valider, valeur: object, nom: str) -> str:
    try:
        return valider(valeur)
    except ids.ErreurId:
        raise Refus(f"{nom} invalide.") from None


# --- M10 : identifiants énumérés --------------------------------------------------------------


def _json(chemin: Path) -> object:
    return json.loads(chemin.read_text(encoding="utf-8"))


def projets_de_l_etat() -> set[str]:
    """Projets (cartes de genre `projet`, chantiers compris) de l'état chargé, sans effet."""
    try:
        pc = lecture.nom_pc(None)
    except ids.ErreurId:
        return set()
    etat = lecture.lire_etat(chemins.racine_github(), pc)
    noms = set()
    for carte in etat.get("cartes") or []:
        for projet in (carte, *(carte.get("projets") or [])):
            if projet.get("genre") == "projet":
                noms.add(projet.get("nom"))
    return noms


def _noms_valides(valeurs) -> set[str]:
    noms = set()
    for valeur in valeurs:
        try:
            noms.add(ids.valider_projet(valeur))
        except ids.ErreurId:
            continue
    return noms


def _projets_yaml() -> dict:
    """`projets.yaml` lu ; fichier absent ou invalide : `{}`."""
    try:
        objet = yaml.safe_load(
            (chemins.donnees() / "projets.yaml").read_text(encoding="utf-8-sig")
        )
    except chemins.ErreurConfiguration:
        raise  # config.json invalide : pas un fichier absent (cause rendue par le serveur)
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    return objet if isinstance(objet, dict) else {}


def chantiers_de_projets_yaml() -> set[str]:
    """Noms des chantiers de `projets.yaml` ; fichier absent ou invalide : aucun."""
    chantiers = _projets_yaml().get("chantiers")
    return {n for n in chantiers if isinstance(n, str)} if isinstance(chantiers, dict) else set()


def projets_de_projets_yaml() -> set[str]:
    """Noms de `projets.yaml` (chantiers, exclus, pauses) ; fichier absent ou invalide : aucun."""
    objet = _projets_yaml()
    valeurs: list = []
    chantiers = objet.get("chantiers")
    if isinstance(chantiers, dict):
        for chantier in chantiers.values():
            liste = chantier.get("projets") if isinstance(chantier, dict) else None
            if isinstance(liste, list):
                valeurs += liste
    if isinstance(objet.get("exclus"), list):
        valeurs += objet["exclus"]
    if isinstance(objet.get("pauses"), dict):
        valeurs += list(objet["pauses"])
    return _noms_valides(v for v in valeurs if isinstance(v, str))


def projets_de_la_table() -> set[str]:
    """Projets de `table-dossiers.json` ; fichier absent ou invalide : aucun."""
    try:
        objet = _json(chemins.table_dossiers())
        schemas.valider("table_dossiers", objet)
    except chemins.ErreurConfiguration:
        raise  # config.json invalide : pas une table absente (cause rendue par le serveur)
    except (OSError, ValueError):
        return set()
    return set(objet["dossiers"].values())


def pcs_connus() -> set[str]:
    """PC ayant un instantané, dans `attente/instantanes/` ou `donnees/instantanes/`."""
    connus = set()
    for dossier in (chemins.instantanes(), chemins.donnees() / "instantanes"):
        try:
            entrees = list(os.scandir(dossier))
        except OSError:
            continue
        for entree in entrees:
            if not entree.name.endswith(".json") or not entree.is_file(follow_symlinks=False):
                continue
            try:
                connus.add(ids.valider_pc(entree.name[: -len(".json")]))
            except ids.ErreurId:
                continue
    return connus


def verifier_projet(projet: str) -> None:
    """M10 : dans l'état chargé et dans `projets.yaml` ou `table-dossiers.json`."""
    if projet not in projets_de_projets_yaml() and projet not in projets_de_la_table():
        raise Refus(ERREUR_PROJET)
    if projet not in projets_de_l_etat():
        raise Refus(ERREUR_PROJET)


def verifier_pc(pc: str) -> None:
    if pc not in pcs_connus():
        raise Refus(ERREUR_PC)


# --- Écriture par création seule --------------------------------------------------------------


def nouvel_id(maintenant: datetime | None = None) -> str:
    """`AAAAMMJJTHHMMSSZ-<8 hex>` (AD-9), suffixe tiré par `secrets`."""
    maintenant = maintenant or datetime.now(UTC)
    return ids.valider_id(f"{maintenant:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}")


ESSAIS_PARTAGE = 5  # `sync` qui lit la réservation la verrouille un instant sous Windows


def _sous_windows(action) -> None:
    """`action()`, réessayée brièvement sur `PermissionError` (fichier ouvert par `sync`)."""
    for essai in range(ESSAIS_PARTAGE):
        try:
            action()
            return
        except PermissionError:
            if essai == ESSAIS_PARTAGE - 1:
                raise
            time.sleep(0.05)


def creer(chemin: Path, contenu: str) -> None:
    """Crée `chemin` avec `contenu` ; lève `FileExistsError` s'il existe, sans jamais l'écraser.

    Le contenu complet est d'abord écrit et synchronisé dans un temporaire voisin (`.tmp`, ignoré
    par `sync`), puis publié par `os.link`, qui échoue si la cible existe. Sans lien physique
    possible, le nom est réservé par création exclusive (`O_CREAT | O_EXCL`, fichier vide) puis
    remplacé d'un coup par le temporaire (`os.replace`) : la cible n'est jamais visible tronquée.
    Tout échec retire le temporaire (et la réservation) puis remonte (`OSError`).
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(f"{chemin.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        with open(temporaire, "x", encoding="utf-8", newline="") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        try:
            os.link(temporaire, chemin)
            return
        except FileExistsError:
            raise
        except OSError:
            pass  # liens physiques indisponibles : réservation exclusive ci-dessous
        os.close(os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY))  # FileExistsError
        try:
            _sous_windows(lambda: os.replace(temporaire, chemin))
        except BaseException:
            _sous_windows(lambda: chemin.unlink(missing_ok=True))  # la réservation, créée ici
            raise
    finally:
        temporaire.unlink(missing_ok=True)


def deposer(objet: dict) -> str:
    """Complète `objet` (schema, id), le valide et l'écrit dans `attente/operations/<id>.json`."""
    for _ in range(ESSAIS_ID):
        id_ = nouvel_id()
        complet = {"schema": operation.SCHEMA, "id": id_, **objet}
        try:
            schemas.valider("operation", complet)
        except ValueError as exc:
            raise Refus(f"Opération invalide : {exc}") from None
        chemin = chemins.joindre_sous(chemins.operations(), f"{id_}.json")
        try:
            creer(chemin, json.dumps(complet, ensure_ascii=False, indent=2) + "\n")
        except FileExistsError:
            continue
        except OSError as exc:
            relance.noter(f"opération non écrite : {type(exc).__name__}")
            raise Indisponible(ERREUR_ECRITURE) from None
        return id_
    relance.noter("opération non écrite : identifiant déjà pris trois fois")
    raise Indisponible(ERREUR_ECRITURE)


def _deposer_et_synchroniser(objet: dict) -> Reponse:
    id_ = deposer(objet)
    sync = relance.demander()
    return Reponse(
        202, donnees={"id": id_, "verbe": objet["verbe"], "projet": objet["projet"], "sync": sync}
    )


# --- Gestionnaires --------------------------------------------------------------------------


def _message(corps: bytes) -> dict:
    objet = lire_corps(corps, CHAMPS_MESSAGE)
    projet = _identifiant(ids.valider_projet, objet["projet"], "projet")
    pc = _identifiant(ids.valider_pc, objet["pc"], "pc") if "pc" in objet else None
    contenu = objet["texte"]
    if not isinstance(contenu, str) or not contenu.strip():
        raise Refus(ERREUR_VIDE)
    if any(0xD800 <= ord(c) <= 0xDFFF for c in contenu):
        raise Refus(ERREUR_CARACTERE)
    try:
        texte.valider_message(contenu)
    except texte.ErreurTexte:
        raise Refus(ERREUR_TAILLE) from None
    if texte.est_suspect(contenu):
        raise Refus(ERREUR_SECRET)
    verifier_projet(projet)
    if pc is not None:
        verifier_pc(pc)
    operation_ = {"verbe": "deposer_message", "projet": projet, "texte": contenu}
    if pc is not None:
        operation_["pc"] = pc
    return operation_


def _projets(corps: bytes) -> dict:
    objet = lire_corps(corps, CHAMPS_PROJETS)
    projet = _identifiant(ids.valider_projet, objet["projet"], "projet")
    patch = objet["patch"]
    champ = patch.get("chantier") if isinstance(patch, dict) else None
    voulu = champ.get("voulu") if isinstance(champ, dict) else None
    if isinstance(voulu, str) and voulu not in chantiers_de_projets_yaml():
        raise Refus(ERREUR_CHANTIER)  # `sync` le rejetterait (patch-impossible), mais tard
    verifier_projet(projet)
    return {"verbe": "modifier_projets", "projet": projet, "patch": patch}


def _gestionnaire(construire):
    def gestionnaire(parametres: dict[str, str], corps: bytes) -> Reponse:
        del parametres
        try:
            return _deposer_et_synchroniser(construire(corps))
        except Refus as exc:
            return Reponse(400, erreur=str(exc))
        except Indisponible as exc:
            return Reponse(503, erreur=str(exc))

    return gestionnaire


message = _gestionnaire(_message)
projets = _gestionnaire(_projets)
