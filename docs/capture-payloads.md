# Capture des payloads de hooks (story 2.1)

Claude Code 2.1.318, Windows 11. Neuf sessions utiles lancées avec `claude -p --model haiku`
dans un bac à sable hors dépôt. Captures brutes : `%LOCALAPPDATA%\pilotage-projets\capture\`.
Fixtures assainies : `tests/fixtures/payloads/` (voir son `LISEZMOI.md`).

Lecture des états : **confirmé** = observé ; **à confirmer** = reste à trancher par les gestes
interactifs de l'utilisateur (section « À confirmer »).

## Forme exec
Confirmé. Une commande avec `command` = chemin de Python et `args` = `["-I", "-S", "<script>"]`
est acceptée par Claude Code. `-I -S`, `ctypes`, `subprocess` et `json` fonctionnent dans le
hook, sans sortie parasite, code de sortie 0.

## Sous-agents et session principale
| Point | État | Constat |
| --- | --- | --- |
| `agent_id` absent en session principale | confirmé | Aucun payload de la session principale (`SessionStart`, `UserPromptSubmit`, `Stop`, `SessionEnd`, `PreToolUse`) ne porte `agent_id` ni `agent_type`. |
| Événements dans un sous-agent | confirmé | `SubagentStart`, `SubagentStop` et le `PreToolUse` émis par le sous-agent portent `agent_id` et `agent_type`. `SubagentStop` ajoute `agent_transcript_path`, `last_assistant_message`, `background_tasks`. Aucun `SessionStart`, `UserPromptSubmit`, `Stop` ni `SessionEnd` propre au sous-agent. `Notification` dans un sous-agent : non observé. |
| Tour déclenché par un sous-agent | confirmé | À la fin du sous-agent, la session reçoit un `UserPromptSubmit` dont `prompt` commence par `<task-notification>`, sans `agent_id`, puis un second `Stop`. Ce n'est pas une saisie de l'utilisateur : `user_prompt_submit.py` l'ignore. Le `Stop` principal précède `SubagentStop`. |
| `AskUserQuestion` | à confirmer | En `-p`, l'outil n'existe pas : ni `PreToolUse` ni `Notification`. |
| Pid parent et heure de création | confirmé | Le parent du hook est `claude.exe` directement (aucun shell intermédiaire). L'heure de création se lit par `GetProcessTimes` (FILETIME). Le hook et `claude.exe` sont dans un job Windows. |
| `source` de `SessionStart` | partiel | `startup` pour une nouvelle session ; `resume` pour `--resume` et pour `--continue` (indiscernables). `resume` ajoute `seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`, `estimated_cache_write_usd`. `clear` et `compact` : à confirmer. |
| `~/.claude/sessions/` | confirmé | Voir ci-dessous. |

Autres faits : `SessionEnd.reason` vaut `other` en `-p`. `Stop` porte `last_assistant_message`,
`stop_hook_active`, `effort.level`, `permission_mode`, `background_tasks`, `session_crons`,
`prompt_id`. `UserPromptSubmit` porte `prompt` et `permission_mode`. `PreToolUse` porte
`tool_name`, `tool_input`, `tool_use_id`. Tous les payloads : `session_id`, `transcript_path`,
`cwd`, `hook_event_name`.

### `~/.claude/sessions/`
Un fichier `<pid>.json` par session interactive (plus un `<pid>.<sha256>.key`, non lu) ; les
sessions `-p` n'en laissent aucun. Champs : `pid`, `sessionId`, `cwd`, `startedAt` (ms),
`procStart` (FILETIME de création du processus, égal à l'heure de création de `claude.exe`),
`version`, `kind`, `entrypoint`, `name`, `status` (`busy`, `idle`, `shell`), `updatedAt`,
`statusUpdatedAt`, et d'autres champs de messagerie. Une session est vivante si le fichier existe,
que le pid est vivant et que sa date de création égale `procStart` (garde contre la réutilisation
d'un pid). Des fichiers de sessions mortes peuvent subsister (fermeture sans `/exit` : à confirmer).

## Breakaway
Confirmé. Le hook est dans un job Windows. `Popen` avec `DETACHED_PROCESS |
CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB` a réussi 18 fois sur 18, sans accès refusé :
le repli sans breakaway n'a pas servi (il reste à coder et n'est pas exercé). L'enfant (30 s de
sommeil) a survécu à la fin de la session `-p`. À confirmer : survie après fermeture de la fenêtre
du terminal sans `/exit`.

## Champs de `Notification`
À confirmer. Aucun `Notification` en `-p`, même pour un outil refusé (seul le `PreToolUse` part).
`notification_type`, `message`, `title` ne sont pas observés. Les fixtures `Notification-*-a-confirmer`
donnent une forme supposée d'après la documentation de Claude Code.

## À confirmer par les gestes de l'utilisateur
1. `AskUserQuestion` : `Notification` ou `PreToolUse` ? Type et texte de la question.
2. Permission native : `notification_type` (`permission_prompt` attendu), `message`, `title`.
3. `source` de `SessionStart` après `/clear` et après `/compact`.
4. `reason` de `SessionEnd` après `/exit` (`prompt_input_exit` attendu) et après `/clear`.
5. Fermeture de fenêtre sans `/exit` : l'enfant breakaway survit-il, le fichier de
   `~/.claude/sessions/` reste-t-il ?

Une fois ces points tranchés, renommer les fixtures concernées (retirer `-a-confirmer` et
`_statut`) et mettre à jour la section « Champs de `Notification` ».

## Vérification de clôture
- Le hook d'enregistrement n'a jamais été posé dans `~/.claude/settings.json` : il n'a existé que
  dans le `settings.local.json` du bac à sable. Contrôlé le 2026-11-06 :
  `grep -cE "capture|payload|pilotage" ~/.claude/settings.json` renvoie `0`. Rien à retirer de la
  config globale.
- Report pour l'utilisateur, non fait à la clôture de la story (les payloads bruts existent encore) :
- [ ] L'utilisateur a joué les gestes, puis supprimé `%LOCALAPPDATA%\pilotage-projets\capture\` (payloads
  bruts, qui contiennent de vrais prompts) et le bac à sable
  `{{RACINE_GITHUB}}\_sandbox\capture-payloads`.
