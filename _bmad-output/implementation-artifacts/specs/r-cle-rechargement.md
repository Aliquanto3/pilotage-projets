---
story: "r-cle"
titre: Clé d'accès gardée le temps d'un rechargement
status: ready-for-dev
date: 2026-11-11
---

# Correctif r-cle : clé d'accès gardée le temps d'un rechargement

Source : recette de l'accueil du 2026-11-11 (rechargement par le bouton du navigateur → écran
« Clé d'accès perdue ») ; décision de l'utilisateur du 2026-11-11 ; AD-14 § Jeton et
EXPERIENCE § Clé d'accès, amendés le même jour. Passe après 4.7 (même `app.js`), avant le tag
`v0.4.0`.

## Règle (AD-14 amendé)
- Le jeton vit dans une variable JS. Il ne passe en `sessionStorage`, clé `pilotage-cle`, qu'au
  déchargement (`pagehide`). Au chargement, et à `pageshow` quand `event.persisted` est vrai, la
  page le relit puis l'efface aussitôt. Aucun `localStorage`, aucun cookie.
- Un fragment d'URL valable l'emporte sur le stockage ; le stockage est effacé dans tous les cas.
- Un jeton relu du stockage et refusé par le serveur (401 à la première lecture) mène à l'écran
  « Clé perdue », pas à « Une autre fenêtre de l'appli a été ouverte ».
- Après « session remplacée » ou tout arrêt (`arreter()`), rien n'est écrit à `pagehide`.
- Tout accès au stockage est dans un `try/catch` : stockage absent ou qui lève → comportement
  d'avant (clé perdue au rechargement), sans erreur.

## À livrer
- `pilotage/web/app.js` : `lireCle()` rend `{ jeton, origine: "fragment" | "stockage" }` ou
  `null` ; écouteurs `pagehide` et `pageshow` ; branchement du 401 initial selon l'origine.
  Le jeton reste dans ce seul module.
- `pilotage/web/cle.js` : phrase de l'écran « Cette page n'a plus de clé valable. Relancez
  l'appli depuis un terminal. » (titre, commande et bouton inchangés).
- `tests/test_web_statique.py` : `sessionStorage` permis seulement dans `app.js` et seulement
  avec la clé littérale `pilotage-cle` ; `localStorage` et `document.cookie` toujours refusés
  partout. Mettre à jour le cas de test de la ligne qui attend un refus de `sessionStorage`.

## Critères d'acceptation
1. Recharger par le bouton du navigateur garde l'appli ouverte, avec ses données.
2. Après le chargement, `sessionStorage` ne contient plus `pilotage-cle`.
3. Fragment et stockage présents : le fragment gagne, le stockage est vidé.
4. Serveur relancé puis onglet rechargé : écran « Clé perdue », stockage vidé.
5. Onglet « session remplacée » puis rechargé : écran « Clé perdue » (rien n'a été écrit).
6. `sessionStorage` qui lève : aucune erreur, écran « Clé perdue » au rechargement.

## Tests
- JS sous Node (même banc que les tests web existants, `window`, `sessionStorage` et `fetch`
  simulés) : un test par critère 2 à 6, plus `pageshow` persisté qui efface le stockage.
- Python : `tests/test_web_statique.py` (motifs ci-dessus, cas positif et négatif).
- `uv run pytest -q tests/test_publication.py` vert.

## Fichiers touchés
`pilotage/web/app.js`, `pilotage/web/cle.js`, `tests/test_web_statique.py`, tests JS d'`app.js`.
Aucun changement serveur.
