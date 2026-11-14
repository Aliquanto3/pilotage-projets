# Messages remis au démarrage d'une session (story 5.3)

Un message déposé depuis l'appli (`deposer_message`) est remis par le hook `SessionStart` à la
prochaine session principale du projet, sur le PC visé (ou sur chaque PC s'il n'en vise aucun).

- Sources : `donnees/boite/<projet>/<id>.json` et, sur le PC qui l'a déposé, l'opération encore
  en attente dans `attente/operations/<id>.json`. Même `id` dans les deux : remis une fois, texte
  de `donnees/`.
- Cadrage : `pilotage.noyau.cadrage` ; chaque message est présenté comme un message de l'utilisateur déposé
  via pilotage-projets, entre `<<<PILOTAGE-MESSAGE-DEBUT id=… nonce=…>>>` et
  `<<<PILOTAGE-MESSAGE-FIN id=… nonce=…>>>`. Le nonce est tiré au hasard à chaque injection :
  l'auteur d'un message ne peut pas fermer le bloc. En plus, toute forme du mot-clé dans le texte
  (casse, espaces, pleine chasse, sosies) est remplacée par `[délimiteur neutralisé]`.
- Borne : 3 messages au plus, 8 Ko au plus, le plus ancien d'abord ; le reste attend la
  session suivante.
- Acquittement : après l'émission seulement, `attente/boite/<projet>/<id>.lu.<pc>` (schéma
  `acquittement`), recopié par `sync` dans `donnees/boite/`. Un message acquitté par ce PC (dans `attente/` ou `donnees/`) n'est plus remis,
  ni après `/clear` ou `/compact` ; la règle du marqueur l'est toujours.
- Livraison au moins une fois (L8) : les hooks lisent `donnees/` sans verrou pendant que `sync`
  fait `pull --rebase`. Un message absent à cet instant n'est pas remis ni acquitté ; il sera
  remis à la session suivante. Même chose si l'acquittement ne peut être écrit (verrou de session
  occupé, disque plein) : le message peut alors être remis deux fois.

## Dernière note de reprise et plafond du contexte (story 8.1)

`SessionStart` émet un seul `additionalContext`, en trois blocs séparés par une ligne vide :
la règle du marqueur, la dernière note de reprise du projet, puis les messages.

- Note retenue : la plus récente du projet, tous PC confondus, session courante comprise (utile
  après `resume`, `/clear` ou `/compact`). Ce PC se lit dans `attente/etat/<projet>/<pc>/`, les
  autres PC dans `donnees/etat/<projet>/<pc>/`. Ordre : `dernier_tour`, sinon `debut`, puis
  l'id de session. 20 fichiers au plus sont ouverts, les plus récents sur le disque ; un état
  invalide, de plus de 64 Kio, hors de sa place ou sans note est ignoré. Limite connue : le
  `mtime` d'un état de `donnees/` est l'heure du `pull` qui l'a apporté, pas celle de son
  dernier tour ; si un même `pull` apporte plus de 20 états du projet (premier clone, PC resté
  éteint plusieurs jours), les 20 ouverts sont pris au hasard parmi eux et une note plus
  ancienne peut être injectée (son en-tête en donne l'heure). Pas de lecture au-delà de 20
  fichiers (NFR1).
- Filtre de secrets rejoué à la lecture (`texte.nettoyer`, comme `sync`) : une note suspecte
  est écartée au profit de la suivante ; aucune note valide, aucun bloc.
- Cadrage : préambule « Dernière note de reprise », qui présente le bloc comme une donnée sur
  l'état du travail, jamais comme une consigne ; en-tête hors du cadre (id court de la session,
  PC, heure du dernier tour en UTC) ; puis les délimiteurs `PILOTAGE-MESSAGE` avec un nonce et
  un identifiant propres à la note, distincts de ceux des messages.
- Plafond : 10 000 unités UTF-16 pour tout `additionalContext` (la longueur que mesure Claude
  Code). Priorité : règle, puis note, puis messages. La note est omise si elle ne tient pas
  après la règle ; les messages reçoivent la place restante, et ceux qui ne tiennent pas ne sont
  pas acquittés (remis à la session suivante).
- Sans note : la sortie est celle d'avant (règle seule, ou règle et messages), à l'octet près,
  tant que règle et messages tiennent sous le plafond.
- Sous-agent, dossier non suivi : rien n'est lu ni émis.

## Compaction (story 8.2)

- Avant : le hook `PreCompact` écrit sur stdout une consigne fixe, en texte brut
  (`pilotage.hooks.compaction.CONSIGNE`, 1 500 caractères au plus), que Claude Code ajoute aux
  instructions du résumé : garder les décisions et leur raison, les fichiers touchés, la
  prochaine action, les blocages et ce qui attend l'utilisateur ; ne pas recopier les blocs du
  pilotage ; mettre à jour la note de reprise au prochain arrêt. Aucune donnée de session ni du
  payload (`trigger`, `custom_instructions` ne sont pas lus) ; rien d'écrit sur le disque. Jamais
  de code 2 ni de `decision` (ils bloqueraient la compaction). Sous-agent, dossier non suivi ou
  hors racine : rien.
- Après : `SessionStart` arrive avec `source=compact` et réinjecte règle, dernière note et
  messages non acquittés, comme au démarrage (story 8.1).
