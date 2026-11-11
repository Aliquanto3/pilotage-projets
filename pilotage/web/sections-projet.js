// Sections du tiroir de la story 4.7 (EXPERIENCE § Tiroir de détail) : État, Sessions par PC,
// Faits du dépôt, Critères de stabilité, Chantier et dépendances. Enregistrées à l'import ; leur
// place vient d'`ORDRE_SECTIONS` (tiroir.js).
//
// Statuts de session et critères sont rédigés par le noyau (`/api/etat`, `details`, AD-11) : rien
// n'est calculé ici, hormis la mise en forme des heures (temps.js). Texte non fiable (note de
// reprise, branche, PC, *quoi*) posé par textContent seulement, jamais tronqué.

import { el } from "./dom.js";
import { titreAttente } from "./synthese.js";
import { heureCourte, lireInstant } from "./temps.js";
import { enregistrerSection } from "./tiroir.js";
import { libelleAction, listeEtiquettes, pastilleAction, pastilleType } from "./types.js";

export const TEXTE_SANS_SESSION = "Aucune session connue.";
export const TEXTE_NON_RELUS = "Faits du dépôt non relus. Lancez un scan.";
export const TEXTE_HORS_CHANTIER = "Hors chantier.";

const CI = new Map([["verte", "verte"], ["rouge", "rouge"], ["en_cours", "en cours"],
  ["aucune", "aucune"]]);

function texteDe(valeur) {
  return typeof valeur === "string" && valeur !== "" ? valeur : null;
}

function entier(valeur) {
  return Number.isInteger(valeur) && valeur >= 0 ? valeur : 0;
}

function bloc() {
  return el("div", "tiroir-bloc");
}

function heure(valeur, maintenant) {
  const instant = lireInstant(valeur);
  return instant === null ? null : heureCourte(instant, maintenant);
}

// --- État ------------------------------------------------------------------------------------

function rendreEtat({ carte, etat }) {
  if (!carte) {
    return null;
  }
  const racine = bloc();
  const attend = carte.action === "attend-utilisateur";
  const tete = el("p", "tiroir-etat");
  tete.append(pastilleAction(carte.action, libelleAction(carte.action, titreAttente(etat))));
  if (attend) {
    tete.append(pastilleType(carte.type));
  }
  racine.append(tete);
  const quoi = attend ? texteDe(carte.quoi) : null;
  if (quoi !== null) {
    racine.append(el("p", "quoi", quoi));
  } else {
    const raison = carte.raison && texteDe(carte.raison.texte);
    if (raison !== null) {
      racine.append(el("p", "raison", raison));
    }
  }
  const phases = Array.isArray(carte.phase) ? carte.phase.filter((p) => texteDe(p) !== null) : [];
  if (phases.length > 0) {
    racine.append(el("p", "phase", `phase : ${phases.join(", ")}`));
  }
  const etiquettes = listeEtiquettes(carte);
  if (etiquettes !== null) {
    racine.append(etiquettes);
  }
  return racine;
}

// --- Sessions par PC -------------------------------------------------------------------------

function ligneSession(session, maintenant) {
  const item = el("li", "session");
  const parties = [];
  const statut = session.statut && texteDe(session.statut.texte);
  if (statut !== null) {
    parties.push(el("span", "session-statut", statut));
  }
  for (const [champ, prefixe] of [["debut", "début"], ["dernier_tour", "dernier tour"],
    ["fin", "fin"]]) {
    const quand = heure(session[champ], maintenant);
    if (quand !== null) {
      parties.push(el("span", null, `${prefixe} ${quand}`));
    }
  }
  const branche = texteDe(session.branche);
  if (branche !== null) {
    parties.push(el("span", "session-branche", branche));
  }
  const meta = el("p", "meta");
  parties.forEach((partie, i) => {
    if (i > 0) {
      meta.append(el("span", "meta-sep", " · "));
    }
    meta.append(partie);
  });
  item.append(meta);
  const note = texteDe(session.note);
  if (note !== null) {
    item.append(el("p", "note-reprise", note));
  }
  return item;
}

function rendreSessions({ detail, maintenant }) {
  const racine = bloc();
  const sessions = detail && Array.isArray(detail.sessions)
    ? detail.sessions.filter((s) => s && typeof s === "object") : [];
  if (sessions.length === 0) {
    racine.append(el("p", "neutre", TEXTE_SANS_SESSION));
    return racine;
  }
  // Sessions déjà triées par PC puis la plus récente d'abord (noyau) : un groupe par PC.
  let liste = null;
  let pcCourant = null;
  for (const session of sessions) {
    const pc = texteDe(session.pc) || "?";
    if (liste === null || pc !== pcCourant) {
      pcCourant = pc;
      liste = el("ul", "sessions");
      racine.append(el("h4", "tiroir-pc", pc), liste);
    }
    liste.append(ligneSession(session, maintenant));
  }
  return racine;
}

// --- Faits du dépôt --------------------------------------------------------------------------

function texteCommits(commits) {
  if (!commits || typeof commits !== "object") {
    return "aucun";
  }
  const parties = Object.keys(commits)
    .filter((type) => entier(commits[type]) > 0)
    .map((type) => `${entier(commits[type])} ${type}`);
  return parties.length > 0 ? parties.join(", ") : "aucun";
}

function rendreFaits({ detail, maintenant }) {
  const racine = bloc();
  const depot = detail && detail.depot && typeof detail.depot === "object" ? detail.depot : null;
  if (depot === null) {
    racine.append(el("p", "neutre", TEXTE_NON_RELUS));
    return racine;
  }
  const stories = depot.sprint_status === "absent"
    ? "pas de sprint-status.yaml" : String(entier(depot.stories_ouvertes));
  const liste = el("ul", "faits-depot");
  liste.append(
    el("li", null, `Release : ${texteDe(depot.tag) || "aucune"}`),
    el("li", null, `Commits depuis la release : ${texteCommits(depot.commits)}`),
    el("li", null, `PR ouvertes : ${entier(depot.prs_ouvertes)}`),
    el("li", null, `Stories ouvertes : ${stories}`),
    el("li", null, `CI de main : ${CI.get(depot.ci) || "aucune"}`),
  );
  racine.append(liste);
  const origine = detail.depot_de && typeof detail.depot_de === "object" ? detail.depot_de : null;
  const pc = origine ? texteDe(origine.pc) : null;
  if (pc !== null) {
    const quand = heure(origine.genere_a, maintenant);
    racine.append(el("p", "meta", quand !== null ? `relus sur ${pc}, ${quand}` : `relus sur ${pc}`));
  }
  return racine;
}

// --- Critères de stabilité -------------------------------------------------------------------

function rendreCriteres({ detail }) {
  const criteres = detail && Array.isArray(detail.criteres) ? detail.criteres : null;
  if (criteres === null) {
    return null;
  }
  const liste = el("ul", "criteres");
  for (const critere of criteres) {
    if (!critere || typeof critere !== "object") {
      continue;
    }
    const etat = critere.rempli === true ? "rempli" : "non rempli";
    const precision = texteDe(critere.precision);
    const texte = `${texteDe(critere.libelle) || ""} : ${etat}${precision ? ` (${precision})` : ""}`;
    liste.append(el("li", critere.rempli === true ? "critere critere-rempli" : "critere", texte));
  }
  return liste;
}

// --- Chantier et dépendances -----------------------------------------------------------------

// Membres d'une dépendance « A ← B » (forme validée par le schéma de projets.yaml).
export function membresDependance(ligne) {
  if (typeof ligne !== "string") {
    return [];
  }
  return ligne.split(" ← ");
}

function rendreChantier({ nom, carte, etat }) {
  const racine = bloc();
  const chantier = carte ? texteDe(carte.chantier) : null;
  racine.append(el("p", null, chantier !== null ? `Chantier : ${chantier}` : TEXTE_HORS_CHANTIER));
  const dependances = etat && Array.isArray(etat.dependances) ? etat.dependances : [];
  for (const ligne of dependances) {
    if (membresDependance(ligne).includes(nom)) {
      racine.append(el("p", "dependance", ligne));
    }
  }
  return racine;
}

enregistrerSection({ id: "etat", titre: "État", rendre: rendreEtat });
enregistrerSection({ id: "sessions", titre: "Sessions par PC", rendre: rendreSessions });
enregistrerSection({ id: "faits", titre: "Faits du dépôt", rendre: rendreFaits });
enregistrerSection({ id: "criteres", titre: "Critères de stabilité", rendre: rendreCriteres });
enregistrerSection({ id: "chantier", titre: "Chantier et dépendances", rendre: rendreChantier });
