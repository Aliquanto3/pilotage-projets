---
story: "5.6"
titre: Messages et réglages dans le tiroir, v0.5.0
status: ready-for-dev
date: 2026-11-11
---

# Story 5.6 : messages et réglages dans le tiroir, `v0.5.0`

Source : epic, story 5.6 (FR34, FR35, UX-DR10, DR12, DR13, NFR10) ; EXPERIENCE § Tiroir,
State Patterns, Confirmation, Fraîcheur, Texte non fiable ; DESIGN § Components ; AD-11, AD-14,
AD-15 ; specs 5.1 à 5.3, 5.5 ; report de 4.11. Tag `v0.5.0` (`v0.4.0` pris par 4.7) : le dernier
critère de l'epic, qui dit `v0.4.0`, est à corriger par l'orchestrateur.

## Déjà là (story/5-5)
- `POST /api/message` `{projet, texte, pc?}` et `POST /api/projets` `{projet, patch}` (corps
  fermés) : 202 `{id, verbe, projet, sync}` ; 400 et 503 `{erreur}` (vide, taille, secret, projet,
  PC, chantier inconnus, écriture). `pc` absent = tous les PC (`pc: null` est refusé).
- `patch` : `{chantier|exclu|pause: {attendu, voulu}}`, `attendu != voulu` ; `chantier` nom ou
  null, `exclu` booléen, `pause` `AAAA-MM-JJ` ou null. `sync` rejette `valeur-differente` si la
  valeur courante n'est ni `attendu` ni `voulu`.
- `GET /api/operations` : `{operations: [{id, verbe, projet, pc?, patch?}], messages: [{id,
  projet, pc, texte, etat, lectures, libelle}]}`, tous projets, triés par id ; `etat`
  `en-attente` | `depose` | `lu`, `libelle` rédigé par le serveur (« lu par pc-bureau à 08:12 »).
- `/api/etat` : `alertes` `{source, code, params, texte}` ; rejet d'un patch : source `operation`,
  `params {id, projet, champ}`, texte « Modification refusée : projets.yaml a changé ailleurs
  (champ pause de projet-a). » ; `fraicheur` `{pc, genere_a, texte}` ; carte `chantier`,
  `categorie`. `types.js` affiche déjà « message en attente » si `carte.message_en_attente === true`.
- Tiroir (4.7) : `enregistrerSection`, `ctx = {nom, carte, detail, etat, maintenant, appeler}`.

## Extensions nécessaires (dans le périmètre, testées ; table C4 inchangée)
1. **`pilotage/serveur/etat.py`** (`GET /api/etat`, toujours sans effet) :
   - chaque carte de projet (`cartes`, `colonnes[*]`, `chantiers[*].projets`, posé par nom sur les
     trois) gagne `message_en_attente` : vrai si un message du projet a `etat != "lu"` dans
     `suivi.messages(suivi.operations_en_attente())` ; nom du champ de 4.11 confirmé ;
   - `chantiers_connus` : noms des chantiers de `projets.yaml` (`mutations.chantiers_de_projets_yaml`,
     vides compris), triés casefold ; `[]` si le fichier est absent ou invalide.
2. **`pilotage/noyau/etat.py` `detail`** : gagne `pause`, `faits["pause"]` tel quel
   (`{"revue": str}`) ou None : seule source de l'`attendu` d'une pause, la carte ne la porte que
   dans les verdicts de pause.

## À livrer
1. **`pilotage/web/operations.js`** (nouveau) : `lireOperations(ctx)` → promesse de `{statut,
   corps}` de `GET /api/operations`, une seule par objet `ctx.etat` (`WeakMap`), partagée par les
   deux sections ; `oublierOperations()` après un 202. `operationsDe(corps, nom)` : opérations et
   messages du projet (corps illisible : listes vides).
2. **`pilotage/web/boite.js`** (nouveau), section `messages`, titre « Messages », avec `maj` :
   - `label` « Message » + `textarea.champ-message` ; `p.meta#boite-compteur`, relié par
     `aria-describedby`, sans `aria-live` : « <n> octets restants » (« 1 octet restant »), octets de
     `new TextEncoder().encode(valeur)`, recalculé à `input` ; au-delà de 2 048 : « <n> octets de
     trop » (« 1 octet de trop »), classe `erreur`, « Déposer » `disabled` ; texte vide ou blancs
     seuls : « Déposer » `disabled` aussi ;
   - `label` « PC visé » + `select` : « Tous les PC » (valeur vide), puis chaque `fraicheur[].pc`
     à `genere_a` non nul (seuls PC connus du serveur), construit à `rendre` seulement ;
   - `button.btn2` « Déposer » : `ctx.appeler("POST", "/api/message", { json })`, `json = {projet:
     ctx.nom, texte}` plus `pc` seulement si un PC est choisi ; bouton `disabled` et section
     `aria-busy` pendant l'appel ; 202 : zone vidée, compteur remis, focus laissé à la zone,
     `annoncer("Message déposé, en attente de synchro.")`, `oublierOperations()`, liste relue ;
   - liste `ul.liste-messages` des messages du projet, plus récent d'abord, 20 au plus puis
     « <n> messages plus anciens non affichés. » ; par message `p.texte-message` (`textContent`)
     puis `p.meta` « Pour tous les PC · <libelle> » ou « Pour <pc> · <libelle> » ; vide :
     « Aucun message. » ; chargement : « Lecture des messages… » ;
   - `maj` relit la liste seulement : zone de texte, compteur et « PC visé » jamais touchés.
3. **`pilotage/web/reglages.js`** (nouveau), section `reglages`, titre « Réglages », avec `maj` :
   - `p` « En vigueur : » + « Chantier : <x> » ou « Aucun chantier (à classer) » + « · en pause
     jusqu'au JJ/MM » ou « · pas de pause » (tirés de `ctx.carte` et `ctx.detail.pause`) ;
   - **Chantier** : `label` « Chantier » + `select` « Aucun (à classer) » (valeur vide) puis
     `etat.chantiers_connus` ; bouton « Classer » si `categorie` vaut « découvert, à classer »,
     « Rattacher » sinon ; patch `{chantier: {attendu: carte.chantier, voulu}}` (vide → null) ;
   - **Pause** : `label` « Date de revue » + `input type=date` (`min` = date locale du jour) ;
     « Mettre en pause » (« Changer la date de revue » si en pause), puis « Lever la pause » si en
     pause ; patch `{pause: {attendu: revue courante ou null, voulu}}`. `revue` hors `AAAA-MM-JJ` :
     contrôles de pause `disabled` et « Date de revue illisible dans projets.yaml : corrigez-la à
     la main. » ;
   - **Exclure** (`btn2`) : remplacé par une confirmation en ligne, `p` « Le projet disparaîtra de
     l'appli sur tous les PC après la synchro. On le réintègre en éditant projets.yaml. », bouton
     « Confirmer l'exclusion de <projet> » qui reçoit le focus, et « Annuler » ; « Annuler » ou
     `Échap` dans la confirmation (`preventDefault`, le tiroir reste ouvert) : confirmation retirée,
     focus à « Exclure » ; confirmer : patch `{exclu: {attendu: false, voulu: true}}` ;
   - **En attente** : par champ visé par une opération `modifier_projets` du projet dans
     `GET /api/operations`, `p.meta` « En attente de synchro : <voulu lisible> » (« rattachement à
     <x> », « retrait du chantier », « pause jusqu'au JJ/MM », « levée de la pause »,
     « exclusion ») et contrôles de ce champ `disabled` ; disparaît quand l'opération quitte la
     liste (appliquée et poussée, ou rejetée) ;
   - **Rejets** : alertes de `ctx.etat.alertes` de source `operation` et `params.projet ===
     ctx.nom`, texte du serveur tel quel dans `div.bandeau-local.alerte` en tête de section ;
   - un seul bouton à la fois envoie ; tous `btn2`. Projet absent de l'état (`ctx.carte` null,
     exclusion appliquée) : « Projet exclu ou retiré : il n'apparaît plus dans l'appli. »,
     contrôles retirés.
4. **Saisie et rafraîchissement** : un contrôle est « en cours » de sa première saisie
   (`input`/`change`) jusqu'au 202 de son envoi ; `maj` n'écrit jamais un contrôle en cours ni le
   focus ; un contrôle au repos reprend à chaque `maj` la valeur en vigueur (rejet compris).
5. **Erreurs** (GET et POST, deux sections) : comme 5.5 (statut 0 → `TEXTE_INJOIGNABLE`, 401 →
   rien, autre → `corps.erreur` non vide sinon « Erreur du serveur local. ») dans un
   `div.bandeau-local.erreur` de la section, `alerter(texte)`, saisie conservée. Réponse tardive
   (autre projet, tiroir fermé ou rouvert, demande plus récente) : ignorée, comme 5.5.
6. **`app.js`** : `import "./boite.js"; import "./reglages.js";` ; dans `appeler`, un 202 d'un POST
   vers `/api/message` ou `/api/projets` pose, si `suivi === null`, `suivi = { motif: "lance",
   finAvant: finDe(etat ? etat.cycle : null) }` puis `relire()` : la synchro qui suit est un
   geste de l'utilisateur (report de 4.11, aucune annonce de hausse). Rien d'autre ne change.
7. **`appli.css`** (jetons de `charte.css`) : `textarea`, `select`, `input[type=date]` en contour
   1 px `trait-fort`, rayon `petit`, cibles ≥ 24 px ; `#boite-compteur.erreur` en `erreur` ;
   `.texte-message` `pre-wrap`, `overflow-wrap: anywhere` ; `.bandeau-local` jetons d'erreur ou
   d'alerte ; `textarea` `min-block-size: 6rem`, `resize: vertical`.
8. **Version** `0.5.0` : `VERSION`, `pyproject.toml`, `uv.lock` (paquet `pilotage-projets`),
   `README.md`, `tests/test_socle.py` ; tag annoté `v0.5.0` et release après fusion.

## Critères d'acceptation
- Messages : compteur exact en octets (accents, emoji), relié par `aria-describedby`, non annoncé ;
  2 049 octets : « 1 octet de trop » en `erreur`, « Déposer » inactif ; « Tous les PC » sans clé
  `pc` ; PC choisi → `pc` ; 202 → zone vidée, message listé « en attente de synchro » d'après
  `GET /api/operations` (jamais inséré localement) ; refus 400 affiché tel quel, saisie gardée.
- Carte de l'accueil : « message en attente » tant qu'un message du projet n'est pas lu ; le
  projet reste dans sa colonne (aucun changement d'action côté front).
- Réglages : chaque geste envoie un seul `POST /api/projets` au patch exact ; « En attente de
  synchro » jusqu'à la sortie de l'opération ; valeur affichée = valeur en vigueur, jamais `voulu`
  avant application ; rejet : bandeau dans le tiroir et contrôle revenu à la valeur en vigueur.
- Exclure : confirmation focalisée et nommée ; Annuler et Échap rendent le focus à « Exclure ».
- Rafraîchissement de 30 s : brouillon, PC visé, date ou chantier en cours, focus inchangés.
- Textes de message hostiles (`<script>`, `HOSTILES`, délimiteurs `<<<PILOTAGE-MESSAGE-…>>>`)
  affichés tels quels ; aucun `innerHTML` ; un seul `btn1` dans le tiroir (celui de 5.5).
- `charte audit --strict`, ruff, `tests/test_publication.py` verts ; tag `v0.5.0` et sa release.

## Tests
- `tests/test_serveur_etat.py` : `message_en_attente` vrai (opération en attente ; message déposé
  non lu), faux après acquittement (`attente/` ou `donnees/`), faux ailleurs, posé sur `cartes`,
  `colonnes` et `chantiers[*].projets` ; `chantiers_connus` trié, chantier vide compris, `[]` sans
  `projets.yaml` ; lecture toujours sans effet (comparaison avant/après de 4.2).
- `tests/test_etat_detail.py` : `pause` `{"revue": "2026-12-01"}` ou None.
- `tests/test_web_boite.py` (nouveau, Node, faux DOM, `appeler` factice) : compteur (ASCII,
  `é`, emoji, 2 048 / 2 049, blancs), corps à deux ou trois clés, 202 → GET relu, 400 secret et
  503 affichés avec saisie gardée, statut 0, 401, liste triée et bornée à 20, « Aucun message. »,
  textes hostiles inertes, `maj` sans toucher zone ni select ni focus, réponse tardive ignorée.
- `tests/test_web_reglages.py` (nouveau) : patch exact des cinq gestes (classer, rattacher,
  retirer, pause, lever, exclure), « Classer » / « Rattacher » selon la catégorie, revue illisible,
  ligne en attente et contrôles inactifs, rejet affiché et valeur reprise, contrôle en cours non
  écrasé par `maj`, confirmation (focus, Annuler, Échap sans fermer le tiroir), projet disparu,
  un seul GET `/api/operations` pour les deux sections par relecture.
- `tests/test_web_accueil.py` : `app.js`, 202 sur `/api/projets` → motif `lance`, pas d'annonce
  de hausse à la relecture suivante ; « message en attente » sur la carte (déjà là, gardé).
- `tests/test_web_statique.py` : modules listés, textes exacts, règles CSS. `faux_dom.mjs` :
  `textarea` et `input` (`value`, `disabled`, `min`, évènement `input`) si absents.
- Local : ruff, ces fichiers, `test_web_tiroir.py`, `test_socle.py`, `test_publication.py`.

## Fichiers touchés
`pilotage/serveur/etat.py`, `pilotage/noyau/etat.py`, `pilotage/web/` (`operations.js`, `boite.js`,
`reglages.js`, `app.js`, `appli.css`), version, tests ci-dessus. Ni `tiroir.js`, `routes.py`,
`mutations.py`, `suivi.py` ni `types.js`.

## Décisions
- **Bouton principal** : aucun nouveau, « Déposer » et réglages secondaires (EXPERIENCE, DESIGN).
- **Validation** : front en confort seulement (compteur, vide, valeur identique, date
  `AAAA-MM-JJ`) ; aucun motif de secret ni règle de caractère dupliqués côté front. Le serveur
  reste seul juge (longueur, substituts, secrets, M10) et son refus s'affiche tel quel.
- **Texte d'un message** : non fiable une fois relu, `textContent` seulement (AD-15). Injecté en
  session par 5.3 (cadrage par nonce, neutralisation des délimiteurs, M15) : rien n'est affaibli,
  le front n'ajoute ni ne retire rien au texte saisi.
- **Réglages** : opérations en file appliquées par `sync` ; l'appli montre la valeur en vigueur
  plus « En attente de synchro : … », jamais de mise à jour optimiste ; champ en attente inactif
  pour éviter un second patch au même `attendu`, rejeté ensuite.
- **`message_en_attente`** : nom de 4.11 confirmé, calculé par le serveur dans `/api/etat` (une
  lecture pour toutes les cartes) plutôt que par le front sur `/api/operations`. « Lu » dès un
  acquittement : un message à tous les PC perd l'étiquette au premier PC qui le lit.
- **Données manquantes** : `chantiers_connus` (un chantier vide doit être proposable, `chantiers`
  ne liste que les non vides) et `detail.pause` (attendu exact) ajoutés plutôt que devinés.
- **Exclusion** : pas de levée depuis l'appli (5.2 : un projet exclu sort de l'état chargé) ;
  la confirmation le dit. Aucun AD amendé : routes inchangées, `/api/etat` garde son rôle.
- **Report** : `GET /api/operations` rend les messages de tous les projets, `boite/` sans purge ;
  filtre par projet ou purge à prévoir si la boîte grossit.
