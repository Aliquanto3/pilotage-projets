# Règle du marqueur de pilotage

Cette règle sert au suivi des projets. Elle ne change rien à ta façon de répondre.

Quand tu t'arrêtes parce que tu attends l'utilisateur (une question, un choix, un test à faire, des données ou un accès à fournir), termine ton message par un marqueur, en dernière ligne :

<!-- pilotage: action=attend-utilisateur | type=choix | quoi="Choisir entre la voie A et la voie B" -->

- `action=attend-utilisateur` et `quoi` sont obligatoires. `quoi` dit en une phrase ce que tu attends, en 200 caractères au plus (au-delà, il est coupé).
- `type` est facultatif : `choix`, `test`, `donnees` ou `acces`. Toute autre valeur est ignorée.
- Champs séparés par `|`, sur une seule ligne. Une valeur sans espace s'écrit `cle=valeur` ; sinon `cle="texte"`, sans guillemet `"` ni `-->` à l'intérieur du texte.
- Aucun secret, jeton, mot de passe ni chemin privé dans `quoi`.
- Seuls comptent les marqueurs des dernières lignes du message : un marqueur suivi d'une ligne de texte est ignoré. Un marqueur mal formé est ignoré en entier ; si tu en écris plusieurs du même genre, seul le dernier compte.

Pour laisser une note de reprise (où tu en es, ce qui reste), termine aussi par un marqueur :

<!-- pilotage: reprise="Étape 3 sur 5 faite ; reste à écrire les tests" -->

- `reprise` est une phrase de 300 caractères au plus, sans guillemet `"` à l'intérieur. Sans nouveau marqueur de reprise, la précédente est conservée.
- Un marqueur par genre, chacun sur sa ligne, dans les dernières lignes du message.

Hors run BMAD, à la fin d'une étape de travail, déclare aussi l'état du dépôt et chaque décision prise :

<!-- pilotage: prochaine="Écrire les tests de X" | branche=feat/x | blocages="aucun" | explore="docs/a.md" | a_explorer="module Y" -->
<!-- pilotage: decision="Garder SQLite" | pourquoi="Un seul poste" -->

- `reprise` dit où en est la session, l'état où en est le dépôt : sections fixes, `prochaine` obligatoire, 300 caractères (`branche` 100). Un état remplace le précédent en entier ; `etat=clos` le vide.
- Décisions : 3 par message au plus, 300 caractères ; journal en ajout seul, daté par le pilotage.
- Chemins relatifs, rien de secret. Si le dépôt a `_bmad-output/implementation-artifacts/run-autonome.md`, il fait foi : l'état n'est pas exigé.

N'écris un marqueur que pour de vrai : ne finis pas un message sur un marqueur cité en exemple, il serait pris pour réel. Si tu n'attends rien, n'écris pas de marqueur d'attente.
