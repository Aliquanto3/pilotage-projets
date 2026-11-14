# Revue 8.2 (reviewer Opus)

## Passe 1 (2026-11-14, SHA revu 493383d, base origin/main 12e096d, CI verte ; correctif d3216b4, CI verte, run 43626802266)

Diff suivi jusqu'aux appelants : `hooks-pilotage.json` → `fusion.EVENEMENTS`/`controler_modele` → `installer` → `installation/cli.py` (seul appelant) → `sync.ps1` (`Fusionner-Pilotage`). `SessionStart` et `_commun` non touchés : le diff ne peut pas ralentir `SessionStart`. Hook rejoué en vrai sous-processus par les tests (fixture réelle `PreCompact-manuel.json`, `trigger` manual et auto, `agent_id`, hors racine, non suivi, payload invalide, `desactive`). Critères d'acceptation couverts : consigne fixe, silence en sous-agent et dossier non suivi, idempotence (`test_sync_ps1.py` 19 verts en local), banc (entrée `pre_compact`, contrôle texte brut).

- Nit · low · second avis 1 · documenté · script retiré pendant une session : code 2, compaction bloquée. Réel, mais hors de portée d'un hook (Python sort avant d'exécuter le script) ; même risque déjà présent pour `Stop`. Doc d'installation complétée : retirer les hooks ou poser `desactive` avant de supprimer le runtime.
- Nit · low · second avis 2 · accepté, corrigé (d3216b4) · la phrase « runtime restauré plus ancien … si `sync.ps1` le copie après coup » était fausse : `restaurer` copie le runtime (étape 1) avant la fusion (étape 3), et le modèle lu est celui du runtime installé, donc un runtime ancien n'ajoute pas d'entrée `PreCompact`. Phrase remplacée.
- Nit · low · second avis 3 · accepté, corrigé (d3216b4) · `C:/Program Files/Git/compact` : chemin générique d'une installation de Git, aucune donnée personnelle ; remplacé par `<dossier de Git>/compact` par prudence (dépôt public).
- Nit · low · second avis 4 · rejeté · garde avant le test « déjà à jour » : un `settings.json` qui référence déjà un script absent est précisément l'état qui bloque les compactions ; un code 1 (et le `throw` de `sync.ps1`, « settings.json n'a pas été modifié ») le signale au lieu de le taire. Comportement voulu.
- Complexité : 0 constat (consigne fixe, aucune structure qui grossit ; `controler_scripts` en O(nombre d'événements)).
- Sécurité : consigne fixe, aucune donnée du payload ni de la session réémise (`custom_instructions` non lu), rien d'écrit, pas d'appel réseau. Aucun constat.

### À valider par l'utilisateur avant fusion
- Effet de comportement : sur chaque projet suivi, toute compaction (manuelle et automatique) reçoit désormais la consigne du pilotage en plus des instructions de l'utilisateur. Essai réel : les deux sont gardées.
- Protocole : supprimer `~/.claude/pilotage/` sans retirer ses hooks de `settings.json` bloquerait les compactions (code 2) ; la doc le dit, aucun script de désinstallation.
- Compaction d'un sous-agent et `trigger=auto` non observés en réel (garde `agent_id` et test `auto` sur payload construit).

Tests locaux : ruff propre ; ciblés 327 verts + 1 sauté (compaction, installation, règle du marqueur, fixtures, hooks session, imports), `test_bench_hooks.py` + `test_publication.py` 17 verts, `test_sync_ps1.py` porte locale 19 verts.
