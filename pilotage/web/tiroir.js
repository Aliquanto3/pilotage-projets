// Tiroir de détail d'un projet (story 4.7, FR5, UX-DR10, DR14) : un seul `dialog` pour toute
// l'appli, non modal à partir de 80 em (1280 px), modal en dessous (`showModal()`, voile).
//
// Contrat de section : un module appelle `enregistrerSection(def)` à son import ; l'ordre affiché
// est celui d'`ORDRE_SECTIONS`, jamais celui des imports. `def = { id, titre, rendre(ctx) ->
// Node | null, maj?(noeud, ctx) }` ; `rendre` null : section absente. `ctx = { nom, carte,
// detail, etat, maintenant, appeler }` ; `appeler` vient d'app.js (seul app.js tient la clé d'accès).
//
// Le contenu n'est construit qu'à l'ouverture (geste de l'utilisateur) : une relecture des 30 s
// (`majTiroir`) le garde tel quel et n'appelle que les `maj` déclarés. Texte non fiable : le nom
// est posé par textContent ; aucun attribut n'est tiré des données (AD-15).

import { el, vider } from "./dom.js";

export const ORDRE_SECTIONS = ["etat", "reprise", "messages", "sessions", "faits",
  "criteres", "chantier", "reglages"];

const MEDIA_LARGE = "(min-width: 80em)";

const SECTIONS = new Map();

// État du singleton.
let dialog = null;
let titre = null;
let corps = null;
let page = null;
let appeler = null;
let retrouver = null;
let requete = null;
let modal = false;
// Vrai pendant un changement de mode : le `close` qu'il provoque n'est pas une fermeture.
let bascule = false;
let etatCourant = null;
// Projet affiché : { nom, origine, noeuds: Map(id -> { def, noeud }) } ; null s'il est fermé.
let affiche = null;

export function enregistrerSection(def) {
  const id = def && typeof def.id === "string" ? def.id : "";
  if (!ORDRE_SECTIONS.includes(id)) {
    throw new Error(`Section de tiroir inconnue : ${id}`);
  }
  if (SECTIONS.has(id)) {
    throw new Error(`Section de tiroir déjà enregistrée : ${id}`);
  }
  SECTIONS.set(id, def);
}

function large() {
  return requete !== null && requete.matches === true;
}

// Ouvre le `dialog` dans le mode du moment.
function montrer() {
  modal = !large();
  if (modal) {
    page.classList.remove("tiroir-ouvert");
    dialog.showModal();
  } else {
    dialog.show();
    page.classList.add("tiroir-ouvert");
  }
}

function dansLeDocument(noeud) {
  return Boolean(noeud) && typeof document.contains === "function" && document.contains(noeud);
}

// Seul chemin de fermeture : l'événement `close` (« Fermer », Échap, `cancel`, `fermerTiroir`).
// Un `dialog` rouvert entre-temps (seuil franchi : `close` synchrone ou différé) n'en est pas une.
function surFermeture() {
  if (bascule || dialog.open || affiche === null) {
    return;
  }
  const { nom, origine } = affiche;
  affiche = null;
  page.classList.remove("tiroir-ouvert");
  let cible = dansLeDocument(origine) ? origine : null;
  if (cible === null && typeof retrouver === "function") {
    const trouve = retrouver(nom);
    cible = dansLeDocument(trouve) ? trouve : null;
  }
  if (cible === null) {
    cible = document.querySelector("main");
    // `main` n'est pas focalisable de lui-même : sans `tabindex`, le focus tomberait sur `body`.
    if (cible && cible.getAttribute("tabindex") === null) {
      cible.setAttribute("tabindex", "-1");
    }
  }
  if (cible) {
    cible.focus();
  }
}

// Échap au document en mode non modal (le mode modal passe par `cancel`).
function surTouche(evenement) {
  if (evenement.key !== "Escape" || evenement.defaultPrevented || modal || !dialog.open) {
    return;
  }
  evenement.preventDefault();
  dialog.close();
}

// Seuil franchi tiroir ouvert : fermé puis rouvert dans l'autre mode, sans reconstruction.
function surSeuil() {
  if (!dialog.open || affiche === null || modal === !large()) {
    return;
  }
  const actif = document.activeElement;
  bascule = true;
  try {
    dialog.close();
    montrer();
  } finally {
    bascule = false;
  }
  (dialog.contains(actif) ? actif : titre).focus();
}

export function initialiserTiroir(options) {
  page = options.page;
  appeler = options.appeler;
  retrouver = options.retrouver;
  if (dialog === null) {
    dialog = el("dialog", "tiroir");
    dialog.setAttribute("aria-labelledby", "tiroir-titre");
    const tete = el("div", "tiroir-tete");
    titre = el("h2", "tiroir-titre");
    titre.setAttribute("id", "tiroir-titre");
    titre.setAttribute("tabindex", "-1");
    const fermer = el("button", "btn2 tiroir-fermer", "Fermer");
    fermer.setAttribute("type", "button");
    fermer.addEventListener("click", () => dialog.close());
    tete.append(titre, fermer);
    corps = el("div", "tiroir-corps");
    dialog.append(tete, corps);
    dialog.addEventListener("close", surFermeture);
    dialog.addEventListener("cancel", (evenement) => {
      evenement.preventDefault();
      dialog.close();
    });
    document.addEventListener("keydown", surTouche);
    requete = typeof window.matchMedia === "function" ? window.matchMedia(MEDIA_LARGE) : null;
    if (requete !== null && typeof requete.addEventListener === "function") {
      requete.addEventListener("change", surSeuil);
    }
  }
  options.hote.append(dialog);
}

function carteDe(etat, nom) {
  const cartes = etat && Array.isArray(etat.cartes) ? etat.cartes : [];
  return cartes.find((c) => c && c.genre === "projet" && c.nom === nom) || null;
}

function detailDe(etat, nom) {
  const details = etat && etat.details;
  if (!details || typeof details !== "object" || !Object.hasOwn(details, nom)) {
    return null;
  }
  return details[nom];
}

function contexte(nom) {
  return {
    nom, carte: carteDe(etatCourant, nom), detail: detailDe(etatCourant, nom), etat: etatCourant,
    maintenant: new Date(), appeler,
  };
}

function construire(nom) {
  vider(corps);
  titre.textContent = nom;
  const noeuds = new Map();
  const ctx = contexte(nom);
  for (const id of ORDRE_SECTIONS) {
    const def = SECTIONS.get(id);
    const contenu = def ? def.rendre(ctx) : null;
    if (contenu) {
      const section = el("section", `tiroir-section tiroir-section-${id}`);
      section.setAttribute("aria-labelledby", `tiroir-section-${id}`);
      const h3 = el("h3", "tiroir-section-titre", def.titre);
      h3.setAttribute("id", `tiroir-section-${id}`);
      section.append(h3, contenu);
      corps.append(section);
      noeuds.set(id, { def, noeud: contenu, section });
    }
  }
  return noeuds;
}

// Ouvre le tiroir de `nom` ; `origine` reprend le focus à la fermeture. Un tiroir déjà ouvert
// garde son `dialog` : contenu et origine sont remplacés. `section` : amenée à l'écran, le focus
// restant sur le titre. Sans `initialiserTiroir` : rien.
export function ouvrirTiroir(nom, origine, { section } = {}) {
  if (dialog === null || typeof nom !== "string") {
    return;
  }
  const noeuds = construire(nom);
  affiche = { nom, origine: origine || null, noeuds };
  if (!dialog.open) {
    montrer();
  }
  titre.focus();
  const cible = section ? noeuds.get(section) : undefined;
  if (cible && typeof cible.section.scrollIntoView === "function") {
    cible.section.scrollIntoView({ block: "nearest" });
  }
}

// Mémorise l'état lu ; tiroir ouvert : appelle seulement les `maj` déclarés, sans reconstruire.
export function majTiroir(etat) {
  etatCourant = etat;
  if (affiche === null || dialog === null || !dialog.open) {
    return;
  }
  const ctx = contexte(affiche.nom);
  for (const { def, noeud } of affiche.noeuds.values()) {
    if (typeof def.maj === "function") {
      def.maj(noeud, ctx);
    }
  }
}

export function fermerTiroir() {
  if (dialog !== null && dialog.open) {
    dialog.close();
  }
}

export function tiroirOuvert() {
  return dialog !== null && dialog.open && affiche !== null ? affiche.nom : null;
}
