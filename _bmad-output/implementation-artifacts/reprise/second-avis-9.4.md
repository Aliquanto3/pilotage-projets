# Second avis 9.4 (commit 62ecbc6, Haiku)

Aucun medium ni high ; 407 tests ciblés verts, ruff vert.
1. low · `tests/test_serveur_rapport.py:409-416` · la fixture libère le verrou après chaque test : un test qui ne le rend pas est masqué.
2. low · `tests/test_serveur_rapport.py:615-640` · `cli.main` installe le navigateur sans remise à zéro dans le test.
3. low · `tests/test_serveur_rapport.py:615-640` · `KeyError` qui masque la cause ; trois essais de port qui peuvent cacher un échec.
4. low · `serveur/appli.py:35` · contrôle sur `?` seulement (`#` non envoyé en HTTP, sans impact).
5. low · `tests/test_serveur.py:623` · `GET /api/inconnue?x=…` rend 400 au lieu de 404 : branche 404 de cette cible plus couverte.
