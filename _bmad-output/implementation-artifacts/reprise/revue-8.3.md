# Revue 8.3

## Passe 1 (2026-11-14, SHA revu 74a0639, CI verte)

Base à jour (origin/main f61ddb2, aucun rebase nécessaire). Correctifs : 4b473aa.

- Important · medium · second avis 1 · accepté, corrigé · `_CHEMIN_ABSOLU` ne voyait `/` et `~` qu'en début de champ. Désormais n'importe où : lecteur, UNC, mot (début ou après blanc, guillemet, parenthèse, `=`, `:`…) qui commence par `/x/` ou `\x\` (Git Bash `/c/…`, `/home/…`, `/Users/…`) ou par `~/`, `~nom/`. URL (`https://a/b`, `s3://…`), `{{RACINE_GITHUB}}/…` et commandes d'un segment (`/clear`, `/agent-cost-kit:reviewer`) restent permises : une commande dans `prochaine` aurait sinon supprimé l'état entier. `/etc` et `~` seuls ne sont plus refusés (aucun nom privé). Tests : `test_texte`, `test_hooks_depot::test_chemin_absolu_supprime`.
- Important · medium · second avis 2 · accepté, corrigé · nouveau champ `etat_ecrit` (schéma : facultatif, seulement avec `etat`, au plus `ecrit`, absent = `ecrit`) ; une décision seule garde la date de l'état ; la péremption de 14 jours porte sur l'état et sur chaque décision (son `ecrit`) ; l'en-tête affiche la date de l'état montré. `sync` retire `etat_ecrit` avec un état refusé. Remplace l'écart déclaré « `ecrit` rafraîchi par une décision seule, péremption au fichier entier ».
- Important · medium · second avis 3 · accepté, corrigé · mesuré : avec la règle allongée par 8.3, seuls 2 messages de 1,8 Ko tiennent après la note (scénario 8.1) et 1 après la note et l'état. Messages du banc ramenés à ~0,9 Ko (total mesuré 9 344 unités, 3 messages remis) ; contrôle exact rétabli (`acquittes == remis`, débuts = messages + note + état) et plafond de 10 000 vérifié à chaque appel. `test_scenario_huit_etats_de_depot` lève le budget (`BUDGET_P95_MS = inf`) et exige le code 0. Le banc devient plutôt plus lourd (3 acquittements au lieu de 1). Marge : ~650 unités ; une règle encore allongée fera échouer le banc, volontairement.
- Nit · low · second avis 4 · accepté, corrigé · la rotation de `sync` écrit un jeton dans le verrou et ne l'efface que s'il est encore le sien (même logique que `_commun.verrou_fichier`). Tests : verrou repris non effacé, verrou rendu.
- Nit · low · second avis 5 · rejeté · `_commun.contexte` ne retient un `cwd` que s'il est exactement une clé de `table-dossiers.json` (dossier du projet) : au démarrage, `ctx.cwd` est le dossier du projet. Pas de sous-dossier possible à `SessionStart`.
- Nit · low · second avis 6 · accepté, corrigé · seul le fichier le plus récent par `ecrit` est considéré ; vidé par le filtre : rien, pas de repli sur un état plus ancien d'un autre PC présenté comme actuel. Test réécrit et ajouté.
- Nit · low · second avis 7 · accepté, corrigé · U+2028, U+2029 et contrôles bidirectionnels (U+202A-202E, U+2066-2069) refusés par `a_controle` (champs et schémas 8.3 seulement).
- Pre-existing · low · revue · documenté · les autres passages du banc dans `test_bench_hooks.py` acceptent encore le code 0 ou 2 (choix de 8.1, commenté) ; même correctif possible (budget levé, code 0) dans une story à part.

Chemin chaud : `SessionStart` et `Stop` passent par la nouvelle expression des chemins (une alternative de plus, coût négligeable) et par une comparaison de chaînes par décision ; `SessionStart` ne refiltre plus qu'un fichier (au lieu de boucler). Aucun import, `stat` ni ouverture de fichier en plus.

Sécurité à faire valider par l'utilisateur : forme exacte du filtre de chemins (mots commençant par `/x/` refusés, commandes d'un segment permises), et absence de repli sur un état plus ancien.

Passe 2 : utile seulement pour relire les correctifs (schéma `etat_depot` modifié) ; non bloquante.

## Passe 2 (2026-11-14, SHA revu 4b473aa, CI verte)

Base à jour (origin/main f61ddb2). Diff relu : 74a0639..4b473aa (correctifs de la passe 1). Aucun constat Important, aucun correctif.

Vérifié, sonde exécutée sur `texte.est_chemin_absolu` : refusés `C:/x`, `\serveur\x`, `/c/Users/x`, `~/x`, `"C:/x"`, `:/home/a/b`, `(/c/x/y)`, `voir:/c/Users/x`, `[/c/a]`, `/c/` ; permis `https://a.b/c/d`, `s3://b/c/d`, `a/b`, `/clear`, `/agent-cost-kit:reviewer`, `14/11`, `14/11/2026`, `origin/main`, `et/ou`. `etat_ecrit` : schéma (seulement avec `etat`, au plus `ecrit`), `sync` le retire avec un état refusé, fichier sans le champ lu avec `ecrit` (couvert par `test_decision_seule_ne_rafraichit_pas_la_date_de_l_etat`, fichier déposé sans `etat_ecrit`). Péremption par état et par décision, absence de repli, verrou de rotation à jeton (même logique que `_commun.verrou_fichier`), refus U+2028/U+2029/bidi, banc exact (`acquittes == remis`, plafond vérifié, constante liée à `cycle.BORNE_CONTEXTE` par test) : corrects. Tests existants modifiés : justifiés (champ `etat_ecrit` dans l'ordre des clés ; `/etc` seul désormais permis, d'où `/etc/x` ; test du repli scindé en deux). Ruff vert ; 339 + 362 tests ciblés verts.

- Nit · low · revue · reporté · `//serveur/partage/x` (forme UNC à barres obliques, affichée par Git Bash et acceptée par Windows) n'est pas refusé : nom de serveur et de partage conservés. Correctif possible : alternative `(?<![^\s"'`(\[{<=,;])//[^\s/\]+[\/]` (sans `:` dans la liste, pour garder les URL).
- Nit · low · revue · reporté · la liste blanche des caractères qui précèdent un chemin oublie guillemets typographiques (`“/home/a/b”`, `«/c/u/x»` sans espace), tiret, `|`, `>`, `*` : faux négatifs. Piste : lookbehind négatif `(?<![\w/\.}])` (le `}` garde `{{RACINE_GITHUB}}/a/b`), à tester contre les faux positifs.
- Nit · low · revue · reporté (décision utilisateur) · le fichier retenu reste le plus récent par `ecrit` (dernière écriture, point 8 de la spec) : une décision seule sur le PC B rend B prioritaire et masque un état plus récent (par `etat_ecrit`) d'un autre PC ; B montre alors son état plus ancien. Pas une régression (même fichier retenu avant la passe 1, état alors présenté comme frais) ; option : clé `date_etat` pour un fichier qui a un état.
- Nit · low · revue · reporté · compatibilité descendante : un PC resté en version antérieure refuse un fichier qui porte `etat_ecrit` (champ inconnu) et l'ignore en silence ; il se replie alors sur un fichier plus ancien (`_lire` écarte un fichier invalide avant le `max`, « sans repli » ne vaut que pour les champs filtrés). À dire dans les notes de version : mettre à jour tous les PC ensemble.
- Nit · low · revue · rejeté · U+200E, U+200F, U+061C (marques de direction) restent permis : elles ne réordonnent pas le texte (pas d'attaque Trojan Source), le refus des U+202A-202E et U+2066-2069 suffit.

Complexité : 0 constat (`SessionStart` ne refiltre plus qu'un fichier).
