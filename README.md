# pilotage-projets

Tableau de bord local qui suit les projets d'un dossier `Documents\GitHub` et les sessions
Claude Code menées en parallèle sur plusieurs PC. Pour chaque projet, il dit quoi reprendre :
stable, à stabiliser, en pause, à relancer ou à classer. L'appli s'ouvre dans le navigateur, sur
`127.0.0.1`.

<!-- Capture d'écran : à ajouter ici (données fictives). -->

## Statut

Outil personnel de son auteur, en version 0.3.0, en développement. Il ne tourne que sous Windows
et il est publié sans support : pas de garantie, et les issues ou demandes de fonctionnalité ne
seront pas forcément traitées. Les commandes de ce fichier ont été vérifiées contre le code ; le
parcours d'installation complet sur un PC neuf, avec un autre compte GitHub que celui de l'auteur,
n'a pas été rejoué.

## Comment ça marche

1. Des hooks Claude Code (début et fin de session, prompt, notification) écrivent de petits
   fichiers d'état dans un dossier local (`%LOCALAPPDATA%\pilotage-projets` par défaut).
2. Un scan lit les dépôts git de `Documents\GitHub` (branches, commits récents, informations de
   `gh`).
3. `lancer.py sync` copie ces faits dans un clone local de la branche `donnees` d'un dépôt GitHub
   **privé à vous**, puis pousse. Une tâche planifiée la relance toutes les 15 minutes ; chaque PC
   pousse ses propres fichiers.
4. `lancer.py appli` lit ce clone et affiche l'état de tous vos PC dans une appli web locale.

Le code (ce dépôt) et les données (le dépôt privé) sont deux dépôts séparés.

## Prérequis

- Windows 11 (PowerShell).
- [uv](https://docs.astral.sh/uv/) et Python 3.14 (uv peut l'installer : `uv python install 3.14`).
- git, avec une identité (`git config --global user.name "…"` et
  `git config --global user.email "…"`) : la synchro crée des commits dans le clone de données.
- [GitHub CLI](https://cli.github.com/) `gh`, authentifié (`gh auth login`) : la synchro s'en sert
  pour vérifier que le dépôt de données est privé.
- Un accès HTTPS à GitHub sans invite, par exemple `gh auth setup-git` (gh devient l'assistant
  d'identification de git) : la synchro lance git avec les invites coupées
  (`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`), donc un clone ou un push qui demanderait
  un mot de passe échoue au lieu d'attendre.
- Claude Code.

## Installation

1. **Dépôt de données.** Sur GitHub, créez un dépôt **privé** (par exemple
   `<votre-login>/pilotage-projets-donnees`) et donnez-lui une branche `donnees` avec au moins un
   commit : la synchro clone cette branche seule et ne la crée pas.
   ```powershell
   gh repo create <votre-login>/pilotage-projets-donnees --private
   git clone https://github.com/<votre-login>/pilotage-projets-donnees.git $env:TEMP\donnees-init
   cd $env:TEMP\donnees-init
   git switch --orphan donnees
   git commit --allow-empty -m "init"
   git push origin donnees
   ```
2. **Le code et son environnement.** Clonez ce dépôt dans `~/.claude/pilotage` (dossier absent ou
   vide : c'est la racine installée par défaut), puis installez les dépendances de l'outil :
   ```powershell
   git clone https://github.com/Aliquanto3/pilotage-projets.git $HOME\.claude\pilotage
   cd $HOME\.claude\pilotage
   uv sync --group outils --no-dev
   ```
3. **Réglages.** Cette commande écrit `~/.claude/pilotage/config.json` et fusionne les hooks dans
   `~/.claude/settings.json` (une copie `settings.json.avant-pilotage-<date>` est gardée, le reste
   du fichier n'est pas touché) :
   ```powershell
   uv run python lancer.py installer-reglages `
     --config "$HOME\.claude\pilotage\config.json" `
     --racine-github "$HOME\Documents\GitHub" `
     --proprietaire <votre-login> `
     --depot-donnees <votre-login>/pilotage-projets-donnees `
     --utilisateur "Votre nom"
   ```
   `--config` et `--racine-github` vont ensemble ; `--proprietaire`, `--depot-donnees` et
   `--utilisateur` ne s'emploient qu'avec `--config`. Sans `--racine`, la racine installée est
   `~/.claude/pilotage` ; sans `--python`, l'interpréteur est `<racine>\.venv\Scripts\python.exe`
   (celui créé par `uv sync` à l'étape 2), sauf si `config.json` en désigne déjà un.
   `--proprietaire` (login GitHub du propriétaire des projets) et `--depot-donnees` (`login/nom`)
   sont facultatifs pour cette commande, qui réussit sans eux (une valeur déjà présente dans
   `config.json` est gardée) ; mais sans ces deux valeurs dans `config.json`, le scan et la
   synchro échouent ensuite avec un message qui demande de relancer l'installation.
   `--utilisateur` (nom affiché) est facultatif. Redémarrez Claude Code pour que les hooks soient pris en compte.
4. **Tâche planifiée.** Le dépôt ne la crée pas : créez-la vous-même, par exemple toutes les
   15 minutes, sans console (`pythonw`) et avec `-I` :
   ```powershell
   $action = New-ScheduledTaskAction `
     -Execute "$HOME\.claude\pilotage\.venv\Scripts\pythonw.exe" `
     -Argument "-I `"$HOME\.claude\pilotage\lancer.py`" sync"
   $declencheur = New-ScheduledTaskTrigger -Once -At (Get-Date) `
     -RepetitionInterval (New-TimeSpan -Minutes 15)
   Register-ScheduledTask -TaskName "pilotage-projets-sync" -Action $action `
     -Trigger $declencheur -Force
   ```
   Cette commande est un exemple, pas rejoué tel quel (`-Force` remplace une tâche du même nom).
5. **Premier tour.**
   ```powershell
   uv run python lancer.py scan    # inventaire de ce PC, rien n'est poussé
   uv run python lancer.py sync    # scan, copie, commit et push vers la branche donnees
   uv run python lancer.py appli   # ouvre l'appli dans le navigateur (127.0.0.1)
   ```
   `scan` et `sync` acceptent `--racine-github` et `--pc` ; `appli` accepte `--port` (47615 par
   défaut) et `--sans-sync`.

L'auteur publie le runtime vers un dépôt de configuration privé et le restaure sur chaque PC avec
un script qui n'est pas dans ce dépôt. C'est sa façon de faire, pas la seule : voir
`docs/installation.md`.

## Ce qui est poussé, ce qui ne l'est jamais

Ce qui part vers la branche `donnees` du dépôt privé :

- des métadonnées : nom du projet, nom du PC, identifiant de session, dossier relatif, branche
  git, horodatages, statut ; l'inventaire des projets (compteurs et faits `git`/`gh`) ;
- deux textes libres tirés de la session : le texte court d'une attente (question posée,
  permission demandée ; 200 caractères au plus) et la **note de reprise** (300 caractères au
  plus), que Claude (le modèle) rédige dans son dernier message pour dire où reprendre, et qui
  peut donc citer le contenu de la session ;
- les messages que vous déposez vous-même depuis l'appli (2 048 octets au plus).

Ces textes passent par un filtre de motifs de secrets (`pilotage/noyau/texte.py`) : la racine
`Documents\GitHub` est remplacée par `{{RACINE_GITHUB}}`, une note ou une attente qui contient un
motif (`ghp_`, `sk-`, `Bearer`, `TOKEN=`…) n'est pas transmise, un message qui en contient un est
refusé. Ce filtre vise la fuite accidentelle d'un jeton, pas le reste du contenu : relisez ce que
Claude écrit dans ses notes de reprise si vos sessions touchent des données sensibles.

Ce qui n'est jamais poussé : le texte de vos prompts (les hooks ne gardent que la date du
dernier). La synchro refuse de pousser si `gh` ne confirme pas que le dépôt de données est privé,
avant le clone et de nouveau avant le push.

Écrit seulement en local, jamais copié vers le dépôt de données, et seulement si vous le lancez à
la main : `outils/extraire_jeu.py` copie des fins de tour tirées des transcriptions (le dernier
message de l'utilisateur compris, passé par le même filtre) sous
`%LOCALAPPDATA%\pilotage-projets\jeu-etiquete\` ; la capture de payloads de
`docs/capture-payloads.md`, faite hors de l'outil, a gardé des payloads bruts sous
`%LOCALAPPDATA%\pilotage-projets\capture\`. Détail et limites : `docs/securite.md`.

## Couper et rallumer les hooks
Les hooks de session vérifient d'abord le fichier `~/.claude/pilotage/desactive` : s'il existe,
ils sortent aussitôt (code 0), sans rien lire ni écrire.

- Couper (PowerShell) : `New-Item -ItemType File "$HOME\.claude\pilotage\desactive"`
- Rallumer : `Remove-Item "$HOME\.claude\pilotage\desactive"`

Sous `PILOTAGE_RACINE_LOCALE` (tests), le fichier est `<racine>\installation\desactive`.
Les erreurs des hooks vont dans `attente\journal\hooks-AAAA-MM.log` (événement et type d'erreur).

## Limites connues

- Windows seulement (chemins, tâche planifiée, mutex, `pythonw`).
- Python 3.14 exact (`requires-python = ">=3.14,<3.15"`).
- Un dépôt de données privé est nécessaire à la synchro entre PC.
- Pas de script d'installation ni de désinstallation : les étapes ci-dessus sont manuelles.
- Les noms locaux `%LOCALAPPDATA%\pilotage-projets` et `~/.claude/pilotage` sont fixes.
- Les formats des hooks de Claude Code évoluent : une mise à jour de Claude Code peut casser la
  capture (voir `docs/capture-payloads.md`).

## Développement

```powershell
uv sync --all-groups
uv run ruff check .
uv run pytest -q --tb=short
```

Les tests redirigent toutes leurs écritures sous un dossier temporaire (`PILOTAGE_RACINE_LOCALE`) :
ils n'écrivent ni dans `~/.claude/` ni dans `%LOCALAPPDATA%`. Les consignes pour Claude Code sont
dans `CLAUDE.md`.

## Licence

Code sous licence Apache-2.0 (fichier `LICENSE`). Les polices embarquées dans
`pilotage/web/polices/` (Atkinson Hyperlegible, JetBrains Mono, Sora) sont sous licence SIL
OFL 1.1 ; leurs textes sont dans `pilotage/web/polices/OFL-*.txt`.
