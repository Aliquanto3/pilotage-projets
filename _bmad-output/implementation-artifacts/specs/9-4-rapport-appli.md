---
story: "9.4"
titre: « Rapport de la semaine » dans l'appli
status: draft
date: 2026-11-14
---

# Story 9.4 : « Rapport de la semaine » dans l'appli

Source : `epics-pilotage-projets.md`, epic 9, story 9.4 (FR47) ; AD-14 (table fermée des routes),
AD-15 (front sans dépendance) ; NFR4, NFR10, NFR11 ; stories 4.1 (matrice de refus), 4.3
(`scan`/`sync` déclenchés), 9.2 (génération), 9.3 (`rapport.generer`).

**Risque :** à risque (nouvelle route du serveur local ; barre du haut partagée). Spec relue
avant le code ; revue sur Opus ; `verif-front` après dev-story.

## Déjà là (après 9.2 et 9.3, empilées)
- `pilotage/serveur/routes.py` : `ROUTES`, liste fermée ; `_declencheur(type_)` pour `scan` et
  `sync` (sans argument, 202 ou 409 « déjà en cours », 500 sans trace) ; `_tardif(module, nom)`.
- `pilotage/serveur/appli.py` : `ThreadingHTTPServer`, jeton, contrôle `Host`/`Origin`, lecture du
  corps, `envoyer_api`.
- `pilotage/serveur/cli.py` : `main(argv, *, navigateur=webbrowser.open, …)`.
- `pilotage/rapport/` : génération d'une semaine (`generer(semaine, maintenant) -> Path` si la 9.3
  l'a extraite, sinon la fonction de `cli.py` équivalente), semaine courante en heure locale,
  `chemins.rapport_semaine()`.
- `pilotage/web/barre.js` : `construireBarre(rappels)`, boutons secondaires Actualiser, Scan,
  Sync (`aria-disabled` pendant un cycle) ; `pilotage/web/app.js` : appels `/api/…`, zone
  `#annonce` (`aria-live="polite"`) et `#alerte` (`role="alert"`).

## À livrer
1. **`pilotage/serveur/rapport.py`** (nouveau) : gestionnaire `rapport(parametres, corps)`.
   - Verrou de module `threading.Lock()`, pris par `acquire(blocking=False)` : déjà pris → 409
     `{"type": "rapport", "etat": "deja_en_cours"}`, erreur « déjà en cours », rien généré.
   - Sinon : génère la page de la **semaine en cours** (heure locale) par la fonction de
     `pilotage/rapport/` (aucune duplication), puis appelle le navigateur avec
     `chemin.resolve().as_uri()` (URI `file:` construite par le serveur, jamais reçue du client).
   - Succès → 200 `{"type": "rapport", "etat": "ouvert", "semaine": "AAAA-Www"}`. **Aucun
     chemin, absolu ou relatif, dans la réponse.**
   - Échec de génération ou d'ouverture → 500, erreur fixe (« rapport impossible »), type
     d'erreur journalisé par `serveur.journaliser` si c'est l'usage, jamais `str(exc)`. Le
     verrou est toujours rendu (`finally`).
   - Navigateur injectable : `configurer(navigateur)` appelé par `serveur/cli.main` avec son
     paramètre `navigateur` (défaut `webbrowser.open`) ; sans configuration, `webbrowser.open`.
     Les tests passent un faux navigateur qui note l'URI.
2. **`routes.py`** : `Route("POST", "/api/rapport", _tardif("rapport", "rapport"))`, sans
   paramètre, placée après `/api/sync`. Corps : même règle que `/api/scan` et `/api/sync` (lire
   comment `appli._lire_corps` et la matrice de 4.1 traitent un corps non vide sur ces routes et
   s'y aligner exactement) ; paramètre de requête, jeton absent ou faux, `Host` ou `Origin`
   étrangers : même refus que les autres routes, rien généré ni ouvert.
3. **Barre du haut** (`barre.js`) : bouton secondaire « Rapport de la semaine » après Sync,
   rappel `rappels.rapport()` ; méthode `majRapport(occupe)` qui pose ou retire
   `aria-disabled="true"` sur ce seul bouton (indépendant de `majOccupe` : un scan n'empêche pas
   d'ouvrir le rapport). Pas de nouvelle couleur ; style des boutons secondaires existants. Si
   la barre déborde à 360 px de large, le libellé reste entier (retour à la ligne permis).
4. **`app.js`** : `rapport()` : bouton désactivé pendant l'appel, `POST /api/rapport` sans corps
   avec le jeton, comme `scan`/`sync` ; 200 → annonce « Rapport de la semaine AAAA-Www ouvert
   dans le navigateur. » dans `#annonce` ; 409 → « Un rapport est déjà en cours. » ; autre
   erreur ou réseau → message d'erreur dans la zone d'erreur habituelle ; bouton réactivé dans
   tous les cas. Aucune donnée de la réponse insérée autrement que par `textContent`, et la
   semaine affichée seulement si elle a la forme `^\d{4}-W\d{2}$`.
5. **Docs** : `README.md` (bouton), `docs/` du serveur si elle liste les routes (AD-14).

## Critères d'acceptation
- **Given** l'appli ouverte avec sa clé, **When** on clique « Rapport de la semaine », **Then**
  `POST /api/rapport` génère `semaine-<courante>.html` et le faux navigateur reçoit une URI
  `file:` de ce fichier ; la réponse 200 ne contient ni `:\`, ni `/` de chemin, ni le nom du
  dossier ; le bouton est `aria-disabled` pendant l'appel puis réactivé ; `#annonce` porte le
  succès.
- **Given** une requête avec un corps, un paramètre, sans jeton, avec un mauvais jeton, un `Host`
  ou un `Origin` étrangers, ou en `GET`, **When** elle arrive sur `/api/rapport`, **Then** elle
  reçoit le même refus que `/api/scan` dans le même cas (matrice de 4.1 étendue à la route), et
  ni génération ni ouverture n'ont lieu.
- **Given** une génération en cours (verrou pris dans le test), **When** une seconde requête
  arrive, **Then** 409 « déjà en cours », aucune seconde génération ; après la première, une
  nouvelle requête réussit (verrou rendu, y compris après une erreur).
- **Given** une erreur de génération ou du navigateur, **When** la requête est traitée, **Then**
  500 avec un message fixe, sans chemin ni trace ; côté front, message d'erreur et bouton
  réactivé.
- **Given** la liste fermée des routes, **When** on la compare, **Then** elle contient
  exactement les routes d'avant plus `POST /api/rapport` (`tests/test_serveur.py`).
- **Given** un écran de 360 px et un zoom de 200 %, **When** la barre s'affiche, **Then** le
  bouton est visible, focalisable au clavier, son libellé entier (vérifié par `verif-front`).

## Tests
- `tests/test_serveur_rapport.py` (nouveau) : succès (faux navigateur, URI `file:`, réponse sans
  chemin), 409 par verrou, verrou rendu après erreur, 500 sans trace, matrice de refus.
- `tests/test_serveur.py` : liste fermée des routes et matrice de refus réalignées.
- Tests du front sous `tests/faux_dom.mjs` (`tests/test_web_*.py` de la barre et de l'app) :
  bouton présent après Sync, `aria-disabled` pendant l'appel, annonces 200/409/erreur, semaine
  de forme invalide non affichée, indépendance avec `majOccupe`.
- `tests/test_imports.py` (`serveur → rapport` : nouvelle arête, graphe du `CLAUDE.md`),
  `tests/test_publication.py`, `tests/test_web_statique.py` (aucune ressource externe).

## Fichiers touchés
`pilotage/serveur/rapport.py` (nouveau), `pilotage/serveur/routes.py`, `pilotage/serveur/cli.py`
(`configurer`), `pilotage/web/barre.js`, `pilotage/web/app.js`, la feuille de style de l'appli si
besoin (sans couleur en dur), `README.md`, `CLAUDE.md` (graphe), tests ci-dessus. Ni
`pilotage/rapport/` (sauf exposer la fonction de génération si la 9.3 ne l'a pas fait), ni
`pilotage/sync/`, ni les hooks.

## Décisions
- **Génération dans le processus du serveur** (fil de la requête, verrou de module) plutôt
  qu'un enfant détaché comme `scan`/`sync` : la page se génère en secondes, sans réseau, et
  l'ouverture doit suivre l'écriture. Le serveur est `ThreadingHTTPServer` : les autres routes
  restent servies pendant la génération.
- **URI construite par le serveur** depuis `chemins.rapport_semaine()` : le client n'envoie rien.
- **Version** : `v0.7.0` est publié par l'orchestrateur après la fusion (pas dans la story).

## Corrections après relecture Opus (2026-11-14) — priment sur ce qui précède
1. **Corps et paramètre** (l'epic exige un refus ; `/api/scan` n'en fait aucun) :
   - corps non vide sur `/api/rapport` → 400 `{"erreur": "corps refusé"}` (texte fixe), rien
     généré ni ouvert ;
   - paramètre de requête : si aucun appel du front (`app.js` et modules) n'envoie de `?…` vers
     `/api/`, `verifier_requete` refuse toute requête `/api/` qui porte un `?` (400, texte fixe),
     matrice de `tests/test_serveur.py` étendue ; sinon, refus limité à `/api/rapport` et le
     dire au rapport. Critères réécrits avec les statuts exacts.
2. **Erreurs** : `Reponse(500, erreur="rapport impossible")`, texte fixe, sans journal (aucun
   gestionnaire n'a accès au serveur) ; `ErreurConfiguration` reçoit le même message fixe (sa
   cause porte un chemin absolu).
3. **Tests du front** : créer `tests/test_web_barre.py` (sous `faux_dom.mjs`) : ordre des boutons,
   `majRapport`, `majOccupe` sans effet sur le bouton du rapport ; sortir le texte d'annonce dans
   une fonction pure `texteRapport(statut, corps)` testée sous node ; ajouter les nouveaux textes à
   `test_textes_exacts_de_l_epic` (`tests/test_web_statique.py`).
4. La table des routes s'appelle `TABLE` (pas `ROUTES`).
5. **Navigateur** : `webbrowser.open` qui rend `False` = échec ; page écrite mais non ouverte →
   500 `{"erreur": "page générée, ouverture impossible"}`. Documenter (README) que l'ouverture
   suit l'application associée aux `.html` et la variable `BROWSER`.
6. **Déterminisme** : `configurer(navigateur, maintenant=None)` (horloge injectable) ; fixture qui
   remet le module à son état initial après chaque test.
7. **Front, aligné sur `lancer()` d'`app.js`** : 401 → rien de plus (écran de session déjà
   affiché par `appeler`) ; 403 → `signalerRefus(403)` ; statut 0 → `TEXTE_INJOIGNABLE` ; après
   `await`, tester `arrete` ; garde `rapportEnCours` contre le double clic ; semaine de forme
   invalide → « Rapport de la semaine ouvert dans le navigateur. ».
8. **Réponses** : égalité exacte du JSON en 200, 400, 409 et 500 (aucun chemin possible).
9. **Graphe** : nouvelle arête `serveur → rapport` ; réécrire la phrase du `CLAUDE.md` sur qui
   importe `rapport` et `tests/test_imports.py`. AD-14 (spine hors dépôt) : mis à jour par
   l'orchestrateur après fusion.
10. Avant d'ouvrir : l'URI commence par `file:` et le nom suit `semaine-AAAA-Www.html`, sinon 500.
11. **Rétention** : non appliquée par le bouton (une seule semaine réécrite ; le prochain `sync`
    taille) : noté dans les Décisions.
12. Test : `GET /api/etat` répond pendant que le verrou du rapport est pris (faux générateur
    bloquant).
13. Le critère `v0.7.0` de l'epic est hors story (orchestrateur).
14. 360 px : `.droite` passe déjà à la ligne ; pas de CSS à ajouter, `verif-front` vérifie.
