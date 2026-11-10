"""Assemblage des faits de tous les PC (AD-11, AD-12, story 3.4) : pur, sans E/S.

Le scan lit les fichiers (`attente/` pour ce PC, `donnees/` pour les autres, M5) et passe ici des
objets déjà validés. Ce module choisit les faits de dépôt, rattache les sessions des autres PC
(vivante ou non) et produit le jeu de faits par projet que `etat.assembler` consomme.

- Faits de dépôt : ceux de l'instantané au `genere_a` le plus récent qui les contient (à égalité,
  nom de PC le plus grand) ; un `faits_depot` à `null` ne masque jamais un plus ancien.
- Faits de poste : chaque PC garde les siens ; `pcs` liste les PC dont l'instantané cite le
  projet, `clone_ici` dit si ce PC l'a cloné.
- Session d'un autre PC : vivante si elle n'est ni finie (`fin` ou `statut=finie`, M4) et si
  l'instantané de son PC la cite dans `sessions_vivantes` et date de moins de 45 min. L4 : la
  dérive d'horloge entre PC est tolérée à 5 min des deux côtés, soit un âge accepté de -5 min
  (inclus) à 50 min (exclu).
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, tzinfo

FRAICHEUR_MAX = timedelta(minutes=45)
DERIVE_HORLOGE = timedelta(minutes=5)
_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def lire_horodatage(valeur: object) -> datetime | None:
    """`AAAA-MM-JJTHH:MM:SSZ` en datetime aware UTC ; None si absent ou illisible."""
    if not isinstance(valeur, str):
        return None
    try:
        return datetime.strptime(valeur, _FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def _par_recence(
    instantanes: Mapping[str, Mapping], maintenant: datetime | None = None
) -> list[tuple[str, Mapping]]:
    """(pc, instantané), le plus récent d'abord ; à égalité, nom de PC décroissant.

    Un `genere_a` illisible, ou postérieur à `maintenant` au-delà de la dérive d'horloge (L4),
    passe après tous les autres : un fichier corrompu d'un PC ne masque pas les autres.
    """
    def cle(paire: tuple[str, Mapping]) -> tuple[bool, datetime, str]:
        genere = lire_horodatage(paire[1].get("genere_a"))
        plausible = genere is not None and (
            maintenant is None or genere <= maintenant + DERIVE_HORLOGE
        )
        return plausible, genere or datetime.min.replace(tzinfo=UTC), paire[0]

    return sorted(instantanes.items(), key=cle, reverse=True)


def depot_le_plus_recent(
    instantanes: Mapping[str, Mapping], projet: str, maintenant: datetime | None = None
) -> tuple[str, Mapping] | tuple[None, None]:
    """(pc, `faits_depot`) du projet dans l'instantané le plus récent qui les contient."""
    for pc, instantane in _par_recence(instantanes, maintenant):
        entree = (instantane.get("projets") or {}).get(projet)
        if isinstance(entree, Mapping) and isinstance(entree.get("faits_depot"), Mapping):
            return pc, entree["faits_depot"]
    return None, None


def instantane_recent(instantane: Mapping | None, maintenant: datetime) -> bool:
    """Instantané assez frais pour dire qu'une session tourne (45 min, dérive de 5 min, L4)."""
    genere = lire_horodatage((instantane or {}).get("genere_a"))
    if genere is None:
        return False
    age = maintenant - genere
    return -DERIVE_HORLOGE <= age < FRAICHEUR_MAX + DERIVE_HORLOGE


def session_distante(
    etat: Mapping, projet: str, instantanes: Mapping[str, Mapping], maintenant: datetime
) -> dict:
    """Copie de l'état d'une session d'un autre PC, avec `vivante`, `distante` et `nouvelles`.

    `nouvelles` : `genere_a` de l'instantané de son PC (None : aucun), pour « sans nouvelles ».
    """
    pc = etat.get("pc")
    instantane = instantanes.get(pc) if isinstance(pc, str) else None
    fini = bool(etat.get("fin")) or etat.get("statut") == "finie"
    entree = ((instantane or {}).get("projets") or {}).get(projet) or {}
    citee = etat.get("session") in (entree.get("sessions_vivantes") or [])
    vivante = not fini and citee and instantane_recent(instantane, maintenant)
    return {
        **etat, "vivante": vivante, "distante": True,
        "nouvelles": (instantane or {}).get("genere_a"),
    }


def assembler_faits(
    locaux: Mapping[str, Mapping],
    instantanes: Mapping[str, Mapping],
    etats_distants: Mapping[str, Mapping[str, list]],
    pc: str,
    maintenant: datetime,
    defauts: Mapping[str, Mapping] | None = None,
    exclus: frozenset[str] | set[str] = frozenset(),
) -> dict[str, dict]:
    """Faits par projet pour `etat.assembler`, tous PC confondus.

    `locaux` : faits des projets clonés sur ce PC (`categorie`, `chantier`, `pause`, `sessions`
    de ce PC). `instantanes` : `{pc: instantané}` y compris celui de ce PC (`pc`).
    `etats_distants` : `{pc: {projet: [états de session]}}` des autres PC seulement.
    `defauts` : `categorie`/`chantier`/`pause` des projets connus d'un autre PC seulement.
    Un projet exclu n'apparaît jamais. Le jeu rendu porte `depot`, `depot_de`, `sessions`, `pcs`,
    `clone_ici`.
    """
    defauts = defauts or {}
    noms = set(locaux)
    for instantane in instantanes.values():
        noms |= set(instantane.get("projets") or {})
    resultat: dict[str, dict] = {}
    for projet in sorted(noms - set(exclus)):
        base = dict(locaux[projet]) if projet in locaux else dict(defauts.get(projet) or {})
        sessions = list(base.get("sessions") or [])
        for autre in sorted(etats_distants):
            if autre == pc:  # M5 : ce PC se lit dans `attente/`, jamais dans `donnees/`
                continue
            sessions += [
                session_distante(etat, projet, instantanes, maintenant)
                for etat in etats_distants[autre].get(projet, [])
            ]
        depot_de, depot = depot_le_plus_recent(instantanes, projet, maintenant)
        resultat[projet] = {
            "categorie": base.get("categorie", "classé"),
            "chantier": base.get("chantier"),
            "pause": base.get("pause"),
            "attente": base.get("attente"),
            "depot": depot,
            # origine des faits de dépôt repris d'un autre PC (None : ce PC ou aucun)
            "depot_de": None if depot_de in (None, pc) else {
                "pc": depot_de, "genere_a": instantanes[depot_de].get("genere_a"),
            },
            "sessions": sessions,
            "clone_ici": projet in locaux,
            "pcs": sorted(
                p for p, i in instantanes.items() if projet in (i.get("projets") or {})
            ),
        }
    return resultat


def fraicheur(
    instantanes: Mapping[str, Mapping], pc: str, fuseau: tzinfo
) -> list[dict]:
    """Une ligne par PC (celui-ci compris), triée par nom : `{pc, genere_a, texte}`."""
    lignes = []
    for nom in sorted(set(instantanes) | {pc}):
        genere = (instantanes.get(nom) or {}).get("genere_a")
        instant = lire_horodatage(genere)
        marque = " (ce PC)" if nom == pc else ""
        heure = instant.astimezone(fuseau).strftime("%d/%m %H:%M") if instant else None
        texte = f"{nom}{marque} : " + (
            f"instantané du {heure}" if heure else "aucun instantané"
        )
        lignes.append({"pc": nom, "genere_a": genere if instant else None, "texte": texte})
    return lignes
