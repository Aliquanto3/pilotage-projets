# Revue 9.2 (Opus)

## Passe 1 (2026-11-14, SHA revu 83a26b5, base f61ddb2 à jour, CI verte ; après correctifs fb168c7 CI verte)

- Important · medium · second avis 1 · accepté, corrigé (fb168c7) · `--semaine 9999-W52` : `bornes_semaine` lève `OverflowError` (lundi + 7 j hors de `date`), traceback avec chemins absolus. Reproduit. Désormais code 2 et message de semaine invalide ; cas ajouté au test paramétré.
- Important · medium · second avis 2 · accepté, corrigé (fb168c7) · `_ERREURS` ne couvre pas `KeyError`/`TypeError`/`AttributeError`… de `lire_entree`/`synthese_semaine`. Filet final `except Exception` : `ERREUR (inattendue : <type>)`, code 1, rien écrit ; testé par injection de panne (`KeyError` dont le message porte un chemin, absent de stderr).
- Important · medium · second avis 3 · accepté, corrigé (fb168c7) · `--semaine ""` prenait la semaine courante (`or`) : désormais `is not None`, code 2 ; cas ajouté au test paramétré.
- Nit · low · second avis 4 · rejeté · `import yaml` transitif par `lecture.py` → `scan` : même exigence que `scan`/`sync`/`appli` (groupe `outils`), que le runtime installe (`uv sync --frozen --no-dev --group outils`, docs/installation.md) et que la CI installe (`--all-groups`). Aligné, rien à changer.
- Nit · low · second avis 5 · rejeté · `", ".join` des phases : la liste est déjà en mémoire (JSON chargé), coût linéaire ; la borne porte sur la sortie, ce qui suffit.
- Nit · low · second avis 6 · accepté, corrigé (fb168c7) · échappatoire `or "{" in texte` : un texte hostile contenant `{` échappait à la borne. Le parseur de test met à part le texte du `<style>` ; assertion sans exception ; hostile `{yyy…}` ajouté (vert : la borne tient).
- Nit · low · écart Réalisation (bornes 50 pour les identifiants, 128 phases) · accepté · mesuré : pire cas 1,73 Mo sous 2 Mo ; identifiants (projet, PC, code, tag, horodatage) tiennent largement en 50.
- Nit · low · écart Réalisation (nettoyage des alertes dans `cli.py`) · accepté · garde `page.py` pur (imports vérifiés par AST) ; testé (`test_alerte_ancienne_avec_chemin_masquee`).
- Nit · low · écart Réalisation (monkeypatch de `chemins.racine_web`) · accepté · ne remplace que l'emplacement d'un fichier lu, le code de rendu et de refus s'exécute réellement.
- Complexité : 0 constat (tables et listes en O(n), coupées à 200 lignes).
- Sécurité vérifiée : CSP juste après `charset`, aucun attribut dynamique, `_texte` unique (Cc/Cf retirés, substituts remplacés), feuille refusée sur `<`, `\`, `url(`, `@import`, `expression(` ; messages d'erreur sans `str(exc)`.
- Emplacement des rapports (`chemins.rapports()`, racine locale) : non modifié, en attente de l'utilisateur.

Tests : ruff vert ; `tests/test_rapport_*.py`, `test_chemins`, `test_lancer`, `test_imports`, `test_publication` : 208 passés. Les trois nouveaux cas échouent sur 83a26b5.

## Passe 2 (2026-11-14, SHA revu fb168c7, base f61ddb2 à jour, CI verte)

Relu : `git diff 83a26b5 fb168c7` (pilotage/rapport/cli.py, tests/test_rapport_cli.py, tests/test_rapport_page.py).

- Correctif OverflowError · tient · `9999-W52` → code 2, rien écrit (test paramétré + `lancer.py rapport` réel). `9999-W51` (bornes valides, calcul en aval hors de `date`) retombe sur le filet : code 1, sans traceback.
- Correctif filet · tient · `except Exception` ne capture ni `SystemExit` (argparse, hors du `try`) ni `KeyboardInterrupt` ; message `ERREUR (inattendue : <type>)`, jamais `str(exc)` ; `.tmp` supprimé par `ecrire_atomique` (`except BaseException` + `unlink`) avant que le filet n'attrape ; test d'injection : stderr exact, dossier des rapports absent.
- Correctif `--semaine ""` · tient · `is not None`, code 2 (test paramétré et exécution réelle).
- Nit · low · reviewer · noté, non corrigé · `test_semaine_extreme_sans_traceback` accepte `0 ou 1` : il ne prouve que l'absence de traceback, ce qui est son but. `0001-W01` donne code 1 (et non 2) alors que la semaine existe : acceptable, la semaine est hors des données possibles.
- Nit · low · reviewer · accepté · l'injection de panne remplace `semaine.synthese_semaine` (module interne) : seul moyen de provoquer une exception hors de `_ERREURS` ; le chemin réel (lecture, rendu, écriture) reste couvert par les autres tests.
- Complexité : 0 constat.

Tests : ruff vert ; `tests/test_rapport_cli.py tests/test_rapport_page.py tests/test_publication.py` : 50 passés. Aucun correctif, SHA final fb168c7.
