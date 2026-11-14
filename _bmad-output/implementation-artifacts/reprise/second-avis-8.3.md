# Second avis 8.3 (diff f61ddb2..74a0639, Haiku)

1. medium · `noyau/texte.py:126` · `_CHEMIN_ABSOLU` ne voit `/` et `~` qu'en début de champ : « voir /c/Users/<nom>/… », « Relire ~/.claude/… », « /home/<nom>/… » passent et sont réinjectés sur d'autres PC.
2. medium · `hooks/depot.py:125` · une décision seule rafraîchit `ecrit` : un état ancien redevient « frais », la péremption de 14 jours est contournée.
3. medium · `outils/bench_hooks.py:257-262`, `tests/test_bench_hooks.py` · contrôle des messages affaibli (préfixe, au moins un ; code 0 ou 2 accepté).
4. low · `sync/copie.py:222-246` · verrou de rotation sans jeton, `unlink` inconditionnel : rotation lente qui efface l'ajout et le verrou de `Stop`.
5. low · `hooks/depot.py:194` · dépôt en run testé sur `cwd`, pas sur le dossier du projet.
6. low · `hooks/depot.py:201-209` · état le plus récent suspect ou vide : un état plus ancien d'un autre PC est pris au lieu d'omettre.
7. low · `noyau/cadrage.py:120-126` · U+2028 et U+2029 passent bruts dans le bloc injecté.
