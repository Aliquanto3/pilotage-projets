# Second avis 9.1 (commit 285524a, Haiku)

1. medium · `lecture.py:61-66` · `git ls-tree` sans `-z` cite les chemins non ASCII : sessions d'un projet accentué perdues.
2. medium · `lecture.py:164-165`, `semaine.py:58-59` · fuseau en décalage fixe pris au lundi : heure de trop ou orpheline aux changements d'heure (W13, W43) ; non testé.
3. medium · `semaine.py:124-141` · « tag daté dans la semaine » remplacé par « tag nouveau depuis l'instantané d'avant lundi » : écart à la spec.
4. medium · `lecture.py:143-153,173` · seules les archives locales sont lues ; sessions archivées des autres PC absentes.
5. medium · `CLAUDE.md`, `tests/test_imports.py:21` · nouvelle arête `rapport → scan` hors spec.
6. low · `lecture.py:176`, `semaine.py:92-95,135` · `message` d'alerte, `tag`, `topics` non passés par le filtre.
7. low · `lecture.py:69,73` · un `git show` par fichier, sans budget global.
8. low · `lecture.py:169-170` · fin de semaine remplacée en silence par l'état courant.
