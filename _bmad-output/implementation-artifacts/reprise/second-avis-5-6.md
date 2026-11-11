# Second avis, story 5.6 (c1c4e50, base 81dba42)

Haiku, lecture seule. Tests ciblés : 342 passés avec Node ; ruff vert.

1. **medium** · `pilotage/serveur/etat.py:27-61` (`projets_avec_message_en_attente`, `chantiers_connus`, `etat`) · certain : `/api/etat` lit désormais `chemins.donnees()` (via `suivi.messages` et `mutations._projets_yaml`) sans garde ; clé `donnees` invalide → `ErreurConfiguration` → 500 « configuration invalide » (`appli.py:232`) : tout l'accueil tombe au lieu d'une alerte de lecture. Prouvé par monkeypatch.
2. **medium** · `pilotage/serveur/etat.py:27-29`, `pilotage/serveur/suivi.py:149-167` · probable : chaque `/api/etat` (30 s et après chaque POST) relit toute la boîte (`donnees/boite`, `attente/boite`, JSON validés, acquittements) ; boîte sans purge (report de la spec) ; coût linéaire non mesuré.
3. **low** · `pilotage/serveur/suivi.py:161` · certain : message « tous les PC » lu au premier acquittement. Décision de spec, retenue par l'orchestrateur, à relire par l'utilisateur.
4. **low** · `pilotage/web/boite.js:154-156` (`deposer`, 202) · certain : la zone est vidée sans contrôle ; ce qui est tapé pendant l'appel (zone non désactivée) est perdu.
5. **low** · `pilotage/web/reglages.js:361-363` (`maj`) · probable : teste `s.ctx.carte` (ancien contexte) ; « projet exclu » ne se rétablit pas si le projet réapparaît sans réouverture.
6. **low** · `pilotage/web/reglages.js:136-152` (`actualiser`) · probable : options du `select` rebâties à chaque `maj` ; une liste ouverte se referme au rafraîchissement de 30 s.
7. **low** · `pilotage/noyau/etat.py:550` · certain : `dict(pause)` recopie tout `faits["pause"]` au lieu de `{revue}` ; exposition actuelle nulle (`scan/inventaire.py:226` ne produit que `revue`).

Vérifié sans défaut : aucun `innerHTML` ; `textContent` pour les textes serveur ; `routes.py` intouché (C4) ; Échap respecte `defaultPrevented` ; double envoi bloqué ; exclusion confirmée ; aucune mise à jour optimiste ; seule une fixture de test enrichie ; version 0.5.0 cohérente ; aucune chaîne privée.
