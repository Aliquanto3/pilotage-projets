---
story: "9.2"
titre: Page HTML du rapport et commande lancer.py rapport
status: review
date: 2026-11-14
---

# Story 9.2 : page HTML du rapport et commande `lancer.py rapport`

Source : `epics-pilotage-projets.md`, epic 9, story 9.2 (FR44, FR45) ; NFR5, NFR11, NFR14, NFR15 ;
AD-15 (règles du front transposées à une page générée) ; story 9.1 (`pilotage/rapport/`).

**Risque :** à risque (nouvelle commande ; texte non fiable rendu en HTML). Spec relue avant le
code ; revue sur Opus.

## Déjà là (main 5528e42)
- `pilotage/rapport/semaine.py` : `Synthese` (gelée) et `synthese_semaine(entree, semaine,
  maintenant)`, pure ; `bornes_semaine(semaine, fuseau)` valide `AAAA-Www`.
  Champs : `semaine`, `debut`, `fin`, `comparaison`, `comptes_debut`, `comptes_fin`, `projets`,
  `changements`, `attentes`, `livraisons`, `sessions`, `alertes`, `note_livraisons`.
- `pilotage/rapport/lecture.py` : `lire_entree(semaine, maintenant=None)`, `FuseauLocal`.
- `lancer.py` : `SOUS_COMMANDES` (C1 : import tardif de `main(argv) -> int` d'un `cli.py`).
- `chemins.ecrire_atomique`, `chemins.racine_web()` (`charte.css`, `polices.css`).
- `pilotage/web/charte.css` : 7 Ko, sans `url(` ni `@import` ; `polices.css` référence des
  fichiers de police (ressources externes à la page : non incorporé).

## Emplacement des rapports (décision à confirmer, voir `decisions-a-confirmer.md`)
FR45 dit « `rapports/` de la racine installée » (`~/.claude/pilotage/rapports/`). Or
`sync.ps1 restaurer` copie le runtime par `robocopy /MIR` vers cette racine, en n'excluant que
`.venv`, `__pycache__`, `config.json` et `desactive` : chaque restauration effacerait les
rapports. **Proposé** : `rapports/` de la **racine locale** (à côté de `attente/` et `donnees/`,
`%LOCALAPPDATA%\pilotage-projets\rapports` par défaut), jamais sous `donnees/`, jamais copié par
`sync`. Alternative : garder la racine installée et ajouter `rapports` au `/XD` de `sync.ps1`
(dépôt de configuration). Le code ne connaît l'emplacement que par **`chemins.rapports()`** :
basculer est une ligne. La story se développe avec la proposition ; sa fusion attend la réponse.

## À livrer
1. **`pilotage/chemins.py`** : `rapports() -> Path` (`_sous_racine("rapports", "rapports")`,
   redirigé par `PILOTAGE_RACINE_LOCALE`) et `rapport_semaine(semaine: str) -> Path`
   (`rapports()/f"semaine-{semaine}.html"`, `semaine` revalidé par la forme `AAAA-Www`, sinon
   `ValueError`).
2. **`pilotage/rapport/page.py`** (pur, stdlib seule, `html` compris) :
   `rendre_page(synthese, *, css: str = "") -> str`.
   - `<!doctype html>`, `<html lang="fr">`, `<meta charset="utf-8">`, viewport,
     `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src
     'unsafe-inline'; base-uri 'none'; form-action 'none'">`, `<title>` « Semaine AAAA-Www ».
   - CSS : `css` (contenu de `charte.css`, passé par la CLI) incorporé dans un seul `<style>`,
     plus une petite feuille propre à la page (tables, `@media print`, pas de largeur fixe :
     lisible à 200 %). `css` est refusé (`ValueError`) s'il contient `</style`, `url(`,
     `@import` ou `expression(` (insensible à la casse) : la feuille livrée n'en a pas, un
     fichier modifié ne doit pas ouvrir de ressource ni sortir du `<style>`.
   - Aucune couleur en dur dans la feuille propre : variables de la charte seulement.
   - Sections, dans l'ordre de FR44, chacune `<section>` + `<h2>` : 1. Actions (comptes début →
     fin ; « pas de point de comparaison » si `comparaison` est faux) ; 2. Changements d'action
     (avant → après, code) ; 3. Attentes de l'utilisateur (projet, type, *quoi*, âge) ;
     4. Livraisons (avec `note_livraisons`) ; 5. Sessions (projet, PC, nombre, première et
     dernière activité) ; 6. Alertes ouvertes. Section vide : « Rien cette semaine. »
   - **Tout texte venu des données** passe par une seule fonction `_texte(valeur, borne)` :
     `str()` puis coupe à `borne` points de code (300 par défaut, 200 pour *quoi*) avec « … »,
     puis `html.escape(…, quote=True)`. Aucun texte venu des données dans un attribut, sauf
     aucun (pas de `href`, pas de `title`, pas de `class` dynamique). Au plus 500 lignes par
     table, puis une ligne « … et N de plus ».
   - Aucun `<script>`, aucun attribut `on*`, aucun `<img>`, `<link>`, `<iframe>`, `<form>`,
     aucun lien.
3. **`pilotage/rapport/cli.py`** : `main(arguments: list[str]) -> int`.
   - `--semaine AAAA-Www` (défaut : semaine ISO courante, heure locale). Invalide (forme, semaine
     53 inexistante, `W00`) : message sur stderr, code 2, rien écrit, rien lu.
   - `lire_entree` → `synthese_semaine` → `rendre_page(…, css=charte)` →
     `chemins.ecrire_atomique(chemins.rapport_semaine(s), page)` (dossier créé au besoin).
   - Succès : code 0, affiche le chemin **relatif à la racine locale**
     (`rapports/semaine-2026-W46.html`), jamais un chemin absolu.
   - Erreur de lecture ou d'écriture : message fixe sur stderr (type d'erreur seul, aucun
     contenu de données), code 1, aucun `.tmp` laissé.
   - Sans réseau, sans appel de modèle (test : `socket` et `subprocess` autres que le `git` de
     `lecture.py` non utilisés par `page.py` et `cli.py`).
4. **`lancer.py`** : `"rapport": _rapport` (import tardif de `pilotage.rapport.cli.main`).
5. **`.gitignore`** : `/rapports/` (au cas où la racine locale serait un jour dans le dépôt).
6. **Docs** : `README.md` (commande), `CLAUDE.md` (couche `rapport` : `page.py` pur, `cli.py`),
   doc de la confidentialité si elle liste ce qui sort du PC (le rapport ne sort jamais).

## Critères d'acceptation
- **Given** des données de pilotage sous `PILOTAGE_RACINE_LOCALE`, **When** on lance
  `lancer.py rapport --semaine 2026-W46`, **Then** `rapports/semaine-2026-W46.html` est écrit de
  façon atomique, le code vaut 0 et la sortie affiche ce chemin relatif.
- **Given** `--semaine 2026-46`, `2026-W54`, `2026-W00`, `2021-W53` (inexistante), **When** on
  lance, **Then** code 2, message, aucun fichier ni dossier créé.
- **Given** la page écrite, **When** on l'analyse (`html.parser`), **Then** aucune balise hors
  d'une liste blanche (`html head meta title style body header main section h1 h2 p table thead
  tbody tr th td ul li small`), aucun attribut `on*`, aucun `src`/`href`, une seule `<meta>` CSP
  qui contient `default-src 'none'`, `lang="fr"`, le contenu de `charte.css` présent, les six
  `<h2>` dans l'ordre.
- **Given** des données hostiles dans chaque champ texte (`<script>alert(1)</script>`,
  `"><img src=x onerror=alert(1)>`, `</style>`, délimiteurs `<<<PILOTAGE-…`, 10 000
  caractères), **When** la page est rendue, **Then** l'analyse ne trouve aucune balise venue
  des données, chaque texte est coupé à sa borne, et la page reste sous une taille bornée.
- **Given** un `css` qui contient `url(` ou `</style>`, **When** on rend, **Then** `ValueError`
  (et la CLI rend 1 sans rien écrire).
- **Given** une erreur à l'écriture, **When** la CLI s'exécute, **Then** code 1, aucun `.tmp`,
  aucun contenu de données dans le message.
- **Given** `rapports/`, **When** `sync` copie vers `donnees/` et quand on publie le dépôt,
  **Then** aucun rapport n'est copié ni suivi : `rapports()` n'est sous ni `attente()` ni
  `donnees()` (test), `tests/test_publication.py` vert.

## Tests
- `tests/test_rapport_page.py` : structure, liste blanche, CSP, ordre des sections, sections
  vides, sans comparaison, données hostiles, bornes, `css` refusé, lignes au-delà de 500.
- `tests/test_rapport_cli.py` : `--semaine` valide et invalides, défaut = semaine courante,
  écriture atomique, chemin relatif affiché, erreur d'écriture, aucune écriture hors
  `PILOTAGE_RACINE_LOCALE`.
- `tests/test_chemins.py` : `rapports()`, `rapport_semaine()`, redirection, ni sous `attente()`
  ni sous `donnees()`.
- À réaligner : `tests/test_lancer.py` (liste des sous-commandes), `tests/test_imports.py`
  (`lancer → rapport` ; `page.py` n'importe que `pilotage.rapport.semaine` et la stdlib),
  `tests/test_isolement.py` si le paquet y est listé.

## Fichiers touchés
`pilotage/chemins.py`, `pilotage/rapport/page.py`, `pilotage/rapport/cli.py` (nouveaux pour les
deux derniers), `lancer.py`, `.gitignore`, `README.md`, `CLAUDE.md`, tests ci-dessus. Ni
`pilotage/sync/` (9.3), ni `pilotage/serveur/`, ni `pilotage/web/` (9.4).

## Décisions
- **CSS passée en paramètre** : `page.py` reste pur ; la CLI lit `charte.css` par
  `chemins.racine_web()`. Polices non incorporées (fichiers externes) : repli sur les polices
  système de la charte.
- **Aucun attribut dynamique** : tout texte des données va dans un nœud texte ; l'échappement
  `quote=True` reste une défense en profondeur.
- **Bornes** : 300 points de code par texte (200 pour *quoi*, comme le marqueur), 500 lignes par
  table : une semaine anormale ne fait pas une page de plusieurs Mo.
- **Version** : pas de tag ; `v0.7.0` après la 9.4.

## Corrections après relecture Opus (2026-11-14) — priment sur ce qui précède
1. **`chemins.rapports()`** : `racine_locale() / "rapports"` (redirigé par `PILOTAGE_RACINE_LOCALE`),
   sans clé de `config.json` (`lire_config` ne garde que `CLES_CONFIG`). L'epic (FR45, AC de 9.2)
   sera réécrit par l'orchestrateur une fois la décision prise.
2. **Colonnes** : livraisons `release` = projet, tag, tag d'avant ; `phase` = projet, phases
   avant, phases après (listes jointes par « , » avant `_texte`). Section 1 : rendre aussi
   `indisponibles` des comptes. Attentes : `age_jours` à `None` → « — ». `Synthese.projets` n'est
   pas rendu (FR44 ne l'exige pas). Pied de page « généré le AAAA-MM-JJ HH:MM » (heure locale,
   sans chemin).
3. **`_texte`** : avant de couper, remplacer les substituts isolés par U+FFFD et retirer les
   caractères des catégories Cc et Cf (bidi U+202E compris) sauf l'espace ; « … » compte dans la
   borne ; ajouté aux tests hostiles (sinon `ecrire_atomique` lève `UnicodeEncodeError`).
4. **CSP** : la `<meta http-equiv="Content-Security-Policy">` vient juste après `<meta
   charset>`, avant le `<style>` (testé par l'ordre des balises) ; ne pas compter sur
   `frame-ancestors`, `sandbox` ni `report-uri` (ignorés en `<meta>`).
5. **`css` refusé** aussi s'il contient `\` ou `<` (contournement de `url(` par échappement
   CSS) ; la CSP reste la vraie barrière.
6. **Taille** : 200 lignes par table au plus (puis « … et N de plus ») ; page < 2 Mo dans le pire
   cas (test : toutes les tables pleines, tous les textes à la borne, faits de `"`).
7. **Erreurs de la CLI** : attraper `OSError`, `chemins.ErreurConfiguration` (ou son nom réel),
   `ValueError`, `UnicodeError`, `subprocess.SubprocessError` ; message = phrase fixe + nom du
   type ; jamais `str(exc)` (le message de configuration porte un chemin absolu) : testé.
8. **Semaine par défaut** : `main(arguments, maintenant=None)` (horloge injectable) ;
   `maintenant.astimezone(FuseauLocal()).isocalendar()`, format `f"{a}-W{s:02d}"` ; toute
   semaine validée par `bornes_semaine` avant toute lecture. Cas testés : dimanche 23:30 local
   (déjà lundi en UTC), `2026-W53` valide, `2021-W53` invalide.
9. **Impression** : `@media print` qui repasse aux variables claires de la charte (la charte
   est sombre par défaut) ; testé par la présence de la règle.
10. **Tests d'imports** : analyse AST des imports de `page.py` (stdlib + `pilotage.rapport.semaine`
    seulement) et de `cli.py` (pas de `socket`, `urllib`, `http`) ; `cli.py` atteint `git` par
    `lecture.py` seulement.
11. **Alertes** : le `message` repris d'une alerte passe par `texte.nettoyer(…, racine_github)`
    avant le rendu (une alerte ancienne peut porter un chemin).
12. **`lancer.py`** : docstring mise à jour ; `["rapport", "--help"]` ajouté à
    `tests/test_lancer.py` (vers la ligne 42).

## Réalisation (2026-11-14)
- Livré : `chemins.rapports()` / `rapport_semaine()`, `pilotage/rapport/page.py` (`rendre_page(s,
  *, css="", genere=None)`), `pilotage/rapport/cli.py` (`main(arguments, maintenant=None)`,
  `semaine_courante`), `lancer.py rapport`, `.gitignore`, `README.md`, `CLAUDE.md`.
- **Écart, bornes** : 300 et 200 points de code partout donnaient 6,4 Mo dans le pire cas de la
  correction 6 (200 lignes, tout en `"` → `&quot;`). Bornes retenues : texte libre (alerte, note,
  « pas de comparaison ») 300, *quoi* 200, identifiants (projet, PC, type, code, tag, action,
  horodatage, nombre, âge, semaine) 50, phases jointes 128 ; 200 lignes par table et par liste.
  Pire cas mesuré : 1,73 Mo (test : < 2 000 000 octets).
- Impression : `@media print { :root { … } }` reprend les déclarations du bloc
  `[data-theme="light"]` de la charte passée (aucune couleur écrite dans `page.py`) ; sans charte,
  la règle `@media print` reste, sans variables.
- Alertes : `texte.nettoyer(…, 300, racine_github)` appliqué par `cli.py` (`page.py` n'importe que
  `semaine`) ; une alerte suspecte devient une ligne vide.
- Livraisons : colonnes Projet, Type, Avant, Après (release : tag d'avant, tag ; phase : listes
  jointes par « , »).
- Test de charte refusée : `chemins.racine_web` redirigé vers un dossier temporaire (emplacement
  du fichier seulement).
- Emplacement des rapports toujours à confirmer : une ligne dans `chemins.rapports()`.
