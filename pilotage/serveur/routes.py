"""Table fermée des routes `/api/` du serveur local (contrat C4, AD-14).

Seul module où l'on déclare une route. Toute requête passe d'abord par
`appli.verifier_requete` (Host, Origin, jeton, puis routage) : une route ajoutée ici hérite
des contrôles sans rien faire de plus. Une route d'AD-14 sans gestionnaire n'est pas encore
livrée : elle rend 404 par le même chemin que les routes inconnues.

Aucune route `/api/` n'est servie sans jeton, lectures comprises (L9) : c'est ce qui permet
d'accepter une requête sans en-tête `Origin`.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pilotage.noyau import ids


@dataclass(frozen=True)
class Reponse:
    """Réponse d'un gestionnaire `/api/`, mise en forme par `appli.envoyer_api`."""

    statut: int
    donnees: object = None
    erreur: str | None = None
    entetes: tuple[tuple[str, str], ...] = ()
    # Corps texte brut (brief, M11) : servi en `text/plain; charset=utf-8` au lieu du JSON.
    texte: str | None = None


# Un gestionnaire reçoit les paramètres du motif (`<id>` → valeur décodée, non validée : à
# valider selon AD-9 par le gestionnaire) et le corps brut de la requête.
Gestionnaire = Callable[[dict[str, str], bytes], Reponse]


@dataclass(frozen=True)
class Route:
    """Une ligne de la table : méthode, motif `/api/...` (`<nom>` = un segment), gestionnaire."""

    methode: str
    motif: str
    gestionnaire: Gestionnaire | None = None
    # (nom du paramètre, validateur AD-9) : un identifiant refusé rend 400 avant le gestionnaire.
    validateurs: tuple[tuple[str, Callable[[object], str]], ...] = ()

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.motif.strip("/").split("/"))

    def correspond(self, segments: list[str]) -> dict[str, str] | None:
        """Paramètres du motif si `segments` (chemin décodé) lui correspond, sinon `None`."""
        modele = self.segments
        if len(modele) != len(segments):
            return None
        parametres: dict[str, str] = {}
        for attendu, recu in zip(modele, segments, strict=True):
            if attendu.startswith("<") and attendu.endswith(">"):
                if not recu:
                    return None
                parametres[attendu[1:-1]] = recu
            elif attendu != recu:
                return None
        return parametres


def valider_parametres(route: Route, parametres: dict[str, str]) -> Reponse | None:
    """400 si un `<id>` ou `<projet>` du chemin n'est pas valide selon AD-9 (`noyau.ids`)."""
    for nom, valider in route.validateurs:
        try:
            valider(parametres.get(nom))
        except ids.ErreurId:
            return Reponse(400, erreur=f"{nom} invalide")
    return None


def _gestionnaire_etat(parametres: dict[str, str], corps: bytes) -> Reponse:
    from pilotage.serveur import etat  # import tardif : etat importe routes (cycle)

    return etat.etat(parametres, corps)


def _tardif(module: str, nom: str) -> Gestionnaire:
    """Gestionnaire `pilotage.serveur.<module>.<nom>`, importé à l'appel (ces modules importent
    `routes`)."""

    def gestionnaire(parametres: dict[str, str], corps: bytes) -> Reponse:
        import importlib

        return getattr(importlib.import_module(f"pilotage.serveur.{module}"), nom)(
            parametres, corps
        )

    return gestionnaire


def _declencheur(type_: str) -> Gestionnaire:
    def gestionnaire(parametres: dict[str, str], corps: bytes) -> Reponse:
        del parametres, corps
        from pilotage import chemins
        from pilotage.serveur import enfants  # import tardif : même raison qu'`etat`

        try:
            issue = enfants.lancer(type_)
        except chemins.ErreurConfiguration as exc:  # cause lisible : l'utilisateur doit corriger
            return Reponse(500, erreur=f"lancement impossible : {exc}")
        except Exception:  # noqa: BLE001 - Popen, config ou fil : réponse propre, sans trace
            return Reponse(500, erreur="lancement impossible")
        if issue == "lance":
            return Reponse(202, donnees={"type": type_, "etat": "lance"})
        return Reponse(
            409, donnees={"type": type_, "etat": "deja_en_cours"}, erreur="déjà en cours"
        )

    return gestionnaire


# Liste fermée d'AD-14. Les stories 4.3, 5.2 et 5.4 posent leur gestionnaire ici.
TABLE: tuple[Route, ...] = (
    Route("GET", "/api/etat", _gestionnaire_etat),
    Route("GET", "/api/brief/<id>", _tardif("reprise", "brief"), (("id", ids.valider_id),)),
    Route(
        "GET", "/api/sessions/<projet>", _tardif("reprise", "sessions"),
        (("projet", ids.valider_projet),),
    ),
    Route("GET", "/api/operations", _tardif("suivi", "operations")),
    Route("POST", "/api/scan", _declencheur("scan")),
    Route("POST", "/api/sync", _declencheur("sync")),
    Route("POST", "/api/reprise", _tardif("reprise", "reprise")),
    Route("POST", "/api/message", _tardif("mutations", "message")),
    Route("POST", "/api/projets", _tardif("mutations", "projets")),
)


def router(
    table: tuple[Route, ...], methode: str, segments: list[str]
) -> tuple[Route | None, dict[str, str], tuple[str, ...]]:
    """Route livrée pour `methode` et `segments`, ses paramètres, et les méthodes permises.

    `(route, paramètres, ())` si trouvée ; `(None, {}, méthodes)` si le chemin existe pour
    d'autres méthodes (405) ; `(None, {}, ())` si le chemin est inconnu ou pas encore livré (404).
    """
    permises: set[str] = set()
    for route in table:
        if route.gestionnaire is None:
            continue
        parametres = route.correspond(segments)
        if parametres is None:
            continue
        if route.methode == methode:
            return route, parametres, ()
        permises.add(route.methode)
    return None, {}, tuple(sorted(permises))
