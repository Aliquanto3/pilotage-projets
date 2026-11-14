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
- 2026-11-14 19:06 · 9.1 · dev · lancé (Sonnet, worktree pilotage-9-1) · —
- 2026-11-14 19:06 · 8.2 · décision · spec écrite (`specs/8-2-precompact.md`) d'après la doc des hooks ; relecture Opus lancée · —
- 2026-11-14 19:09 · 8.2 · décision · relecture Opus de la spec : 2 bloquants et 8 corrections intégrés (ordre des événements, tests à réaligner, isolement de l'essai, garde du script absent) · —
- 2026-11-14 19:09 · 8.2 · dev · lancé (Opus, worktree pilotage-8-2) · —
- 2026-11-14 19:14 · run · fusion · préalable chore/etat-run-sprint7 (#11) MERGED · 12e096d
- 2026-11-14 19:17 · 9.1 · dev · fini, poussé (CI de branche lancée) · 285524a
- 2026-11-14 19:18 · 9.1 · PR · #12 en brouillon (CI de branche) ; second avis lancé · 285524a
- 2026-11-14 19:21 · 8.2 · dev · fini (Opus) ; essai réel : stdout de PreCompact pris dans le résumé, SessionStart compact réinjecté ; rebasé, PR #13 en brouillon ; second avis lancé · 493383d
- 2026-11-14 19:21 · 9.1 · second-avis · 8 constats (5 medium, 3 low), `reprise/second-avis-9.1.md` · 285524a
- 2026-11-14 19:21 · 9.1 · décision · arête `rapport → scan` admise (lecture des faits, comme `sync → scan`), la revue la vérifie ; reviewer Opus lancé · 285524a
- 2026-11-14 19:25 · 8.2 · second-avis · 4 low, aucun Important, `reprise/second-avis-8.2.md` ; reviewer Opus lancé · 493383d
- 2026-11-14 19:39 · 9.1 · review · passe 1 : 1 Important corrigé (fuseau aux changements d'heure), 4 nits, 3 rejetés ; `reprise/revue-9.1.md` · 2517f4d
- 2026-11-14 19:39 · 9.1 · CI · verte (Windows) · 2517f4d
- 2026-11-14 19:39 · 9.1 · fusion · #12 MERGED · 5528e42
- 2026-11-14 19:41 · 9.2 · décision · spec écrite (`specs/9-2-page-rapport.md`) ; emplacement des rapports à confirmer (`decisions-a-confirmer.md`), la story se développe, sa fusion attend · —
- 2026-11-14 19:41 · 8.2 · review · passe 1 : aucun Important, 2 nits corrigés (doc d'installation, chemin générique), 1 documenté, 1 rejeté ; `reprise/revue-8.2.md` · d3216b4
- 2026-11-14 19:41 · 8.2 · CI · verte · d3216b4
- 2026-11-14 19:41 · 8.2 · décision · bench à vide : session_start p95 98,0 ms, pre_compact 48,2 ms (marge faible pour 8.3) ; fusion sans attente humaine (consigne fixe voulue par l'epic, aucun point de sécurité nouveau) · d3216b4
- 2026-11-14 19:42 · 8.2 · fusion · #13 MERGED · f61ddb2
- 2026-11-14 19:44 · 9.2 · décision · relecture Opus de la spec : 2 bloquants (clé de config inexistante, écart à FR45 confirmé et recommandé), 10 corrections intégrées · —
- 2026-11-14 19:44 · 8.3 · décision · spec écrite (`specs/8-3-etat-depot.md`) : état et décisions par marqueur, écrits par `Stop` hors dépôt ; proposition précisée dans `decisions-a-confirmer.md` ; relecture Opus lancée · —
- 2026-11-14 19:45 · 9.2 · dev · lancé (Opus, worktree pilotage-9-2) · —
- 2026-11-14 19:47 · 8.3 · décision · relecture Opus de la spec : 3 bloquants (projet de Stop, concurrence, chemins) et 11 corrections intégrées ; granularité et péremption ajoutées à `decisions-a-confirmer.md` · —
- 2026-11-14 19:47 · 8.3 · dev · lancé (Opus, worktree pilotage-8-3) · —
- 2026-11-14 19:54 · 9.2 · dev · fini (Opus) ; spec retirée du commit de story (fichier d'état), PR #14 en brouillon ; second avis lancé · 83a26b5
- 2026-11-14 19:56 · 9.2 · second-avis · 3 medium, 3 low, `reprise/second-avis-9.2.md` ; reviewer Opus lancé · 83a26b5
- 2026-11-14 20:09 · 9.2 · review · passe 1 : 3 Important corrigés (OverflowError, filet d'erreur sans traceback, `--semaine ""`), 1 nit corrigé, 2 rejetés ; `reprise/revue-9.2.md` · fb168c7
- 2026-11-14 20:09 · 9.2 · CI · verte · fb168c7
- 2026-11-14 20:09 · 9.2 · attente humaine · fusion suspendue à la décision sur l'emplacement des rapports ; V3 empilée sur `story/9-2` · fb168c7
- 2026-11-14 20:11 · 9.2 · review · passe 2 : aucun Important, 2 nits notés · fb168c7
- 2026-11-14 20:11 · 9.3 · dev · lancé (Sonnet, worktree pilotage-9-3, empilée sur story/9-2) · —
- 2026-11-14 20:12 · 9.4 · décision · spec écrite (`specs/9-4-rapport-appli.md`) ; relecture Opus après libération d'un agent (plafond de 2) · —
- 2026-11-14 20:19 · 9.3 · dev · fini (Sonnet) ; code d'alerte `rapport-non-genere` (le schéma refuse `_`) accepté ; PR en brouillon empilée sur #14 ; second avis lancé · 458f9a2
- 2026-11-14 20:23 · 9.3 · second-avis · 5 low, aucun Important, `reprise/second-avis-9.3.md` ; reviewer Opus lancé · 458f9a2
- 2026-11-14 20:23 · 8.3 · dev · fini (Opus) ; spec retirée de la branche ; banc chargé : session_start p95 112 ms (base 102), stop 96 ms (base 77) ; 2 décisions ajoutées (budget, messages repoussés) ; PR #16 en brouillon ; second avis lancé · 74a0639
- 2026-11-14 20:27 · 8.3 · second-avis · 3 medium, 4 low, `reprise/second-avis-8.3.md` ; reviewer Opus lancé · 74a0639
- 2026-11-14 20:40 · 9.3 · review · passe 1 : 1 Important corrigé (rétention séparée, reprise à chaque cycle), 4 nits rejetés, 1 documenté ; `reprise/revue-9.3.md` · c4c5c32
- 2026-11-14 20:40 · 9.3 · CI · verte · c4c5c32
- 2026-11-14 20:40 · 9.4 · décision · relecture Opus de la spec lancée ; passe 2 de 9.3 ensuite (plafond de 2 agents) · —
- 2026-11-14 20:43 · 9.4 · décision · relecture Opus de la spec : 3 bloquants (refus du corps et du paramètre, erreurs sans journal, tests du front à créer) et 11 corrections intégrées · —
- 2026-11-14 20:43 · 9.4 · dev · lancé (Opus, worktree pilotage-9-4, empilée sur story/9-3) · —
- 2026-11-14 20:50 · 9.4 · dev · fini (Opus) ; refus global du paramètre de requête sur /api/ ; PR en brouillon empilée sur #15 ; second avis lancé · 62ecbc6
- 2026-11-14 20:50 · 9.4 · report · verif-front non joué : aucun serveur Playwright sur ce poste ; vérification de l'écran reportée à la recette de l'utilisateur · 62ecbc6
- 2026-11-14 20:50 · 8.3 · review · passe 1 : 3 Important corrigés (chemins absolus partout, date propre à l'état, banc rétabli en contrôle exact), 3 nits corrigés, 1 rejeté ; `reprise/revue-8.3.md` ; passe 2 lancée · 4b473aa
- 2026-11-14 20:50 · 8.3 · CI · verte · 4b473aa
- 2026-11-14 20:53 · 9.4 · second-avis · 5 low, aucun Important, `reprise/second-avis-9.4.md` ; reviewer Opus lancé (avec la passe 2 de 9.3) · 62ecbc6
- 2026-11-14 20:56 · 8.3 · review · passe 2 : aucun Important, 4 nits reportés (UNC `//`, chemin collé à certains signes, décision seule qui masque un état d'un autre PC, ancienne version qui ignore `etat_ecrit`), 1 rejeté · 4b473aa
- 2026-11-14 20:56 · 8.3 · attente humaine · fusion suspendue aux décisions de `decisions-a-confirmer.md` (emplacement, granularité, budget, messages, filtre des chemins) ; banc à vide à rejouer · 4b473aa
