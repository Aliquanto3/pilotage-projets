# Fixtures de payloads de hooks

Payloads Claude Code 2.1.318 (Windows 11), assainis : aucun texte réel, identifiants factices,
chemins en jetons (`{{RACINE_GITHUB}}`, `{{HOME}}`, `{{SLUG_PROJET}}`). Compte rendu :
`docs/capture-payloads.md`. Nom : `<evenement>-<cas>.json`.

## Fixtures observées
Capturées par un vrai Claude Code (`claude -p`), puis assainies. Aucun marquage.

## Fixtures « à confirmer »
Cas non observés, construits sur la forme des payloads réels (champs communs `session_id`,
`transcript_path`, `cwd`, `hook_event_name`) et sur la documentation de Claude Code. Deux
marques, toutes deux obligatoires (vérifiées par `tests/test_fixtures_payloads.py`) :
- le nom se termine par `-a-confirmer.json` ;
- le JSON contient `"_statut": "a_confirmer"`.

| Fixture | Consommée par | À trancher par les gestes de l'utilisateur |
| --- | --- | --- |
| `Notification-permission-a-confirmer.json` | stories 2.4, 5.3 | champs `message`, `title`, `notification_type` |
| `Notification-askuserquestion-a-confirmer.json` | stories 2.4, 2.5, 5.3 | `Notification` ou `PreToolUse` ; type et texte. `notification_type: elicitation_dialog` est inventé, rien ne l'atteste |
| `SessionStart-clear-a-confirmer.json` | story 2.5 | `source` vaut-il `clear` |
| `SessionStart-compact-a-confirmer.json` | story 2.5 | `source` vaut-il `compact` |

Une fois confirmée, la fixture perd son suffixe et son champ `_statut`.

## Garde contre les données personnelles
`tests/test_fixtures_payloads.py` scanne tous les fichiers du dossier (seuls des `.json` sont
admis, hors ce `LISEZMOI.md`) :
- motifs génériques de chemins personnels, actifs partout, CI comprise : lecteur suivi de
  `Users` (`C:\Users`, `D:/Users`), forme Git Bash (`/c/Users`), segment `\Users\`, slug `C--Users` ;
- `USERNAME`, `USER` et `COMPUTERNAME` de la machine : garde locale seulement (en CI, ces variables
  désignent le runner). Le vrai nom n'est écrit nulle part dans le dépôt, ni en clair ni haché (un
  prénom haché se retrouve par dictionnaire) : relancer ce test en local avant d'ajouter une fixture ;
- aucun caractère de contrôle dans les chaînes (un `\f` mal échappé dans un chemin Windows devient
  un saut de page).
