"""Rendu Markdown de `TABLEAU.md` à partir de l'assemblage du noyau (story 1.6).

Aucun texte n'est calculé ici : les libellés d'action et les raisons viennent de
`noyau.etat` (`libelle_action`, `raison["texte"]`) ; ce module ne fait que les ranger.
"""

from collections.abc import Mapping
from datetime import datetime

from pilotage.noyau import alertes as texte_alertes
from pilotage.noyau import assemblage as assemblage_pc
from pilotage.noyau import etat, faits

EMOJI = {etat.ATTEND: "🔴", etat.A_RELANCER: "🟠", etat.TOURNE: "🟢", etat.RIEN: "⚪"}
PREFIXE_PHASE = "status-"
SANS_PHASE = "—"


def _phase(depot: Mapping | None) -> str:
    """Topics `status-*` du dépôt (énumération fermée de `noyau.faits`), dans l'ordre du noyau."""
    topics = set((depot or {}).get("topics") or [])
    phases = [t for t in faits.TOPICS if t.startswith(PREFIXE_PHASE) and t in topics]
    return ", ".join(phases) or SANS_PHASE


def _origine(depot_de: Mapping | None) -> str:
    """« · dépôt vu par <pc> le JJ/MM HH:MM » pour des faits de dépôt d'un autre PC."""
    if not depot_de:
        return ""
    instant = assemblage_pc.lire_horodatage(depot_de.get("genere_a"))
    quand = f" le {instant.astimezone().strftime('%d/%m %H:%M')}" if instant else ""
    return f" · dépôt vu par {depot_de['pc']}{quand}"


def rendre(
    assemblage: Mapping,
    depots: Mapping[str, Mapping | None],
    dependances: list[str],
    genere: datetime,
    fraicheur: list[dict] | None = None,
    alertes_lecture: list[dict] | None = None,
    utilisateur: str = "",
) -> str:
    """`TABLEAU.md` : quatre sections dans l'ordre d'action, puis chantiers et dépendances.

    `depots` : `faits_depot` par projet (pour la phase) ; `dependances` : lignes « A ← B » de
    `projets.yaml`, reprises telles quelles ; `genere` : instant de l'assemblage, en tête (un
    ancien fichier laissé par un scan en échec reste ainsi daté). `fraicheur` : une ligne par PC
    (`noyau.assemblage.fraicheur`) ; `alertes_lecture` : alertes calculées à la lecture de
    `donnees/`, montrées ici et jamais écrites ailleurs. `utilisateur` : nom affiché (« Attend
    <nom> »), vide : « Vous attend ». Sections absentes si vides.
    """
    projets = list(assemblage["cartes"])  # une carte par projet (story 4.8)
    projets.sort(key=lambda p: (p["nom"].casefold(), p["nom"]))
    horodatage = genere.astimezone().strftime("%Y-%m-%d %H:%M")
    lignes = ["# Tableau des projets", "", f"_Généré le {horodatage}._", ""]
    for action in etat.ACTIONS:
        membres = [p for p in projets if p["action"] == action]
        libelle = etat.libelle_action(action, utilisateur)
        lignes.append(f"## {EMOJI[action]} {libelle} ({len(membres)})")
        lignes.append("")
        for p in membres:
            chantier = p["chantier"] or SANS_PHASE
            type_ = f" · type : {p['type']}" if action == etat.ATTEND else ""
            ici = "" if p.get("clone_ici", True) else " · pas cloné ici"
            ici += _origine(p.get("depot_de"))
            lignes.append(
                f"- **{p['nom']}** : {p['raison']['texte']}{type_}{ici} · phase : "
                f"{_phase(depots.get(p['nom']))} · chantier : {chantier}"
            )
        if not membres:
            lignes.append("_aucun_")
        lignes.append("")
    lignes += ["## Chantiers", ""]
    chantiers = list(assemblage.get("chantiers") or [])
    for c in chantiers:
        noms = ", ".join(p["nom"] for p in c["projets"])
        lignes.append(
            f"- **{c['nom']}** : {EMOJI[c['action']]} "
            f"{etat.libelle_action(c['action'], utilisateur)}, "
            f"{c['raison']['texte']} · projets : {noms}"
        )
    if not chantiers:
        lignes.append("_aucun_")
    lignes += ["", "## Dépendances", ""]
    lignes += [f"- {d}" for d in dependances] or ["_aucune_"]
    if fraicheur:
        lignes += ["", "## Fraîcheur des PC", ""]
        lignes += [f"- {f['texte']}" for f in fraicheur]
    if alertes_lecture:
        lignes += ["", "## Alertes de lecture", ""]
        lignes += [f"- {texte_alertes.texte(a)}" for a in alertes_lecture]
    return "\n".join(lignes) + "\n"
