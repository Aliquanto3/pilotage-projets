# Revue 9.3 (rapport hebdomadaire généré par `sync`)

## Passe 1 (2026-11-14, SHA revu 458f9a2, base origin/story/9-2 fb168c7 à jour ; CI verte sur 458f9a2 et sur le correctif c4c5c32)

- Important · medium · second avis 1 · accepté, corrigé (c4c5c32) · rétention dans le même `try` que la génération : un `unlink` refusé (fichier ouvert sous Windows) faisait lever l'alerte « non généré » alors que le rapport était écrit, la boucle s'arrêtait au premier fichier verrouillé, et la rétention n'était jamais reprise (le rapport existant fait sortir l'étape). Désormais : rétention séparée, rejouée à chaque cycle (`os.scandir` de `rapports/`, dossier absent toléré), chaque suppression isolée, une ligne de journal fixe en cas d'échec, sans alerte. Tests : fichier verrouillé isolé, reprise au cycle suivant, dossier absent.
- Nit · low · second avis 2 · rejeté · pas de délai entre deux essais : la spec et le texte de l'alerte promettent un « nouvel essai au prochain cycle » ; ~96 lignes fixes par jour dans un journal mensuel, coût acceptable ; un délai demanderait un état persistant de plus.
- Nit · low · second avis 3 · rejeté · rapport figé au premier cycle de la semaine : conforme au critère « aux cycles suivants, rien n'est écrit ni recalculé » ; `lancer.py rapport AAAA-Www` le régénère à la demande.
- Nit · low · second avis 4 · rejeté · `# ruff: noqa: F401, F811` de fichier : nécessaire pour importer les fixtures de `tests/test_sync_cli.py`, limité au fichier de test.
- Nit · low · second avis 5 · rejeté · changement d'année testé à midi seulement : la semaine précédente est calculée en heure locale par `astimezone` puis `- 7 jours`, indépendante de l'heure ; le second avis a vérifié lundi 00:30 et les changements d'heure à la main.
- Nit · low · relecture · documenté · le code d'alerte est `rapport-non-genere` (le schéma refuse `_`), décision de l'orchestrateur ; écart de forme avec la spec qui écrit `rapport_non_genere`.
- Complexité : 0 constat (rétention O(n) sur au plus ~13 fichiers par cycle).
