// Accueil kanban (onglet Projets, stories 4.5, 4.6 et 4.11, FR30, UX-DR2, DR3, DR6, DR7, DR8, DR9,
// DR15, DR19, DR21, DR25).
//
// Texte non fiable (AD-15) : le *quoi*, les noms, les raisons, les PC et les étiquettes sont posés
// par textContent seulement (el), sans lien ni Markdown, et jamais tronqués ni coupés par le code :
// l'affichage entier est laissé à `overflow-wrap: anywhere` (appli.css). La session de la carte
// « Tourne » est déjà abrégée à 8 caractères par le serveur (noyau.etat) : rien n'est coupé ici.
// Aucun attribut n'est tiré des données. Les comptes viennent de `/api/etat` (AD-11) : rien n'est
// compté ici, hormis la longueur de chaque colonne pour sa tuile.

import { annoncer, el, vider } from "./dom.js";
import { creerTete, titreAttente } from "./synthese.js";
import { depuisCourt, depuisVieillissante, etiquetteFraicheur, heureCourte, lireInstant } from "./temps.js";
import { TYPES, icone, pastilleType } from "./types.js";

const COLONNES = [
  { action: "attend-utilisateur", titre: "Vous attend", vide: "Personne ne vous attend." },
  { action: "a-relancer", titre: "À relancer", vide: "Rien à relancer." },
  { action: "tourne", titre: "Tourne", vide: "Aucune session active." },
  { action: "rien-a-faire", titre: "Rien à faire", vide: "Aucun projet stable ni en pause." },
];

const ICONES_ACTION = {
  "attend-utilisateur": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  "a-relancer": "M4 12a8 8 0 1 1 3 6.2M4 19v-5h5",
  "tourne": "M8 5v14l11-7z",
  "rien-a-faire": "M5 12l4.5 4.5L19 7",
};

const TRACE_SABLIER = "M6 3h12M6 21h12M7 3c0 4 4 6 5 9 1-3 5-5 5-9M7 21c0-4 4-6 5-9 1 3 5 5 5 9";

// Familles (EXPERIENCE § Tuiles chiffrées), dans l'ordre fixe, libellés au singulier et au pluriel.
const FAMILLES_RELANCER = [
  ["arretee", "arrêtée", "arrêtées"],
  ["sans-nouvelles", "sans nouvelles", "sans nouvelles"],
  ["run-bloque", "run bloqué", "runs bloqués"],
  ["sans-session", "sans session", "sans session"],
  ["pause-a-revoir", "pause à revoir", "pauses à revoir"],
  ["non-relu", "non relu", "non relus"],
  ["a-stabiliser", "à stabiliser", "à stabiliser"],
];
const FAMILLES_RIEN = [
  ["stable", "stable", "stables"],
  ["pause", "en pause", "en pause"],
  ["a-classer", "à classer", "à classer"],
];

// Icône du motif d'une ligne Rien à faire (DESIGN § Components) : coche, pause, dossier. Table
// sans prototype, lue par `Map` : une famille « constructor » ou « __proto__ » ne donne rien.
const ICONES_MOTIF = new Map([
  ["stable", "M5 12.5l4.5 4.5L19 7.5"],
  ["pause", "M8.5 5v14M15.5 5v14"],
  ["a-classer", "M3 6.5h6.5l2 2.5H21v10H3z"],
]);

const ID_LISTE_RIEN = "liste-rien-a-faire";
const NOM_REPLI = "Afficher la liste de Rien à faire";

function entier(valeur) {
  return Number.isInteger(valeur) && valeur > 0 ? valeur : 0;
}

function projets(n) {
  return `${n} ${n > 1 ? "projets" : "projet"}`;
}

function nomDe(carte) {
  return typeof carte.nom === "string" ? carte.nom : "";
}

function raisonDe(carte) {
  return carte.raison && typeof carte.raison.texte === "string" ? carte.raison.texte : "";
}

function texteDe(valeur) {
  return typeof valeur === "string" && valeur !== "" ? valeur : null;
}

// Étiquettes non interactives (EXPERIENCE § Component Patterns) : « message en attente » (champ
// `message_en_attente`, alimenté par la story 5.6), « pas cloné ici », « à classer ».
function etiquettes(carte) {
  const textes = [];
  if (carte.message_en_attente === true) {
    textes.push("message en attente");
  }
  if (carte.clone_ici === false) {
    textes.push("pas cloné ici");
  }
  // « à classer » une seule fois : pas en étiquette quand c'est déjà la raison affichée.
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

function ajouterEtiquettes(noeud, carte) {
  const liste = etiquettes(carte);
  if (liste !== null) {
    noeud.append(liste);
  }
}

// Nom du projet : un vrai bouton, précédé de l'action en texte masqué. Le tiroir de la story 4.7
// l'ouvrira : d'ici là, il reste atteignable au clavier et annoncé « indisponible ».
function titreCarte(prefixe, carte) {
  const titre = el("h3", "carte-nom");
  titre.append(el("span", "masque", prefixe));
  const bouton = el("button", "btn-lien nom-projet", nomDe(carte));
  bouton.setAttribute("type", "button");
  bouton.setAttribute("aria-disabled", "true");
  titre.append(bouton);
  return titre;
}

// Place de « Reprendre » sur la ligne du nom (bouton ajouté par la story 5.5) : vide d'ici là.
function placeReprise() {
  return el("div", "carte-reprise");
}

// PC « sans nouvelles » d'après la ligne de fraîcheur (même seuil que la barre du haut).
function pcSansNouvelles(pc, fraicheur, maintenant) {
  if (pc === null || !Array.isArray(fraicheur)) {
    return false;
  }
  const ligne = fraicheur.find((l) => l && l.pc === pc);
  return ligne ? etiquetteFraicheur(ligne, maintenant).vieux : false;
}

// Ligne méta de la carte Attend : PC de l'attente retenue par le noyau, puis « depuis … ». Une
// attente vieillissante prend les formes d'EXPERIENCE § Voice and Tone.
function metaAttente(carte, maintenant, fraicheur) {
  const pc = texteDe(carte.pc);
  const instant = lireInstant(carte.depuis);
  const vieillissante = carte.vieillissante === true && instant !== null;
  let depuis = null;
  if (vieillissante) {
    depuis = depuisVieillissante(instant, maintenant, pcSansNouvelles(pc, fraicheur, maintenant));
  } else if (instant !== null) {
    depuis = depuisCourt(instant, maintenant);
  }
  return { pc, depuis, vieillissante };
}

function ligneMeta(parties) {
  const meta = el("p", "meta");
  parties.forEach((partie, i) => {
    if (i > 0) {
      meta.append(el("span", "meta-sep", " · "));
    }
    meta.append(partie);
  });
  return meta;
}

// Un `article` par carte, dans le `li` de la liste (UX-DR19).
function dansItem(article) {
  const item = el("li");
  item.append(article);
  return item;
}

// `titre` : libellé de la colonne (`titreAttente`), repris en préfixe masqué du nom.
function carteAttend(carte, maintenant, fraicheur, titre) {
  const article = el("article", "carte carte-attend");
  const ligne = el("div", "carte-ligne");
  ligne.append(titreCarte(`${titre} : `, carte), pastilleType(carte.type));
  article.append(ligne);
  // *quoi* vide : aucun texte de remplacement (EXPERIENCE § State Patterns).
  const quoi = texteDe(carte.quoi);
  if (quoi !== null) {
    article.append(el("p", "quoi", quoi));
  }
  const { pc, depuis, vieillissante } = metaAttente(carte, maintenant, fraicheur);
  const parties = [];
  if (pc !== null) {
    parties.push(el("span", "meta-pc", pc));
  }
  if (depuis !== null) {
    const partie = el("span", vieillissante ? "depuis depuis-vieillissante" : "depuis");
    if (vieillissante) {
      partie.append(icone(TRACE_SABLIER, "icone-sablier"));
    }
    partie.append(el("span", null, depuis));
    parties.push(partie);
  }
  if (parties.length > 0) {
    article.append(ligneMeta(parties));
  }
  ajouterEtiquettes(article, carte);
  article.append(placeReprise());
  return dansItem(article);
}

// Nom, raison, puis la ligne méta « PC · dernier tour » prise sur la carte (`pc` et `dernier_tour`
// de la session de la clé de tri : ce PC peut différer de celui que cite la raison).
function carteRelancer(carte, maintenant) {
  const article = el("article", "carte carte-relancer");
  article.append(titreCarte("À relancer : ", carte), el("p", "raison", raisonDe(carte)));
  const parties = [];
  const pc = texteDe(carte.pc);
  if (pc !== null) {
    parties.push(el("span", "meta-pc", pc));
  }
  const tour = lireInstant(carte.dernier_tour);
  if (tour !== null) {
    parties.push(el("span", null, `dernier tour ${heureCourte(tour, maintenant)}`));
  }
  if (parties.length > 0) {
    article.append(ligneMeta(parties));
  }
  ajouterEtiquettes(article, carte);
  article.append(placeReprise());
  return dansItem(article);
}

// PC, session (déjà sur 8 caractères côté serveur) et heure de la session vivante.
function carteTourne(carte) {
  const article = el("article", "carte carte-tourne");
  const params = carte.raison && carte.raison.params ? carte.raison.params : {};
  const parties = [params.pc, params.session, params.dernier_etat]
    .filter((p) => typeof p === "string" && p !== "");
  article.append(el("h3", "carte-nom", nomDe(carte)));
  article.append(el("p", "meta", parties.length > 0 ? parties.join(" · ") : raisonDe(carte)));
  ajouterEtiquettes(article, carte);
  return dansItem(article);
}

// Nom, puis le motif : icône (coche, pause ou dossier) et texte de la raison.
function ligneRien(carte) {
  const ligne = el("article", "ligne-rien");
  const motif = el("p", "raison motif");
  const trace = ICONES_MOTIF.get(carte.famille);
  if (trace !== undefined) {
    motif.append(icone(trace, `icone-motif icone-motif-${carte.famille}`));
  }
  motif.append(el("span", null, raisonDe(carte)));
  ligne.append(el("h3", "carte-nom", nomDe(carte)), motif);
  ajouterEtiquettes(ligne, carte);
  return dansItem(ligne);
}

// Compteur par type (colonne Attend) : un type absent n'apparaît pas.
function compteurTypes(types) {
  const liste = el("ul", "compteur-types");
  liste.setAttribute("aria-label", "Attentes par type");
  for (const type of TYPES) {
    const n = types ? entier(types[type.cle]) : 0;
    if (n > 0) {
      const item = el("li");
      // lu « choix : 2 » (EXPERIENCE.md, Accessibility Floor)
      item.append(pastilleType(type.cle), el("span", "masque", " : "), el("span", "type-compte", n));
      liste.append(item);
    }
  }
  return liste;
}

// « 1 arrêtée · 2 sans nouvelles » : une famille à 0 n'apparaît pas.
function detailFamilles(familles, liste) {
  return liste
    .map(([cle, un, plusieurs]) => [entier(familles ? familles[cle] : 0), un, plusieurs])
    .filter(([n]) => n > 0)
    .map(([n, un, plusieurs]) => `${n} ${n > 1 ? plusieurs : un}`)
    .join(" · ");
}

// Ligne de détail de la tuile (EXPERIENCE § Tuiles chiffrées) ; "" : pas de ligne.
function detailTuile(action, cartes, comptes, maintenant) {
  const c = comptes || {};
  if (action === "attend-utilisateur") {
    if (cartes.length === 0) {
      return "aucune attente en cours";
    }
    // La colonne est triée par le noyau, plus ancienne attente d'abord.
    const premiere = cartes[0];
    const instant = lireInstant(premiere.depuis);
    const heure = instant !== null ? `, ${heureCourte(instant, maintenant)}` : "";
    return `plus ancienne : ${nomDe(premiere)}${heure}`;
  }
  if (cartes.length === 0) {
    return "";
  }
  if (action === "a-relancer") {
    return detailFamilles(c.familles, FAMILLES_RELANCER);
  }
  if (action === "rien-a-faire") {
    return detailFamilles(c.familles, FAMILLES_RIEN);
  }
  const pcs = c.pcs_tourne && typeof c.pcs_tourne === "object" ? c.pcs_tourne : {};
  return Object.keys(pcs)
    .filter((pc) => entier(pcs[pc]) > 0)
    .map((pc) => `${entier(pcs[pc])} sur ${pc}`)
    .join(" · ");
}


// --- Story 4.6 : mise à jour sur place --------------------------------------------------------
// Le rendu garde, par conteneur, les nœuds déjà posés. Une relecture (toutes les 30 s) ne remplace
// que les cartes dont l'empreinte a changé ; les autres nœuds restent les mêmes objets, donc le
// focus et le défilement ne bougent pas.

const CONTEXTES = new WeakMap();
// Tête « Coup d'œil » (story 4.10), créée une fois par conteneur et jamais reconstruite : l'état
// ouvert des aides survit aux relectures, à Actualiser, à F5 et au retour depuis Chantiers.
const TETES = new WeakMap();
// État du repli « Afficher » de Rien à faire, par conteneur : conservé pendant la session
// (relectures, Actualiser, F5, retour depuis Chantiers), replié à chaque ouverture de l'appli.
const REPLIS = new WeakMap();

const FABRIQUES = {
  "attend-utilisateur": carteAttend,
  "a-relancer": carteRelancer,
  "tourne": carteTourne,
  "rien-a-faire": ligneRien,
};

// Tuile chiffrée posée une fois (UX-DR8) : le chiffre (aria-hidden), puis le `h2` (icône, titre et
// texte masqué « , 3 projets ») et la ligne de détail. Seuls le chiffre, le texte masqué et le
// détail changent ensuite : le focus posé sur le titre reste dessus.
function creerTuile(def) {
  const tuile = el("div", "tuile-colonne");
  const chiffre = el("span", `chiffre-tuile chiffre-${def.action}`);
  chiffre.setAttribute("aria-hidden", "true");
  const h2 = el("h2", "colonne-titre");
  h2.setAttribute("id", `titre-${def.action}`);
  h2.setAttribute("tabindex", "-1"); // reçoit le focus si la carte focalisée disparaît
  const lu = el("span", "masque");
  const libelle = el("span", "colonne-libelle", def.titre);
  h2.append(icone(ICONES_ACTION[def.action], `icone-action icone-${def.action}`),
    libelle, lu);
  const texte = el("div", "tuile-texte");
  const detail = el("p", "tuile-detail");
  texte.append(h2);
  tuile.append(chiffre, texte);
  return { tuile, chiffre, h2, lu, libelle, titreTexte: def.titre, texte, detail };
}

function creerColonne(def, repli) {
  const section = el("section", `colonne colonne-${def.action}`);
  section.setAttribute("aria-labelledby", `titre-${def.action}`);
  const col = {
    def, section, n: -1, detailTexte: null, ...creerTuile(def), types: null, typesSig: null,
    vide: el("p", "neutre vide", def.vide), liste: el("ul", `cartes cartes-${def.action}`),
    bouton: null, cartes: new Map(),
  };
  // Phrase de la colonne Attend vide masquée : la synthèse et le détail l'ont déjà dite.
  if (def.action === "attend-utilisateur") {
    col.vide.setAttribute("aria-hidden", "true");
  }
  if (def.action === "rien-a-faire") {
    // < 760 px : liste repliée derrière « Afficher » ; au-delà, la CSS masque le bouton et montre
    // la liste quel que soit son état.
    col.liste.setAttribute("id", ID_LISTE_RIEN);
    col.bouton = el("button", "btn2 repli-bouton", "Afficher");
    col.bouton.setAttribute("type", "button");
    col.bouton.setAttribute("aria-label", NOM_REPLI);
    col.bouton.setAttribute("aria-controls", ID_LISTE_RIEN);
    col.bouton.setAttribute("aria-expanded", String(repli.ouvert));
    col.bouton.addEventListener("click", () => {
      repli.ouvert = !repli.ouvert;
      col.bouton.setAttribute("aria-expanded", String(repli.ouvert));
    });
  }
  return col;
}

// Remet les enfants de `parent` dans l'ordre `voulus` en ne déplaçant que ce qui est mal placé.
function ajuster(parent, voulus) {
  const gardes = new Set(voulus);
  for (const enfant of Array.from(parent.childNodes)) {
    if (!gardes.has(enfant)) {
      parent.removeChild(enfant);
    }
  }
  voulus.forEach((noeud, i) => {
    const actuel = parent.childNodes[i] || null;
    if (actuel !== noeud) {
      parent.insertBefore(noeud, actuel);
    }
  });
}

// Clé stable d'une carte : (genre, nom), unique dans /api/etat (noyau.etat.assembler : un projet
// par nom, un chantier par nom). `depot_de` (objet {pc, genere_a}) n'y entre pas : il change à
// chaque instantané et ferait perdre le focus.
function cleCarte(carte) {
  return `${carte.genre}\u0000${nomDe(carte)}`;
}

// Empreinte du contenu rendu : la carte entière, les textes calculés (heures relatives) et le titre
// de la colonne (le nom affiché peut changer entre deux lectures).
function empreinte(carte, action, maintenant, fraicheur, titre) {
  let calcule = "";
  if (action === "attend-utilisateur") {
    calcule = metaAttente(carte, maintenant, fraicheur);
  } else if (action === "a-relancer") {
    const tour = lireInstant(carte.dernier_tour);
    calcule = tour !== null ? heureCourte(tour, maintenant) : "";
  }
  return JSON.stringify([carte, calcule, titre]);
}

function majTuile(col, cartes, comptes, maintenant) {
  const n = cartes.length;
  if (col.n !== n) {
    col.chiffre.textContent = String(n);
    col.chiffre.className = `chiffre-tuile chiffre-${col.def.action}${n === 0 ? " chiffre-zero" : ""}`;
    col.lu.textContent = `, ${projets(n)}`;
    col.n = n;
  }
  const detail = detailTuile(col.def.action, cartes, comptes, maintenant);
  if (col.detailTexte !== detail) {
    col.detail.textContent = detail;
    col.detailTexte = detail;
    ajuster(col.texte, detail ? [col.h2, col.detail] : [col.h2]);
  }
}

function majColonne(col, cartes, etat, maintenant, suivi) {
  const { def } = col;
  const comptes = etat.comptes;
  const n = cartes.length;
  const titre = def.action === "attend-utilisateur" ? titreAttente(etat) : def.titre;
  if (col.titreTexte !== titre) {
    col.libelle.textContent = titre;
    col.titreTexte = titre;
  }
  majTuile(col, cartes, comptes, maintenant);
  const voulus = [col.tuile];
  if (def.action === "attend-utilisateur" && n > 0) {
    const sig = JSON.stringify(comptes && comptes.types ? comptes.types : {});
    if (col.typesSig !== sig) {
      col.types = compteurTypes(comptes && comptes.types);
      col.typesSig = sig;
    }
    voulus.push(col.types);
  }
  // Une carte garde son nœud si son empreinte est la même, même d'une colonne à l'autre.
  const suivantes = new Map();
  const items = [];
  for (const carte of cartes) {
    const cle = cleCarte(carte);
    const emp = empreinte(carte, def.action, maintenant, etat.fraicheur, titre);
    const ancienne = suivi.anciennes.get(cle);
    const noeud = ancienne && ancienne.emp === emp
      ? ancienne.noeud : FABRIQUES[def.action](carte, maintenant, etat.fraicheur, titre);
    suivantes.set(cle, { noeud, emp });
    suivi.nouvelles.set(cle, { noeud, colonne: col });
    items.push(noeud);
  }
  col.cartes = suivantes;
  ajuster(col.liste, items);
  if (n === 0) {
    voulus.push(col.vide);
  } else if (col.bouton) {
    voulus.push(col.bouton, col.liste);
  } else {
    voulus.push(col.liste);
  }
  ajuster(col.section, voulus);
}

function creerContexte(conteneur, repli) {
  vider(conteneur);
  const ctx = {
    titre: el("h2", "masque", "Projets"),
    chargement: el("p", "neutre", "Chargement…"), grille: el("div", "kanban"),
    colonnes: COLONNES.map((def) => creerColonne(def, repli)), attend: null,
  };
  ajuster(ctx.grille, ctx.colonnes.map((c) => c.section));
  return ctx;
}

// Seul le rafraîchissement automatique annonce une hausse d'Attend : jamais au premier
// chargement, ni pendant une action de l'utilisateur (Actualiser, F5, Scan, Sync, réglage) ni pendant le
// cycle qu'il a lancé (`cycle` : motif du suivi d'app.js, "lance", "deja", "observe" ou null).
export function lectureAutomatique({ premiere, actionUtilisateur, cycle }) {
  return !premiere && !actionUtilisateur && (cycle === null || cycle === undefined || cycle === "observe");
}

// « Nouvelle attente : projet-a » ou « Nouvelles attentes : projet-a, projet-b » : les projets entrés dans
// Attend, si le compte de la colonne augmente. Un seul message, qui remplace le précédent.
function annoncerHausse(avant, noms) {
  if (avant === null || noms.length <= avant.length) {
    return;
  }
  const connus = new Set(avant);
  const nouveaux = noms.filter((nom) => !connus.has(nom));
  if (nouveaux.length === 1) {
    annoncer(`Nouvelle attente : ${nouveaux[0]}`);
  } else if (nouveaux.length > 1) {
    annoncer(`Nouvelles attentes : ${nouveaux.join(", ")}`);
  }
}

// etat : données de /api/etat, ou null tant qu'elles ne sont pas arrivées. maintenant : horloge
// des heures relatives (« hier 09:05 »), injectée par les tests. options.annoncer : vrai pour une
// relecture du rafraîchissement automatique (voir `lectureAutomatique`).
export function rendreAccueil(conteneur, etat, maintenant = new Date(), options = {}) {
  let repli = REPLIS.get(conteneur);
  if (repli === undefined) {
    repli = { ouvert: false };
    REPLIS.set(conteneur, repli);
  }
  let ctx = CONTEXTES.get(conteneur);
  const reutilise = ctx !== undefined && Array.from(conteneur.childNodes).includes(ctx.grille);
  if (!reutilise) {
    ctx = creerContexte(conteneur, repli);
    CONTEXTES.set(conteneur, ctx);
  }
  let tete = TETES.get(conteneur);
  if (tete === undefined) {
    tete = creerTete();
    TETES.set(conteneur, tete);
  }
  tete.maj(etat, maintenant);
  if (etat === null) {
    ajuster(conteneur, [ctx.titre, tete.element, ctx.chargement]);
    return;
  }
  const colonnes = etat.colonnes || {};
  const lesCartes = (def) => (Array.isArray(colonnes[def.action]) ? colonnes[def.action] : []);
  // Quelle carte porte le focus avant la mise à jour ?
  const actif = typeof document !== "undefined" ? document.activeElement : null;
  let focalisee = null;
  let colonneActive = null; // colonne qui contient le focus hors carte (titre, bouton du repli)
  const suivi = { anciennes: new Map(), nouvelles: new Map() };
  for (const col of ctx.colonnes) {
    if (actif && col.section.contains(actif)) {
      colonneActive = col;
    }
    for (const [cle, c] of col.cartes) {
      suivi.anciennes.set(cle, c);
      if (actif && c.noeud.contains(actif)) {
        focalisee = { cle, colonne: col };
      }
    }
  }
  ctx.colonnes.forEach((col) => {
    majColonne(col, lesCartes(col.def), etat, maintenant, suivi);
  });
  ajuster(conteneur, [ctx.titre, tete.element, ctx.grille]);

  if (focalisee !== null) {
    const nouvelle = suivi.nouvelles.get(focalisee.cle);
    let cible = nouvelle ? nouvelle.noeud.querySelector(".nom-projet") : null;
    if (!cible) {
      // La carte a disparu (ou n'a plus de bouton) : le titre de sa colonne reprend le focus.
      cible = (nouvelle ? nouvelle.colonne : focalisee.colonne).h2;
    }
    if (document.activeElement !== cible) {
      cible.focus();
    }
  } else if (colonneActive !== null && !colonneActive.section.contains(actif)) {
    // Le bouton du repli focalisé a disparu (colonne vidée) : le titre de la colonne le reprend.
    colonneActive.h2.focus();
  }
  const noms = lesCartes(COLONNES[0]).map(nomDe);
  if (reutilise && options && options.annoncer === true) {
    annoncerHausse(ctx.attend, noms);
  }
  ctx.attend = noms;
}
