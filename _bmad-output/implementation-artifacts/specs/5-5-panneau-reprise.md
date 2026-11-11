---
story: "5.5"
titre: Panneau de reprise dans le tiroir
status: ready-for-dev
date: 2026-11-11
---

# Story 5.5 : panneau de reprise dans le tiroir

Source : `epics-pilotage-projets.md`, story 5.5 (FR32 interface, UX-DR8, UX-DR10, UX-DR11, NFR10) ;
EXPERIENCE § Tiroir de détail (panneau de reprise), Flux 2, Voice and Tone, Accessibility Floor ;
DESIGN § Components (`bloc-commande`, `encre-pleine`) ; AD-14, AD-15 ; `securite.md` § Commandes
de reprise ; spec 5.4 (routes livrées) ; contrat du tiroir de la 4.7. Pas de changement de version
(`v0.5.0` à la 5.6).

## Déjà là (main a24104f)
- `GET /api/sessions/<projet>` : `{ok, donnees: {projet, pc, clone_ici, sessions, proposee}}` ;
  chaque session `{session, pc, ce_pc, debut, dernier_tour, branche, statut, fin}`, triées par
  activité décroissante ; `proposee` : id ou null. 404 « Projet inconnu. » hors état chargé.
- `POST /api/reprise` `{projet, session, pc}` (corps fermé) : `{commande, mode, brief, raison}` ;
  `mode` `resume` ou `brief` ; sans commande : `raison` « pas cloné ici » ou « dossier de la
  session introuvable ». 400 (identifiant, apostrophe), 503 (PC local, écriture).
- `GET /api/brief/<id>` : `text/plain; charset=utf-8`, 404 JSON « Brief inconnu. ».
- `tiroir.js` (registre, `ctx.appeler`, `tiroirOuvert()`), `cle.js` `blocCommande(commande)`,
  `accueil.js` `placeReprise()` : `div.carte-reprise` vide, dernier enfant des cartes Attend et
  Relancer, placé par la grille. `app.js` `appeler(methode, chemin)` : sans corps, lit du JSON
  seulement, 401 → `sessionRemplacee` (tiroir fermé, écran remplacé).

## Extensions nécessaires (dans le périmètre, testées)
1. **Serveur** (`pilotage/serveur/reprise.py`) : la réponse de `POST /api/reprise` gagne
   `dossier` (chemin absolu du dossier cité dans la commande, modes `resume` et `brief`) et
   `chemin_brief` (chemin absolu du brief, mode `brief`) ; null sinon, `_sans_commande` compris.
   Sans eux, le front devrait extraire le dossier ou le chemin de la commande, ce qui est exclu.
2. **`app.js` `appeler(methode, chemin, { json, texte } = {})`** : `json` (objet) → `body:
   JSON.stringify(json)` et `Content-Type: application/json` ; `texte: true` et statut 200 →
   `{statut, corps: null, texte: await reponse.text()}` (autre statut : JSON comme avant). Appels
   existants inchangés ; 401 toujours traité ici seul. Plus `import "./reprise.js";`.

## À livrer
1. **`pilotage/web/reprise.js`** (nouveau), `enregistrerSection({ id: "reprise", titre:
   "Reprise", rendre })`, sans `maj` (le panneau garde les données de son ouverture, comme 4.7).
   `rendre(ctx)` rend tout de suite `div.panneau-reprise` (`aria-busy="true"`, `p.meta`
   « Recherche des sessions… »), puis lance `ctx.appeler("GET", "/api/sessions/" +
   encodeURIComponent(ctx.nom))`. Cas, dans cet ordre :
   - `clone_ici` faux : « Pas cloné sur ce PC. Clonez le dépôt sous Documents\GitHub, puis
     relancez un scan. » (`p.meta`), aucun POST ;
   - `sessions` vide : « Aucune session à reprendre sur ce projet. » ;
   - une session : ligne descriptive ; plusieurs : `label` « Session à reprendre » + `select`
     (option : `<pc>` + « (ce PC) » si `ce_pc`, « · début HH:MM », « · dernier tour … » par
     `temps.js`), valeur = rang dans `sessions`, sélectionnée = `proposee` (sinon la première) ;
   - puis `POST /api/reprise` avec `{projet: ctx.nom, session, pc}` de la session choisie, à
     l'affichage puis à chaque `change` du `select` (focus laissé au `select`) ;
   - `mode` `resume` : `blocCommande(commande)` puis « Dossier : » + `dossier` (`p.chemin-reprise`) ;
   - `mode` `brief` : `blocCommande(commande)`, « Brief : » + `chemin_brief`, bouton secondaire
     « Voir le brief » (`btn2`, `aria-expanded`, `aria-controls`) ;
   - `commande` null : « pas cloné ici » → texte « Pas cloné… » ci-dessus ; « dossier de la
     session introuvable » → « Dossier de la session introuvable sur ce PC. Choisissez une autre
     session ou relancez un scan. » ; autre raison : affichée telle quelle (`textContent`).
   `aria-busy` retiré à chaque fin de chargement. La commande n'est jamais assemblée, découpée ni
   modifiée : seule la chaîne `commande` reçue va à `blocCommande`.
2. **Brief** : premier clic → `ctx.appeler("GET", "/api/brief/" + encodeURIComponent(brief),
   { texte: true })` ; `pre.brief` (`textContent`, `tabindex=0` pour défiler au clavier), tronqué
   à `BORNE_BRIEF = 32768` caractères suivis de « … (brief tronqué à l'affichage) » ; bouton →
   « Masquer le brief ». Clics suivants : bascule `hidden`, sans nouvel appel. 404 : « Brief
   introuvable (purgé ou effacé). Fermez puis rouvrez le tiroir pour en préparer un autre. »
3. **Erreurs** (GET sessions, POST, GET brief) : statut 0 → `TEXTE_INJOIGNABLE` (constante
   déplacée d'`app.js` vers `dom.js` et importée par les deux) ; 401 → rien (app.js a déjà
   remplacé l'écran) ; 400, 403, 404 sessions, 503 → `corps.erreur` s'il est une chaîne non vide,
   sinon « Erreur du serveur local. » ; texte d'erreur dans le panneau et `annoncer`.
4. **Réponse tardive** : compteur de module `demande`, incrémenté à chaque `rendre` et à chaque
   `change` ; une réponse ne s'applique que si son numéro est le dernier, `tiroirOuvert() ===
   ctx.nom` et le panneau est dans le document. Projet changé, tiroir fermé ou rouvert :
   réponse ignorée, rien n'est écrit ni annoncé.
5. **`accueil.js`** : `placeReprise(carte)` pose dans `div.carte-reprise` un `button.btn2.reprendre`
   « Reprendre » + `span.masque` « ` <nom>` » (nom accessible « Reprendre <projet> ») ; clic →
   `ouvrirTiroir(nom, bouton, { section: "reprise" })`. Cartes Attend et Relancer seulement ;
   toujours dernier enfant de l'`article` ; `boutonNom` vise toujours `.nom-projet`.
6. **`appli.css`** (jetons de `charte.css` seulement) : `.panneau-reprise` en colonne ;
   `pre.brief` `white-space: pre-wrap`, `overflow-wrap: anywhere`, police `commande`, fond
   `surface-alt`, `max-block-size: 20rem`, `overflow: auto` ; `.chemin-reprise` police `commande`,
   `overflow-wrap: anywhere` ; `.reprendre` et `select` ≥ 24 × 24 px, focus visible existant.

## Critères d'acceptation
- Cartes Attend et Relancer : « Reprendre » secondaire, nommé « Reprendre <projet> », dernier
  dans le DOM, à droite sur la ligne du nom ; aucune carte Tourne ni ligne Rien à faire n'en a.
  Clic : tiroir ouvert, section Reprise amenée à l'écran, focus sur le titre, rendu à
  « Reprendre » à la fermeture.
- Les cinq cas affichent les textes exacts ci-dessus ; la liste propose `proposee` par défaut.
- La commande affichée est octet pour octet celle du serveur ; `reprise.js` ne contient ni
  `claude`, ni `--resume`, ni `Set-Location`, ni `clipboard`.
- Un seul `btn1` dans le tiroir, celui de `blocCommande` : « Copié » 2 s et annoncé ; échec →
  commande sélectionnée, « Ctrl+C pour copier » relié par `aria-describedby`.
- Brief en texte brut inerte, `pre-wrap`, borné ; réponses tardives sans effet ; 401 par app.js.
- Aucun `innerHTML`, `charte audit --strict`, `tests/test_publication.py` et ruff verts.

## Tests
- `tests/test_serveur_reprise.py` : `dossier` égal au chemin cité dans la commande (resume et
  brief), `chemin_brief` sous `chemins.briefs()` et cité dans la commande, null sans commande.
- `tests/test_web_reprise.py` (nouveau, Node, faux DOM, `ctx.appeler` factice par
  `initialiserTiroir`) : cinq cas et textes ; `proposee` sélectionnée ; `change` → POST avec le
  `pc` de l'option, corps à trois clés ; commande factice sans « claude » affichée telle quelle ;
  valeurs hostiles (`HOSTILES`, `$(calc)`) inertes dans commande, dossier, PC, brief ; brief
  tronqué, 404, bascule sans second appel ; réponses tardives (autre projet, fermé, rouvert,
  `change` rapide) ignorées ; statut 0, 400, 404, 503, 401 ; un seul `btn1`, copie réussie et
  repli (`navigator.clipboard` factice).
- `tests/test_web_accueil.py` : « Reprendre » sur Attend et Relancer, absent ailleurs, dernier
  enfant, nom accessible, clic → section `reprise` (espion `scrollIntoView`), `boutonNom`
  inchangé ; `app.js` sous Node : POST avec `Content-Type` et corps JSON, mode `texte`, 401 sur
  `/api/sessions` → écran remplacé et tiroir fermé.
- `tests/test_web_statique.py` : `reprise.js` listé, textes exacts, littéraux interdits, règles
  CSS (`pre-wrap`, `max-block-size`). `faux_dom.mjs` : `select`/`option` (`value`,
  `selectedIndex`, `change`) si absents.
- Local : ruff, ces fichiers, `test_web_tiroir.py`, `test_publication.py`.

## Fichiers touchés
`pilotage/serveur/reprise.py` ; `pilotage/web/` (`reprise.js`, `accueil.js`, `app.js`, `dom.js`,
`appli.css`) ; tests ci-dessus et `faux_dom.mjs`. Ni `tiroir.js` ni `cle.js` (contrats tenus).

## Décisions
- **Chargement** : GET à chaque construction de la section (ouverture, autre projet,
  réouverture), jamais au rafraîchissement de 30 s (pas de `maj`) : les sessions ne sont pas dans
  `/api/etat` et le tiroir n'est jamais reconstruit. Réponse tardive filtrée par numéro de
  demande et `tiroirOuvert()`, car le nœud fermé reste dans le `dialog`.
- **Commande** : POST automatique de la session proposée, comme le Flux 2 ; une session d'un
  autre PC écrit donc un brief local à chaque affichage (jamais poussé, purgé à 7 jours).
- **Données manquantes** : `dossier` et `chemin_brief` ajoutés au serveur plutôt que tirés de la
  commande ; `clone_ici` faux tranche avant tout POST, la raison du serveur sert de filet.
- **Brief** : `textContent` dans un `pre`, borné côté front par prudence (le serveur borne déjà
  chaque section) ; chargé au geste seulement, une fois.
- **Bouton principal** : `blocCommande` réutilisé tel quel ; « Reprendre », « Voir le brief » et
  « Fermer » restent secondaires ; un seul bloc de commande à la fois.
- **Erreurs** : `appeler` reste le seul point qui voit le jeton et le 401 ; le panneau ne rend
  que des textes. Aucun AD amendé.
