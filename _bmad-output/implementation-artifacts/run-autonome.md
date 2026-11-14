# Run autonome : pilotage-projets, epics 8 et 9 (`v0.6.0`, `v0.7.0`)

Fichier d'état de l'orchestrateur, à relire en premier après chaque `/clear`. Lu par `/agent-cost-kit:avancement-run`. Run précédent (stories 4.7 à 5.6, terminé le 2026-11-11) : archive privée du projet, hors de ce dépôt. Ce dépôt est **public** : ce fichier ne porte ni chemin absolu, ni prénom, ni coût, ni détail du dépôt de données (`tests/test_publication.py` en garde une partie).

- **Planification** (hors dépôt, dossier `_bmad-output/` partagé de la racine GitHub) : `planning-artifacts/epics-pilotage-projets.md`, epics 8 (reprise du fil) et 9 (rapport de la semaine) ; architecture `ARCHITECTURE-SPINE.md` ; UX `ux-designs/ux-pilotage-projets-2026-11-05/`. Origine : plan `veille-agents-code/synthese/plan-memoire-agents-2026-11-14.md`, étapes 3 et 4.
- **Suivi** : `sprint-status.yaml`, à côté de ce fichier. Specs : `specs/`. Second avis : `reprise/second-avis-<id>.md`. Décisions à confirmer : `decisions-a-confirmer.md`, à côté de ce fichier.
- **Worktrees** : `../_worktrees/pilotage-<id>`, branches `story/<id>`.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 8 à 9 | 8.2, 8.3 (8.1 déjà fusionnée), 9.1 à 9.4 |
| Hors run | Epic 6 | 6.1 à 6.5 dépendent de l'utilisateur (étiquetage, banc, 50 sessions, recette) |

Au plus 2 stories en développement à la fois, chacune dans son worktree.
Plafond : 2 agents actifs à la fois dans ce run (un second run tourne sur le même PC, dans `librarian-bench`).

## Règles

- Types : `dev` (dev-story → second-avis → reviewer → intégration), `mixte` (code par l'agent, puis « attente humaine »), `humaine` (jamais confiée à un agent). ★ = story pivot, dev-story sur Opus.
- Chaîne par story : `agent-cost-kit:dev-story` (Sonnet ; Opus pour 8.2, 8.3, 9.2 et 9.4, à risque) → `agent-cost-kit:second-avis` → `agent-cost-kit:reviewer` (Opus, rebasé d'abord, avec la liste du second avis et l'état de la CI de la branche) → PR, CI verte sur les trois OS, fusion. Appels bloquants, jamais en arrière-plan.
- **Stories à risque (8.2, 8.3, 9.2, 9.4)** : l'orchestrateur écrit la spec dans `specs/` d'après l'epic et le code ; un sous-agent Opus indépendant, en lecture seule, la relit avant le code (décision du 2026-11-14). Les points de sécurité, de protocole ou de publication vont dans `decisions-a-confirmer.md` ; la story se développe, mais sa fusion attend la validation de l'utilisateur (`attente humaine` au journal) et le run avance sur le reste.
- **Stories non à risque (9.1, 9.3)** : dev-story directement sur l'entrée de l'epic (petite story bien décrite).
- 9.4 change un écran : vérification `verif-front` après dev-story, correction seulement sur un FAIL de la spec.
- Deux stories du même écran ou du même fichier partagé ne vont jamais dans la même vague (8.2 et 8.3 : même injection, même `regle-marqueur.md`).
- Fichiers d'état du run (ce fichier, sprint status, décisions) : jamais dans une PR de story, seulement par une PR `chore/etat-run-*`. Fusion des PR par `scripts/file_prs.py` du kit ; journaliser `fusion` seulement après avoir vérifié `MERGED`. Avant de fusionner, vérifier que les contrôles existent.
- Suite complète : par la CI de branche ; en local, ruff et tests ciblés. Attente : `gh run watch <id> --interval 60 --exit-status`. Toute CI rouge va au journal, même corrigée dans la foulée.
- **Avant chaque push** : `uv run pytest -q tests/test_publication.py` vert. `tests/test_sync_ps1.py` joué en local pour toute story qui touche `pilotage/installation/` (8.2).
- Tests par `PILOTAGE_RACINE_LOCALE`, jamais dans les vrais dossiers ; dans chaque prompt d'agent : jamais de vrai `sync`, de planificateur, de `claude` (sauf l'essai de 8.2 ci-dessous) ni de `~/.claude`.
- **Essai réel de `PreCompact` (8.2)** : seulement par `claude -p --settings <fichier temporaire>` lancé dans un dossier de travail temporaire, avec `PILOTAGE_RACINE_LOCALE` pointé vers un dossier temporaire. Résultat (ce que `PreCompact` peut rendre, `trigger`, sous-agent) consigné dans la spec de 8.2.
- Versions : `v0.6.0` après la fusion de 8.3 (fin de l'epic 8), `v0.7.0` après 9.4, toujours tagué après `v0.6.0`. Release seulement après une CI verte de `main` sur le commit tagué. Manifeste `VERSION`, tag annoté, release avec notes, puis runtime publié dans le dépôt de configuration (`outils/publier_config.py`).
- `git worktree prune` avant chaque lancement ; worktrees supprimés en fin de run seulement (`scripts/menage_run.py` en simulation, puis `--appliquer` ; branches distantes seulement avec `--distant`, liste montrée à l'utilisateur).
- Heure du journal prise par `date`. `uv run python` sous Windows.

## Autorisations de l'utilisateur (2026-11-14)

- Pousser les branches `story/*` et `chore/etat-run-*` sur ce dépôt public, ouvrir les PR, les fusionner après CI verte et revue.
- Tags et releases `v0.6.0` et `v0.7.0` ; publication du runtime dans le dépôt de configuration.
- **Interdit** : `sync.ps1 restaurer` ou `installer-reglages` sur ce PC, toucher `~/.claude/settings.json`, `portfolio.json` ou le topic `ai-portfolio`. L'activation des nouveaux hooks sur ce PC est faite par l'utilisateur après la release.
- Une décision qui touche la sécurité ou un AD [ADOPTED] attend son accord (`attente humaine`).

## Sessions autorisées à modifier le périmètre

- (aucune)

## Contrats partagés en cours

- Plafond de tout `additionalContext` : 10 000 unités UTF-16, priorité règle, note, état du dépôt, messages (FR41, posé par 8.1).
- Dossier des rapports : `rapports/` de la racine installée, nom `semaine-AAAA-Www.html` (FR45) ; jamais copié par `sync`.

## Brief

- **Tâche du run** : étapes 3 et 4 du plan mémoire du 2026-11-14 : finir l'epic 8 (8.2 `PreCompact`, 8.3 état par dépôt et journal de décisions) et livrer l'epic 9 (rapport de la semaine sans appel de modèle), `v0.6.0` puis `v0.7.0`.
- **Intention courante** : démarrage ; PR `chore/etat-run-sprint7` d'abord (voir Préalable).
- **Plan des vagues restantes** : V1 à V3 ci-dessous.
- **Artefacts utiles** : `pilotage/hooks/cycle.py` (`injecter`), `noyau/cadrage.py`, `noyau/texte.py`, `pilotage/sync/cycle.py` (`ETAPES`), `pilotage/serveur/routes.py` (`_declencheur`), spec `specs/8-1-note-reinjectee.md`.
- **Pièges rencontrés** : (aucun pour l'instant)

## Préalable — PR `chore/etat-run-sprint7`

Avant V1 : une PR qui commite `.gitignore` (lignes `verif-front` déjà écrites, plus `/_bmad/` et `/.claude/skills/`), `.claude/cost-kit/`, `.claude/agents/verif-front.md`, les specs `6-4-recette-appli.md` et `8-1-note-reinjectee.md`, ce fichier, `decisions-a-confirmer.md` et le sprint status. `tests/test_publication.py` vert avant le push ; `_bmad/` et `.claude/skills/` restent hors du dépôt (ils portent le prénom de l'utilisateur).

## Sprint 7 — Reprise du fil et rapport de la semaine, `v0.6.0` puis `v0.7.0`

| Vague | Stories en parallèle | Après | Fichiers ou écrans touchés |
|---|---|---|---|
| V1 | 8.2 · 9.1 | 8.2 ← 8.1 | 8.2 `pilotage/hooks/`, `hooks-pilotage.json`, `pilotage/installation/`, `outils/bench_hooks.py` ; 9.1 `pilotage/rapport/semaine.py`, `pilotage/rapport/lecture.py` |
| V2 | 8.3 · 9.2 | 8.3 ← 8.2 ; 9.2 ← 9.1 | 8.3 `pilotage/hooks/cycle.py`, `regle-marqueur.md`, `noyau/cadrage.py` ; 9.2 `pilotage/rapport/page.py`, `pilotage/rapport/cli.py`, `lancer.py` |
| V3 | 9.3 · 9.4 | 9.3 ← 9.2 ; 9.4 ← 9.2 ; 9.4 ← 8.3 | 9.3 `pilotage/sync/cycle.py` ; 9.4 `pilotage/serveur/routes.py`, `pilotage/web/app.js`, `pilotage/web/appli.css` (barre du haut) |

`v0.6.0` est tagué dès la fusion de 8.3 ; `v0.7.0` après 9.4.

## Journal

Une ligne par étape : `- AAAA-MM-JJ HH:MM · story · étape · résultat · commit`. Étapes : `dev` (« lancé », puis « fini »), `second-avis`, `review`, `PR`, `fusion` (MERGED vérifié), `CI` (« rouge » si échec), `blocked`, `attente humaine`, `décision`, `report`, `clôture`, `ménage`.

- 2026-11-14 18:47 · run · décision · cadrage du run (epics 8 et 9) ; autorisations de l'utilisateur du 2026-11-14 · —
- 2026-11-14 19:03 · run · PR · préalable chore/etat-run-sprint7 ouverte · —
