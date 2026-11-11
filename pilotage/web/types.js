// Types d'attente et icônes décoratives, partagés par l'accueil (compteur, cartes) et l'aide
// « Les types d'attente, en clair » de la tête (story 4.10). Aucune donnée n'entre dans un attribut.

import { el, svg } from "./dom.js";

// Types d'attente, dans l'ordre du compteur (UX-DR3) : libellé, classe de couleur d'appoint, tracé,
// et sens affiché dans l'aide (EXPERIENCE § Types d'attente, majuscule initiale).
export const TYPES = [
  { cle: "choix", libelle: "choix", classe: "type-choix", trace: "M6 3v6m0 0a3 3 0 1 0 0 6m0-6a3 3 0 1 1 0 6m0 0v6m12-18v6a4 4 0 0 1-4 4h-2",
    sens: "Trancher entre des options ou valider une proposition." },
  { cle: "test", libelle: "test", classe: "type-test", trace: "M9 4h6v3H9zM7 6H5v14h14V6h-2m-9 8 2 2 4-4",
    sens: "Tester l'application ou une story (recette)." },
  { cle: "donnees", libelle: "données", classe: "type-donnees", trace: "M3 12V4h8l10 10-8 8zM7.5 8.5h.01",
    sens: "Labelliser ou annoter des données." },
  { cle: "acces", libelle: "accès", classe: "type-acces", trace: "M8 15a4 4 0 1 1 3.5-2L21 13v3h-3v3h-3v-3h-3.5",
    sens: "Fournir une connexion, une clé, un compte, ou activer une ressource (Ollama, GPU)." },
  { cle: "a-qualifier", libelle: "à qualifier", classe: "type-a-qualifier", trace: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5M12 17h.01",
    sens: "Lire la session pour savoir quoi faire." },
];

// Icône SVG décorative à un tracé (les couleurs viennent de appli.css).
export function icone(trace, classe) {
  const racine = svg("svg", classe);
  racine.setAttribute("viewBox", "0 0 24 24");
  racine.setAttribute("aria-hidden", "true");
  racine.setAttribute("focusable", "false");
  const chemin = svg("path");
  chemin.setAttribute("d", trace);
  racine.append(chemin);
  return racine;
}

function typeDe(cle) {
  return TYPES.find((t) => t.cle === cle) || TYPES[TYPES.length - 1];
}

// Pastille de type : icône puis libellé ; un type absent ou inconnu donne « à qualifier ».
export function pastilleType(cle) {
  const type = typeDe(cle);
  const pastille = el("span", `pastille-type ${type.classe}`);
  pastille.append(icone(type.trace, "icone-type"), el("span", "pastille-libelle", type.libelle));
  return pastille;
}

// Pastille d'action (tiroir, onglet Chantiers, story 4.7) : couleurs des chiffres de tuile
// (DESIGN § Components, `pastille-attend`…). Table lue par `Map` : une action inconnue (ou
// « constructor ») donne la pastille neutre. `libelle` : texte de la colonne, posé par textContent.
const CLASSES_ACTION = new Map([
  ["attend-utilisateur", "pastille-attend"],
  ["a-relancer", "pastille-relancer"],
  ["tourne", "pastille-tourne"],
  ["rien-a-faire", "pastille-rien"],
]);

export function pastilleAction(action, libelle) {
  const classe = CLASSES_ACTION.get(action) || "pastille-neutre";
  return el("span", `pastille-action ${classe}`, libelle);
}

// Libellés des colonnes hors Attend (celui d'Attend : `titreAttente` de synthese.js).
const LIBELLES_ACTION = new Map([
  ["a-relancer", "À relancer"],
  ["tourne", "Tourne"],
  ["rien-a-faire", "Rien à faire"],
]);

// Libellé d'une action ; `attend` : libellé d'Attend (nom configuré) ; inconnue : "".
export function libelleAction(action, attend) {
  if (action === "attend-utilisateur") {
    return attend;
  }
  return LIBELLES_ACTION.get(action) || "";
}

// Étiquettes non interactives d'une carte (EXPERIENCE § Component Patterns) : « message en
// attente » (champ `message_en_attente`, alimenté par la story 5.6), « pas cloné ici », « à
// classer » (pas quand c'est déjà la raison affichée). Partagées par l'accueil et le tiroir.
export function listeEtiquettes(carte) {
  const textes = [];
  if (carte.message_en_attente === true) {
    textes.push("message en attente");
  }
  if (carte.clone_ici === false) {
    textes.push("pas cloné ici");
  }
  if (carte.categorie === "découvert, à classer" && !(carte.raison && carte.raison.code === "a-classer")) {
    textes.push("à classer");
  }
  if (textes.length === 0) {
    return null;
  }
  const liste = el("ul", "etiquettes");
  for (const texte of textes) {
    const item = el("li");
    item.append(el("span", "etiquette", texte));
    liste.append(item);
  }
  return liste;
}
