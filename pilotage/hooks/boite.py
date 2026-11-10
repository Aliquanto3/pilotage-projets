"""Boîte aux lettres de `SessionStart` (AD-13, M17, story 5.3) : messages et acquittements.

- `a_injecter(ctx)` : `(id, texte)` des messages du projet lus dans `donnees/boite/<projet>/` et
  dans `attente/operations/` (`deposer_message` de ce projet, parmi les `MAX_OPERATIONS_LUES`
  plus récentes, filtrées sur les octets avant le parse), dédoublonnés par `id` (version de
  `donnees/` d'abord), qui visent ce PC ou aucun PC et qu'aucun `<id>.lu.<pc>` valide de ce PC
  ne marque (ni dans `attente/boite/` ni dans `donnees/boite/`) ; triés par `id`.
  Acquittement de `attente/` vide ou invalide : ignoré, journalisé `AcquittementInvalide` ; le
  message est remis (au moins une fois), et le nouvel acquittement remplace l'ancien.
- `acquitter(ctx, identifiants)` : `attente/boite/<projet>/<id>.lu.<pc>` (schéma `acquittement`),
  sous le verrou de session (AD-3), après l'émission seulement ; création exclusive sans
  `fsync` (seule la présence compte ; perdu sur coupure : remis à nouveau).

Fichier illisible ou invalide : ignoré, journalisé `MessageInvalide` (jamais son contenu).
L8 : `donnees/` est lu sans verrou ; un message absent un instant (`pull --rebase`) n'est pas
acquitté et sera remis à la session suivante.
"""

import json
import os
from pathlib import Path

from pilotage import chemins
from pilotage.hooks import _commun
from pilotage.noyau import ids, schemas

_EVENEMENT = "SessionStart"  # nom du journal (ce module n'est pas un point d'entrée)
ESSAIS_ACQUITTEMENT = 1
INVALIDE = "MessageInvalide"
ACQUITTEMENT_INVALIDE = "AcquittementInvalide"
MAX_OPERATIONS_LUES = 32  # opérations en attente lues au plus (les plus récentes), NFR1
BORNE_OCTETS = 64 * 1024  # même borne que `sync.operations` : au-delà, invalide


def _noms(dossier: Path) -> set[str]:
    """Noms des fichiers ordinaires du dossier (liens ignorés) ; dossier absent : vide."""
    try:
        with os.scandir(dossier) as entrees:
            return {e.name for e in entrees if e.is_file(follow_symlinks=False)}
    except OSError:
        return set()


def _id_de(nom: str) -> str | None:
    if not nom.endswith(".json"):
        return None
    try:
        return ids.valider_id(nom[: -len(".json")])
    except ids.ErreurId:
        return None


def _lire_json(chemin: Path) -> object:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _commun.journaliser(_EVENEMENT, INVALIDE)
        return None


def _valide(nom_schema: str, objet: object) -> bool:
    try:
        schemas.valider(nom_schema, objet)
    except schemas.ErreurValidation:
        _commun.journaliser(_EVENEMENT, INVALIDE)
        return False
    return True


def _messages_donnees(dossier: Path, noms: set[str], projet: str, acquitte) -> dict[str, dict]:
    messages: dict[str, dict] = {}
    for nom in sorted(noms):
        identifiant = _id_de(nom)
        if identifiant is None or acquitte(identifiant):
            continue  # acquittement recopié, nom hors convention, ou déjà lu (jamais relu)
        objet = _lire_json(dossier / nom)
        if objet is None or not _valide("message", objet):
            continue
        if objet["id"] != identifiant or objet["projet"] != projet:
            _commun.journaliser(_EVENEMENT, INVALIDE)
            continue
        messages[identifiant] = objet
    return messages


def _lire_operation(chemin: Path, projet: str) -> object:
    """Opération lue si ses octets peuvent la rattacher à `projet` et à `deposer_message` ;
    sinon `None` sans journal (autre projet, autre verbe). Trop grosse ou illisible : journalisé."""
    try:
        with open(chemin, "rb") as flux:
            brut = flux.read(BORNE_OCTETS + 1)
    except OSError:
        _commun.journaliser(_EVENEMENT, INVALIDE)
        return None
    # `json.dumps` n'échappe jamais `[a-z0-9._-]` : un projet ou un verbe absent des octets est
    # absent de l'objet.
    if b'"deposer_message"' not in brut or f'"{projet}"'.encode() not in brut:
        return None
    if len(brut) > BORNE_OCTETS:
        _commun.journaliser(_EVENEMENT, INVALIDE)
        return None
    try:
        return json.loads(brut.decode("utf-8"))
    except ValueError:  # UnicodeDecodeError compris
        _commun.journaliser(_EVENEMENT, INVALIDE)
        return None


def _messages_operations(projet: str, deja: dict[str, dict], acquitte) -> dict[str, dict]:
    dossier = chemins.operations()
    messages: dict[str, dict] = {}
    candidats = sorted(i for i in map(_id_de, _noms(dossier)) if i is not None)
    for identifiant in candidats[-MAX_OPERATIONS_LUES:]:  # ids horodatés : les plus récentes
        if identifiant in deja or acquitte(identifiant):
            continue  # M17 : la version de `donnees/` prime ; déjà lu : rien à relire
        objet = _lire_operation(dossier / f"{identifiant}.json", projet)
        if objet is None:
            continue
        if (
            not isinstance(objet, dict)
            or objet.get("verbe") != "deposer_message"
            or objet.get("projet") != projet
        ):
            continue  # autre verbe ou autre projet : pas un message de cette session
        if not _valide("operation", objet):
            continue
        if objet["id"] != identifiant:
            _commun.journaliser(_EVENEMENT, INVALIDE)
            continue
        messages[identifiant] = objet
    return messages


def acquittement_valide(chemin: Path, identifiant: str, projet: str, pc: str) -> bool:
    """Vrai si `chemin` est un acquittement lisible, valide et qui porte `identifiant`, `projet`
    et `pc` ; sinon faux, sans journal (l'appelant décide)."""
    try:
        objet = json.loads(chemin.read_text(encoding="utf-8"))
        schemas.valider("acquittement", objet)
    except (OSError, ValueError):  # JSON, UnicodeDecodeError, ErreurValidation
        return False
    return (objet["id"], objet["projet"], objet["pc"]) == (identifiant, projet, pc)


def a_injecter(ctx) -> list[tuple[str, str]]:
    """Messages à remettre à cette session, triés par `id` (le plus ancien d'abord).

    Un message acquitté n'est pas relu (coût constant quand la boîte grossit) : un
    acquittement de `donnees/boite/` compte par sa présence (validé par `sync` à la copie) ;
    un acquittement de `attente/boite/` est relu et validé (vide ou invalide : journalisé, le
    message est remis)."""
    dossier_donnees = chemins.joindre_sous(chemins.boite_donnees(), ctx.projet)
    dossier_attente = chemins.joindre_sous(chemins.boite_attente(), ctx.projet)
    noms_donnees = _noms(dossier_donnees)
    noms_attente = _noms(dossier_attente)
    vus: dict[str, bool] = {}

    def acquitte(identifiant: str) -> bool:
        if identifiant not in vus:
            nom = f"{identifiant}.lu.{ctx.pc}"
            valide = nom in noms_donnees
            if not valide and nom in noms_attente:
                valide = acquittement_valide(
                    dossier_attente / nom, identifiant, ctx.projet, ctx.pc
                )
                if not valide:
                    _commun.journaliser(_EVENEMENT, ACQUITTEMENT_INVALIDE)
            vus[identifiant] = valide
        return vus[identifiant]

    messages = _messages_donnees(dossier_donnees, noms_donnees, ctx.projet, acquitte)
    messages.update(_messages_operations(ctx.projet, messages, acquitte))
    return sorted(
        (identifiant, objet["texte"])
        for identifiant, objet in messages.items()
        if objet.get("pc", ctx.pc) == ctx.pc
    )


def acquitter(ctx, identifiants: list[str]) -> None:
    """Écrit un acquittement par message émis ; lève `VerrouOccupe` ou `OSError` (journalisés
    par l'appelant : le message sera remis à la session suivante)."""
    if not identifiants:
        return
    heure = _commun.maintenant()
    dossier = chemins.joindre_sous(chemins.boite_attente(), ctx.projet)  # résolu une fois
    with _commun.verrou(ctx.session, ESSAIS_ACQUITTEMENT):
        for identifiant in identifiants:
            objet = {
                "schema": 1, "id": identifiant, "projet": ctx.projet, "pc": ctx.pc,
                "session": ctx.session, "heure": heure,
            }
            schemas.valider("acquittement", objet)
            nom = ids.valider_segment(f"{identifiant}.lu.{ctx.pc}")  # id et pc déjà validés
            contenu = json.dumps(objet, ensure_ascii=False, indent=2) + "\n"
            # Déjà présent et valide (autre session au même instant) : rien écrasé (AD-3) ;
            # présent mais vide ou invalide (coupure entre création et écriture) : remplacé.
            if not chemins.creer_exclusif(dossier / nom, contenu) and not acquittement_valide(
                dossier / nom, identifiant, ctx.projet, ctx.pc
            ):
                chemins.ecrire_atomique(dossier / nom, contenu)
