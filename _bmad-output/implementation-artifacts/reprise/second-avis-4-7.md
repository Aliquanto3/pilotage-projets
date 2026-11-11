# Second avis, story 4.7 (868749f, base 67780d8)

Haiku, lecture seule. Tests ciblés verts (334 + 136, Node 24, `PILOTAGE_EXIGER_NODE=1`), ruff vert.

- **medium** · `pilotage/noyau/etat.py` (`criteres`, ~425-470) contre `critere_manquant` (~121) : `criteres` somme les commits hors docs/chore, `critere_manquant` teste `any(n)` ; `_depot_lisible` n'exige pas n >= 0. Commits `{feat: 2, fix: -2}` : `critere_manquant` = « commits-depuis-release », `criteres` rend « commits » rempli. Données invalides seulement.
- **low** · `pilotage/web/app.js:85-87` (`sessionRemplacee`) : `vider(racine)` retire le dialog ouvert sans `close` ; `affiche` reste non nul ; au redémarrage, `ouvrirTiroir` ne rappelle pas `montrer()` si `dialog.open` reste vrai, donc non modal sous 1280 px. Raisonnement DOM, non exécuté.
- **low** · `pilotage/web/tiroir.js:207` (`majTiroir`) : aucun `maj` déclaré, statut des sessions et heures relatives figés pendant l'ouverture. Choix de spec.
- **low** · `pilotage/noyau/etat.py:500-510` (`_session_affichee`) : la liste blanche dit « ni identifiant de session », mais `session[:8]` sort déjà dans `raison.params` (~260) ; `note` (reprise) désormais exposée pour tous les projets à chaque `/api/etat`.
- **low** · `pilotage/web/app.js:397`, `appli.css:990` : marge sur `#racine` (barre et bandeaux décalés) au lieu de `main` (spec § 8). Écart déclaré.
- **nit** · `pilotage/web/chantiers.js:48-62` : dépendances aussi dans Découverts et Hors chantier (écart déclaré).
- **nit** · `chantiers.js:62`, `tiroir.js:95` : nom vide, le clic ouvre un tiroir sans titre.
- **nit** · `pilotage/noyau/etat.py:527-530` (`detail`) : `fuseau` vérifié mais inutilisé.

Vérifié sans défaut : `textContent` partout pour le texte non fiable ; un seul `dialog` ; focus au retour (origine, puis `retrouver`, puis `main`) ; seuil 80em ; tiroir non reconstruit au rafraîchissement ; Node exigé en CI ; tests isolés.
