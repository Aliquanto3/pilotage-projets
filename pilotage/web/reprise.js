// Panneau de reprise du tiroir (story 5.5, FR32, UX-DR8, UX-DR10, UX-DR11) : sessions du projet
// (`GET /api/sessions/<projet>`), commande de la session choisie (`POST /api/reprise`) et brief
// à la demande (`GET /api/brief/<id>`).
//
// La commande vient du serveur (AD-9) : la chaîne reçue va telle quelle à `blocCommande`, sans
// être assemblée, découpée ni modifiée ici. Texte non fiable (PC, dossier, brief, erreurs) posé
// par textContent seulement (AD-15). Les appels passent par `ctx.appeler` (app.js tient seul la
// clé d'accès et traite seul le 401).
//
// Section construite à chaque ouverture du tiroir, sans `maj` : le panneau garde les données de
// son ouverture. Une réponse arrivée après une autre demande, ou tiroir fermé, rouvert ou passé à
// un autre projet, est ignorée.

import { blocCommande } from "./cle.js";
import { TEXTE_INJOIGNABLE, annoncer, el, vider } from "./dom.js";
import { heureCourte, lireInstant } from "./temps.js";
import { enregistrerSection, tiroirOuvert } from "./tiroir.js";

export const BORNE_BRIEF = 32768;
export const TEXTE_RECHERCHE = "Recherche des sessions…";
export const TEXTE_PAS_CLONE = "Pas cloné sur ce PC. Clonez le dépôt sous Documents\\GitHub, puis relancez un scan.";
export const TEXTE_AUCUNE = "Aucune session à reprendre sur ce projet.";
export const TEXTE_DOSSIER_ABSENT = "Dossier de la session introuvable sur ce PC. Choisissez une autre session ou relancez un scan.";
export const TEXTE_BRIEF_ABSENT = "Brief introuvable (purgé ou effacé). Fermez puis rouvrez le tiroir pour en préparer un autre.";
export const TEXTE_TRONQUE = "… (brief tronqué à l'affichage)";
const TEXTE_ERREUR = "Erreur du serveur local.";
const RAISON_PAS_CLONE = "pas cloné ici";
const RAISON_DOSSIER_ABSENT = "dossier de la session introuvable";

// Numéro de la dernière demande (construction ou changement de session).
let demande = 0;
let compteur = 0;

function texteDe(valeur) {
  return typeof valeur === "string" && valeur !== "" ? valeur : null;
}

// Texte d'un échec, ou null pour un 401 (app.js a déjà remplacé l'écran).
function texteEchec(statut, corps) {
  if (statut === 401) {
    return null;
  }
  if (statut === 0) {
    return TEXTE_INJOIGNABLE;
  }
  return corps && texteDe(corps.erreur) !== null ? corps.erreur : TEXTE_ERREUR;
}

function heure(valeur, maintenant) {
  const instant = lireInstant(valeur);
  return instant === null ? null : heureCourte(instant, maintenant);
}

// « pc (ce PC) · début HH:MM · dernier tour … ».
function libelleSession(session, maintenant) {
  const pc = texteDe(session.pc) || "";
  const parties = [session.ce_pc === true ? `${pc} (ce PC)` : pc];
  const debut = heure(session.debut, maintenant);
  if (debut !== null) {
    parties.push(`début ${debut}`);
  }
  const tour = heure(session.dernier_tour, maintenant);
  if (tour !== null) {
    parties.push(`dernier tour ${tour}`);
  }
  return parties.join(" · ");
}

function finir(panneau) {
  panneau.removeAttribute("aria-busy");
}

function occuper(panneau) {
  panneau.setAttribute("aria-busy", "true");
}

function rendre(ctx) {
  demande += 1;
  const numero = demande;
  const panneau = el("div", "panneau-reprise");
  occuper(panneau);
  panneau.append(el("p", "meta", TEXTE_RECHERCHE));
  charger(ctx, panneau, numero);
  return panneau;
}

// Vrai si la réponse à la demande `numero` peut encore s'appliquer au panneau.
function actuelle(ctx, panneau, numero) {
  return numero === demande && tiroirOuvert() === ctx.nom
    && typeof document.contains === "function" && document.contains(panneau);
}

function echouer(zone, panneau, texte) {
  vider(zone);
  zone.append(el("p", "meta erreur-reprise", texte));
  finir(panneau);
  annoncer(texte);
}

async function charger(ctx, panneau, numero) {
  const { statut, corps } = await ctx.appeler("GET", "/api/sessions/" + encodeURIComponent(ctx.nom));
  if (statut === 401 || !actuelle(ctx, panneau, numero)) {
    return;
  }
  const donnees = statut === 200 && corps && corps.ok ? corps.donnees : null;
  if (!donnees || typeof donnees !== "object") {
    echouer(panneau, panneau, texteEchec(statut, corps));
    return;
  }
  vider(panneau);
  finir(panneau);
  if (donnees.clone_ici !== true) {
    panneau.append(el("p", "meta", TEXTE_PAS_CLONE));
    return;
  }
  const sessions = Array.isArray(donnees.sessions)
    ? donnees.sessions.filter((s) => s && typeof s === "object") : [];
  if (sessions.length === 0) {
    panneau.append(el("p", "meta", TEXTE_AUCUNE));
    return;
  }
  const maintenant = ctx.maintenant instanceof Date ? ctx.maintenant : new Date();
  const resultat = el("div", "resultat-reprise");
  let rang = 0;
  if (sessions.length === 1) {
    panneau.append(el("p", "meta session-reprise", libelleSession(sessions[0], maintenant)));
  } else {
    compteur += 1;
    const id = `reprise-session-${compteur}`;
    const label = el("label", "etiquette-reprise", "Session à reprendre");
    label.setAttribute("for", id);
    const select = el("select", "choix-reprise");
    select.id = id;
    sessions.forEach((session, i) => {
      const option = el("option", null, libelleSession(session, maintenant));
      option.value = String(i);
      select.append(option);
    });
    const proposee = sessions.findIndex((s) => s.session === donnees.proposee);
    rang = proposee >= 0 ? proposee : 0;
    select.selectedIndex = rang;
    select.addEventListener("change", () => {
      const choisi = Number(select.value);
      if (Number.isInteger(choisi) && choisi >= 0 && choisi < sessions.length) {
        demande += 1;
        preparer(ctx, panneau, resultat, sessions[choisi], demande);
      }
    });
    panneau.append(label, select);
  }
  panneau.append(resultat);
  preparer(ctx, panneau, resultat, sessions[rang], numero);
}

// Commande de `session` : POST, puis bloc de commande et chemins cités par le serveur.
async function preparer(ctx, panneau, resultat, session, numero) {
  occuper(panneau);
  const { statut, corps } = await ctx.appeler("POST", "/api/reprise", {
    json: { projet: ctx.nom, session: session.session, pc: session.pc },
  });
  if (statut === 401 || !actuelle(ctx, panneau, numero)) {
    return;
  }
  const donnees = statut === 200 && corps && corps.ok ? corps.donnees : null;
  if (!donnees || typeof donnees !== "object") {
    echouer(resultat, panneau, texteEchec(statut, corps));
    return;
  }
  vider(resultat);
  finir(panneau);
  const commande = texteDe(donnees.commande);
  if (commande === null) {
    const raison = texteDe(donnees.raison);
    let texte = raison || TEXTE_ERREUR;
    if (raison === RAISON_PAS_CLONE) {
      texte = TEXTE_PAS_CLONE;
    } else if (raison === RAISON_DOSSIER_ABSENT) {
      texte = TEXTE_DOSSIER_ABSENT;
    }
    resultat.append(el("p", "meta", texte));
    return;
  }
  resultat.append(blocCommande(commande));
  if (donnees.mode === "brief") {
    resultat.append(el("p", "chemin-reprise", `Brief : ${texteDe(donnees.chemin_brief) || ""}`));
    const id = texteDe(donnees.brief);
    if (id !== null) {
      resultat.append(...zoneBrief(ctx, panneau, id, numero));
    }
  } else {
    resultat.append(el("p", "chemin-reprise", `Dossier : ${texteDe(donnees.dossier) || ""}`));
  }
}

function borner(brut) {
  if (brut.length <= BORNE_BRIEF) {
    return brut;
  }
  // Coupure hors d'une paire de substitution (caractère hors du plan de base).
  const code = brut.charCodeAt(BORNE_BRIEF - 1);
  const fin = code >= 0xd800 && code <= 0xdbff ? BORNE_BRIEF - 1 : BORNE_BRIEF;
  return `${brut.slice(0, fin)}${TEXTE_TRONQUE}`;
}

// Bouton « Voir le brief », `pre` du brief et message d'échec. Chargé au premier clic, une fois.
function zoneBrief(ctx, panneau, id, numero) {
  compteur += 1;
  const idPre = `brief-reprise-${compteur}`;
  const bouton = el("button", "btn2 voir-brief", "Voir le brief");
  bouton.type = "button";
  bouton.setAttribute("aria-expanded", "false");
  bouton.setAttribute("aria-controls", idPre);
  const pre = el("pre", "brief");
  pre.id = idPre;
  pre.tabIndex = 0;
  pre.hidden = true;
  const message = el("div", "message-brief");
  let charge = false;
  let enCours = false;

  function montrer(visible) {
    pre.hidden = !visible;
    bouton.setAttribute("aria-expanded", visible ? "true" : "false");
    bouton.textContent = visible ? "Masquer le brief" : "Voir le brief";
  }

  bouton.addEventListener("click", async () => {
    if (charge) {
      montrer(pre.hidden);
      return;
    }
    if (enCours) {
      return;
    }
    enCours = true;
    occuper(panneau);
    const reponse = await ctx.appeler("GET", "/api/brief/" + encodeURIComponent(id), { texte: true });
    enCours = false;
    if (reponse.statut === 401 || !actuelle(ctx, panneau, numero)) {
      return;
    }
    if (reponse.statut === 200 && typeof reponse.texte === "string") {
      vider(message);
      finir(panneau);
      pre.textContent = borner(reponse.texte);
      charge = true;
      montrer(true);
      return;
    }
    const texte = reponse.statut === 404 ? TEXTE_BRIEF_ABSENT : texteEchec(reponse.statut, reponse.corps);
    echouer(message, panneau, texte);
  });

  return [bouton, pre, message];
}

enregistrerSection({ id: "reprise", titre: "Reprise", rendre });
