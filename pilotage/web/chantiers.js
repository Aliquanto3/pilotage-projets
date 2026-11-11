// Vue Chantiers (story 4.7, EXPERIENCE § Component Patterns, DESIGN `bloc-chantier`) : un bloc par
// chantier dans l'ordre du noyau (action puis nom, AD-11), puis « Découverts, à classer », puis
// « Hors chantier » ; un bloc vide n'est pas affiché. Le nom d'un dépôt ouvre son tiroir.
//
// Relecture des 30 s : la vue n'est reconstruite que si l'empreinte des données lues change, et le
// focus est rendu au bouton du même projet. Texte non fiable posé par textContent (AD-15) ; aucun
// attribut n'est tiré des données.

import { el, vider } from "./dom.js";
import { AUCUN_PROJET, titreAttente } from "./synthese.js";
import { ouvrirTiroir } from "./tiroir.js";
import { libelleAction, pastilleAction } from "./types.js";

export const TITRE_DECOUVERTS = "Découverts, à classer";
export const TITRE_HORS_CHANTIER = "Hors chantier";
const A_CLASSER = "découvert, à classer";

// Par conteneur : { racine, empreinte, boutons: Map(nom -> bouton) }.
const VUES = new WeakMap();

function texteDe(valeur) {
  return typeof valeur === "string" && valeur !== "" ? valeur : null;
}

function objets(valeur) {
  return Array.isArray(valeur) ? valeur.filter((x) => x && typeof x === "object") : [];
}

function dependancesDe(etat) {
  return Array.isArray(etat.dependances) ? etat.dependances.filter((d) => typeof d === "string") : [];
}

// Blocs à afficher : { titre, action | null, depots: [{nom, action}] }, dans l'ordre de la vue.
function blocs(etat) {
  const resultat = objets(etat.chantiers).map((chantier) => ({
    titre: texteDe(chantier.nom) || "", action: chantier.action, depots: objets(chantier.projets),
  }));
  const cartes = objets(etat.cartes).filter((c) => c.genre === "projet");
  resultat.push({ titre: TITRE_DECOUVERTS, action: null,
    depots: cartes.filter((c) => c.categorie === A_CLASSER) });
  resultat.push({ titre: TITRE_HORS_CHANTIER, action: null,
    depots: cartes.filter((c) => c.categorie !== A_CLASSER && texteDe(c.chantier) === null) });
  return resultat
    .map((b) => ({ ...b, depots: b.depots.map((d) => ({ nom: texteDe(d.nom) || "", action: d.action })) }))
    .filter((b) => b.depots.length > 0);
}

function construireBloc(bloc, dependances, attend, boutons) {
  const section = el("section", "bloc-chantier");
  const tete = el("div", "bloc-chantier-tete");
  tete.append(el("h3", "bloc-chantier-titre", bloc.titre));
  if (bloc.action) {
    tete.append(pastilleAction(bloc.action, libelleAction(bloc.action, attend)));
  }
  section.append(tete);
  const lignes = el("ul", "depots");
  const noms = new Set();
  for (const depot of bloc.depots) {
    const item = el("li", "ligne-depot");
    const bouton = el("button", "btn-lien nom-projet", depot.nom);
    bouton.setAttribute("type", "button");
    bouton.addEventListener("click", () => ouvrirTiroir(depot.nom, bouton));
    item.append(bouton, pastilleAction(depot.action, libelleAction(depot.action, attend)));
    lignes.append(item);
    noms.add(depot.nom);
    if (!boutons.has(depot.nom)) {
      boutons.set(depot.nom, bouton);
    }
  }
  section.append(lignes);
  // Dépendances « A ← B » (forme validée par le schéma) dont A est un dépôt du bloc.
  for (const ligne of dependances) {
    if (noms.has(ligne.split(" ← ")[0])) {
      section.append(el("p", "dependance", ligne));
    }
  }
  return section;
}

// Bouton du nom d'un projet dans la vue Chantiers de `conteneur`, ou null.
export function boutonNom(conteneur, nom) {
  const vue = VUES.get(conteneur);
  return vue !== undefined ? vue.boutons.get(nom) || null : null;
}

// etat : données de /api/etat, ou null tant qu'elles ne sont pas arrivées.
export function rendreChantiers(conteneur, etat) {
  if (etat === null || typeof etat !== "object") {
    VUES.delete(conteneur);
    vider(conteneur);
    conteneur.append(el("h2", "masque", "Chantiers"), el("p", "neutre", "Chargement…"));
    return;
  }
  const lesBlocs = blocs(etat);
  const dependances = dependancesDe(etat);
  const attend = titreAttente(etat);
  // Seules les données lues par la vue entrent dans l'empreinte (ni `depot_de`, ni les heures).
  const empreinte = JSON.stringify([lesBlocs, dependances, attend]);
  const ancienne = VUES.get(conteneur);
  const enPlace = ancienne !== undefined && Array.from(conteneur.childNodes).includes(ancienne.racine);
  if (enPlace && ancienne.empreinte === empreinte) {
    return;
  }
  // Projet dont le bouton porte le focus : il le retrouve après la reconstruction.
  const actif = typeof document !== "undefined" ? document.activeElement : null;
  let focalise = null;
  if (enPlace && actif) {
    for (const [nom, bouton] of ancienne.boutons) {
      if (bouton === actif) {
        focalise = nom;
      }
    }
  }
  const dansLaVue = enPlace && Boolean(actif) && conteneur.contains(actif);
  vider(conteneur);
  const titre = el("h2", "masque", "Chantiers");
  titre.setAttribute("tabindex", "-1"); // reprend le focus si le projet focalisé disparaît
  const racine = el("div", "chantiers");
  const boutons = new Map();
  for (const bloc of lesBlocs) {
    racine.append(construireBloc(bloc, dependances, attend, boutons));
  }
  if (lesBlocs.length === 0) {
    racine.append(el("p", "neutre", AUCUN_PROJET));
  }
  conteneur.append(titre, racine);
  VUES.set(conteneur, { racine, empreinte, boutons });
  if (focalise !== null) {
    (boutons.get(focalise) || titre).focus();
  } else if (dansLaVue) {
    titre.focus();
  }
}
