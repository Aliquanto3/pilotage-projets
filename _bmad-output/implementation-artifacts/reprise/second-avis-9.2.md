# Second avis 9.2 (commit 83a26b5, Haiku)

1. medium · `cli.py:132`, `semaine.py:64` · `--semaine 9999-W52` : `OverflowError` non attrapée, traceback avec chemins absolus.
2. medium · `cli.py:146` · `_ERREURS` ne couvre ni `TypeError`, `KeyError`, `AttributeError`, `IndexError`, `OverflowError` levées par `lire_entree` / `synthese_semaine` : traceback.
3. medium · `cli.py:130` · `--semaine ""` traité comme absent (code 0) au lieu du code 2.
4. low · `lecture.py:21` → `scan/inventaire.py:17` · `import yaml` transitif (groupe `outils`) : `lancer.py rapport` échoue sans ce groupe.
5. low · `page.py:284` · `", ".join` matérialise toute la liste avant la borne (mémoire).
6. low · `tests/test_rapport_page.py:198` · échappatoire `or "{" in texte` dans l'assertion de borne.
