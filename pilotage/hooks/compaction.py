"""Consigne de compaction (story 8.2, FR42) : texte fixe écrit par `PreCompact` sur stdout.

Claude Code prend le stdout d'un `PreCompact` sorti avec 0 comme instructions du résumé de
compaction (essai du 2026-11-14 : la consigne du hook et celle de `/compact` sont gardées toutes
les deux). Le texte est fixe : aucune donnée de session, de projet ni du payload (ni `trigger` ni
`custom_instructions`), pour ne pas ouvrir un second canal de texte vers le résumé. Règle, note
de reprise, état du dépôt (story 8.3) et messages reviennent après la compaction par
`SessionStart` `source=compact`.

Jamais de code 2, de `decision` ni de JSON : un blocage ferait échouer une compaction automatique.
"""

from pilotage.hooks import _commun

CONSIGNE = (
    "Consigne du pilotage des projets pour ce résumé de compaction :\n"
    "- garde les décisions prises et leur raison ;\n"
    "- garde la liste des fichiers créés, modifiés ou supprimés ;\n"
    "- garde la prochaine action prévue ;\n"
    "- garde les blocages en cours et ce qui attend l'utilisateur ;\n"
    "- ne recopie pas les blocs ajoutés par le pilotage (règle du marqueur, note de reprise, "
    "état du dépôt, messages) : ils reviennent d'eux-mêmes après la compaction ;\n"
    "- au prochain arrêt, la session met à jour sa note de reprise par le marqueur `reprise`, "
    "et l'état du dépôt par son marqueur s'il a changé.\n"
)
BORNE_CONSIGNE = 1500  # caractères


def consigner(payload: dict) -> None:
    """Écrit `CONSIGNE` sur stdout pour une session principale d'un dossier suivi, sinon rien."""
    if _commun.contexte(payload) is None:
        return
    _commun.emettre(CONSIGNE.encode("utf-8"))
