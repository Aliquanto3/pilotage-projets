// Barre du haut (UX-DR4, UX-DR5) : pictogramme, h1, onglets, ligne d'état, ligne de fraîcheur,
// boutons secondaires Actualiser, Scan, Sync et Rapport de la semaine (story 9.4).

import { TEXTE_INJOIGNABLE, el, svg, vider } from "./dom.js";
import { etiquetteFraicheur } from "./temps.js";

export const ONGLETS = [
  { nom: "projets", libelle: "Projets" },
  { nom: "chantiers", libelle: "Chantiers" },
];

const MOTIF_SEMAINE = /^\d{4}-W\d{2}$/;

// Texte de la réponse de `POST /api/rapport` : `{annonce}` (zone `#annonce`) ou `{erreur}` (zone
// d'alerte). 401 et 403 sont traités par l'appelant avant. La semaine n'est reprise que si elle a
// la forme `AAAA-Www` : aucune autre donnée de la réponse n'entre dans le texte, sauf l'erreur.
export function texteRapport(statut, corps) {
  if (statut === 200) {
    const donnees = corps && typeof corps === "object" ? corps.donnees : null;
    const semaine = donnees && typeof donnees === "object" ? donnees.semaine : null;
    if (typeof semaine === "string" && MOTIF_SEMAINE.test(semaine)) {
      return { annonce: `Rapport de la semaine ${semaine} ouvert dans le navigateur.` };
    }
    return { annonce: "Rapport de la semaine ouvert dans le navigateur." };
  }
  if (statut === 409) {
    return { annonce: "Un rapport est déjà en cours." };
  }
  if (statut === 0) {
    return { erreur: TEXTE_INJOIGNABLE };
  }
  const erreur = corps && typeof corps.erreur === "string" && corps.erreur ? corps.erreur : null;
  return { erreur: erreur || "Erreur du serveur local." };
}

function pictogramme() {
  const dessin = svg("svg", "picto");
  dessin.setAttribute("viewBox", "0 0 32 32");
  dessin.setAttribute("width", "28");
  dessin.setAttribute("height", "28");
  dessin.setAttribute("aria-hidden", "true");
  dessin.setAttribute("focusable", "false");
  const fond = svg("rect", "picto-fond");
  fond.setAttribute("width", "32");
  fond.setAttribute("height", "32");
  fond.setAttribute("rx", "8");
  const traits = svg("path", "picto-traits");
  traits.setAttribute("d", "M9 10h14M9 16h9M9 22h14");
  const point = svg("circle", "picto-point");
  point.setAttribute("cx", "23");
  point.setAttribute("cy", "16");
  point.setAttribute("r", "2.5");
  dessin.append(fond, traits, point);
  return dessin;
}

function boutonSecondaire(libelle, rappel) {
  const bouton = el("button", "btn2", libelle);
  bouton.type = "button";
  bouton.addEventListener("click", () => {
    if (bouton.getAttribute("aria-disabled") === "true") {
      return;
    }
    rappel();
  });
  return bouton;
}

// rappels : {onglet(nom), actualiser(), scan(), sync(), rapport()}.
export function construireBarre(rappels) {
  const entete = el("header", "barre");
  const logo = el("div", "logo");
  logo.append(pictogramme(), el("h1", "titre", "Pilotage"));

  const nav = el("nav", "onglets");
  nav.setAttribute("aria-label", "Vues");
  const boutonsOnglets = new Map();
  for (const onglet of ONGLETS) {
    const bouton = el("button", "onglet", onglet.libelle);
    bouton.type = "button";
    bouton.addEventListener("click", () => rappels.onglet(onglet.nom));
    boutonsOnglets.set(onglet.nom, bouton);
    nav.append(bouton);
  }

  const droite = el("div", "droite");
  const etat = el("p", "etat");
  etat.id = "ligne-etat";
  etat.tabIndex = -1;
  const fraicheur = el("ul", "fraicheur");
  fraicheur.setAttribute("aria-label", "Fraîcheur des données");
  const actualiser = boutonSecondaire("Actualiser", rappels.actualiser);
  const scan = boutonSecondaire("Scan", rappels.scan);
  const sync = boutonSecondaire("Sync", rappels.sync);
  const rapport = boutonSecondaire("Rapport de la semaine", rappels.rapport);
  droite.append(etat, fraicheur, actualiser, scan, sync, rapport);
  entete.append(logo, nav, droite);

  return {
    element: entete,
    majEtat(texte) {
      etat.textContent = texte || "";
    },
    majFraicheur(lignes, maintenant) {
      vider(fraicheur);
      for (const ligne of Array.isArray(lignes) ? lignes : []) {
        const { texte, vieux } = etiquetteFraicheur(ligne, maintenant);
        const item = el("li", vieux ? "pc vieux" : "pc");
        if (vieux) {
          item.append(el("span", "masque", "Alerte : "));
        }
        item.append(el("span", null, texte));
        fraicheur.append(item);
      }
    },
    // Scan ou Sync en cours : les deux boutons restent focalisables mais inactifs.
    majOccupe(occupe) {
      for (const bouton of [scan, sync]) {
        if (occupe) {
          bouton.setAttribute("aria-disabled", "true");
        } else {
          bouton.removeAttribute("aria-disabled");
        }
      }
    },
    // Rapport en cours : ce seul bouton, indépendant de `majOccupe` (un scan n'empêche pas
    // d'ouvrir le rapport).
    majRapport(occupe) {
      if (occupe) {
        rapport.setAttribute("aria-disabled", "true");
      } else {
        rapport.removeAttribute("aria-disabled");
      }
    },
    majOnglet(nom) {
      for (const [cle, bouton] of boutonsOnglets) {
        if (cle === nom) {
          bouton.setAttribute("aria-current", "page");
        } else {
          bouton.removeAttribute("aria-current");
        }
      }
    },
  };
}
