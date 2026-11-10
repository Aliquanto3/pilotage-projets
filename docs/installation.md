# Publication et installation du runtime

Installation à la main : voir le `README.md`. Ce document décrit la façon de faire de l'auteur :
les PC exécutent une version figée du runtime, publiée dans un dépôt de configuration privé
(`claude-config`), jamais le clone de développement. Ce n'est pas la seule façon d'installer l'outil.

## Publier une version
1. Mettre `VERSION` et `pyproject.toml` au même numéro, `uv lock`, fusionner sur `main`.
2. Tag annoté `vX.Y.Z` sur `main`, release GitHub avec notes.
3. `uv run python outils/publier_config.py vX.Y.Z --vers <claude-config>` : copie en miroir,
   depuis le tag (`git archive`, jamais la copie de travail), `pilotage/`, `lancer.py`,
   `pyproject.toml`, `uv.lock`, `VERSION`, `hooks-pilotage.json`, `regle-marqueur.md` vers
   `claude-config/claude/pilotage/`. Refus (code 1, rien écrit) : tag absent ou non SemVer,
   `VERSION` du tag différent, copie de travail sale (source ou `claude-config`).
4. Commiter et pousser `claude-config`.

## Installer sur un PC : `sync.ps1 restaurer`
`sync.ps1` est le script du dépôt de configuration de l'auteur ; il n'est pas dans ce dépôt.
Les clés d'identité (`proprietaire_github`, `depot_donnees`, `utilisateur`) restent dans
`config.json` d'une installation à l'autre ; au premier PC, les donner avec `--proprietaire`,
`--depot-donnees` et `--utilisateur` (voir le `README.md`).

Copie de `CLAUDE.md`, de `github/CLAUDE.md` et des mémoires (inchangé), puis, si
`claude/pilotage/` est publié :
1. `robocopy /MIR` vers `~/.claude/pilotage/`, hors `.venv`, `__pycache__`, `config.json` et
   `desactive` ;
2. `uv python install 3.14`, `uv sync --frozen --no-dev --group outils --managed-python` ;
3. et 4. `lancer.py installer-reglages --depuis <réglages du dépôt> --config <config.json>
   --racine-github <racine>` : valide `config.json` (`python`, `pythonw`, `racine_github`,
   `port` à 47615 si absent), fusionne les hooks du pilotage dans `settings.json`, puis
   écrit `config.json` (seulement si la fusion a réussi).

Sans runtime publié mais avec un runtime déjà installé (`~/.claude/pilotage/lancer.py` et son
`.venv`), `restaurer` refait seulement l'étape 3 et 4 avec ce runtime : les hooks du pilotage
locaux restent en place. Sans runtime du tout, `settings.json` est celui du dépôt (sans hooks du
pilotage).

`settings.json` n'est écrit qu'à la fin, atomiquement : uv absent ou une étape en échec laisse
`settings.json` inchangé, avec un message et un code non nul. Deux `restaurer` de suite donnent
les mêmes octets.

## Tâche planifiée (story 3.5)
Après la fusion des réglages (runtime publié seulement), `restaurer` supprime puis recrée la tâche
`pilotage-projets-sync` : toutes les 15 min, utilisateur connecté, sans élévation,
`MultipleInstances IgnoreNew`, démarrage et maintien sur batterie, rattrapage d'un déclenchement
manqué (`StartWhenAvailable`), arrêt après 10 min, action `pythonw -I <racine installée>\lancer.py
sync` (`lancer.py` ajoute lui-même son dossier à `sys.path`, que `-I` omet). Deux `restaurer`
donnent une seule tâche. Enregistrement en échec : code non nul, relancer `restaurer`. Tests :
`-SansTache` construit la tâche sans l'enregistrer (`TACHE-JSON: ...`) ; `-JournalTache <fichier>`
suit la branche d'enregistrement, valide les objets par `New-ScheduledTask` et journalise les appels. Vérifier : `Get-ScheduledTask pilotage-projets-sync`.

## `sync.ps1 sauver`
Lecture de `settings.json` en JSON, retrait des entrées du pilotage, sérialisation (par le runtime
installé : `installer-reglages --exporter-sans-pilotage`), puis remplacement de la racine GitHub
par `{{RACINE_GITHUB}}`. Toute entrée dont le script est sous un `*/pilotage/hooks/` est retirée,
quelle que soit sa racine (clone de dev compris) ; l'installation, elle, ne retire que les hooks
de la racine installée. Si le texte exporté contient encore `pilotage/hooks` (commande shell non
reconnue), ou si le runtime est absent et que `settings.json` en contient : refus, rien n'est sauvé.

## Fenêtres de console
Aucune fenêtre de console : `pythonw` (tâche et synchro détachée des hooks) n'a pas de console, donc tout enfant console (`git`, `gh`, `taskkill`, `tasklist`) en ouvrirait une neuve. Tout `subprocess` de `pilotage/` passe `**chemins.options_sans_fenetre()` (`CREATE_NO_WINDOW` sous Windows) ; `tests/test_sans_fenetre.py` le garde par AST. Deux exceptions : `_lancer_detache` (`DETACHED_PROCESS`, incompatible) et le `Popen` de `serveur/enfants.py`, qui combine `CREATE_NO_WINDOW` avec `CREATE_NEW_PROCESS_GROUP` (vérifié par `tests/test_serveur_enfants.py`).
