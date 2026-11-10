# Outils

Scripts hors runtime (`bench_hooks.py`, `publier_config.py`), ajoutés par leurs stories.

- `bench_hooks.py` (story 2.2) : `uv run python outils/bench_hooks.py [--python CHEMIN] [--appels 50] [--messages 3]`,
  p50 et p95 de chaque hook hors premier appel, sous une racine temporaire ; code 2 si un p95
  dépasse 100 ms. `--messages N` (story 5.3) : N messages en attente remis à chaque
  `SessionStart` ; `--operations-autres N` : N opérations d'un autre projet en attente (écartées).
- `publier_config.py` (story 2.8) : `uv run python outils/publier_config.py <tag> --vers <claude-config>`,
  copie en miroir le runtime du tag vers `claude-config/claude/pilotage/` (voir `docs/installation.md`).
