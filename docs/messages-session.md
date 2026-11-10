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
