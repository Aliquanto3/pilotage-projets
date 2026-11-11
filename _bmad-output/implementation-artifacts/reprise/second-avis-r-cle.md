# Second avis, correctif r-cle (e9fdbfb, sur 56a79f7)

Haiku, lecture seule, sans test lancé.

1. **medium** · `pilotage/web/app.js:95-103` (`surPageHide`) · probable : la clé est écrite à chaque `pagehide`, donc aussi à la fermeture de l'onglet ; la restauration de session du navigateur (Ctrl+Maj+T, reprise au démarrage) reprend `sessionStorage` et reconnecte l'appli si le serveur tourne encore. **Note de l'orchestrateur** : risque résiduel présenté à l'utilisateur et accepté le 2026-11-11 (le navigateur ne distingue pas rechargement et fermeture à `pagehide`) ; à documenter dans la spec et AD-14, pas à corriger.
2. **medium** · `tests/test_web_statique.py` (`STOCKAGE_PERMIS`, `_stockage`) · certain : la garde ne vérifie que le préfixe `sessionStorage.getItem("pilotage-cle")` ; `alerter(window.sessionStorage.getItem("pilotage-cle"))` ou `console.log(...)` dans app.js passe.
3. **low** · `tests/test_web_statique.py` (`_stockage`) · certain : `window["sessionStorage"]` ou `window["session"+"Storage"]` contournent `\bsessionStorage\b` ; idem localStorage et cookie.
4. **low** · `pilotage/web/app.js:81-84` (`lireCle`) · probable : `replaceState` avant `relireStockage` ; s'il lève, la clé n'est pas effacée et `demarrer()` lève.
5. **low** · `pilotage/web/app.js:154-161` (401 initial) · probable : onglet rechargé après remplacement de session sans 401 intermédiaire → « Clé perdue » au lieu de « session remplacée ». Conséquence de la spec.
6. **nit** · `tests/test_web_statique.py` : les cas testent la fonction de garde, pas l'appli (les tests JS de test_web_accueil.py font foi).

Vérifié sans défaut : stockage toujours sous try/catch ; pas d'écriture après `arreter()` ; jeton seulement dans l'en-tête Authorization ; fragment invalide sans effet sur le stockage ; tests JS rouges sans le correctif ; Node exigé en CI ; ni localStorage ni cookie.
