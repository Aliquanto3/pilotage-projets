# Second avis, story 5.5 (d7dfb74, base a24104f)

Haiku, lecture seule. Tests ciblés : 294 passés.

1. **medium** · `tests/test_web_accueil.py:463` (garde) et `pilotage/web/appli.css` (`pre.brief`, `overflow-y: auto`) · certain : la garde `overflow(-x)?:\s*(scroll|auto)` ne voit pas `overflow-y` ; le défilement vertical du brief passe sans exception nommée, alors que la spec dit `overflow: auto`. Garde affaiblie en silence.
2. **low** · `pilotage/web/tiroir.js` (`construire`) et `reprise.js` (`rendre`) · certain : chaque ouverture du tiroir fait un POST `/api/reprise`, donc un brief écrit dans `attente/briefs` (et un par `change`), sans déduplication, même pour une ouverture sur une autre section. Conforme à la spec (« à chaque affichage »), pas de boucle (`majTiroir` n'appelle pas `rendre`).
3. **low** · `tests/test_web_accueil.py`, fixture `_executer_reprise` · certain : littéraux `"C:\briefs\b.md"` (`\b` = retour arrière) et `"D:\demo"` corrompus ; aucune assertion ne les lit.
4. **nit** · `tests/test_web_accueil.py:321-322` : exception de troncature `brut.slice(0, fin)` pour reprise.js, chaîne exacte, une occurrence : étroite.

Vérifié sans défaut : commande du serveur passée telle quelle à `blocCommande` ; `_cite` refuse apostrophes et Cc/Cf/Zl/Zp ; `el()`/`textContent` seulement ; jeton dans app.js ; `routes.py` inchangé (C4) ; `dossier` par `joindre_sous`, `chemin_brief` par `chemins.briefs()`, refus avant écriture ; réponses tardives filtrées (numéro, `tiroirOuvert()`, `document.contains`) ; un seul `btn1` ; aucune fuite ; écritures sous `PILOTAGE_RACINE_LOCALE`.
