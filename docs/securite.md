# Sécurité du serveur local

Règles appliquées par le code du serveur local (`lancer.py appli`), qui n'écoute que sur
`127.0.0.1`. Chaque règle a son test (`tests/test_serveur*.py`).

## Toute requête (`serveur/appli.py`)

Ordre des contrôles, pour toute méthode et toute cible :

1. `Host` ∈ {`127.0.0.1:<port>`, `localhost:<port>`}, sinon 403 ;
2. `Origin` présent et différent de l'appli : 403 ;
3. préfixe `/api/` : `Authorization: Bearer <jeton>` (aléatoire, 256 bits, régénéré à chaque
   lancement, comparé à temps constant), sinon 401 ;
4. routage sur la table fermée (`serveur/routes.py`) : route inconnue 404, méthode non permise
   405 avec `Allow`, identifiant du chemin invalide 400.

Corps borné à 64 Kio (413 au-delà), lu après le jeton seulement. Sans jeton, seuls `/` et les
fichiers statiques de `pilotage/web/` sont servis ; ils ne contiennent aucune donnée de projet.
Les lectures (`GET`) n'ont aucun effet : ni écriture, ni mutex, ni processus.

## Mutations (`POST /api/message`, `POST /api/projets`)

- Corps JSON strict (clé dupliquée, `NaN`, autre chose qu'un objet : 400), champs fermés.
- Identifiants énumérés, jamais de chaîne libre : `projet` et `pc` validés par
  `noyau/ids.py` ; un identifiant avec `'; calc; '`, `$(…)`, guillemets ou retour à la ligne
  est refusé.
- Un projet n'est accepté que s'il figure dans l'état chargé **et** dans `projets.yaml` ou
  `table-dossiers.json` ; un PC visé doit avoir un instantané. Sinon 400.
- Message : non vide, 2 048 octets UTF-8 au plus, le serveur fait foi ; un message qui
  contient un motif de secret (filtre de `noyau/texte.py`) est refusé, jamais altéré.
- Tout refus rend 400 sans rien écrire.
- L'opération (id généré par le serveur) est écrite dans `attente/operations/<id>.json`
  par création seule : contenu complet écrit dans un `.tmp` voisin puis publié (lien physique,
  ou réservation exclusive du nom puis remplacement), jamais d'écrasement, jamais de fichier
  tronqué visible, jamais d'écriture dans `donnees/`, que seul `sync` modifie. Écriture
  impossible : 503, rien laissé, cause au journal des enfants.
- Puis `sync` est lancée en tableau d'arguments, sans shell (`serveur/enfants.py`). Cycle occupé :
  une seule relance en file, au plus 5 fois par série (une mutation reçue pendant la série ne
  remet pas le compteur à zéro), de 2 s à 30 s ; au-delà, abandon journalisé et l'opération
  attend le cycle planifié.

## Commandes de reprise (`serveur/reprise.py`, story 5.4)

- `GET /api/sessions/<projet>` : sessions lues sans effet (ce PC dans `attente/etat/`, les
  autres dans `donnees/etat/`), validées par le schéma `session` et à leur place ; projet absent
  de l'état chargé : 404.
- `POST /api/reprise` : corps JSON fermé `{projet, session, pc}`, identifiants validés par
  `noyau/ids.py` (`'; calc; '`, `$(…)`, guillemets, retour à la ligne : 400, rien d'écrit) puis énumérés
  (projet de l'état chargé, session présente pour ce PC). Aucune chaîne libre.
- Le chemin est reconstruit côté serveur par `chemins.joindre_sous` (résolu, sous la racine
  GitHub) et cité entre apostrophes ; un chemin qui contient une apostrophe (`'`, ou `‘ ’ ‚ ‛`,
  lues comme telles par PowerShell), un caractère de contrôle, de format (bidi, espace
  de largeur nulle) ou un séparateur de ligne est refusé (400).
- Formes rendues, jamais exécutées : `Set-Location -LiteralPath '<dossier>'; claude --resume
  <uuid>` (session de ce PC) ; `Set-Location -LiteralPath '<dossier>'; claude 'Lis le brief de
  reprise <chemin> puis reprends le travail décrit.'` (autre PC). Le serveur ne lance aucun
  processus pour une reprise ; le module n'importe pas `subprocess` et ne contient ni
  `cmd /c` ni `Invoke-Expression` (test statique).
- Brief : `attente/briefs/<id>.md` (id validé par `noyau/ids.py`), création seule, jamais dans `donnees/`, donc jamais
  poussé ; jamais recopié dans la commande. Tout contenu tiré d'une session ou d'un dépôt (état,
  note, stories, journal du run, messages de commit lus dans le reflog) est encadré par
  `cadrage.cadrer_message` avec un nonce par brief : une donnée, jamais une consigne.
  Ligne suspecte (`texte.est_suspect`) omise ; briefs de plus de 7 jours purgés à l'écriture
  d'un nouveau.
- `GET /api/brief/<id>` : id `AAAAMMJJTHHMMSSZ-<8 hex>`, fichier trouvé par listage de
  `attente/briefs/`, servi en `text/plain; charset=utf-8`, `nosniff`, `no-store`.
- Projet non cloné ici : aucune commande, raison « pas cloné ici ».

## Limites assumées

- Le filtre de motifs de secrets (`noyau/texte.py`) vise la fuite accidentelle d'un jeton ou d'une
  clé dans un texte libre. Il n'est pas conçu contre une personne qui le contourne exprès.
- Le jeton de l'appli est transmis au navigateur dans le fragment de l'URL (`#...`), jamais en
  paramètre de requête. L'appli efface le fragment de la barre d'adresse après l'avoir lu, mais
  l'URL ouverte au lancement peut rester dans l'historique du navigateur. Le jeton est tiré au
  hasard à chaque lancement : l'URL d'un lancement précédent ne donne plus accès à rien, celle
  du lancement en cours reste valable tant que l'appli tourne.
- Un processus qui tourne sous le même compte Windows que l'utilisateur est hors périmètre : il
  peut lire les fichiers locaux (`attente/`, `config.json`) et contourner le serveur.
- Le contrôle « dépôt privé » dépend de `gh` et du compte GitHub connecté. Il est refait avant
  le push, mais un court intervalle subsiste entre le contrôle et le push : un dépôt rendu public
  dans cet intervalle ne serait pas détecté avant ce push.
