"""Validateur de l'état court d'un dépôt sur un PC (story 8.3, AD-10, FR43).

`attente/depots/<projet>/<pc>.json` (et sa copie dans `donnees/`) : `schema` (1), `projet`,
`pc`, `session` (dernière à l'avoir écrit), `ecrit` (ISO Z), `etat` facultatif (`prochaine`
obligatoire, `branche`, `blocages`, `explore`, `a_explorer` facultatifs, bornés par `BORNES`),
`decisions` : les `MAX_DECISIONS` dernières décisions de ce PC (schéma `decision`), la plus
ancienne d'abord. Tout autre champ est refusé.

`filtrer_etat` et `filtrer_decision` rejouent le filtre des champs (`texte.nettoyer_champ`) :
à l'écriture par `Stop`, à la copie par `sync` et à la lecture par `SessionStart`.
"""

from pilotage.noyau import ids, texte
from pilotage.noyau.schemas import decision
from pilotage.noyau.schemas.erreurs import ErreurValidation

SCHEMA = 1
OBLIGATOIRES = frozenset({"schema", "projet", "pc", "session", "ecrit", "decisions"})
CHAMPS = OBLIGATOIRES | {"etat"}
# Points de code, dans l'ordre d'affichage (le même que `marqueur.CHAMPS_ETAT`).
BORNES = {"prochaine": 300, "branche": 100, "blocages": 300, "explore": 300, "a_explorer": 300}
MAX_DECISIONS = 5


def valider(objet: object) -> None:
    """Lève `ErreurValidation` pour un champ inconnu ou manquant, un type ou une forme invalide."""
    if not isinstance(objet, dict):
        raise ErreurValidation("etat_depot : un objet est attendu")
    inconnus = sorted(str(c) for c in objet.keys() - CHAMPS)
    if inconnus:
        raise ErreurValidation(f"etat_depot : champ inconnu : {', '.join(inconnus)}")
    manquants = sorted(OBLIGATOIRES - objet.keys())
    if manquants:
        raise ErreurValidation(f"etat_depot : champ manquant : {', '.join(manquants)}")
    if type(objet["schema"]) is not int or objet["schema"] != SCHEMA:
        raise ErreurValidation(f"etat_depot : schema {SCHEMA} attendu")
    try:
        ids.valider_projet(objet["projet"])
        ids.valider_pc(objet["pc"])
        ids.valider_session(objet["session"])
    except ValueError as exc:  # ErreurId
        raise ErreurValidation(f"etat_depot : {exc}") from None
    decision.horodatage(objet["ecrit"], "ecrit", "etat_depot")
    if "etat" in objet:
        etat = objet["etat"]
        if not isinstance(etat, dict) or "prochaine" not in etat:
            raise ErreurValidation("etat_depot : etat : objet avec `prochaine` attendu")
        inconnus = sorted(str(c) for c in etat.keys() - BORNES.keys())
        if inconnus:
            raise ErreurValidation(f"etat_depot : etat : champ inconnu : {', '.join(inconnus)}")
        for cle, valeur in etat.items():
            decision.champ_texte(valeur, BORNES[cle], f"etat.{cle}", "etat_depot")
    decisions = objet["decisions"]
    if not isinstance(decisions, list) or len(decisions) > MAX_DECISIONS:
        raise ErreurValidation(f"etat_depot : decisions : liste de {MAX_DECISIONS} au plus")
    for ligne in decisions:
        decision.valider(ligne)


def filtrer_etat(etat: object, racine_github: str | None = None) -> dict | None:
    """Champs de l'état refiltrés et bornés (copie) ; champ refusé : supprimé ; `prochaine`
    refusé, ou `etat` qui n'est pas un objet : `None` (état entier ignoré)."""
    if not isinstance(etat, dict):
        return None
    propre = {}
    for cle, borne in BORNES.items():
        if cle in etat:
            valeur = texte.nettoyer_champ(etat[cle], borne, racine_github)
            if valeur:
                propre[cle] = valeur
    return propre if "prochaine" in propre else None


def filtrer_decision(ligne: object, racine_github: str | None = None) -> dict | None:
    """Ligne de décision refiltrée (copie) : `decision` refusée, ou ligne qui n'est pas un
    objet : `None` ; `pourquoi` refusé : supprimé. Les autres champs sont gardés tels quels."""
    if not isinstance(ligne, dict):
        return None
    propre = dict(ligne)
    propre["decision"] = texte.nettoyer_champ(
        ligne.get("decision"), decision.BORNE_DECISION, racine_github
    )
    if not propre["decision"]:
        return None
    if "pourquoi" in ligne:
        pourquoi = texte.nettoyer_champ(ligne["pourquoi"], decision.BORNE_DECISION, racine_github)
        if pourquoi:
            propre["pourquoi"] = pourquoi
        else:
            del propre["pourquoi"]
    return propre
