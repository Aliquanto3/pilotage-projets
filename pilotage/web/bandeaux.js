// Bandeaux sous la barre du haut (UX-DR16) : un par alerte, affiché tant qu'elle existe,
// repliable mais jamais supprimable par l'utilisateur.

import { alerter, el } from "./dom.js";

const CODES_ERREUR = new Set(["depot-public", "depot-non-configure"]);

// "erreur" ou "alerte" (DESIGN.md § Colors).
export function typeBandeau(code) {
  return CODES_ERREUR.has(code) ? "erreur" : "alerte";
}

// Type d'un bandeau, toujours tiré de la table fermée : la classe CSS ne reprend jamais une
// valeur reçue de l'API. Seules les alertes locales (403) portent `type: "erreur"`.
function typeDe(alerte) {
  return alerte.source === "page" && alerte.type === "erreur" ? "erreur" : typeBandeau(alerte.code);
}

function cleAlerte(alerte) {
  return `${alerte.source || ""}|${alerte.code || ""}|${alerte.texte || ""}`;
}

export function construireBandeaux() {
  const zone = el("div", "bandeaux");
  const replies = new Set();
  const elements = new Map();
  let connues = new Set();

  function bandeau(alerte, cle) {
    const type = typeDe(alerte);
    const boite = el("div", `bandeau bandeau-${type}`);
    const tete = el("div", "bandeau-tete");
    tete.append(el("span", "bandeau-type", type === "erreur" ? "Erreur" : "Alerte"));
    const texte = el("p", "bandeau-texte", alerte.texte || alerte.code || "");
    const replier = el("button", "btn-lien");
    replier.type = "button";
    function appliquer() {
      const replie = replies.has(cle);
      texte.hidden = replie;
      replier.textContent = replie ? "Déplier" : "Replier";
      replier.setAttribute("aria-expanded", replie ? "false" : "true");
    }
    replier.addEventListener("click", () => {
      if (replies.has(cle)) {
        replies.delete(cle);
      } else {
        replies.add(cle);
      }
      appliquer();
    });
    appliquer();
    tete.append(replier);
    boite.append(tete, texte);
    return boite;
  }

  return {
    element: zone,
    // alertes : liste `{source, code, texte}` de /api/etat ; locales : `{code, texte, type}`
    // produites par la page (403). Une erreur nouvelle est annoncée par la région role=alert.
    maj(alertes, locales) {
      const toutes = [...(Array.isArray(alertes) ? alertes : []), ...(locales || [])];
      const presentes = new Set();
      for (const alerte of toutes) {
        const cle = cleAlerte(alerte);
        if (presentes.has(cle)) {
          continue;
        }
        presentes.add(cle);
        if (!elements.has(cle)) {
          // Bandeau nouveau seulement : un bandeau déjà affiché n'est pas reconstruit, le focus
          // posé sur son bouton survit au rafraîchissement.
          const noeud = bandeau(alerte, cle);
          elements.set(cle, noeud);
          zone.append(noeud);
        }
        const type = typeDe(alerte);
        if (type === "erreur" && !connues.has(cle)) {
          alerter(alerte.texte || "");
        }
      }
      for (const [cle, noeud] of [...elements]) {
        if (!presentes.has(cle)) {
          noeud.remove();
          elements.delete(cle);
          replies.delete(cle);
        }
      }
      connues = presentes;
      zone.hidden = presentes.size === 0;
    },
  };
}
