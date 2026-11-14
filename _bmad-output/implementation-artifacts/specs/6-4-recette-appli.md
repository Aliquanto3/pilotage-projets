---
story: "6.4"
titre: Recette de l'appli (mixte)
status: ready-for-dev
date: 2026-11-11
base: v0.5.0
---

# Story 6.4 : recette de l'appli (mixte)

Source : epic, story 6.4 (NFR10, NFR11, NFR12, UX-DR9, UX-DR18, UX-DR19 ; `securite.md`, M14) ;
EXPERIENCE § Foundation (objectif des 10 s), Tiroir de détail, State Patterns, Interaction
Primitives, Accessibility Floor, Key Flows 1 à 6, Clé d'accès, Fraîcheur, Texte non fiable,
Responsive ; DESIGN § Layout & Spacing (budget de hauteur, grille). Base : `v0.5.0`.

## Décisions de l'utilisateur (2026-11-11)
- La story 6.4 est amendée sur place dans l'epic ; cette spec porte la liste de recette.
- **10 s** : seuil exigé en **1366 × 768** seulement. À **700 px**, le temps est relevé et
  consigné, sans seuil (DESIGN : le budget de hauteur ne s'applique pas sous 760 px ; nommer les
  stables y demande de déplier « Rien à faire », dépliage compris dans le temps).
- **Données** : un jeu de démo reproductible (partie A, code) pour les flux 2 à 6, les échecs et
  le *quoi* piégé ; le Flux 1 chronométré se joue aussi sur les vraies données, sur les deux PC
  (partie B). Le chronomètre qui fait foi est celui des vraies données.

## Partie A — jeu de démo (code : `dev-story`)

### À livrer
1. **`pilotage/chemins.py`** : `mode_demo() -> bool`, vrai seulement si `PILOTAGE_DEMO=1` **et**
   `PILOTAGE_RACINE_LOCALE` posée (sinon ignorée, sans erreur).
2. **Serveur sous `mode_demo()`** : pas de synchro d'ouverture ; `Scan` et `Sync` ne lancent
   aucun processus et rendent un état lisible (« Désactivé en démo. ») ; aucun appel à `git`,
   `gh` ni `claude`. `reprise`, `message` et `projets` écrivent sous la racine de démo comme
   d'habitude (les opérations restent « en attente de synchro »). Hors démo : comportement
   inchangé (tests de non-régression).
3. **`outils/jeu_demo.py <dossier> [--variante accueil|echecs]`** :
   - refuse un dossier existant non vide, et tout dossier sous la racine locale par défaut
     (`%LOCALAPPDATA%\pilotage-projets`) ou sous `~/.claude` ;
   - écrit l'état attendu par `lancer.py appli` (même format que les écrivains existants ; chaque
     fichier soumis à un validateur C2 passe `schemas.valider`) ; horodatages calculés à partir
     de l'heure de construction (jeu à construire juste avant la recette) ;
   - PC `pc-a` (ce PC) et `pc-b` (sans nouvelles depuis la veille 23:10) ; projets
     `projet-a` à `projet-l`, jamais un nom réel ;
   - écrit `corrige.md` à la racine du jeu : réponses attendues du chronomètre (qui attend, avec
     son *quoi* ; qui relancer ; qui est stable) ;
   - affiche la commande PowerShell de lancement (`PILOTAGE_RACINE_LOCALE`, `PILOTAGE_DEMO`, et
     les variables de propriétaire et de dépôt sous racine surchargée, valeurs fictives).
4. **`outils/LISEZMOI.md`** : une section « Jeu de démo ».

### Contenu des variantes
| Variante | Contenu |
|---|---|
| `accueil` | État du Flux 1, aucun bandeau. 12 projets : Attend 3 (`choix` avec *quoi*, attente vieillissante commencée la veille 22:47 sur `pc-b` ; `test` avec *quoi* ; « à qualifier » sans *quoi*) ; À relancer 3 (arrêtée, sans nouvelles de `pc-b`, pause à revoir) ; Tourne 1 ; Rien à faire 5 (4 stables, 1 en pause). Sessions : une reprenable sur ce PC, une seulement sur `pc-b` (brief, avec note de reprise sur deux lignes), un projet à plusieurs sessions reprenables, un sans session, un non cloné ici. Messages : un « en attente de synchro », un « déposé », un « lu par pc-b à 08:12 ». |
| `echecs` | `accueil` plus : alertes « synchro abandonnée (conflit de rebase) » et « opération rejetée (champ pause) » ; un dépôt « à classer » et un chantier sans projet ; trois *quoi* piégés : `<img src=x onerror="document.title='XSS'">`, `javascript:document.title='XSS'`, `"><svg onload="document.title='XSS'">` (jamais `alert`, qui bloquerait le navigateur) ; un *quoi* et une note de reprise de 300 caractères sans espace. |

### Tests (`tests/test_jeu_demo.py`, ciblés)
- `/api/etat` sur la variante `accueil` : colonnes 3, 3, 1, 5, et les noms de `corrige.md`.
- Chaque fichier écrit passe son validateur ; refus des dossiers interdits ou non vides.
- `mode_demo()` : faux sans racine surchargée ; sous démo, aucun lancement d'enfant (`enfants`
  simulé), pas de synchro d'ouverture.
- `uv run pytest -q tests/test_publication.py` vert.

### Fichiers touchés
`outils/jeu_demo.py`, `outils/LISEZMOI.md`, `pilotage/chemins.py`, le module du serveur qui lance
la synchro d'ouverture, Scan et Sync, tests. Aucun changement dans `pilotage/web/`.

## Partie B — liste de recette (humaine, après fusion de A)

### Préparation
- Edge et Chrome à jour. Thèmes clair et sombre (thème du système).
- **1366 × 768** : portable de cette définition, fenêtre maximisée ; sinon, émulation DevTools au
  viewport relevé sur ce portable. Consigner `innerWidth × innerHeight`.
- **700 px** : fenêtre de 700 px de large, hauteur pleine (demi-fenêtre à côté du terminal).
  Consigner `innerWidth`.
- Jeu construit juste avant : `uv run python outils/jeu_demo.py <dossier> --variante …`.
- **Chronomètre** : départ au premier affichage de l'accueil, arrêt quand les trois listes sont
  dites à voix haute (qui attend et son *quoi*, qui relancer, qui est stable). Une réponse fausse
  ou oubliée fait échouer l'essai. Sur le jeu, seul le premier essai par largeur compte (après
  lui, le jeu est connu).
- Colonne **Temps** des parcours du tiroir : relevée, sans seuil.

Légende des largeurs : **L** = 1366 × 768, **É** = 700 px, **L+É** = les deux.

### A. Accueil
| # | Larg. | Données | Geste | Attendu |
|---|---|---|---|---|
| A1 | L | vraies, PC allumé du matin, l'autre PC ayant travaillé la veille | Ouvrir l'appli, chronométrer (Flux 1) | **< 10 s**, réponses justes (vérifiées ensuite sur l'écran). Une fois sur chaque PC |
| A2 | É | vraies | Idem, dépliage de « Rien à faire » compris | Temps relevé, réponses justes |
| A3 | L+É | `accueil` | Idem, premier essai | L < 10 s ; É relevé ; réponses conformes à `corrige.md` |
| A4 | L | `accueil` | Sans défiler, aides fermées | Première carte (ou ligne) de chaque colonne visible ; aides sur une rangée ; clair et sombre |
| A5 | É | `accueil` | Parcourir la page | Barre du haut sur deux lignes ; une colonne, dans l'ordre d'action ; bloc des stables sous la phrase ; « Rien à faire » repliée, « Afficher » bascule `aria-expanded` ; aucun défilement horizontal |
| A6 | L+É | `accueil` | Lire la synthèse et les cartes | Noms en attente en or avec l'heure de début ; sablier en or gras sur l'attente vieillissante ; carte « à qualifier » sans texte de remplacement ; « sans nouvelles de pc-b » en alerte |
| A7 | L | `accueil` | `Tab` depuis le haut | Ordre : barre, deux aides, Attend, À relancer, Tourne, Rien à faire ; focus visible partout ; synthèse, barre et tuiles hors du focus |
| A8 | L | `accueil` | Zoom à 200 %, puis viewport de 320 px CSS | Une colonne, rien de perdu, aucun défilement horizontal, chaînes longues coupées |
| A9 | L | `accueil` | Émuler `forced-colors` puis `prefers-reduced-motion` | Barre de répartition et légende lisibles ; aucune transition, halo sans soulèvement |
| A10 | L+É | `accueil` | `F5`, `Ctrl+R`, bouton de rechargement, puis serveur relancé et rechargement, puis relance dans un nouvel onglet (Flux 6) | Actualisation sans rechargement ; clé gardée au rechargement ; écran « Clé d'accès perdue » ; l'ancien onglet affiche « Une autre fenêtre de l'appli a été ouverte » ; le fragment disparaît de la barre d'adresse ; jeton jamais affiché |
| A11 | — | — | `charte audit --strict` et `contrastes.py` (deux thèmes, segments et chiffres compris), commandes de la story 4.9 | Les deux passent |

### B. Tiroir
| # | Larg. | Données | Geste | Attendu |
|---|---|---|---|---|
| B1 | L+É | `accueil` | Clic sur un nom, puis `Entrée` sur un nom, puis `Échap` | Le tiroir s'ouvre, focus sur son titre ; `Échap` le ferme et rend le focus au nom |
| B2 | L | `accueil` | Ouvrir le tiroir | Non modal, 480 px à droite ; accueil resserré en 2 × 2, rien de recouvert ; `Tab` atteint l'accueil et le tiroir |
| B3 | É | `accueil` | Ouvrir le tiroir, `Tab` en boucle | Plein écran, modal, voile ; le focus reste dans le tiroir |
| B4 | L+É | `accueil` | Parcourir le tiroir | Sections dans l'ordre (État, Reprise, Messages, Sessions, Faits, Critères, Chantier, Réglages) ; critères « rempli » ou « non rempli » ; listes vides : « Aucune session connue. », « Aucun message. », « Hors chantier. » |
| B5 | L | `accueil` | Tiroir ouvert et brouillon tapé, attendre 30 s | Tiroir non reconstruit, brouillon et focus intacts |
| B6 | L+É | `echecs` | Ouvrir les cartes et tiroirs piégés, dans Edge **et** Chrome | Texte affiché tel quel ; titre de l'onglet inchangé (jamais « XSS ») ; aucun lien ; console sans erreur de script ; chaîne de 300 caractères coupée, sans défilement horizontal |

### C. Reprise
| # | Larg. | Données | Geste | Attendu | Temps |
|---|---|---|---|---|---|
| C1 | L+É | `accueil` | « Reprendre » sur la carte du projet repris sur ce PC | Tiroir ouvert sur Reprise ; commande et dossier tels que rendus par le serveur ; « Copier la commande » → « Copié » 2 s, annoncé | relevé |
| C2 | L+É | `accueil` | Projet vu seulement sur `pc-b` | Commande « nouvelle session avec brief » et chemin du brief ; « Voir le brief » en texte brut, retours à la ligne conservés | relevé |
| C3 | L | `accueil` | Projet à plusieurs sessions | Liste PC, début, dernier tour ; par défaut la plus récente de ce PC | — |
| C4 | L | `accueil` | Projet sans session, puis projet non cloné | « Aucune session à reprendre sur ce projet. » ; « Pas cloné sur ce PC… », aucune commande | — |
| C5 | L | `accueil` | Refuser le presse-papiers au site, puis Copier | Commande sélectionnée, consigne « Ctrl+C pour copier » | — |
| C6 | L | vraies, deux PC | Flux 2 : reprendre sur ce PC une session de l'autre PC, coller dans Windows Terminal | La session démarre avec le brief et sa note de reprise | relevé |

### D. Messages
| # | Larg. | Données | Geste | Attendu | Temps |
|---|---|---|---|---|---|
| D1 | L+É | `accueil` | Taper un texte accentué, puis dépasser 2 048 octets, puis vider | Compteur en octets UTF-8 (« é » compte 2) ; « <n> octets de trop » en erreur, « Déposer » inactif ; inactif aussi si vide ; compteur jamais annoncé à la frappe | — |
| D2 | L+É | `accueil` | Choisir « PC visé », Déposer | Choix « Tous les PC » et PC connus ; zone vidée, annonce « Message déposé, en attente de synchro. » ; carte « message en attente » ; le projet reste dans Attend | relevé |
| D3 | L | `accueil` | Lire la liste des messages | États « en attente de synchro », « déposé », « lu par pc-b à 08:12 » | — |
| D4 | L | `accueil` | Déposer un texte refusé par le serveur (motif de secret, story 5.2) | Bandeau d'erreur local, saisie gardée | — |
| D5 | L | vraies, deux PC | Flux 3 : message vers l'autre PC, session lancée là-bas | Message reçu, encadré ; attente effacée au premier prompt ; « lu par <pc> à HH:MM » | relevé |

### E. Réglages
| # | Larg. | Données | Geste | Attendu | Temps |
|---|---|---|---|---|---|
| E1 | L+É | `accueil` | Mettre en pause avec une date, puis lever la pause | Réglage « en attente de synchro » | relevé |
| E2 | L | `echecs` | Classer le dépôt « à classer » dans un chantier ; ouvrir l'onglet Chantiers | Réglage « en attente de synchro » ; dépôt dans « Découverts, à classer » tant que rien n'est poussé | relevé |
| E3 | L+É | `echecs` | « Exclure », puis « Annuler », puis « Exclure » et confirmer | Confirmation en ligne qui reçoit le focus et nomme le projet ; « Annuler » rend le focus à « Exclure » ; aucune boîte native | — |
| E4 | L+É | `echecs` | Lire les bandeaux, en replier un ; ouvrir le tiroir du projet rejeté | Textes de EXPERIENCE § Bandeaux ; repliable, pas supprimable ; rejet aussi dans le tiroir, le réglage montre la valeur en vigueur ; erreurs annoncées par `role="alert"` | — |
| E5 | L | vraies | Flux 5 sur un projet choisi pour la recette : pause datée, synchro, puis levée | Après le push, le projet passe dans Rien à faire, « pause jusqu'au … », puis revient | relevé |
| E6 | L | vraies | Flux 4 si un dépôt « à classer » existe : le classer | Après le push, il quitte « Découverts, à classer » pour son chantier | relevé |

### Consignation
- Résultats dans `_bmad-output/implementation-artifacts/recette/6-4-<AAAA-MM-JJ>.md` : une
  ligne par numéro (OK ou KO, temps, navigateur, viewport, constat). Le dépôt est public :
  **aucun nom de projet réel, aucun *quoi* réel** ; pour A1 et A2, seulement le temps, le PC et
  le nombre de projets par colonne.
- Chaque KO ouvre un correctif (spec `specs/r-<id>.md`) avant la v1 ; A1 au-dessus de 10 s
  rouvre le budget de hauteur (DESIGN § Layout & Spacing).

## Critères d'acceptation
1. Partie A fusionnée, CI verte sur les trois OS, `test_publication` vert.
2. A1 sous 10 s sur chaque PC ; A2 et les temps du tiroir relevés.
3. Toutes les lignes de A à E à OK, ou couvertes par un correctif fusionné puis rejouées.
4. Compte rendu consigné, sans donnée réelle.
