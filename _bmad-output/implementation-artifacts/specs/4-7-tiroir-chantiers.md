---
story: "4.7"
titre: Tiroir de détail et vue Chantiers, v0.4.0
status: ready-for-dev
date: 2026-11-11
---

# Story 4.7 : tiroir de détail et vue Chantiers, `v0.4.0`

Source : `epics-pilotage-projets.md`, story 4.7 (FR5, FR30, NFR10, UX-DR10, DR14, DR19, DR20) ;
sprint-change-proposal du 2026-11-07 ; EXPERIENCE § Tiroir de détail, Component et State
Patterns, Accessibility Floor, Fraîcheur, Responsive ; DESIGN § Components, Elevation & Depth ;
AD-11, AD-14, AD-15 ; reports de 4.5 et 4.11. Tag de fin `v0.4.0` (`v0.3.0` a servi à la
bascule publique) : le titre de l'epic est à corriger par l'orchestrateur.

## Déjà là
- `/api/etat` : `cartes` (`chantier`, `categorie`, `clone_ici`, `depot_de`, `phase`,
  `etiquettes`…), `colonnes`, `chantiers` (par nom), `dependances` (`"A ← B"`), `utilisateur`.
  Manquent : sessions par PC, faits du dépôt, critères. `chantiers.js` : état neutre de 4.4 ;
  `accueil.js` : nom en bouton `aria-disabled` (Attend, Relancer), annonce dans `rendreAccueil`.

## À livrer
1. **Noyau** (`pilotage/noyau/etat.py`, pur) :
   - `criteres(depot) -> list[dict]` : cinq entrées dans l'ordre d'`etats-action.md`,
     `{code, libelle, rempli, precision}` ; codes `release`, `commits`, `stories`, `prs`, `ci` ;
     libellés « une release publiée », « aucun commit hors docs/chore depuis la release »,
     « aucune story ouverte », « aucune PR ouverte », « CI de main verte » ; `precision` : le tag
     (release remplie), « 4 commits », « 1 story ouverte » / « 2 stories ouvertes », « rouge »,
     « en cours », « aucune CI », « pas de sprint-status.yaml » (`sprint_status == "absent"` :
     critère des stories rempli) ; None sinon. Cohérent avec `critere_manquant` (test).
   - `detail(faits, fuseau) -> dict` : `sessions` (liste blanche : `pc`, `statut` `{code, texte}`,
     `debut`, `dernier_tour`, `fin`, `branche`, `note` tirée de `reprise` ; ni `session`, ni
     `dossier`, ni `pid`), triées par PC (casefold) puis plus récente d'abord (`_plus_recent`) ;
     statuts calculés par les aides existantes : `attend` « en attente » (`_attente_valide`),
     `active` « active », `finie` « finie », `arretee` « arrêtée sans fin propre » (ce PC),
     `sans-nouvelles` « sans nouvelles de <pc> » (distante) ; `depot` (liste blanche : `tag`,
     `commits` dans l'ordre de `TYPES_COMMIT` sans les zéros, `prs_ouvertes`, `stories_ouvertes`,
     `ci`, `sprint_status`) ou None ; `depot_de` ; `criteres` (None sans `depot`).
   - `assembler` rend en plus `details` (`{nom: detail}`, à part des cartes : leur empreinte ne
     bouge pas à chaque tour ; lu par `Object.hasOwn`). `chantiers` trié par action (`ACTIONS`)
     puis par nom (AD-11 : le tri est au noyau ; `TABLEAU.md` suit). Aucun changement du serveur
     ni de `scan/lecture.py` : `details` passe par `lire_etat`.
2. **`pilotage/web/tiroir.js`** (contrat de section, singleton : un seul tiroir à la fois) :
   ```js
   export const ORDRE_SECTIONS = ["etat", "reprise", "messages", "sessions", "faits",
     "criteres", "chantier", "reglages"];
   // def = { id, titre, rendre(ctx) -> Node | null, maj?(noeud, ctx) -> void }
   // id hors ORDRE_SECTIONS ou déjà pris : Error. rendre null : section absente.
   export function enregistrerSection(def) {}
   // ctx = { nom, carte, detail, etat, maintenant, appeler } ; appeler vient d'app.js.
   export function initialiserTiroir({ hote, page, appeler, retrouver }) {}
   export function ouvrirTiroir(nom, origine, { section } = {}) {}
   export function majTiroir(etat) {}  // mémorise ; appelle seulement les `maj` déclarés
   export function fermerTiroir() {}
   export function tiroirOuvert() {}   // nom du projet ouvert, ou null
   ```
   5.5 (`reprise.js`) et 5.6 (`boite.js`, `reglages.js`) n'ajoutent qu'un module qui appelle
   `enregistrerSection` à l'import et une ligne d'import dans `app.js`. `section` : amenée à
   l'écran (`scrollIntoView`), le focus reste sur le titre.
   - `dialog.tiroir`, `aria-labelledby="tiroir-titre"`, `h2#tiroir-titre` (nom, `tabindex=-1`),
     bouton secondaire « Fermer » ; une `section` par entrée, `h3` d'id `tiroir-section-<id>`.
   - `matchMedia("(min-width: 80em)")` vrai : `show()` et classe `tiroir-ouvert` sur `page` ;
     faux : `showModal()`. Seuil franchi tiroir ouvert : fermé puis rouvert dans l'autre mode,
     sans reconstruction. Ouvrir un autre projet : même `dialog`, contenu et origine remplacés.
   - Fermeture (« Fermer », `Échap` au document en non modal sauf `defaultPrevented`, `cancel` en
     modal) par un seul chemin (`close`) : focus à `origine` si elle est encore dans le document,
     sinon à `retrouver(nom)` (bouton du même projet dans la vue courante), sinon à `main`.
3. **`pilotage/web/sections-projet.js`** : les cinq sections de 4.7, enregistrées à l'import.
   - État : pastille d'action (libellé de la colonne, `titreAttente` pour Attend), *quoi*
     (Attend, s'il est non vide) sinon raison, pastille de type (Attend), « phase : status-dev »
     (absente sans phase), étiquettes de la carte.
   - Sessions par PC : un `h4` par PC puis une liste : statut, « début 08:41 », « dernier tour
     hier 22:47 », « fin … », branche, note de reprise en `p.note-reprise` (`pre-wrap`) ; heures par
     `temps.js`. Liste vide : « Aucune session connue. »
   - Faits du dépôt : release (« aucune »), commits par type (« 3 feat, 1 fix » ; « aucun »), PR
     ouvertes, stories ouvertes (« pas de sprint-status.yaml »), CI de main ; `depot_de` : « relus
     sur pc-bureau, hier 23:10 ». Sans `depot` : « Faits du dépôt non relus. Lancez un scan. »
   - Critères de stabilité (absente sans `depot`) : « <libellé> : rempli » ou « : non rempli »,
     puis « (précision) » ; sans sprint-status : « rempli (pas de sprint-status.yaml) ».
   - Chantier et dépendances : « Chantier : chantier-x » ou « Hors chantier. » ; dépendances où le
     projet figure (A ou B), en police de commande.
4. **`pilotage/web/types.js`** : `pastilleAction(action, libelle)`, classe tirée d'une `Map`
   des quatre actions (action inconnue : pastille neutre), couleurs des chiffres de tuile.
5. **`pilotage/web/chantiers.js`** : `rendreChantiers(conteneur, etat, maintenant, options)` :
   `h2` masqué « Chantiers » ; un `section.bloc-chantier` par chantier (ordre du noyau) : `h3`
   nom puis pastille d'action, une ligne par dépôt (bouton du nom, pastille), dépendances dont A
   est dans le bloc (`p.dependance`, `commande`, `texte-attenue`) ; puis « Découverts, à classer »
   (`categorie` à classer), puis « Hors chantier » (classés sans chantier), dans l'ordre de
   `cartes` ; bloc vide absent. Reconstruit seulement si l'empreinte des données lues change ;
   focus rendu au bouton du même projet. Exporte `boutonNom(conteneur, nom)`.
6. **`pilotage/web/accueil.js`** (reports) : le bouton du nom de toutes les cartes et lignes
   (Attend, Relancer, Tourne « Tourne : », Rien à faire « Rien à faire : ») ouvre le tiroir
   (`ouvrirTiroir(nom, bouton)`), sans `aria-disabled` ; exporte `boutonNom`. L'annonce sort de
   `rendreAccueil` : `texteHausse(avant, noms) -> string | null` exportée, pure.
7. **`pilotage/web/app.js`** : `initialiserTiroir` au démarrage (`hote` et `page` = `#racine`,
   `appeler`, `retrouver` par la vue courante) ; dans `appliquer`, quel que soit l'onglet :
   `majTiroir(donnees)`, puis si `lectureAutomatique(...)`, `texteHausse(attendConnus, noms)` →
   `annoncer` ; `attendConnus` mis à jour à chaque lecture appliquée (null au départ).
8. **`appli.css`** (jetons de `charte.css` seulement) : `dialog.tiroir` 30rem à droite, fixé,
   `surface`, contour 1 px `trait-fort`, `--halo`, rayon grand, titre en `titre-tiroir` ;
   `::backdrop` en `--voile` ; fondu 150 ms sous `prefers-reduced-motion: no-preference` seulement ;
   `.tiroir-ouvert` : marge de 30rem pour `main`, grille 2 × 2 de 80em à 110em ; plein écran sous
   80em ; `.note-reprise` `pre-wrap` + `overflow-wrap: anywhere` ; blocs en `surface-alt` ;
   bouton « Fermer » et boutons de nom ≥ 24 px.
9. **Version `0.4.0`** : `VERSION`, `pyproject.toml`, `uv.lock`, `README.md`, `test_socle.py` ;
   tag annoté et release par l'orchestrateur, après la fusion.

## Critères d'acceptation
- Clic ou `Entrée` sur le nom de toute carte, ligne ou dépôt de Chantiers : tiroir ouvert, titre
  focalisé ; `Échap` le ferme et rend le focus à l'origine ; un seul `dialog` dans le DOM.
- ≥ 1280 px : non modal, accueil resserré de 480 px, rien recouvert, grille 2 × 2 sous 1760 px ;
  en dessous : `showModal()` et voile. Contour `trait-fort` et halo.
- Sections État, Sessions par PC, Faits du dépôt, Critères, Chantier et dépendances, dans cet
  ordre, sans section vide ni « bientôt disponible » ; phase et chantier y figurent ; chaque
  critère dit « rempli » ou « non rempli » ; textes vides exacts ; note en `pre-wrap`.
- Chantiers : action puis nom, puis Découverts, puis Hors chantier ; bloc vide masqué ; `A ← B`
  en police de commande ; le nom d'un dépôt ouvre son tiroir.
- 30 s : tiroir jamais reconstruit (mêmes nœuds) ; hausse d'Attend annoncée une fois, sur l'un
  ou l'autre onglet, jamais au premier chargement ni après une action de l'utilisateur.
- Texte non fiable inerte, aucun `innerHTML`, audit de la charte `--strict` et
  `tests/test_publication.py` verts, version 0.4.0 partout.

## Tests
- `tests/test_etat_detail.py` (nouveau) : `criteres` (chaque critère rempli ou non, précisions,
  sprint-status absent) ; propriété « premier non rempli ↔ `critere_manquant` » sur une grille de
  dépôts ; statut de chaque cas de session ; tri ; listes blanches ; `depot` None ; commits.
- `tests/test_etat.py` : clés d'`assembler` (`details`, vide sans projet), tri des chantiers ;
  `tests/test_serveur_etat.py` : `details` dans `/api/etat`.
- `tests/test_web_tiroir.py` (Node, faux DOM avec `show`, `showModal`, `close`, `matchMedia`) :
  registre (ordre, id inconnu ou double, `rendre` null, section factice « reprise » à sa place),
  deux modes, focus, `Échap`, `cancel`, origine détachée, un seul tiroir, `majTiroir` sans
  reconstruction ni `rendre`, `maj` appelé, franchissement du seuil, textes vides, valeurs hostiles.
- `tests/test_web_chantiers.py` : blocs, ordre, Découverts, Hors chantier, bloc vide, dépendances,
  ouverture du tiroir, focus conservé, pas de reconstruction sans changement.
- `tests/test_web_accueil.py` : quatre colonnes sans `aria-disabled`, préfixes, clic, `texteHausse` ;
  `app.js` sous Node (fetch et minuteurs factices) : hausse pendant Chantiers annoncée une fois,
  rien au retour sur Projets ni au premier chargement.
- `tests/test_web_statique.py` : nouveaux modules, textes exacts (« Aucune session connue. »,
  « Hors chantier. », « Découverts, à classer »), règles CSS (halo, voile, 150 ms, `pre-wrap`).
- Local : ruff, `uv run pytest -q` sur ces fichiers, `test_socle.py`, `test_publication.py`.

## Fichiers touchés
`pilotage/noyau/etat.py` ; `pilotage/web/` (`tiroir.js`, `sections-projet.js`, `chantiers.js`,
`accueil.js`, `app.js`, `types.js`, `appli.css`) ; version ; tests. Rien d'autre (couches tenues).

## Décisions
- **Reports.** Bouton du nom branché pour les quatre colonnes et Chantiers. Étiquettes des
  cartes Attend : déjà livrées par 4.11 (« message en attente », « pas cloné ici », « à
  classer ») ; la phase va au tiroir ; les topics hors phase (`etiquettes`) n'ont pas de place
  dans l'UX et restent non affichés. Annonce : décidée dans `app.js` pour tout onglet, car le
  retour sur Projets est une action de l'utilisateur et absorberait la hausse.
- **Données.** `details` à part des cartes, calculé au noyau : statuts et critères appliquent
  `etats-action.md` (AD-11), le web n'en rédige aucun. Listes blanches : aucun identifiant de
  session, dossier ni pid n'est exposé (la reprise de 5.5 a sa propre route). Note et branche
  sont du texte déjà borné à l'écriture, affiché inerte (NFR5, AD-15) : pas d'AD amendé.
- **Registre.** Ordre fixé par `ORDRE_SECTIONS`, pas par l'ordre d'import ; `ctx.appeler`
  évite que le jeton sorte d'`app.js` ; `maj` facultatif pour les mises à jour ciblées de 5.6.
- **Rafraîchissement.** Contenu remplacé seulement par un geste (autre nom, réouverture) : un
  tiroir ouvert montre les données de son ouverture. **Version** : `v0.4.0` ici, `v0.5.0` à 5.6.
