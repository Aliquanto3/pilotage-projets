// Opérations en file et messages (story 5.6) : `GET /api/operations`, lu une seule fois par état
// chargé (`ctx.etat`) et partagé par les sections « Messages » et « Réglages » du tiroir.
//
// Aucune mise à jour optimiste : ce que montrent les deux sections vient de cette lecture. Après
// un 202, `oublierOperations()` force la lecture suivante. Les appels passent par `ctx.appeler`
// (app.js tient seul la clé d'accès et traite seul le 401).

import { TEXTE_INJOIGNABLE, alerter, el, vider } from "./dom.js";

export const TEXTE_ERREUR = "Erreur du serveur local.";

// Clé des lectures faites sans état chargé (`ctx.etat` null).
const SANS_ETAT = {};
let lectures = new WeakMap();

// Promesse de `{statut, corps}` de `GET /api/operations`, une seule par objet `ctx.etat`.
export function lireOperations(ctx) {
  const cle = ctx.etat && typeof ctx.etat === "object" ? ctx.etat : SANS_ETAT;
  let promesse = lectures.get(cle);
  if (promesse === undefined) {
    promesse = ctx.appeler("GET", "/api/operations");
    lectures.set(cle, promesse);
  }
  return promesse;
}

// Après un dépôt accepté : la lecture en mémoire ne décrit plus la file.
export function oublierOperations() {
  lectures = new WeakMap();
}

function objets(liste) {
  return Array.isArray(liste) ? liste.filter((o) => o && typeof o === "object") : [];
}

// Opérations et messages du projet `nom` ; corps illisible : listes vides.
export function operationsDe(corps, nom) {
  const donnees = corps && corps.ok === true && corps.donnees && typeof corps.donnees === "object"
    ? corps.donnees : {};
  return {
    operations: objets(donnees.operations).filter((o) => o.projet === nom),
    messages: objets(donnees.messages).filter((m) => m.projet === nom),
  };
}

// Texte d'un échec, ou null pour un 401 (app.js a déjà remplacé l'écran).
export function texteEchec(statut, corps) {
  if (statut === 401) {
    return null;
  }
  if (statut === 0) {
    return TEXTE_INJOIGNABLE;
  }
  return corps && typeof corps.erreur === "string" && corps.erreur !== "" ? corps.erreur : TEXTE_ERREUR;
}

// Bandeau d'erreur de la section dans `zone` (texte posé par textContent) ; `alerter` seulement
// quand le texte change ou après un geste (`geste`), pour qu'une erreur de lecture qui dure ne
// soit pas relue à chaque relecture.
export function montrerErreur(zone, texte, geste = false) {
  const actuel = zone.firstChild ? zone.firstChild.textContent : null;
  vider(zone);
  zone.append(el("div", "bandeau-local erreur", texte));
  if (geste || actuel !== texte) {
    alerter(texte);
  }
}

export function effacerErreur(zone) {
  vider(zone);
}
