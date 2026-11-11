// Section « Réglages » du tiroir (story 5.6, FR35, UX-DR10, DR12, DR13) : chantier, pause et
// exclusion d'un projet, chacun par un seul `POST /api/projets` au patch exact
// `{champ: {attendu, voulu}}`, appliqué plus tard par `sync`.
//
// Aucune mise à jour optimiste : les contrôles montrent la valeur en vigueur (`ctx.carte`,
// `ctx.detail.pause`), plus « En attente de synchro : … » tant que l'opération du champ est dans
// `GET /api/operations` (champ alors inactif : un second patch au même `attendu` serait rejeté).
// Un contrôle est « en cours » de sa première saisie jusqu'au 202 de son envoi : `maj` ne
// l'écrit pas, ni le focus ; au repos, il reprend la valeur en vigueur (rejet compris).
// Rejets : alertes `operation` du projet, texte du serveur posé par textContent (AD-15).

import { el, vider } from "./dom.js";
import {
  effacerErreur, lireOperations, montrerErreur, operationsDe, oublierOperations, texteEchec,
} from "./operations.js";
import { enregistrerSection, tiroirOuvert } from "./tiroir.js";

export const CATEGORIE_A_CLASSER = "découvert, à classer";
export const TEXTE_ABSENT = "Projet exclu ou retiré : il n'apparaît plus dans l'appli.";
export const TEXTE_ILLISIBLE = "Date de revue illisible dans projets.yaml : corrigez-la à la main.";
export const TEXTE_CONFIRMATION = "Le projet disparaîtra de l'appli sur tous les PC après la "
  + "synchro. On le réintègre en éditant projets.yaml.";
const AUCUN_CHANTIER = "Aucun (à classer)";

const ETATS = new WeakMap();
let compteurIds = 0;

const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

// Vrai pour une date `AAAA-MM-JJ` du calendrier.
export function dateLisible(valeur) {
  const m = typeof valeur === "string" ? DATE.exec(valeur) : null;
  if (m === null) {
    return false;
  }
  const date = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return date.getUTCFullYear() === Number(m[1]) && date.getUTCMonth() === Number(m[2]) - 1
    && date.getUTCDate() === Number(m[3]);
}

function jjMm(valeur) {
  const m = DATE.exec(valeur);
  return `${m[3]}/${m[2]}`;
}

function deuxChiffres(n) {
  return n < 10 ? `0${n}` : String(n);
}

// Date locale du jour en `AAAA-MM-JJ`.
function aujourdhui(maintenant) {
  const d = maintenant instanceof Date ? maintenant : new Date();
  return `${d.getFullYear()}-${deuxChiffres(d.getMonth() + 1)}-${deuxChiffres(d.getDate())}`;
}

// Valeurs en vigueur : { chantier, enPause, revue, lisible }.
function enVigueur(ctx) {
  const carte = ctx.carte;
  const chantier = typeof carte.chantier === "string" && carte.chantier !== "" ? carte.chantier : null;
  const pause = ctx.detail && ctx.detail.pause && typeof ctx.detail.pause === "object"
    ? ctx.detail.pause : null;
  const revue = pause !== null && typeof pause.revue === "string" ? pause.revue : null;
  return { chantier, enPause: pause !== null, revue, lisible: pause === null || dateLisible(revue) };
}

function texteEnVigueur(v) {
  const chantier = v.chantier === null ? "Aucun chantier (à classer)" : `Chantier : ${v.chantier}`;
  let pause = "pas de pause";
  if (v.enPause) {
    pause = v.lisible ? `en pause jusqu'au ${jjMm(v.revue)}` : "en pause";
  }
  return `En vigueur : ${chantier} · ${pause}`;
}

// « En attente de synchro : … » d'un champ du patch.
function texteAttente(champ, voulu) {
  if (champ === "chantier") {
    return typeof voulu === "string" ? `rattachement à ${voulu}` : "retrait du chantier";
  }
  if (champ === "pause") {
    return typeof voulu === "string" && dateLisible(voulu) ? `pause jusqu'au ${jjMm(voulu)}`
      : "levée de la pause";
  }
  return "exclusion";
}

// Champs du projet visés par une opération `modifier_projets` en file : Map(champ -> texte).
function enAttente(operations) {
  const champs = new Map();
  for (const o of operations) {
    if (o.verbe !== "modifier_projets" || !o.patch || typeof o.patch !== "object") {
      continue;
    }
    for (const champ of ["chantier", "pause", "exclu"]) {
      const regle = Object.hasOwn(o.patch, champ) ? o.patch[champ] : null;
      if (regle && typeof regle === "object") {
        champs.set(champ, texteAttente(champ, regle.voulu));
      }
    }
  }
  return champs;
}

function actuelle(s, numero) {
  return (numero === undefined || numero === s.numero) && tiroirOuvert() === s.ctx.nom
    && typeof document.contains === "function" && document.contains(s.noeud);
}

function ligneAttente(zone, texte) {
  vider(zone);
  if (texte) {
    zone.append(el("p", "meta attente-reglage", `En attente de synchro : ${texte}`));
  }
}

function options(s, v) {
  const connus = Array.isArray(s.ctx.etat && s.ctx.etat.chantiers_connus)
    ? s.ctx.etat.chantiers_connus.filter((n) => typeof n === "string" && n !== "") : [];
  if (v.chantier !== null && !connus.includes(v.chantier)) {
    connus.push(v.chantier);
  }
  vider(s.chantier);
  const aucun = el("option", null, AUCUN_CHANTIER);
  aucun.value = "";
  s.chantier.append(aucun);
  for (const nom of connus) {
    const option = el("option", null, nom);
    option.value = nom;
    s.chantier.append(option);
  }
  s.chantier.value = v.chantier === null ? "" : v.chantier;
}

// Valeurs des contrôles au repos, libellés et états `disabled` d'après l'état et la file.
function actualiser(s) {
  const v = enVigueur(s.ctx);
  s.vigueur = v;
  s.texteVigueur.textContent = texteEnVigueur(v);
  vider(s.rejets);
  const alertes = s.ctx.etat && Array.isArray(s.ctx.etat.alertes) ? s.ctx.etat.alertes : [];
  for (const a of alertes) {
    if (a && a.source === "operation" && a.params && a.params.projet === s.ctx.nom
      && typeof a.texte === "string") {
      s.rejets.append(el("div", "bandeau-local alerte", a.texte));
    }
  }
  if (!s.enCours.has("chantier")) {
    options(s, v);
  }
  if (!s.enCours.has("pause")) {
    s.date.value = v.enPause && v.lisible ? v.revue : "";
  }
  s.date.min = aujourdhui(s.ctx.maintenant);
  s.rattacher.textContent = s.ctx.carte.categorie === CATEGORIE_A_CLASSER ? "Classer" : "Rattacher";
  s.mettre.textContent = v.enPause ? "Changer la date de revue" : "Mettre en pause";
  s.lever.hidden = !v.enPause;
  vider(s.illisible);
  if (!v.lisible) {
    s.illisible.append(el("p", "meta erreur", TEXTE_ILLISIBLE));
  }
  ligneAttente(s.attenteChantier, s.attente.get("chantier"));
  ligneAttente(s.attentePause, s.attente.get("pause"));
  ligneAttente(s.attenteExclu, s.attente.get("exclu"));
  etats(s);
}

// États `disabled` seuls (appelé aussi à chaque saisie).
function etats(s) {
  const v = s.vigueur;
  const occupe = s.envoi !== null;
  const voulu = s.chantier.value === "" ? null : s.chantier.value;
  const chantierPris = occupe || s.attente.has("chantier");
  s.chantier.disabled = chantierPris;
  s.rattacher.disabled = chantierPris || voulu === v.chantier;
  const pausePrise = occupe || s.attente.has("pause") || !v.lisible;
  s.date.disabled = pausePrise;
  s.mettre.disabled = pausePrise || !dateLisible(s.date.value) || s.date.value === v.revue;
  s.lever.disabled = pausePrise;
  const excluPris = occupe || s.attente.has("exclu");
  s.exclure.disabled = excluPris;
  s.confirmer.disabled = excluPris;
}

async function chargerAttente(s) {
  s.numero += 1;
  const numero = s.numero;
  const { statut, corps } = await lireOperations(s.ctx);
  if (statut === 401 || !actuelle(s, numero) || s.ctx.carte === null) {
    return;
  }
  if (statut !== 200) {
    s.erreurLecture = true;
    montrerErreur(s.erreur, texteEchec(statut, corps));
    return;
  }
  if (s.erreurLecture) {
    s.erreurLecture = false;
    effacerErreur(s.erreur);
  }
  s.attente = enAttente(operationsDe(corps, s.ctx.nom).operations);
  actualiser(s);
}

async function envoyer(s, champ, attendu, voulu) {
  if (s.envoi !== null) {
    return;
  }
  s.envoi = champ;
  etats(s);
  s.noeud.setAttribute("aria-busy", "true");
  const json = { projet: s.ctx.nom, patch: { [champ]: { attendu, voulu } } };
  const { statut, corps } = await s.ctx.appeler("POST", "/api/projets", { json });
  s.envoi = null;
  s.noeud.removeAttribute("aria-busy");
  if (statut === 202) {
    oublierOperations();
  }
  if (statut === 401 || !actuelle(s) || s.ctx.carte === null) {
    return;
  }
  if (statut === 202) {
    s.enCours.delete(champ);
    s.erreurLecture = false;
    effacerErreur(s.erreur);
    if (champ === "exclu") {
      fermerConfirmation(s);
    }
    actualiser(s);
    chargerAttente(s);
    return;
  }
  etats(s);
  montrerErreur(s.erreur, texteEchec(statut, corps), true);
}

function ouvrirConfirmation(s) {
  s.exclure.hidden = true;
  s.confirmation.hidden = false;
  s.confirmer.focus();
}

function fermerConfirmation(s) {
  s.confirmation.hidden = true;
  s.exclure.hidden = false;
  s.exclure.focus();
}

function bouton(texte, classe) {
  const b = el("button", `btn2 ${classe}`, texte);
  b.type = "button";
  return b;
}

function champ(texte, controle, prefixe) {
  compteurIds += 1;
  controle.id = `${prefixe}-${compteurIds}`;
  const label = el("label", "etiquette-reglage", texte);
  label.setAttribute("for", controle.id);
  return label;
}

function absent(noeud) {
  vider(noeud);
  noeud.append(el("p", "meta", TEXTE_ABSENT));
}

function construire(ctx) {
  const noeud = el("div", "reglages");
  const s = {
    ctx, noeud, numero: 0, envoi: null, enCours: new Set(), attente: new Map(), vigueur: null,
    erreurLecture: false,
    rejets: el("div", "rejets-reglages"),
    erreur: el("div", "erreur-reglages"),
    texteVigueur: el("p", "en-vigueur"),
    chantier: el("select", "choix-chantier"),
    rattacher: bouton("Rattacher", "rattacher"),
    attenteChantier: el("div", "attente-chantier"),
    date: el("input", "date-revue"),
    mettre: bouton("Mettre en pause", "mettre-en-pause"),
    lever: bouton("Lever la pause", "lever-pause"),
    illisible: el("div", "revue-illisible"),
    attentePause: el("div", "attente-pause"),
    exclure: bouton("Exclure", "exclure"),
    confirmation: el("div", "confirmation-exclusion"),
    confirmer: bouton(`Confirmer l'exclusion de ${ctx.nom}`, "confirmer-exclusion"),
    annuler: bouton("Annuler", "annuler-exclusion"),
    attenteExclu: el("div", "attente-exclusion"),
  };
  s.date.type = "date";
  const blocChantier = el("div", "reglage");
  blocChantier.append(champ("Chantier", s.chantier, "reglage-chantier"), s.chantier, s.rattacher,
    s.attenteChantier);
  const blocPause = el("div", "reglage");
  blocPause.append(champ("Date de revue", s.date, "reglage-pause"), s.date, s.mettre, s.lever,
    s.illisible, s.attentePause);
  s.confirmation.hidden = true;
  s.confirmation.append(el("p", "meta", TEXTE_CONFIRMATION), s.confirmer, s.annuler);
  const blocExclu = el("div", "reglage");
  blocExclu.append(s.exclure, s.confirmation, s.attenteExclu);
  noeud.append(s.rejets, s.erreur, s.texteVigueur, blocChantier, blocPause, blocExclu);

  s.chantier.addEventListener("change", () => {
    s.enCours.add("chantier");
    etats(s);
  });
  for (const type of ["input", "change"]) {
    s.date.addEventListener(type, () => {
      s.enCours.add("pause");
      etats(s);
    });
  }
  s.rattacher.addEventListener("click", () => {
    if (!s.rattacher.disabled) {
      envoyer(s, "chantier", s.vigueur.chantier, s.chantier.value === "" ? null : s.chantier.value);
    }
  });
  s.mettre.addEventListener("click", () => {
    if (!s.mettre.disabled) {
      envoyer(s, "pause", s.vigueur.revue, s.date.value);
    }
  });
  s.lever.addEventListener("click", () => {
    if (!s.lever.disabled) {
      envoyer(s, "pause", s.vigueur.revue, null);
    }
  });
  s.exclure.addEventListener("click", () => {
    if (!s.exclure.disabled) {
      ouvrirConfirmation(s);
    }
  });
  s.annuler.addEventListener("click", () => fermerConfirmation(s));
  s.confirmation.addEventListener("keydown", (evenement) => {
    if (evenement.key === "Escape" && !s.confirmation.hidden) {
      evenement.preventDefault();
      fermerConfirmation(s);
    }
  });
  s.confirmer.addEventListener("click", () => {
    if (!s.confirmer.disabled) {
      envoyer(s, "exclu", false, true);
    }
  });
  return s;
}

function rendre(ctx) {
  const s = construire(ctx);
  ETATS.set(s.noeud, s);
  if (ctx.carte === null) {
    absent(s.noeud);
    return s.noeud;
  }
  actualiser(s);
  chargerAttente(s);
  return s.noeud;
}

function maj(noeud, ctx) {
  const s = ETATS.get(noeud);
  if (s === undefined || s.ctx.carte === null) {
    return;
  }
  s.ctx = ctx;
  if (ctx.carte === null) {
    absent(noeud);
    return;
  }
  actualiser(s);
  chargerAttente(s);
}

enregistrerSection({ id: "reglages", titre: "Réglages", rendre, maj });
