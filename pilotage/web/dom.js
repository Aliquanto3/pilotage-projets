// Aides DOM sûres (AD-15) : le DOM n'est écrit que par createElement, createElementNS (espace
// SVG seulement) et textContent. Aucun attribut n'est tiré des données.

export const SVG = "http://www.w3.org/2000/svg";

// Élément `balise`, avec sa classe et son texte (posé par textContent) s'ils sont donnés.
export function el(balise, classe, texte) {
  const noeud = document.createElement(balise);
  if (classe) {
    noeud.className = classe;
  }
  if (texte !== undefined && texte !== null) {
    noeud.textContent = String(texte);
  }
  return noeud;
}

// Élément SVG, classe CSS seulement (les couleurs viennent de appli.css).
export function svg(balise, classe) {
  const noeud = document.createElementNS(SVG, balise);
  if (classe) {
    noeud.setAttribute("class", classe);
  }
  return noeud;
}

export function vider(noeud) {
  while (noeud.firstChild) {
    noeud.removeChild(noeud.firstChild);
  }
}

// Régions d'annonce posées par index.html dès le chargement (UX-DR19). Le texte est vidé puis
// réécrit au tour suivant pour qu'une annonce identique soit relue.
function ecrireRegion(id, texte) {
  const region = document.getElementById(id);
  if (!region) {
    return;
  }
  region.textContent = "";
  window.setTimeout(() => {
    region.textContent = String(texte);
  }, 50);
}

export function annoncer(texte) {
  ecrireRegion("annonce", texte);
}

export function alerter(texte) {
  ecrireRegion("alerte", texte);
}
