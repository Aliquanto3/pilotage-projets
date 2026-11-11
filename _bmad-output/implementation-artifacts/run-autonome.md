# Run autonome : pilotage-projets, reprise à la story 4.7

Suite publique du run du 2026-11-06 au 2026-11-10. Son journal, ses specs (1.1 à 7.3) et ses
reports sont dans l'archive privée du projet, hors de ce dépôt. Ce dépôt est **public** : ce
fichier ne porte ni chemin absolu, ni prénom, ni coût, ni détail du dépôt de données
(`tests/test_publication.py` en garde une partie).

- **Planification** (hors dépôt, dossier `_bmad-output/` partagé de la racine GitHub) :
  `planning-artifacts/epics-pilotage-projets.md`, architecture `ARCHITECTURE-SPINE.md`,
  UX `ux-designs/ux-pilotage-projets-2026-11-05/` (`DESIGN.md`, `EXPERIENCE.md`), sprint-change-proposal du 2026-11-07.
- **Suivi** : `sprint-status.yaml`, à côté de ce fichier. Specs : `specs/`. Second avis : `reprise/second-avis-<id>.md`.
- **Worktrees** : `../_worktrees/pilotage-<id>`, branches `story/<id>`.

Relire ce fichier après chaque `/clear`.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 4 à 5 | Stories 4.7, 5.5, 5.6 (V17 à V19). |
| Hors run | Epic 6 | 6.1 à 6.5 dépendent de l'utilisateur (étiquetage, banc, 50 sessions, recette). |

Au plus 1 story en développement à la fois (les trois stories touchent le tiroir).

## Règles

- Chaîne par story : `agent-cost-kit:dev-story` → `agent-cost-kit:second-avis` → `agent-cost-kit:reviewer` (Opus, rebase d'abord) → PR, CI verte, fusion. Appels bloquants.
- Stories du même écran : jamais dans la même vague. Fichiers d'état : seulement par une PR `chore/etat-run-*`, jamais dans une PR de story.
- Suite complète : par la CI de branche ; en local, ruff et tests ciblés. Attente : `gh run watch <id> --interval 60 --exit-status`. Après fusion, vérifier `MERGED` avant de journaliser.
- **Avant chaque push** : `uv run pytest -q tests/test_publication.py` vert (le dépôt est public).
- Versions : `v0.4.0` après la fusion de 4.7 et du correctif r-cle (fin de l'epic 4), `v0.5.0` à 5.6, `v1.0.0` à 6.5 (décision du 2026-11-11 : `v0.3.0` a servi à la bascule publique). Manifeste, tag annoté, release avec notes.
- Heure du journal prise par `date`. `uv run python` sous Windows. Tests par `PILOTAGE_RACINE_LOCALE`, jamais dans les vrais dossiers ; dans chaque prompt d'agent : jamais de vrai sync, planificateur, `claude` ni `~/.claude`.

## Autorisations de l'utilisateur (2026-11-11 09:28)

- Pousser les branches `story/*` et `chore/etat-run-*` sur ce dépôt public, ouvrir les PR, les fusionner après CI verte et revue.
- **Interdit** : `sync.ps1 restaurer` ou `installer-reglages` sur ce PC, toucher `~/.claude/settings.json`, `portfolio.json` ou le topic `ai-portfolio`.
- Une décision qui touche la sécurité ou un AD [ADOPTED] attend son accord (`attente humaine`).

## Sprint 6 — Tiroir, reprise et boîte aux lettres, `v0.4.0` puis `v0.5.0`

| Vague | Stories en parallèle | Après |
|---|---|---|
| V16 | recette de l'accueil (humaine) | 4.5, 4.6, 4.10, 4.11 |
| V17 | 4.7 | 4.7 ← V16 |
| V17b | r-cle | r-cle ← 4.7 (même `app.js`) ; tag `v0.4.0` après r-cle |
| V18 | 5.5 | 5.5 ← 4.7 ; 5.5 ← 5.4 |
| V19 | 5.6 | 5.6 ← 5.5 ; 5.6 ← 5.2 |

Reports à traiter dans 4.7 (venus de 4.5 et 4.11) : brancher le bouton du nom des cartes
(aujourd'hui `aria-disabled`) ; noms des lignes Rien à faire et Tourne en bouton ; annonce d'une
hausse d'Attend pendant l'onglet Chantiers, à décider dans `app.js` ; étiquettes sur les cartes
Attend. Report vers 5.6 : confirmer le champ `message_en_attente`, lu en provisoire par 4.11.

## Rapport de fin du 2026-11-11

Run terminé : V16 à V19 faites, plus le correctif r-cle (V17b). Aucun agent en cours.

- **Fusionné** : 4.7 (#3), r-cle (#4), 5.5 (#6), 5.6 (#7) ; PR d'état #2 et #5. CI de `main` verte après chaque fusion.
- **Versions** : `v0.4.0` (fin de l'epic 4) et `v0.5.0` (fin de l'epic 5), tags annotés et releases ; runtime publié dans le dépôt de configuration (v0.4.0 puis v0.5.0).
- **Décisions de sécurité** : AD-14 amendé (clé gardée le temps d'un rechargement, accord de l'utilisateur) ; risque résiduel nommé (restauration d'un onglet fermé).
- **Ménage** : worktrees et branches locales retirés ; branches distantes fusionnées listées, en attente d'accord.
- **Reste hors run** : epic 6 (6.1 à 6.5, avec l'utilisateur) ; parties humaines de 2.1, 2.8, 3.5.
- **Reports** : purge de la boîte aux lettres et des acquittements (règle de rétention à décider) ; filtre par projet de `GET /api/operations` ; audit de la charte `--strict` (outil absent de ce dépôt) ; reports antérieurs à v0.3.0 dans l'archive privée.

## À faire par l'utilisateur

1. **Réinstaller le runtime v0.5.0** sur chaque PC : dans le clone du dépôt de configuration, `git pull` puis `.\sync.ps1 restaurer`. Sur le PC de dev, l'interrupteur `desactive` reste posé (hooks coupés) jusqu'à son retrait.
2. **Relire deux choix de 5.6** : message « tous les PC » lu dès le premier PC ; exclusion non réversible depuis l'appli.
3. **Accord pour supprimer les branches distantes fusionnées** : `chore/etat-run-reprise-4-7`, `chore/etat-run-v17`, `story/r-cle`.

## Journal

- 2026-11-11 09:28 · run · décision · reprise à 4.7 sur le dépôt public ; push, PR et fusion autorisés ; 4.7 → v0.4.0, 5.6 → v0.5.0 ; périmètre 4.7, 5.5, 5.6 · 9436d23
- 2026-11-11 09:28 · V16 · attente humaine · recette de l'accueil, worktree recette-v030 prêt · 9436d23
- 2026-11-11 09:28 · 4.7 · décision · spec écrite pendant la recette (Opus) ; dev lancé après « recette accueil OK » · —
- 2026-11-11 09:38 · 4.7 · décision · spec écrite (specs/4-7-tiroir-chantiers.md) : registre de sections dans tiroir.js, détails du projet par noyau/etat (clé details à part des cartes), tri des chantiers au noyau, annonce de hausse d'Attend dans app.js ; titre de l'epic passé à v0.4.0 · —
- 2026-11-11 09:50 · run · fusion · PR d'état #2 (état, sprint status, spec 4.7), CI verte, MERGED vérifié · 67780d8
- 2026-11-11 12:24 · V16 · attente humaine · recette de l'accueil validée par l'utilisateur, sauf l'écran « Clé d'accès perdue » au rechargement par le bouton du navigateur (comportement prévu, Flux 6) : décision en attente (message plus clair, ou clé gardée en sessionStorage) · 67780d8
- 2026-11-11 12:24 · 4.7 · dev · lancé (Opus, story transverse noyau et web) · —
- 2026-11-11 12:35 · r-cle · décision · accord de l'utilisateur : clé gardée en sessionStorage le temps d'un rechargement (écrite à pagehide, relue et effacée au chargement), AD-14 et EXPERIENCE amendés hors dépôt, spec specs/r-cle-rechargement.md ; vague V17b après 4.7, tag v0.4.0 après r-cle ; recette de l'accueil close · —
- 2026-11-11 12:43 · 4.7 · dev · fini : noyau/etat criteres, detail, details, tri des chantiers ; tiroir.js (registre), sections-projet.js, chantiers.js réécrit ; bouton du nom sur les quatre colonnes ; hausse d'Attend annoncée sur tous les onglets ; v0.4.0 ; 577 tests ciblés · 868749f
- 2026-11-11 12:43 · 4.7 · PR · #3 ouverte · 868749f
- 2026-11-11 12:43 · 4.7 · second-avis · lancé (Haiku) · —
- 2026-11-11 12:48 · 4.7 · second-avis · rien de high ; 1 medium (criteres et critere_manquant divergent sur des comptes de commits négatifs), 4 low (tiroir resté ouvert après session remplacée, sections sans maj, note de reprise exposée pour tous les projets, marge sur #racine), 3 nits · 868749f
- 2026-11-11 12:48 · 4.7 · review · lancée (Opus), liste du second avis transmise · —
- 2026-11-11 12:54 · 4.7 · CI · verte avant revue (PR #3) · 868749f
- 2026-11-11 12:55 · 4.7 · review · passe 1 : 0 Important ; 2 low corrigés (tiroir fermé avant l'écran session remplacée, focus de repli sur main avec tabindex -1), medium du second avis ramené à nit (comptes négatifs refusés par le schéma) et aligné sur critere_manquant ; 4 rejetés (sections sans maj par choix de spec, fuseau imposé par la signature, nom vide impossible, raison.params antérieur) ; écarts du dev acceptés ; details sans session, dossier ni pid ; 338 tests ciblés ; pas de passe 2, delta relu par l'orchestrateur · 56a79f7
- 2026-11-11 12:56 · r-cle · dev · lancé (Sonnet), empilé sur story/4-7 (56a79f7) · —
- 2026-11-11 12:58 · r-cle · dev · fini : lireCle fragment puis stockage, écriture à pagehide seulement, effacement au chargement et à pageshow persisté, 401 initial sur clé gardée → Clé perdue, try/catch ; garde statique limitée à app.js et pilotage-cle ; tests Node des critères 2 à 6 · e9fdbfb
- 2026-11-11 12:58 · r-cle · second-avis · lancé (Haiku) · —
- 2026-11-11 13:00 · r-cle · second-avis · rien de high ; 2 medium (clé reprise par la restauration d'un onglet fermé : risque résiduel accepté par l'utilisateur, à documenter ; garde statique limitée au préfixe getItem), 3 low, 1 nit · e9fdbfb
- 2026-11-11 13:05 · 4.7 · CI · verte (PR #3, 56a79f7, 9 min) · 56a79f7
- 2026-11-11 13:05 · 4.7 · fusion · #3 fusionnée (squash), MERGED vérifié · 76f9657
- 2026-11-11 13:06 · r-cle · PR · rebasée sur main (--onto, après squash de #3), #4 ouverte · 735eda0
- 2026-11-11 13:06 · r-cle · review · lancée (Opus), liste du second avis transmise · —
- 2026-11-11 13:18 · r-cle · review · passe 1 : 1 Important corrigé (garde statique par appels exacts sur pilotage-cle, accès par crochets aux globaux refusé), 1 low corrigé (stockage vidé avant replaceState), risque résiduel n°1 nommé en commentaire, 2 rejetés (critère 5 de la spec, tests JS déjà présents) ; 202 tests ciblés ; pas de passe 2, delta relu par l'orchestrateur · c2ae550
- 2026-11-11 13:18 · r-cle · CI · verte (PR #4) · c2ae550
- 2026-11-11 13:18 · r-cle · fusion · #4 fusionnée (squash), MERGED vérifié · a24104f
- 2026-11-11 13:24 · 5.5 · décision · spec écrite (specs/5-5-panneau-reprise.md) : sessions chargées à la construction de la section, réponse tardive ignorée ; POST /api/reprise rend dossier et chemin_brief, appeler accepte un corps JSON et une lecture texte ; POST dès l'affichage comme le Flux 2 (brief local écrit à chaque ouverture pour une session d'un autre PC, jamais poussé, purgé à 7 jours) ; aucun AD [ADOPTED] touché · —
- 2026-11-11 13:24 · 5.5 · dev · lancé (Opus, serveur et web) · —
- 2026-11-11 13:30 · run · CI · main verte sur a24104f (après #3 et #4) · a24104f
- 2026-11-11 13:30 · run · décision · tag annoté v0.4.0 et release publiés (fin de l'epic 4 : 4.7 et r-cle) · a24104f
- 2026-11-11 13:36 · v0.4.0 · fusion · runtime v0.4.0 publié dans claude-config (publier_config depuis le tag, 99 fichiers, porte test_sync_ps1 19 passés), PR #7 fusionnée, MERGED vérifié ; réinstallation des PC laissée à l'utilisateur · 50771aa
- 2026-11-11 13:36 · 5.5 · dev · fini : reprise.js (cinq cas, POST à l'affichage, réponses tardives filtrées, brief borné à 32768), bouton Reprendre, appeler avec corps JSON et lecture texte, POST /api/reprise rend dossier et chemin_brief ; gardes CSS et troncature retouchées (exception nommée) ; 404 tests ciblés · d7dfb74
- 2026-11-11 13:36 · 5.5 · second-avis · lancé (Haiku) · —
- 2026-11-11 13:39 · 5.5 · PR · #6 ouverte · d7dfb74
- 2026-11-11 13:39 · 5.5 · second-avis · rien de high ; 1 medium (garde CSS aveugle à overflow-y), 2 low (POST et brief écrit à chaque ouverture du tiroir, littéraux de fixture corrompus), 1 nit ; commande, textContent, C4, dossier et chemin_brief vérifiés sans défaut · d7dfb74
- 2026-11-11 13:39 · 5.5 · review · lancée (Opus), liste du second avis transmise · —
- 2026-11-11 13:42 · run · fusion · PR d'état #5, CI verte, MERGED vérifié · ee874ef
- 2026-11-11 13:48 · 5.5 · review · passe 1 : 1 Important corrigé (garde CSS par règle : horizontal refusé partout, vertical seulement pour dialog.tiroir et pre.brief, trou préexistant de 4.7 fermé), 1 low corrigé (littéraux de fixture échappés, chemin du brief vérifié) ; POST à chaque ouverture gardé (Reprise visible dès l'ouverture, Flux 2) ; écarts du dev acceptés ; tests seuls touchés, 337 tests ciblés ; pas de passe 2 · 1f125af
- 2026-11-11 13:57 · 5.6 · décision · spec écrite (specs/5-6-messages-reglages.md) : aucun bouton principal ajouté ; validation front de confort, serveur seul juge ; réglages affichés « En attente de synchro » d'après /api/operations, sans mise à jour optimiste ; message_en_attente confirmé, calculé par serveur/etat ; extensions sans nouvelle route (message_en_attente, chantiers_connus, pause dans detail) ; v0.5.0 ; epic corrigé · —
- 2026-11-11 13:57 · 5.6 · décision · options de la spec retenues, à relire par l'utilisateur : message à tous les PC lu dès le premier PC (étiquette retirée alors) ; exclusion non réversible depuis l'appli (édition de projets.yaml, dit à la confirmation) · —
- 2026-11-11 13:57 · 5.6 · report · GET /api/operations sans filtre par projet et boite/ jamais purgée : rejoint le report « purge des acquittements » · —
- 2026-11-11 14:00 · 5.5 · CI · verte (PR #6) · 1f125af
- 2026-11-11 14:00 · 5.5 · fusion · #6 fusionnée (squash), MERGED vérifié · 81dba42
- 2026-11-11 14:00 · 5.6 · dev · lancé (Opus, serveur, noyau et web ; story à risque côté messages) · —
- 2026-11-11 14:17 · 5.6 · dev · fini : operations.js (lecture partagée de la file), boite.js, reglages.js, 202 traité comme synchro lancée, message_en_attente et chantiers_connus dans /api/etat, pause dans detail ; v0.5.0 ; aucune garde assouplie · c1c4e50
- 2026-11-11 14:17 · 5.6 · second-avis · lancé (Haiku) · —
- 2026-11-11 14:21 · 5.6 · PR · #7 ouverte · c1c4e50
- 2026-11-11 14:21 · 5.6 · second-avis · rien de high ; 2 medium (/api/etat en 500 si la clé donnees est invalide ; boîte entière relue à chaque /api/etat), 5 low (dont message tous PC lu au premier PC, décision retenue) ; textContent, C4, double envoi, exclusion confirmée, pas d'optimisme vérifiés · c1c4e50
- 2026-11-11 14:21 · 5.6 · review · lancée (Opus), liste du second avis transmise · —
- 2026-11-11 14:40 · 5.6 · review · passe 1 : 0 Important ; n°1 préexistant (lire_etat lève déjà sur clé donnees invalide, 500 voulu), n°2 mesuré (1 000 messages et 2 000 acquittements en 37 ms) et reporté avec la purge de la boîte ; 5 nits corrigés (zone en lecture seule pendant l'envoi, contrôles rétablis si le projet réapparaît, options du chantier recréées seulement si la liste change, pause en liste blanche {revue}, focus rendu à la section) ; 1 rejeté ; 372+94+89 tests ciblés ; pas de passe 2, delta relu par l'orchestrateur · e8ccc1b
- 2026-11-11 14:40 · 5.6 · CI · verte (PR #7, trois OS) · e8ccc1b
- 2026-11-11 14:40 · 5.6 · fusion · #7 fusionnée (squash), MERGED vérifié · 8b40ce5
- 2026-11-11 14:54 · run · CI · main verte sur 8b40ce5 (après #7) · 8b40ce5
- 2026-11-11 14:54 · run · décision · tag annoté v0.5.0 et release publiés (fin de l'epic 5 : 5.5 et 5.6) · 8b40ce5
- 2026-11-11 14:55 · v0.5.0 · fusion · runtime v0.5.0 publié dans claude-config (103 fichiers, porte test_sync_ps1 19 passés), PR #8 fusionnée, MERGED vérifié ; réinstallation laissée à l'utilisateur · 2faa8f6
- 2026-11-11 14:56 · run · ménage · 4 worktrees retirés, 0 verrous levés, 4 branches locales, 0 distantes supprimées · —
- 2026-11-11 14:57 · run · décision · fin du run (V16 à V19 et r-cle) : rapport de fin écrit ; aucun agent en cours · 8b40ce5
