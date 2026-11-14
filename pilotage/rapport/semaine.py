"""Synthèse d'une semaine ISO (story 9.1, FR44) : pure, stdlib seule, sans E/S ni sous-processus.

L'action de chaque projet vient de `noyau.etat` (`assembler` -> `calculer_action`), jamais d'un
calcul d'ici. `entree` est un dict préparé par `rapport.lecture` :
    faits    : faits par projet à la fin de la semaine (sortie de `assemblage.assembler_faits`)
    debut    : idem au début de la semaine, ou None (aucun point de comparaison)
    sessions : états de session de tous les PC, vivantes et archivées (`projet`, `pc`, `session`,
               `debut`, `dernier_tour`, `fin`) ; les autres champs ne sont jamais lus
    alertes  : alertes ouvertes `{code, params}` ; exclus : projets à omettre
    fuseau   : tzinfo qui situe le lundi 00:00 (début de semaine)
Seuls des champs énumérés ou bornés et filtrés (`noyau.texte`) sortent : ni note de reprise, ni
prompt, ni titre de PR, ni message de commit.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from pilotage.noyau import alertes as noyau_alertes
from pilotage.noyau import etat
from pilotage.noyau import texte as noyau_texte
from pilotage.noyau.assemblage import lire_horodatage

INDISPONIBLE = "faits indisponibles"
SANS_COMPARAISON = "pas de point de comparaison"
# Les données ne datent pas les tags : une release est un tag nouveau depuis le début de semaine.
LIVRAISON_APPROCHEE = (
    "release : tag nouveau depuis le début de la semaine (les données ne datent pas les tags)"
)
_CODE_FAITS_ABSENTS = "faits-absents"  # code de raison de `calculer_action`, pour le libellé seul
_SEMAINE = re.compile(r"([0-9]{4})-W([0-9]{2})")
_FORME = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class Synthese:
    semaine: str
    debut: str  # lundi 00:00 local, ISO
    fin: str  # lundi suivant 00:00 local, ISO
    comparaison: bool  # faux : pas d'état de début, `changements` et `livraisons` vides
    comptes_debut: dict | None
    comptes_fin: dict
    projets: tuple  # {nom, action, raison, indisponible} triés par action puis nom
    changements: tuple  # {projet, avant, apres, code}
    attentes: tuple  # {projet, type, quoi, age_jours}
    livraisons: tuple  # {projet, type: "release"|"phase", ...}
    sessions: tuple  # {projet, pc, nombre, premiere, derniere}
    alertes: tuple  # textes
    note_livraisons: str = LIVRAISON_APPROCHEE  # approximation de « tag daté dans la semaine »


def bornes_semaine(semaine: str, fuseau: tzinfo) -> tuple[datetime, datetime]:
    """(lundi 00:00, lundi suivant 00:00) de la semaine ISO `AAAA-Www`, dans `fuseau`."""
    trouve = _SEMAINE.fullmatch(semaine) if isinstance(semaine, str) else None
    if trouve is None:
        raise ValueError(f"semaine ISO AAAA-Www attendue, pas {semaine!r}")
    try:
        lundi = date.fromisocalendar(int(trouve[1]), int(trouve[2]), 1)
    except ValueError:
        raise ValueError(f"semaine ISO inexistante : {semaine!r}") from None
    debut = datetime.combine(lundi, time(), tzinfo=fuseau)
    return debut, datetime.combine(lundi + timedelta(days=7), time(), tzinfo=fuseau)


def _rang(action: str) -> int:
    return etat.ACTIONS.index(action)


def _par_nom(nom: str) -> tuple[str, str]:
    return nom.casefold(), nom


def _cartes(faits: Mapping, exclus: frozenset, instant: datetime, fuseau: tzinfo) -> dict:
    retenus = {nom: f for nom, f in faits.items() if nom not in exclus}
    return {c["nom"]: c for c in etat.assembler(retenus, instant, fuseau)["cartes"]}


def _indisponible(carte: Mapping) -> bool:
    return carte["raison"]["code"] == _CODE_FAITS_ABSENTS


def _comptes(cartes: Mapping[str, dict]) -> dict:
    par_action = Counter(c["action"] for c in cartes.values())
    comptes: dict = {a: par_action[a] for a in etat.ACTIONS}
    comptes["indisponibles"] = sum(_indisponible(c) for c in cartes.values())
    return comptes


def _depot(faits: Mapping, nom: str) -> Mapping:
    depot = (faits.get(nom) or {}).get("depot")
    return depot if isinstance(depot, Mapping) else {}


def _phases(depot: Mapping) -> list[str]:
    topics = depot.get("topics")
    if not isinstance(topics, list):
        return []
    return sorted(t for t in topics if isinstance(t, str) and t.startswith("status-"))


def _age_jours(depuis: object, instant: datetime) -> int | None:
    debut = lire_horodatage(depuis)
    return None if debut is None else max(0, (instant - debut).days)


def _attentes(cartes: Mapping[str, dict], instant: datetime) -> tuple:
    lignes = [
        {
            "projet": c["nom"], "type": c["type"],
            "quoi": noyau_texte.nettoyer(str(c["quoi"] or ""), noyau_texte.BORNE_QUOI),
            "age_jours": _age_jours(c["depuis"], instant),
        }
        for c in cartes.values() if c["action"] == etat.ATTEND
    ]
    return tuple(sorted(lignes, key=lambda x: _par_nom(x["projet"])))


def _changements(avant: Mapping[str, dict], apres: Mapping[str, dict]) -> tuple:
    lignes = [
        {"projet": nom, "avant": avant[nom]["action"], "apres": c["action"],
         "code": c["raison"]["code"]}
        for nom, c in apres.items() if nom in avant and avant[nom]["action"] != c["action"]
    ]
    return tuple(sorted(lignes, key=lambda x: (_rang(x["apres"]), *_par_nom(x["projet"]))))


def _livraisons(debut: Mapping, fin: Mapping, noms: Iterable[str]) -> tuple:
    """Release nouvelle (tag différent) et changement de topic `status-*` entre les deux états.

    Approximation (`LIVRAISON_APPROCHEE`, rendue dans `Synthese.note_livraisons`) : les
    instantanés ne portent que le dernier tag, sans date ; « tag daté dans la semaine » devient
    « tag de fin de semaine différent de celui du début ». Deux releases dans la semaine n'en
    font qu'une (la dernière) ; un tag retiré puis remis n'est pas vu.
    """
    lignes = []
    for nom in sorted(noms, key=_par_nom):
        avant, apres = _depot(debut, nom), _depot(fin, nom)
        if not avant or not apres:  # faits indisponibles d'un côté : rien à comparer
            continue
        if apres.get("tag") and apres.get("tag") != avant.get("tag"):
            lignes.append({"projet": nom, "type": "release", "tag": apres["tag"],
                           "avant": avant.get("tag")})
        if _phases(avant) != _phases(apres):
            lignes.append({"projet": nom, "type": "phase", "avant": _phases(avant),
                           "apres": _phases(apres)})
    return tuple(lignes)


def _sessions(
    sessions: Iterable[Mapping], exclus: frozenset, debut: datetime, fin: datetime
) -> tuple:
    vues: set[tuple] = set()
    groupes: dict[tuple[str, str], list[tuple[datetime, datetime]]] = {}
    for s in sessions:
        projet, pc = s.get("projet"), s.get("pc")
        premiere = lire_horodatage(s.get("debut"))
        if not isinstance(projet, str) or not isinstance(pc, str) or projet in exclus:
            continue
        if premiere is None or (pc, s.get("session")) in vues:
            continue
        vues.add((pc, s.get("session")))
        derniere = max(
            (d for d in (lire_horodatage(s.get("fin")), lire_horodatage(s.get("dernier_tour")))
             if d is not None),
            default=premiere,
        )
        derniere = max(derniere, premiere)
        if premiere < fin and derniere >= debut:
            groupes.setdefault((projet, pc), []).append((premiere, derniere))
    return tuple(
        {"projet": projet, "pc": pc, "nombre": len(plages),
         "premiere": min(p for p, _ in plages).strftime(_FORME),
         "derniere": max(d for _, d in plages).strftime(_FORME)}
        for (projet, pc), plages in sorted(
            groupes.items(), key=lambda g: (*_par_nom(g[0][0]), g[0][1])
        )
    )


def synthese_semaine(entree: Mapping, semaine: str, maintenant: datetime) -> Synthese:
    """Synthèse de `semaine` (`AAAA-Www`) ; `maintenant` est aware. Même entrée, même rendu."""
    if maintenant.tzinfo is None:
        raise ValueError("synthese_semaine : `maintenant` doit porter un fuseau")
    fuseau = entree["fuseau"]
    debut, fin = bornes_semaine(semaine, fuseau)
    exclus = frozenset(entree.get("exclus") or ())
    instant_fin = min(maintenant, fin)
    cartes_fin = _cartes(entree["faits"], exclus, instant_fin, fuseau)
    avant = entree.get("debut")
    cartes_debut = None if avant is None else _cartes(avant, exclus, debut, fuseau)
    comparaison = cartes_debut is not None
    projets = tuple(sorted(
        ({"nom": c["nom"], "action": c["action"], "raison": c["raison"]["code"],
          "indisponible": _indisponible(c)} for c in cartes_fin.values()),
        key=lambda p: (_rang(p["action"]), *_par_nom(p["nom"])),
    ))
    alertes = sorted(
        noyau_alertes.texte(a, fuseau) for a in entree.get("alertes") or []
        if isinstance(a, Mapping)
    )
    return Synthese(
        semaine=semaine, debut=debut.isoformat(), fin=fin.isoformat(), comparaison=comparaison,
        comptes_debut=_comptes(cartes_debut) if comparaison else None,
        comptes_fin=_comptes(cartes_fin), projets=projets,
        changements=_changements(cartes_debut, cartes_fin) if comparaison else (),
        attentes=_attentes(cartes_fin, instant_fin),
        livraisons=_livraisons(avant, entree["faits"], cartes_fin) if comparaison else (),
        sessions=_sessions(entree.get("sessions") or [], exclus, debut, fin),
        alertes=tuple(alertes),
    )
