# Second avis 8.2 (commit 493383d, Haiku)

Aucun medium ni high. Tests ciblés 308 verts, `test_sync_ps1.py` (porte locale) 19 verts, ruff propre.
1. low · `pre_compact.py:32` · script retiré pendant une session : Python sort en 2, compaction bloquée ; la garde ne joue qu'à l'installation.
2. low · `docs/installation.md:41-42` · phrase fausse sur l'ordre de `sync.ps1` (la copie du runtime précède la fusion).
3. low · `docs/capture-payloads.md:57` · chemin absolu générique (`C:/Program Files/Git/compact`).
4. low · `fusion.py:377-378` · garde avant le test « déjà à jour » : code 1 sur un poste où un script manque.
