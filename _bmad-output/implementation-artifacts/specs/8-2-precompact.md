---
story: "8.2"
titre: Hook PreCompact et consigne de compaction
status: review
date: 2026-11-14
---

# Story 8.2 : hook `PreCompact` et consigne de compaction

Source : plan `veille-agents-code/synthese/plan-memoire-agents-2026-11-14.md`, étape 3, constat 6
(« une compaction perd le fil ») ; `epics-pilotage-projets.md`, epic 8, story 8.2 (FR42) ; AD-1,
AD-2, AD-7, AD-13 ; NFR1, NFR2 ; stories 2.1 (capture des payloads), 2.7 (fusion de
`settings.json`), 8.1 (note réinjectée par `SessionStart`).

**Risque :** à risque (nouveau point d'entrée exécuté dans toutes les sessions, nouvelle entrée de
`settings.json`). Spec relue avant le code ; revue sur Opus ; `bench_hooks.py` rejoué ;
`tests/test_sync_ps1.py` joué en local (porte de `pilotage/installation/`).

## Ce que dit la doc des hooks (lue le 2026-11-14, page « Hooks reference »)
- Entrée de `PreCompact` : champs communs, `trigger` (`manual` pour `/compact`, `auto` pour la
  compaction automatique ou au repos) et `custom_instructions` (texte passé à `/compact`, `null`
  sinon, toujours `null` en `auto`). `agent_id` : non documenté pour cet événement.
- Sortie : code 0 sans blocage → **le stdout sert d'instructions au résumé de compaction**
  (10 000 caractères au plus). Pas de `hookSpecificOutput.additionalContext` documenté. Code 2 ou
  `"decision": "block"` **bloquent la compaction** (et, en auto de récupération, font échouer la
  requête) : le hook ne doit jamais les produire.
- Compaction d'un sous-agent : non documentée.
- `PostCompact` existe (entrée `trigger`, `compact_summary`) mais ne peut rien rendre.
- `SessionStart` avec `source=compact` existe ; que son `additionalContext` revienne après la
  compaction n'est pas écrit en toutes lettres (le guide des hooks le donne comme cas d'usage).

## Étape 0 : essai réel (avant le code, consigné ici et dans `docs/capture-payloads.md`)
Seulement par `claude -p --model haiku --settings <fichier temporaire>` lancé dans un dossier de
travail temporaire hors dépôt, `PILOTAGE_RACINE_LOCALE` pointé vers un dossier temporaire ; jamais
`~/.claude/settings.json`. Les hooks de l'essai sont de petits scripts de capture (écrivent le
payload brut dans le dossier temporaire), pas les hooks du pilotage.
1. Session A : `claude -p … "réponds OK" --output-format json` → `session_id`.
2. `claude -p … --resume <id> "/compact garde le mot ZEBRE"` : capturer `PreCompact` (champs,
   `trigger`, `custom_instructions`, présence d'`agent_id`), `PostCompact` (`compact_summary`) et
   le `SessionStart` qui suit (`source`).
3. Même essai avec un `PreCompact` qui écrit sur stdout « Mentionne le mot CORMORAN dans le
   résumé » : le mot apparaît-il dans `compact_summary` ? Les deux consignes (utilisateur et hook)
   sont-elles gardées ?
4. Un `SessionStart` qui rend un `additionalContext` contenant « HERON » : après la compaction,
   une question « quel oiseau t'a été donné ? » le retrouve-t-elle ?
5. Sous-agent : non essayé (coûteux et non provoquable de façon fiable) ; garde par `agent_id`
   quand même (AD-2).
Si `/compact` n'est pas accepté en `-p`, le consigner, et s'en tenir à la doc. Si l'essai montre que
le stdout de `PreCompact` n'influe pas sur le résumé, le hook est quand même livré (sans effet
nuisible) et la consigne passe aussi par `SessionStart` `source=compact` (voir Décisions).

Résultat de l'essai (2026-11-14, Claude Code 2.1.325, Windows 11, 4 appels haiku, ~0,01 $) :
`--setting-sources ""` accepté (réglages de l'utilisateur non chargés). Sous Git Bash, `/compact`
est réécrit en `C:/Program Files/Git/compact` : `MSYS_NO_PATHCONV=1` nécessaire.
- `/compact <texte>` accepté en `-p --resume`. Ordre : `SessionStart` `resume`, `PreCompact`,
  `SessionStart` `compact`, `PostCompact`.
- `PreCompact` : `session_id`, `transcript_path`, `cwd`, `prompt_id`, `hook_event_name`,
  `trigger=manual`, `custom_instructions="garde le mot ZEBRE"` ; pas d'`agent_id`. `auto` non
  provoqué.
- Stdout du hook (texte brut) **pris en compte** : CORMORAN et ZEBRE tous deux dans
  `compact_summary`. Accents intacts (« décisions », « résumé ») : `CONSIGNE` reste accentuée.
- `SessionStart` `source=compact` (champs en plus : `prompt_id`, `model`) : `additionalContext`
  HERON retrouvé à la question suivante. Pas de repli par `cycle.py` nécessaire.

## Déjà là (main 8383662)
- `SessionStart` (`hooks/cycle.demarrer`) émet règle, dernière note de reprise (8.1) et messages,
  pour toute `source`, `compact` compris : après une compaction, la note et la règle reviennent
  déjà. L'état du dépôt viendra avec la 8.3.
- Points d'entrée `pilotage/hooks/<événement>.py` sur un même modèle (interrupteur `desactive`
  lu avant tout import du paquet, `_commun.executer`, `SystemExit(0)` toujours).
- `_commun.contexte(payload)` rend `None` pour un sous-agent (`agent_id`) et un dossier non suivi.
- `installation/fusion.py` : `EVENEMENTS` et `controler_modele` exigent exactement les événements
  de `hooks-pilotage.json`, un groupe sans matcher, une entrée exec `-I -S`.

## À livrer
1. **`pilotage/hooks/pre_compact.py`** (nouveau) : même modèle que `session_start.py`
   (`EVENEMENT = "PreCompact"`, interrupteur, `_commun.executer(EVENEMENT, compaction.consigner)`,
   sortie 0 toujours).
2. **`pilotage/hooks/compaction.py`** (nouveau, hooks → noyau et chemins seulement) :
   - `CONSIGNE` : texte fixe, en français, sans aucune donnée de session ni de projet, au plus
     1 500 caractères. Contenu : dans le résumé, garder les décisions prises (et pourquoi), les
     fichiers touchés, la prochaine action, les blocages et ce qui attend l'utilisateur ; ne pas
     recopier les blocs cadrés du pilotage (règle, note, messages), ils reviennent par
     `SessionStart` `source=compact` ; rappeler qu'au prochain
     arrêt la session met à jour sa note de reprise par le marqueur `reprise`.
   - `consigner(payload) -> None` : `ctx = _commun.contexte(payload)` ; `None` (sous-agent, dossier
     non suivi, `cwd` hors racine) → rien. Sinon écrit `CONSIGNE` sur stdout en texte brut UTF-8
     (`_commun.emettre`), une seule fois. Aucun fichier écrit, aucun verrou, aucune synchro, aucun
     état lu ; `trigger` et `custom_instructions` ne sont ni lus ni recopiés (l'essai dira s'ils
     coexistent avec le stdout).
   - Jamais de code 2, jamais de `decision`, jamais de JSON sur stdout (un JSON serait pris pour
     une sortie de contrôle) ; toute erreur journalisée par `_commun.journaliser` (type seul).
3. **`hooks-pilotage.json`** : groupe `PreCompact` (même forme que les autres), placé après `Stop`.
   **`installation/fusion.py`** : `EVENEMENTS` gagne `"PreCompact"` au même rang. Une installation
   antérieure (sans `PreCompact`) est mise à niveau par le rejeu d'`installer-reglages` : entrée
   ajoutée une fois, autres entrées intactes, second passage identique à l'octet.
4. **`outils/bench_hooks.py`** : `"pre_compact": ("PreCompact", {"trigger": "auto",
   "custom_instructions": None})` ; le banc vérifie que seul `SessionStart` émet du JSON et que
   `PreCompact` émet la consigne (adapter le contrôle « tout autre hook reste muet »).
5. **Docs** : `docs/capture-payloads.md` (section `PreCompact`, résultat de l'étape 0) ;
   `docs/messages-session.md` (compaction : consigne avant, règle et note après par
   `SessionStart` `compact`) ; liste des hooks du `README.md` et de la doc d'installation si elle
   en tient une.

## Critères d'acceptation
- **Given** une session principale d'un projet suivi, **When** `PreCompact` arrive avec
  `trigger=manual` ou `trigger=auto`, **Then** stdout porte exactement `CONSIGNE` (texte brut,
  ≤ 1 500 caractères, aucune donnée du payload), code de sortie 0, aucun fichier créé sous
  `PILOTAGE_RACINE_LOCALE`.
- **Given** un payload avec `custom_instructions` hostile (délimiteurs du cadrage, `"><script>`,
  10 000 caractères), **When** le hook s'exécute, **Then** stdout est `CONSIGNE` à l'octet près.
- **Given** un sous-agent (`agent_id`), un dossier non suivi, un `cwd` hors racine, un payload
  invalide ou l'interrupteur `desactive`, **When** `PreCompact` se déclenche, **Then** rien n'est
  émis ni écrit (journal d'erreur seulement pour un payload invalide, comme les autres hooks).
- **Given** une erreur à l'émission, **When** le hook s'exécute, **Then** code 0, erreur
  journalisée sans contenu.
- **Given** `SessionStart` avec `source=compact` après une note laissée, **When** il s'exécute,
  **Then** règle et note sont injectées comme pour `startup` (test de non-régression).
- **Given** `hooks-pilotage.json` et un `settings.json` avec des hooks tiers et une installation
  du pilotage sans `PreCompact`, **When** `installer-reglages` est rejoué deux fois, **Then**
  l'entrée `PreCompact` du pilotage existe une fois, les autres entrées sont intactes, et le
  second passage laisse les mêmes octets (`tests/test_installation.py` ; `test_sync_ps1.py` en
  local avec `PILOTAGE_SYNC_PS1` et `PILOTAGE_EXIGER_SYNC_PS1=1`).
- **Given** `bench_hooks.py`, **When** il rejoue `PreCompact`, **Then** le p95 reste sous 100 ms
  (mesure consignée dans le commit ou la PR).

## Tests
- `tests/test_hooks_compaction.py` (nouveau), par processus `-I -S` comme `test_hooks_session.py` :
  manuel, auto, `custom_instructions` hostile, sous-agent, non suivi, hors racine, payload
  invalide, `desactive`, rien écrit, stdout exact.
- `tests/test_hooks_session.py` : `source=compact` injecte règle et note.
- `tests/test_installation.py` : événements du modèle, mise à niveau d'une installation sans
  `PreCompact`, idempotence à l'octet.
- `tests/test_bench_hooks.py` : `pre_compact` dans les scénarios.
- `tests/test_isolement.py`, `tests/test_imports.py`, `tests/test_publication.py`,
  `tests/test_fixtures_payloads.py` (ajouter une fixture `PreCompact` assainie tirée de l'essai)
  verts.

## Fichiers touchés
`pilotage/hooks/pre_compact.py`, `pilotage/hooks/compaction.py` (nouveaux) ;
`hooks-pilotage.json`, `pilotage/installation/fusion.py` ; `outils/bench_hooks.py` ; docs
ci-dessus ; fixtures et tests ci-dessus. Ni `cycle.py`, ni `noyau/cadrage.py`, ni
`regle-marqueur.md` (8.3 les touche).

## Décisions
- **Consigne par le stdout de `PreCompact`** : c'est la voie documentée pour orienter le résumé ;
  `SessionStart` `compact` ramène déjà règle et note (8.1). Si l'essai montre que le stdout est
  ignoré, la consigne passe par `SessionStart` `source=compact` seulement, comme le dit l'epic,
  dans cette story (`cycle.py` ; la 8.3 vient après, en V2 : pas de conflit).
- **Texte fixe, sans donnée** : un hook de compaction qui recopierait l'état ou la note
  doublerait l'injection de `SessionStart` et ouvrirait un second canal de texte non fiable vers
  le résumé.
- **Jamais bloquant** : un blocage de compaction automatique peut faire échouer la requête ; le
  hook ne connaît ni code 2 ni `decision`.
- **Garde sous-agent** par `agent_id` même si la doc n'en dit rien (AD-2).
- **Version** : pas de tag à cette story ; `v0.6.0` après la 8.3.
- **Script absent** : le code 2 d'un Python qui ne trouve pas son script bloquerait une
  compaction ; d'où la garde d'installation. Un runtime restauré plus ancien que `settings.json`
  reste possible par `sync.ps1` : noté dans la doc d'installation (ordre : runtime d'abord).

## Corrections après relecture Opus (2026-11-14) — priment sur ce qui précède
1. **Ordre exact**, dans `hooks-pilotage.json` comme dans `fusion.EVENEMENTS` :
   `("SessionStart", "UserPromptSubmit", "Stop", "PreCompact", "Notification", "SessionEnd")`.
2. **Tests existants à réaligner** : `tests/test_regle_marqueur.py` (vers la ligne 164,
   `test_seul_session_start_ecrit_sur_stdout` : ajouter le payload `PreCompact`, renommer ; en
   nominal `PreCompact` rend exactement `CONSIGNE`, rien pour un payload invalide ou un
   `agent_id`, tout autre hook reste muet) ; `tests/test_installation.py` vers la ligne 255 (ordre
   des clés) et vers la ligne 276 (`test_fusion_garde_groupe_vide_d_origine` : passer l'événement
   tiers vide sur `PostCompact`).
3. **Essai, isolement** : `--settings` s'ajoute aux réglages de l'utilisateur sans les remplacer ;
   ajouter `--setting-sources ""` (ou `project,local`) si la version l'accepte, sinon le
   consigner et filtrer la capture sur les seuls scripts de l'essai.
4. **Essai, étape 4** : n'émettre HERON que si `source == "compact"`, capturer le `source` de chaque
   `SessionStart` (un `--resume` de plus déclenche un `SessionStart` `resume`).
5. **Essai, accents** : vérifier qu'un mot accentué de la consigne (« décisions ») arrive intact dans
   `compact_summary` sous Windows ; sinon `CONSIGNE` en ASCII.
6. **`CONSIGNE`** : ne commence pas par `{`, ne contient ni délimiteur du cadrage (`PILOTAGE-`), ni
   `## Dernière note de reprise`, ni marqueur `<!-- pilotage:` (test) ; sinon le banc et la
   sortie la prendraient pour un JSON ou un bloc cadré.
7. **Banc** : entrée `pre_compact` placée avant `session_end` dans `HOOKS` (`session_end` clôt les
   sessions).
8. **Fixtures** : ajouter `PreCompact-*.json` assainie à la liste attendue de
   `tests/test_fixtures_payloads.py` (vers la ligne 44) ; `SessionStart-compact-a-confirmer.json`
   garde son nom, le constat va dans `docs/capture-payloads.md`.
9. **`source=compact`** : déjà couvert par `tests/test_hooks_session.py` (vers la ligne 520), à
   garder vert, pas de nouveau test.
10. **Script absent** : Python qui ne trouve pas son script sort avec le code 2, qui bloque une
    compaction. Garde ajoutée si elle n'existe pas : `installer-reglages` refuse d'écrire
    `settings.json` (code non nul, message clair) si un script référencé par le modèle est absent
    du runtime installé ; test. La doc d'installation dit l'ordre : runtime d'abord, réglages
    ensuite.
