# Revue 9.1 (reviewer, Opus)

## Passe 1 (2026-11-14, SHA revu 8f1d080 — 285524a rebasé sur origin/main 12e096d, CI verte sur 2517f4d)

Correctifs : commit 2517f4d (`story/9-1`, poussé avec force-with-lease).

- Important · medium · second avis 2 · accepté, corrigé · le fuseau était un décalage fixe pris au lundi : la borne de fin d'une semaine de changement d'heure était décalée d'une heure (vérifié : une session du lundi 30 mars 00:30 heure d'été comptée dans W13). Nouvelle classe `lecture.FuseauLocal` (tzinfo dont `utcoffset` et `fromutc` interrogent le système à chaque instant, via `astimezone()`, avec `fold` pour l'heure répétée) ; `zoneinfo` est inutilisable ici (pas de `tzdata` sous Windows, CI Windows seule). Tests : bornes W13/W43 avec la règle de Paris 2026 (sous-classe de test), session du lundi suivant exclue, conversions aller-retour, accord avec le système sur chaque borne.
- Nit · low · second avis 3 · documenté · les instantanés ne portent que le dernier tag, sans date (`faits_depot.tag`) : approximation gardée, décrite dans la docstring de `_livraisons` (deux releases dans la semaine n'en font qu'une) et nommée dans la synthèse (`Synthese.note_livraisons`, `LIVRAISON_APPROCHEE`). Écart assumé au critère « tag daté dans la semaine ».
- Nit · low · second avis 1 · rejeté (durci quand même) · `ids.valider_projet` et les noms de PC sont ASCII (`[a-z0-9._-]`) : aucun chemin de `instantanes/` ou `etat/` valide n'est cité par `core.quotePath`. `-z` ajouté à `ls-tree`, sans coût.
- Rejeté · second avis 4 · les sessions archivées des autres PC ne manquent pas : `archivage.py` n'archive qu'après 7 jours sans tour, donc toute session active pendant la semaine W est encore dans `donnees/etat/` au dernier commit avant le lundi suivant (lu pour une semaine finie) et dans `donnees/` courant pour la semaine en cours. Seules manquent les activités postérieures au dernier `sync` de la semaine, inhérent à la source.
- Rejeté · second avis 5 · arête `rapport → scan` nécessaire (`lire_autres_pcs`, `inventaire`, `sessions.vivantes_claude`, `lire_alertes_ecrites` : mêmes faits que le scan) et décidée par l'orchestrateur ; bornée à `lecture.py`, désormais testé (`test_arete_rapport_scan_bornee_a_la_lecture` : `semaine.py` n'importe que `pilotage.noyau`).
- Rejeté · second avis 6 · `tag` validé `vX.Y.Z` et `topics` énumérés (`faits.TOPICS`) par le schéma `instantane` ; les alertes sont celles du catalogue du noyau (modèles, `message` hérité d'avant M8 écrit par le pilotage), pas un texte de session. L'échappement HTML et la borne de rendu relèvent de 9.2 (FR45).
- Nit · low · second avis 7 · rejeté · un `git show` par fichier : `etat/` ne garde que 7 jours de sessions (archivage), deux commits lus par rapport, hors hook ; `git cat-file --batch` possible plus tard si la mesure le montre.
- Nit · low · second avis 8 · documenté · repli silencieux sur l'état courant pour une semaine finie sans commit : écrit dans la docstring du module.
- Complexité : 0 constat (`_sessions` en O(n) avec ensemble de dédoublonnage ; aucune structure parcourue à chaque événement).

Tests : `uv run ruff check .` ; `tests/test_rapport_semaine.py`, `tests/test_imports.py`, `tests/test_alertes.py`, `tests/test_publication.py` verts en local. Passe 2 : non nécessaire (le seul Important est corrigé et testé).
