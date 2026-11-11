// Point d'entrée de l'appli (contrat C3) : clé d'accès, appels à l'API, routeur des onglets,
// relecture des données. Seul module qui tient le jeton, dans une variable et nulle part ailleurs
// (AD-14, UX-DR17) : ni stockage du navigateur, ni DOM.

import { boutonNom as boutonAccueil, lectureAutomatique, rendreAccueil, texteHausse } from "./accueil.js";
import { construireBandeaux } from "./bandeaux.js";
import { construireBarre } from "./barre.js";
import { boutonNom as boutonChantiers, rendreChantiers } from "./chantiers.js";
import { ecranClePerdue, ecranSessionRemplacee } from "./cle.js";
import { alerter, annoncer, el, vider } from "./dom.js";
import "./sections-projet.js";
import { suivreChargement } from "./synthese.js";
import { heureCourte, lireInstant } from "./temps.js";
import { fermerTiroir, initialiserTiroir, majTiroir } from "./tiroir.js";

const MOTIF_JETON = /^[A-Za-z0-9_-]{16,128}$/;
const PERIODE_MS = 30000;
// L6 (story 4.3) : au plus une relecture de /api/etat par seconde.
const ECART_MIN_MS = 1000;

const TEXTE_DEJA = "Une synchro tourne déjà. L'accueil se mettra à jour à sa fin.";
const TEXTE_INJOIGNABLE = "Serveur local injoignable. Relancez l'appli par lancer.py.";
const ALERTE_403 = {
  source: "page",
  code: "requete-refusee",
  type: "erreur",
  texte: "Requête refusée par le serveur local (origine non reconnue). Rouvrez l'appli par lancer.py.",
};

let jeton = null;
let arrete = false;
let etat = null;
let onglet = "projets";
let locales = [];
let barre = null;
let bandeaux = null;
let contenu = null;

// Relecture : une requête à la fois, au plus une par seconde.
let enVol = false;
let enAttente = false;
let derniere = 0;
let minuteurRelecture = null;
let minuteurPeriode = null;
let chargement = null;
let annoncerLecture = false;
let premiereLecture = true;
// Noms de la colonne Attend à la dernière lecture appliquée (null avant la première) : la hausse
// s'annonce quel que soit l'onglet (story 4.7), sinon le retour sur Projets l'absorberait.
let attendConnus = null;

// Suivi d'un cycle (scan ou synchro) : motif "lance" (bouton), "deja" (409) ou "observe".
let lancement = false;
let suivi = null;
// Numéro de chaque GET /api/etat : une réponse à un GET parti avant la réponse du dernier POST
// est ignorée (elle décrirait l'état d'avant le lancement).
let numeroLecture = 0;
let lectureMin = 0;

// Lit la clé du fragment puis efface le fragment de la barre d'adresse, dans tous les cas.
function lireCle() {
  const brut = window.location.hash.slice(1);
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  return MOTIF_JETON.test(brut) ? brut : null;
}

function arreter() {
  arrete = true;
  if (minuteurPeriode !== null) {
    window.clearInterval(minuteurPeriode);
  }
  if (minuteurRelecture !== null) {
    window.clearTimeout(minuteurRelecture);
  }
  if (chargement !== null) {
    chargement.finir();
  }
}

function sessionRemplacee() {
  if (arrete) {
    return;
  }
  arreter();
  jeton = null;
  // Tiroir fermé par son seul chemin (`close`) : retiré ouvert, il laisserait la marge de 30 rem.
  fermerTiroir();
  const racine = document.getElementById("racine");
  vider(racine);
  const ecran = ecranSessionRemplacee();
  racine.append(ecran);
  const titre = ecran.querySelector("h2");
  if (titre) {
    titre.focus();
  }
}

// `{statut, corps}` ; statut 0 si le serveur est injoignable. 401 : session remplacée.
async function appeler(methode, chemin) {
  let reponse;
  try {
    reponse = await window.fetch(chemin, {
      method: methode,
      headers: { Authorization: `Bearer ${jeton}` },
      cache: "no-store",
      credentials: "omit",
    });
  } catch {
    return { statut: 0, corps: null };
  }
  if (reponse.status === 401) {
    sessionRemplacee();
    return { statut: 401, corps: null };
  }
  let corps = null;
  try {
    corps = await reponse.json();
  } catch {
    corps = null;
  }
  return { statut: reponse.status, corps };
}

function erreurDe(corps) {
  return corps && typeof corps.erreur === "string" && corps.erreur ? corps.erreur : "Erreur du serveur local.";
}

function signalerRefus(statut) {
  locales = statut === 403 ? [ALERTE_403] : [];
  if (bandeaux !== null) {
    bandeaux.maj(etat ? etat.alertes : [], locales);
  }
}

function majEtat(texte, annonce) {
  barre.majEtat(texte);
  if (annonce && texte) {
    annoncer(texte);
  }
}

function rendreVue() {
  if (etat === null && !chargement.lent()) {
    // Avant 300 ms, ou premier chargement en échec : `main` vide, l'erreur est dans la barre
    // du haut ou un bandeau (State Patterns).
    vider(contenu);
    return;
  }
  const vue = onglet === "chantiers" ? rendreChantiers : rendreAccueil;
  vue(contenu, etat, new Date());
}

function texteFin(dernier) {
  if (!dernier) {
    return "";
  }
  const instant = lireInstant(dernier.fin);
  const heure = instant ? heureCourte(instant, new Date()) : "";
  const scan = dernier.type === "scan";
  if (dernier.resultat === "fait") {
    return scan ? `Scan fait à ${heure}` : `Synchro faite à ${heure}`;
  }
  if (dernier.resultat === "deja_en_cours") {
    return TEXTE_DEJA;
  }
  return scan ? `Scan en échec à ${heure}` : `Synchro en échec à ${heure}`;
}

function finDe(cycle) {
  return cycle && cycle.dernier ? cycle.dernier.fin : null;
}

function suivreCycle(cycle) {
  const enCours = Boolean(cycle && cycle.en_cours);
  barre.majOccupe(enCours || lancement);
  if (enCours) {
    if (suivi === null) {
      suivi = { motif: "observe", finAvant: finDe(cycle) };
    }
    if (suivi.motif !== "deja") {
      const texte = cycle.type === "scan" ? "Scan en cours…" : "Synchro en cours…";
      majEtat(texte, suivi.annonce !== texte);
      suivi.annonce = texte;
    }
    relireBientot();
    return;
  }
  if (suivi !== null) {
    const { motif, finAvant } = suivi;
    suivi = null;
    const dernier = cycle ? cycle.dernier : null;
    if (dernier && dernier.fin !== finAvant) {
      majEtat(texteFin(dernier), true);
    } else if (motif !== "deja") {
      majEtat("", false);
    }
  } else if (premiereLecture && cycle && cycle.dernier) {
    majEtat(texteFin(cycle.dernier), false);
  }
}

function nomsAttend(donnees) {
  const colonnes = donnees && donnees.colonnes ? donnees.colonnes : {};
  const cartes = Array.isArray(colonnes["attend-utilisateur"]) ? colonnes["attend-utilisateur"] : [];
  return cartes.map((c) => (c && typeof c.nom === "string" ? c.nom : ""));
}

// Bouton du même projet dans la vue courante (retour du focus à la fermeture du tiroir).
function retrouver(nom) {
  return onglet === "chantiers" ? boutonChantiers(contenu, nom) : boutonAccueil(contenu, nom);
}

function appliquer(donnees) {
  etat = donnees;
  chargement.finir();
  barre.majFraicheur(donnees.fraicheur, new Date());
  bandeaux.maj(donnees.alertes, locales);
  rendreVue();
  majTiroir(donnees);
  // Avant suivreCycle : la dernière lecture d'un cycle lancé par l'utilisateur porte encore son motif.
  const automatique = lectureAutomatique({
    premiere: premiereLecture, actionUtilisateur: annoncerLecture || lancement,
    cycle: suivi ? suivi.motif : null,
  });
  const noms = nomsAttend(donnees);
  const hausse = automatique ? texteHausse(attendConnus, noms) : null;
  if (hausse !== null) {
    annoncer(hausse);
  }
  attendConnus = noms;
  suivreCycle(donnees.cycle);
  premiereLecture = false;
}

async function lireEtat() {
  numeroLecture += 1;
  const numero = numeroLecture;
  const { statut, corps } = await appeler("GET", "/api/etat");
  if (arrete || numero <= lectureMin) {
    return;
  }
  if (statut === 200 && corps && corps.ok && corps.donnees) {
    locales = [];
    appliquer(corps.donnees);
    if (annoncerLecture) {
      annoncerLecture = false;
      annoncer("Données actualisées");
    }
    return;
  }
  annoncerLecture = false;
  if (etat === null) {
    // Premier chargement en échec : ni aria-busy ni espaces réservés ; l'état d'erreur suit.
    chargement.finir();
    rendreVue();
  }
  // Le suivi du cycle s'interrompt : boutons réactivés avec le message d'erreur, sans attendre
  // la relecture suivante (un cycle encore en cours sera retrouvé par elle).
  suivi = null;
  barre.majOccupe(lancement);
  if (statut === 0) {
    majEtat(TEXTE_INJOIGNABLE, true);
    return;
  }
  if (statut === 403) {
    signalerRefus(403);
    return;
  }
  const texte = erreurDe(corps);
  majEtat(texte, false);
  alerter(texte);
}

function relire() {
  if (arrete) {
    return;
  }
  if (enVol) {
    enAttente = true;
    return;
  }
  const attente = derniere + ECART_MIN_MS - Date.now();
  if (attente > 0) {
    if (minuteurRelecture === null) {
      minuteurRelecture = window.setTimeout(() => {
        minuteurRelecture = null;
        relire();
      }, attente);
    }
    return;
  }
  enVol = true;
  derniere = Date.now();
  lireEtat().finally(() => {
    enVol = false;
    if (enAttente) {
      enAttente = false;
      relire();
    }
  });
}

// Pendant un cycle : relecture une seconde après la précédente.
function relireBientot() {
  if (minuteurRelecture === null && !enVol) {
    minuteurRelecture = window.setTimeout(() => {
      minuteurRelecture = null;
      relire();
    }, ECART_MIN_MS);
  } else if (enVol) {
    enAttente = true;
  }
}

function actualiser() {
  annoncerLecture = true;
  relire();
}

async function lancer(type) {
  if (lancement || suivi !== null || (etat && etat.cycle && etat.cycle.en_cours)) {
    return;
  }
  lancement = true;
  barre.majOccupe(true);
  const finAvant = finDe(etat ? etat.cycle : null);
  const { statut, corps } = await appeler("POST", `/api/${type}`);
  lancement = false;
  lectureMin = numeroLecture;
  if (arrete) {
    return;
  }
  if (statut === 202) {
    const texte = type === "scan" ? "Scan en cours…" : "Synchro en cours…";
    suivi = { motif: "lance", finAvant, annonce: texte };
    majEtat(texte, true);
    relire();
    return;
  }
  if (statut === 409) {
    suivi = { motif: "deja", finAvant };
    majEtat(TEXTE_DEJA, true);
    relire();
    return;
  }
  barre.majOccupe(false);
  if (statut === 0) {
    majEtat(TEXTE_INJOIGNABLE, true);
    return;
  }
  if (statut === 403) {
    signalerRefus(403);
    return;
  }
  const texte = erreurDe(corps);
  majEtat(texte, false);
  alerter(texte);
}

function changerOnglet(nom) {
  onglet = nom;
  barre.majOnglet(nom);
  rendreVue();
}

// F5 et Ctrl+R relisent les données sans recharger ; Ctrl+F5 et Ctrl+Maj+R restent natifs.
function surTouche(evenement) {
  if (arrete) {
    // Écran « Une autre fenêtre… » : F5 et Ctrl+R gardent leur effet natif.
    return;
  }
  const sansAutre = !evenement.shiftKey && !evenement.altKey && !evenement.metaKey;
  const f5 = evenement.key === "F5" && !evenement.ctrlKey && sansAutre;
  const ctrlR = (evenement.key === "r" || evenement.key === "R") && evenement.ctrlKey && sansAutre;
  if (f5 || ctrlR) {
    evenement.preventDefault();
    actualiser();
  }
}

function demarrer() {
  const racine = document.getElementById("racine");
  jeton = lireCle();
  vider(racine);
  if (jeton === null) {
    racine.append(ecranClePerdue());
    return;
  }
  barre = construireBarre({
    onglet: changerOnglet,
    actualiser,
    scan: () => lancer("scan"),
    sync: () => lancer("sync"),
  });
  bandeaux = construireBandeaux();
  contenu = el("main", "contenu");
  contenu.id = "contenu";
  racine.append(barre.element, bandeaux.element, contenu);
  initialiserTiroir({ hote: racine, page: racine, appeler, retrouver });
  barre.majOnglet(onglet);
  bandeaux.maj([], []);
  // Réponse plus lente que 300 ms : espaces réservés et aria-busy jusqu'à la réponse (UX-DR15).
  chargement = suivreChargement(contenu, rendreVue, window);
  chargement.demarrer();
  window.addEventListener("keydown", surTouche);
  minuteurPeriode = window.setInterval(relire, PERIODE_MS);
  relire();
}

demarrer();
