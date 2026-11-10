"""Assemblage de l'état de tous les PC (stories 1.6, 3.4 et 4.2) : un seul code pour le scan et
pour le serveur.

`assembler_tout` est pur à l'égard des fichiers qu'il reçoit : il lit seulement `donnees/` (autres
PC) et rend l'assemblage du noyau. `lire_etat` en est la version sans effet pour le serveur
(AD-14) : elle ne prend aucun mutex, ne lance aucun processus et n'écrit rien ; l'instantané de
ce PC est celui que le dernier scan a écrit dans `attente/instantanes/`, sans appel à `gh`.
"""

import json
import os
import platform
from datetime import UTC, datetime, tzinfo
from pathlib import Path

from pilotage import chemins
from pilotage.noyau import alertes as texte_alertes
from pilotage.noyau import assemblage, etat, faits, ids, schemas
from pilotage.scan import donnees, inventaire, sessions

ALERTE_ALERTES_ILLISIBLES = "alertes-illisibles"
ALERTE_INSTANTANE_ABSENT = "instantane-absent"
MESSAGE_INSTANTANE_ABSENT = "Aucun instantané de ce PC : lancer un scan"
ALERTE_PC_INVALIDE = "pc-invalide"
MESSAGE_PC_INVALIDE = "Nom de ce PC invalide : état local non lu"
SOURCE_LECTURE = "lecture"
PREFIXE_PHASE = "status-"


def nom_pc(demande: str | None) -> str:
    """Nom de ce PC (`demande`, sinon `COMPUTERNAME`, sinon le nom d'hôte), validé par AD-9.

    Partagé par le scan, la sync et le serveur, normalisé par `ids.normaliser_pc` comme dans les
    hooks (nom d'hôte court : avant le premier `.`) ; lève `ids.ErreurId` s'il ne reste aucun
    caractère `[a-z0-9-]`.
    """
    brut = demande or os.environ.get("COMPUTERNAME") or platform.node().split(".")[0]
    return ids.normaliser_pc(brut)


def assembler_tout(
    inv: inventaire.Inventaire,
    config: dict,
    instantane: dict,
    etats: dict[str, list[dict]],
    pc: str,
    maintenant: datetime,
    fuseau: tzinfo,
) -> dict:
    """Assemblage du noyau pour tous les PC.

    Rend `assemblee` (`etat.assembler`), `depots`, `dependances`, `fraicheur` et
    `alertes_lecture` (alertes de `donnees/`, calculées à chaque lecture, jamais écrites).
    """
    exclus = set(config.get("exclus") or [])
    locaux = {
        p["projet"]: {
            "categorie": p["categorie"],
            "chantier": p["chantier"],
            "pause": p["pause"],
            "attente": None,
            "sessions": etats.get(p["projet"], []),
        }
        for p in inv.projets
    }
    # M5 : ce PC vient d'`attente/` (instantané), les autres de `donnees/`
    autres, etats_distants, alertes_lecture = donnees.lire_autres_pcs(pc)
    instantanes = {**autres, pc: instantane}
    chantier_de, pauses = inventaire.rattachements(config)
    defauts = {
        nom: {
            "categorie": inventaire.CATEGORIE_CLASSE if nom in chantier_de
            else inventaire.CATEGORIE_A_CLASSER,
            "chantier": chantier_de.get(nom),
            "pause": pauses.get(nom),
        }
        for i in autres.values() for nom in i["projets"]
    }
    faits = assemblage.assembler_faits(
        locaux, instantanes, etats_distants, pc, maintenant, defauts, exclus
    )
    dependances = [
        d for d in config.get("dependances") or []
        if not exclus & set(d.split(" ← "))  # forme « A ← B » validée par le schéma
    ]
    return {
        "assemblee": etat.assembler(faits, maintenant, fuseau),
        "depots": {nom: f["depot"] for nom, f in faits.items()},
        "dependances": dependances,
        "fraicheur": assemblage.fraicheur(instantanes, pc, fuseau),
        "alertes_lecture": alertes_lecture,
    }


def phase_et_etiquettes(depot: dict | None) -> tuple[list[str], list[str]]:
    """(topics `status-*`, autres topics) du dépôt, dans l'ordre du noyau (`faits.TOPICS`)."""
    topics = set((depot or {}).get("topics") or [])
    presents = [t for t in faits.TOPICS if t in topics]
    phases = [t for t in presents if t.startswith(PREFIXE_PHASE)]
    return phases, [t for t in presents if t not in phases]


def _json(chemin: Path) -> object:
    return json.loads(chemin.read_text(encoding="utf-8"))


def _instantane_local(pc: str) -> dict | None:
    """Instantané de ce PC écrit par le dernier scan, ou None (absent, illisible ou invalide)."""
    try:
        objet = _json(chemins.instantanes() / f"{pc}.json")
        schemas.valider("instantane", objet)
    except (OSError, ValueError):
        return None
    return objet


def lire_alertes_ecrites() -> tuple[list[dict], bool]:
    """(alertes de `attente/alertes.json`, fichier présent mais illisible ou invalide)."""
    chemin = chemins.alertes_json()
    if not chemin.exists():
        return [], False
    try:
        objet = _json(chemin)
        schemas.valider("alertes", objet)
    except (OSError, ValueError):
        return [], True
    return objet["alertes"], False


def _alerte_rendue(source: str, alerte: dict, fuseau: tzinfo) -> dict:
    """`{source, code, params, texte}` : texte rédigé par le noyau (M8), heure dans `fuseau`."""
    return {
        "source": source,
        "code": alerte["code"],
        "params": alerte.get("params") or {},
        "texte": texte_alertes.texte(alerte, fuseau),
    }


def lire_etat(
    racine_github: Path, pc: str | None, maintenant: datetime | None = None
) -> dict:
    """État assemblé sans effet (AD-14) : cartes, colonnes, chantiers, comptes, fraîcheur, alertes.

    Les alertes écrites (`alertes.json`) viennent d'abord, puis celles de lecture, calculées ici.
    `pc` None (nom de ce PC invalide) : état vide et alerte de lecture `pc-invalide`.
    """
    maintenant = maintenant or datetime.now(UTC)
    fuseau = maintenant.astimezone().tzinfo
    if pc is None:
        rendu = {**etat.assembler({}, maintenant, fuseau), "dependances": [], "fraicheur": []}
        lecture: list[dict] = []
        fin = [{"code": ALERTE_PC_INVALIDE, "message": MESSAGE_PC_INVALIDE}]
    else:
        rendu, lecture, absent = _etat_du_pc(racine_github, pc, maintenant, fuseau)
        fin = [{"code": ALERTE_INSTANTANE_ABSENT, "message": MESSAGE_INSTANTANE_ABSENT}] * absent
    ecrites, illisible = lire_alertes_ecrites()
    if illisible:
        lecture.append({"code": ALERTE_ALERTES_ILLISIBLES, "params": {}})
    lecture += fin
    return {
        **rendu,
        "alertes": [_alerte_rendue(a["source"], a, fuseau) for a in ecrites]
        + [_alerte_rendue(SOURCE_LECTURE, a, fuseau) for a in lecture],
    }


def _etat_du_pc(
    racine_github: Path, pc: str, maintenant: datetime, fuseau: tzinfo
) -> tuple[dict, list[dict], bool]:
    """(état assemblé, alertes de lecture de `donnees/`, instantané de ce PC absent)."""
    inv = inventaire.inventorier(racine_github)
    config, _, _ = inventaire.lire_projets(chemins.donnees() / "projets.yaml")
    config = config or {}
    instantane = _instantane_local(pc)
    claude, _ = sessions.vivantes_claude()
    etats, _ = sessions.lire_etats(pc, claude=claude)
    assemble = assembler_tout(
        inv, config, instantane or {"schema": 1, "genere_a": None, "projets": {}},
        etats, pc, maintenant, fuseau,
    )
    # cartes de projet (les dépôts d'un chantier en font partie), puis cartes de chantier
    assemblee = assemble["assemblee"]
    for carte in (*assemblee["cartes"], *assemblee["chantiers"]):
        carte["phase"], carte["etiquettes"] = phase_et_etiquettes(
            assemble["depots"].get(carte["nom"]) if carte["genre"] == "projet" else None
        )
    rendu = {
        **assemble["assemblee"],
        "dependances": assemble["dependances"],
        "fraicheur": assemble["fraicheur"],
    }
    return rendu, list(assemble["alertes_lecture"]), instantane is None
