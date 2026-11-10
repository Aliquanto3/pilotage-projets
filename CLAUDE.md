# pilotage-projets

Calcule et affiche l'action à mener sur chaque projet de `Documents\GitHub`
(stable, à stabiliser, en pause, à relancer, à classer), à partir des faits déposés par les
hooks Claude Code et le scan de chaque PC. Code sur `main` ; l'état partagé vit sur la branche `donnees` d'un dépôt privé séparé,
désigné par `depot_donnees` (`config.json`).

## Couches
- `pilotage/noyau/` : pur, bibliothèque standard sans E/S ni `subprocess`.
- `pilotage/chemins.py` : seule source des chemins, et `ecrire_atomique` (`.tmp` puis `os.replace`).
- `pilotage/hooks/` : un point d'entrée par événement, stdlib seule.
- `pilotage/scan/`, `sync/`, `serveur/` : outils, seuls à pouvoir importer PyYAML.
- `pilotage/installation/` : fusion de `settings.json`.
- `pilotage/web/` : HTML, JS, CSS statiques, charte locale (`charte.css`, `polices.css`), aucun CDN.
- `lancer.py` : sous-commandes, importe toutes les couches sauf hooks.

Graphe des imports (vérifié par `tests/test_imports.py`) : tout importe `noyau` ; tout sauf
`noyau` importe `chemins` ; `sync → scan`, `serveur → sync` ; rien d'autre entre couches.

## Commandes
- Lint : `uv run ruff check .`
- Tests : `uv run pytest -q --tb=short`
- Installation des dépendances : `uv sync --all-groups`
- Sous Windows : `uv run python`, jamais `python` nu.

## Règle des tests
`PILOTAGE_RACINE_LOCALE` redirige `attente/`, `donnees/`, `table-dossiers.json` et
l'installation. La fixture autouse de `tests/conftest.py` la pose sous `tmp_path` : aucun test
n'écrit dans `~/.claude/` ni dans `%LOCALAPPDATA%`.

`tests/test_sync_ps1.py` est propre à l'installation de l'auteur (dépôt de configuration privé qui
contient `sync.ps1`) : sauté en CI. Porte locale de l'auteur : avant toute fusion qui touche
`pilotage/installation/`, le jouer avec `PILOTAGE_SYNC_PS1=<claude-config>/sync.ps1` et
`PILOTAGE_EXIGER_SYNC_PS1=1` (script introuvable : échec au lieu du saut).

## Contrats partagés
- **C1** `lancer.py` : `scan`, `sync`, `appli`, `installer-reglages` délèguent, par import
  tardif, à `main(argv) -> int` de `pilotage/{scan,sync,serveur,installation}/cli.py`. Une story
  ne modifie que son `cli.py`.
- **C2** `pilotage/noyau/schemas/` : un module par validateur, qui expose
  `valider(objet) -> None` et lève `ErreurValidation` ; une ligne par validateur dans
  `REGISTRE` (`__init__.py`). `schemas.valider(nom, objet)` lève `SchemaInconnu` pour un nom absent.
- **C5** clés de `table-dossiers.json` : `pilotage.noyau.ids.cle_dossier(relatif: str) -> str`
  (`/`, sans `/` final, `casefold()`), appliquée par le scan, exigée par le validateur, et par les
  hooks au relatif de leur `cwd` ; doublon de casse : alerte `dossier-doublon-casse`.

## Charte graphique
Aucune couleur en dur : on les prend dans les fichiers de `pilotage/web/` (`charte.css`,
`polices.css`).
