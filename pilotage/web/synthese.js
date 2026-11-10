// Tête de l'accueil « Coup d'œil » (story 4.10, UX-DR22, DR23, DR24) : phrase-synthèse, bloc des
// stables, barre de répartition et sa légende, deux aides repliables.
//
// L'appli ne compte rien (AD-11 amendé) : les comptes viennent de `comptes` de /api/etat, les noms
// et les heures des cartes de `colonnes`, dans l'ordre du serveur. Ce module met en forme
// seulement : heures, accords, pourcentage arrondi, largeur des segments.
//
// Texte non fiable (AD-15) : les noms de projet sont posés par textContent (el), dans des `span`,
// jamais en lien ni en attribut, et jamais coupés par le code.

import { el, svg, vider } from "./dom.js";
import { heureCourte, lireInstant } from "./temps.js";
import { TYPES, icone, pastilleType } from "./types.js";

export const AUCUN_PROJET =
  "Aucun projet trouvé sous Documents\\GitHub. Lancez un scan avec le bouton Scan de la barre du haut.";
export const PERSONNE = "Personne ne vous attend.";
// Au-delà de ce délai sans réponse, `main` porte aria-busy et la tête ses espaces réservés.
export const DELAI_CHARGEMENT_MS = 300;
// Trois noms au plus dans la synthèse, puis « et N autres » (règle 5).
const NOMS_MAX = 3;

// Libellé d'Attend : « Attend <nom> » si `/api/etat` porte un nom affiché (`utilisateur`), sinon
// « Vous attend ». Le nom n'est posé que par textContent (el), comme tout texte des données.
export function titreAttente(etat) {
  const nom = etat && typeof etat.utilisateur === "string" ? etat.utilisateur.trim() : "";
  return nom ? `Attend ${nom}` : "Vous attend";
}

// Groupes de la barre, dans l'ordre des segments (DESIGN § Components) : compte lu dans
// `comptes.actions` (groupes d'action) ou `comptes.familles` (motifs de Rien à faire).
const GROUPES = [
  { cle: "attend", libelle: "Vous attend", source: "actions", nom: "attend-utilisateur",
    trace: "M12 2.5l3.1 6.4 7 .9-5.1 4.9 1.2 6.9L12 18.3l-6.2 3.3 1.2-6.9L1.9 9.8l7-.9z" },
  { cle: "relancer", libelle: "À relancer", source: "actions", nom: "a-relancer",
    trace: "M19 12a7 7 0 1 1-2.3-5.2M17.5 3v4.5H13" },
  { cle: "tourne", libelle: "Tourne", source: "actions", nom: "tourne", trace: "M7 4.5v15L19.5 12z" },
  { cle: "stable", libelle: "stables", source: "familles", nom: "stable", trace: "M5 12.5l4.5 4.5L19 7.5" },
  { cle: "pause", libelle: "en pause", source: "familles", nom: "pause", trace: "M8.5 5v14M15.5 5v14" },
  { cle: "a-classer", libelle: "à classer", source: "familles", nom: "a-classer",
    trace: "M3 6.5h6.5l2 2.5H21v10H3z" },
];

const TRACE_LIVRE = "M3 5.5c3-1.2 6-1.2 9 .6 3-1.8 6-1.8 9-.6v13c-3-1.2-6-1.2-9 .6-3-1.8-6-1.8-9-.6zM12 6.1v13";
const TRACE_INFO = "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5v.1";
const TRACE_CHEVRON = "M6 9.5l6 6 6-6";
const CRITERES = [
  "Une release publiée",
  "Aucun commit hors docs/chore depuis la release",
  "Aucune story ouverte",
  "Aucune PR ouverte",
  "CI de main verte",
];

function deuxChiffres(n) {
  return String(n).padStart(2, "0");
}

function entier(valeur) {
  return Number.isInteger(valeur) && valeur > 0 ? valeur : 0;
}

function compte(comptes, source, nom) {
  const table = comptes && comptes[source] && typeof comptes[source] === "object" ? comptes[source] : {};
  return entier(table[nom]);
}

function cartesDe(etat, action) {
  const colonnes = etat && etat.colonnes ? etat.colonnes : {};
  return Array.isArray(colonnes[action]) ? colonnes[action] : [];
}

function nomDe(carte) {
  return carte && typeof carte.nom === "string" ? carte.nom : "";
}

function pluriel(n, un, plusieurs) {
  return n > 1 ? plusieurs : un;
}

// « depuis HH:MM », « depuis hier HH:MM », « depuis le JJ/MM » (EXPERIENCE § Voice and Tone) ;
// `matin` : une heure du jour avant 12:00 devient « depuis ce matin » (règle 6). "" sans heure.
export function texteDepuis(valeur, maintenant, matin) {
  const instant = lireInstant(valeur);
  if (instant === null) {
    return "";
  }
  const court = heureCourte(instant, maintenant);
  const hm = `${deuxChiffres(instant.getHours())}:${deuxChiffres(instant.getMinutes())}`;
  if (court === hm) {
    return matin && instant.getHours() < 12 ? "depuis ce matin" : `depuis ${hm}`;
  }
  return court.startsWith("hier ") ? `depuis ${court}` : `depuis le ${court}`;
}

// Liste lue « a », « a et b », « a, b et c » : chaque élément est une liste de parties.
function joindre(elements) {
  const parties = [];
  elements.forEach((element, i) => {
    if (i > 0) {
      parties.push({ texte: i === elements.length - 1 ? " et " : ", " });
    }
    parties.push(...element);
  });
  return parties;
}

// Première phrase (règles 1, 2, 5, 6) : noms des projets qui attendent, groupés par heure de
// début consécutive identique, dans l'ordre de la colonne.
function phraseAttente(attentes, maintenant) {
  if (attentes.length === 0) {
    return [{ texte: PERSONNE }];
  }
  const groupes = [];
  const montres = Math.min(attentes.length, NOMS_MAX);
  for (let i = 0; i < montres; i += 1) {
    const depuis = texteDepuis(attentes[i].depuis, maintenant, true);
    const dernier = groupes[groupes.length - 1];
    if (dernier && dernier.depuis === depuis) {
      dernier.elements.push([{ nom: nomDe(attentes[i]) }]);
    } else {
      groupes.push({ depuis, elements: [[{ nom: nomDe(attentes[i]) }]] });
    }
  }
  const reste = attentes.length - montres;
  if (reste > 0) {
    const autres = [{ texte: `${reste} ${pluriel(reste, "autre", "autres")}` }];
    // Une heure commune à tous les autres, sinon aucune : « et 2 autres depuis ce matin » ne
    // doit pas couvrir une attente de l'après-midi.
    const heures = new Set();
    for (let i = montres; i < attentes.length; i += 1) {
      heures.add(texteDepuis(attentes[i].depuis, maintenant, true));
    }
    const depuis = heures.size === 1 ? [...heures][0] : "";
    const dernier = groupes[groupes.length - 1];
    if (depuis && dernier.depuis === depuis) {
      dernier.elements.push(autres);
    } else {
      groupes.push({ depuis, elements: [autres], autres: true });
    }
  }
  const parties = [];
  groupes.forEach((groupe, i) => {
    if (i > 0) {
      parties.push({ texte: groupe.autres ? ", et " : ", " });
    }
    parties.push(...(groupe.autres ? groupe.elements[0] : joindre(groupe.elements)));
    if (i === 0) {
      parties.push({ texte: groupe.elements.length > 1 ? " vous attendent" : " vous attend" });
    }
    if (groupe.depuis) {
      parties.push({ texte: ` ${groupe.depuis}` });
    }
  });
  parties.push({ texte: "." });
  return parties;
}

// Seconde phrase (règles 3, 4, 7) : comptes des autres colonnes, un compte nul omis ; si personne
// n'attend, le plus ancien projet à relancer (première carte de la colonne) est daté par son
// dernier tour, omis s'il n'en a pas.
function phraseComptes(etat, maintenant, attendVide) {
  const comptes = etat.comptes;
  const relancer = compte(comptes, "actions", "a-relancer");
  const tourne = compte(comptes, "actions", "tourne");
  const repos = compte(comptes, "actions", "rien-a-faire");
  let tete = "";
  let date = "";
  if (relancer > 0) {
    tete = `${relancer} ${pluriel(relancer, "projet", "projets")} à relancer`;
    const premier = cartesDe(etat, "a-relancer")[0];
    date = attendVide && premier ? texteDepuis(premier.dernier_tour, maintenant, false) : "";
    if (date) {
      tete += relancer > 1 ? `, le plus ancien ${date}` : `, ${date}`;
    }
  }
  const suite = [];
  if (tourne > 0) {
    suite.push(tourne > 1 ? `${tourne} tournent` : "1 qui tourne");
  }
  if (repos > 0) {
    suite.push(`${repos} au repos`);
  }
  if (!tete && suite.length === 0) {
    return "";
  }
  if (!tete) {
    return `${suite.join(", ")}.`;
  }
  if (suite.length === 0) {
    return `${tete}.`;
  }
  return `${tete}${date ? " ; " : ", "}${suite.join(", ")}.`;
}

// Parties de la phrase-synthèse : `{texte}` ou `{nom}` (nom de projet mis en valeur).
export function partiesSynthese(etat, maintenant) {
  const attentes = cartesDe(etat, "attend-utilisateur");
  const parties = phraseAttente(attentes, maintenant);
  const seconde = phraseComptes(etat, maintenant, attentes.length === 0);
  if (seconde) {
    parties.push({ texte: ` ${seconde}` });
  }
  return parties;
}

function aucunProjet(etat) {
  return !Array.isArray(etat.cartes) || etat.cartes.length === 0;
}

function rendrePhrase(p, etat, maintenant) {
  for (const partie of partiesSynthese(etat, maintenant)) {
    p.append(partie.nom !== undefined ? el("span", "synthese-nom", partie.nom) : el("span", null, partie.texte));
  }
}

// « 4 sur 12 projets stables », puis « 33 % des projets suivis ».
function blocStables(comptes) {
  const suivis = entier(comptes && comptes.suivis);
  const stables = entier(comptes && comptes.stables);
  const bloc = el("div", "bloc-stables");
  const ligne = el("p", "stables-ligne");
  ligne.append(el("span", "stables-chiffre", stables),
    el("span", null, ` sur ${suivis} ${pluriel(suivis, "projet stable", "projets stables")}`));
  const part = suivis > 0 ? Math.round((100 * stables) / suivis) : 0;
  bloc.append(ligne, el("p", "stables-part", `${part} % des projets suivis`));
  return bloc;
}

function iconeGroupe(groupe) {
  const racine = icone(groupe.trace, `icone-groupe groupe-${groupe.cle}`);
  racine.setAttribute("width", "12");
  racine.setAttribute("height", "12");
  return racine;
}

// Barre (segments décoratifs) et légende `ul` lue « Attend Camille : 3 » (`titreAttente`).
function rendreRepartition(conteneur, comptes, libelleAttend) {
  const suivis = entier(comptes && comptes.suivis);
  const barre = el("div", "barre-repartition");
  barre.setAttribute("aria-hidden", "true");
  if (suivis === 0) {
    return; // comptes absents ou incohérents : ni barre ni légende plutôt que des largeurs fausses
  }
  const legende = el("ul", "legende-repartition");
  legende.setAttribute("aria-label",
    suivis > 1 ? `Répartition des ${suivis} projets suivis` : `Répartition de ${suivis} projet suivi`);
  for (const groupe of GROUPES) {
    const n = compte(comptes, groupe.source, groupe.nom);
    if (n === 0) {
      continue;
    }
    // Largeur proportionnelle au compte ; les 4 px entre segments sont pris par flex-shrink, au
    // prorata de chaque largeur, ce qui garde les proportions (appli.css).
    const segment = svg("svg", `segment segment-${groupe.cle}`);
    segment.setAttribute("width", `${Number(((100 * n) / suivis).toFixed(3))}%`);
    segment.setAttribute("aria-hidden", "true");
    segment.setAttribute("focusable", "false");
    barre.append(segment);
    const item = el("li");
    const libelle = groupe.cle === "attend" ? libelleAttend : groupe.libelle;
    item.append(iconeGroupe(groupe), el("span", null, libelle), el("span", "masque", " :"),
      el("span", "legende-compte", ` ${n}`));
    legende.append(item);
  }
  if (barre.childNodes.length > 0) {
    conteneur.append(barre, legende); // aucun groupe non nul (comptes incohérents) : rien
  }
}

function resume(trace, titre) {
  const summary = el("summary", "aide-resume");
  summary.append(icone(trace, "icone-aide"), el("span", "aide-titre", titre),
    icone(TRACE_CHEVRON, "chevron-aide"));
  return summary;
}

function aideTypes() {
  const aide = el("details", "aide aide-types");
  const corps = el("div", "aide-corps");
  corps.append(el("p", null, "Chaque carte Attend porte un type : il dit ce que la session attend de vous."));
  const liste = el("ul", "aide-types-liste");
  for (const type of TYPES) {
    const item = el("li");
    item.append(pastilleType(type.cle), el("span", null, type.sens));
    liste.append(item);
  }
  corps.append(liste);
  aide.append(resume(TRACE_LIVRE, "Les types d'attente, en clair"), corps);
  return aide;
}

function aideStable() {
  const aide = el("details", "aide aide-stable");
  const corps = el("div", "aide-corps");
  const liste = el("ol", "aide-criteres");
  for (const critere of CRITERES) {
    liste.append(el("li", null, critere));
  }
  corps.append(el("p", null, "Un projet est stable quand il remplit les cinq critères :"), liste,
    el("p", null, "Stable, il va dans Rien à faire. Inactif sans être stable, il passe dans "
      + "À relancer avec la raison « à stabiliser », suivie du premier critère qui manque."));
  aide.append(resume(TRACE_INFO, "Quand un projet est-il stable ?"), corps);
  return aide;
}

// Tête posée une fois : `maj(etat, maintenant)` réécrit la synthèse, le bloc et la barre, et ne
// touche jamais aux aides (créées fermées, leur état ouvert reste celui choisi par l'utilisateur).
export function creerTete() {
  const element = el("div", "tete");
  const haut = el("div", "tete-haut");
  const repartition = el("div", "repartition");
  const aides = el("div", "aides");
  aides.append(aideTypes(), aideStable());
  element.append(haut, repartition, aides);

  function maj(etat, maintenant = new Date()) {
    vider(haut);
    vider(repartition);
    if (etat === null || etat === undefined) {
      // Chargement lent : espaces réservés de hauteur fixe, sans animation.
      const reserveSynthese = el("div", "reserve reserve-synthese");
      const reserveBarre = el("div", "reserve reserve-barre");
      reserveSynthese.setAttribute("aria-hidden", "true");
      reserveBarre.setAttribute("aria-hidden", "true");
      haut.append(reserveSynthese);
      repartition.append(reserveBarre);
      return;
    }
    if (aucunProjet(etat)) {
      haut.append(el("p", "synthese aucun-projet", AUCUN_PROJET));
      return;
    }
    const phrase = el("p", "synthese");
    rendrePhrase(phrase, etat, maintenant);
    haut.append(phrase, blocStables(etat.comptes));
    rendreRepartition(repartition, etat.comptes, titreAttente(etat));
  }

  return { element, maj };
}

// aria-busy de `main` pendant un chargement lent (State Patterns) ; retiré à l'arrivée des données.
export function marquerOccupe(main, occupe) {
  if (occupe) {
    main.setAttribute("aria-busy", "true");
  } else {
    main.removeAttribute("aria-busy");
  }
}

// Chargement initial (State Patterns) : sans réponse après 300 ms, `main` prend aria-busy et
// `rendre()` pose les espaces réservés ; `finir()`, appelé à toute réponse (données ou erreur),
// annule le délai et retire aria-busy. `lent()` : espaces réservés à afficher.
export function suivreChargement(main, rendre, minuteur = globalThis) {
  let phase = "attente";
  let id = null;
  return {
    demarrer() {
      id = minuteur.setTimeout(() => {
        id = null;
        if (phase === "attente") {
          phase = "lent";
          marquerOccupe(main, true);
          rendre();
        }
      }, DELAI_CHARGEMENT_MS);
    },
    finir() {
      if (id !== null) {
        minuteur.clearTimeout(id);
        id = null;
      }
      phase = "fini";
      marquerOccupe(main, false);
    },
    lent() {
      return phase === "lent";
    },
  };
}
