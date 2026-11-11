// Section « Messages » du tiroir (story 5.6, FR34, UX-DR10, DR12, DR13) : dépôt d'un message pour
// une session du projet (`POST /api/message`) et liste des messages du projet, lue sur
// `GET /api/operations` (jamais insérée localement).
//
// Le serveur reste seul juge du texte (longueur, caractères, secrets) : le compteur et le bouton
// inactif sont un confort, le texte saisi part tel quel, sans rien ajouter ni retirer. Le texte
// d'un message, une fois relu, n'est pas fiable : posé par textContent seulement (AD-15).
//
// `maj` (relecture des 30 s) relit la liste seulement : zone de texte, compteur et « PC visé » ne
// sont jamais touchés, ni le focus. Une réponse arrivée après une demande plus récente, ou tiroir
// fermé, rouvert ou passé à un autre projet, est ignorée.

import { annoncer, el, vider } from "./dom.js";
import {
  effacerErreur, lireOperations, montrerErreur, operationsDe, oublierOperations, texteEchec,
} from "./operations.js";
import { enregistrerSection, tiroirOuvert } from "./tiroir.js";

export const BORNE_MESSAGE = 2048;
export const MESSAGES_AFFICHES = 20;
export const TEXTE_DEPOSE = "Message déposé, en attente de synchro.";
export const TEXTE_LECTURE = "Lecture des messages…";
export const TEXTE_AUCUN = "Aucun message.";
export const TOUS_LES_PC = "Tous les PC";

// État de chaque section construite : { ctx, numero, envoi, zone, ... }.
const ETATS = new WeakMap();
let compteurIds = 0;

export function octets(texte) {
  return new TextEncoder().encode(texte).length;
}

// « 2048 octets restants », « 1 octet restant », « 3 octets de trop », « 1 octet de trop ».
export function texteCompteur(n) {
  const reste = BORNE_MESSAGE - n;
  if (reste >= 0) {
    return reste < 2 ? `${reste} octet restant` : `${reste} octets restants`;
  }
  const trop = -reste;
  return trop < 2 ? `${trop} octet de trop` : `${trop} octets de trop`;
}

function pcsConnus(etat) {
  const fraicheur = etat && Array.isArray(etat.fraicheur) ? etat.fraicheur : [];
  const noms = [];
  for (const f of fraicheur) {
    if (f && typeof f.pc === "string" && f.pc !== "" && f.genere_a != null && !noms.includes(f.pc)) {
      noms.push(f.pc);
    }
  }
  return noms;
}

function actuelle(s, numero) {
  return numero === s.numero && tiroirOuvert() === s.ctx.nom
    && typeof document.contains === "function" && document.contains(s.noeud);
}

// Compteur et bouton « Déposer » d'après la zone de texte.
function majSaisie(s) {
  const n = octets(s.zone.value);
  s.compteur.textContent = texteCompteur(n);
  if (n > BORNE_MESSAGE) {
    s.compteur.classList.add("erreur");
  } else {
    s.compteur.classList.remove("erreur");
  }
  s.bouton.disabled = s.envoi || n > BORNE_MESSAGE || s.zone.value.trim() === "";
  // Zone en lecture seule pendant l'envoi : le 202 la vide, rien de tapé entre-temps n'est perdu.
  s.zone.readOnly = s.envoi;
}

function ligneMessage(message) {
  const item = el("li", "message");
  const pc = typeof message.pc === "string" && message.pc !== "" ? message.pc : null;
  const libelle = typeof message.libelle === "string" ? message.libelle : "";
  item.append(
    el("p", "texte-message", typeof message.texte === "string" ? message.texte : ""),
    el("p", "meta", `${pc === null ? "Pour tous les PC" : `Pour ${pc}`} · ${libelle}`),
  );
  return item;
}

function rendreListe(s, messages) {
  vider(s.liste);
  if (messages.length === 0) {
    s.liste.append(el("p", "meta", TEXTE_AUCUN));
    return;
  }
  const tries = [...messages].sort((a, b) => {
    const x = String(a.id);
    const y = String(b.id);
    return x < y ? 1 : x > y ? -1 : 0;
  });
  const ul = el("ul", "liste-messages");
  for (const [i, message] of tries.entries()) {
    if (i >= MESSAGES_AFFICHES) {
      break;
    }
    ul.append(ligneMessage(message));
  }
  s.liste.append(ul);
  const caches = tries.length - MESSAGES_AFFICHES;
  if (caches > 0) {
    const texte = caches === 1 ? "1 message plus ancien non affiché."
      : `${caches} messages plus anciens non affichés.`;
    s.liste.append(el("p", "meta", texte));
  }
}

async function chargerListe(s) {
  s.numero += 1;
  const numero = s.numero;
  const { statut, corps } = await lireOperations(s.ctx);
  if (statut === 401 || !actuelle(s, numero)) {
    return;
  }
  if (statut !== 200) {
    if (s.liste.textContent === TEXTE_LECTURE) {
      vider(s.liste);
    }
    s.erreurLecture = true;
    montrerErreur(s.erreur, texteEchec(statut, corps));
    return;
  }
  if (s.erreurLecture) {
    s.erreurLecture = false;
    effacerErreur(s.erreur);
  }
  rendreListe(s, operationsDe(corps, s.ctx.nom).messages);
}

async function deposer(s) {
  if (s.envoi || s.bouton.disabled) {
    return;
  }
  const texte = s.zone.value;
  const json = { projet: s.ctx.nom, texte };
  if (s.select.value !== "") {
    json.pc = s.select.value;
  }
  s.envoi = true;
  majSaisie(s);
  s.noeud.setAttribute("aria-busy", "true");
  const { statut, corps } = await s.ctx.appeler("POST", "/api/message", { json });
  s.envoi = false;
  s.noeud.removeAttribute("aria-busy");
  if (statut === 202) {
    oublierOperations();
  }
  if (statut === 401 || tiroirOuvert() !== s.ctx.nom || !document.contains(s.noeud)) {
    majSaisie(s);
    return;
  }
  if (statut === 202) {
    s.zone.value = "";
    majSaisie(s);
    s.erreurLecture = false;
    effacerErreur(s.erreur);
    s.zone.focus();
    annoncer(TEXTE_DEPOSE);
    chargerListe(s);
    return;
  }
  majSaisie(s);
  montrerErreur(s.erreur, texteEchec(statut, corps), true);
}

function rendre(ctx) {
  compteurIds += 1;
  const idZone = `boite-message-${compteurIds}`;
  const idPc = `boite-pc-${compteurIds}`;
  const noeud = el("div", "boite");
  const erreur = el("div", "erreur-boite");
  const labelZone = el("label", "etiquette-boite", "Message");
  labelZone.setAttribute("for", idZone);
  const zone = el("textarea", "champ-message");
  zone.id = idZone;
  zone.setAttribute("aria-describedby", "boite-compteur");
  const compteur = el("p", "meta");
  compteur.id = "boite-compteur";
  const labelPc = el("label", "etiquette-boite", "PC visé");
  labelPc.setAttribute("for", idPc);
  const select = el("select", "choix-pc");
  select.id = idPc;
  const tous = el("option", null, TOUS_LES_PC);
  tous.value = "";
  select.append(tous);
  for (const pc of pcsConnus(ctx.etat)) {
    const option = el("option", null, pc);
    option.value = pc;
    select.append(option);
  }
  const bouton = el("button", "btn2 deposer", "Déposer");
  bouton.type = "button";
  const liste = el("div", "messages-projet");
  liste.append(el("p", "meta", TEXTE_LECTURE));
  noeud.append(erreur, labelZone, zone, compteur, labelPc, select, bouton, liste);
  const s = {
    ctx, noeud, erreur, zone, compteur, select, bouton, liste, numero: 0, envoi: false,
    erreurLecture: false,
  };
  ETATS.set(noeud, s);
  zone.addEventListener("input", () => majSaisie(s));
  bouton.addEventListener("click", () => deposer(s));
  majSaisie(s);
  chargerListe(s);
  return noeud;
}

// Relecture des 30 s : la liste seulement.
function maj(noeud, ctx) {
  const s = ETATS.get(noeud);
  if (s === undefined) {
    return;
  }
  s.ctx = ctx;
  chargerListe(s);
}

enregistrerSection({ id: "messages", titre: "Messages", rendre, maj });
