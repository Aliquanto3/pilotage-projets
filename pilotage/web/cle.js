// Écrans sans données (UX-DR17, UX-DR15) et bloc de commande partagé (`blocCommande`).

import { annoncer, el } from "./dom.js";

export const COMMANDE_APPLI = "uv run lancer.py appli";
export const DUREE_COPIE_MS = 2000;

let compteur = 0;

// Commande sur encre-pleine, bouton principal « Copier la commande » → « Copié » pendant 2 s ;
// sans presse-papiers, la commande est sélectionnée et la consigne « Ctrl+C pour copier »
// s'affiche, reliée au bloc par aria-describedby.
export function blocCommande(commande) {
  compteur += 1;
  const idConsigne = `consigne-copie-${compteur}`;
  const bloc = el("div", "bloc-commande");
  const code = el("code", "commande", commande);
  code.tabIndex = 0;
  const consigne = el("p", "consigne", "Ctrl+C pour copier");
  consigne.id = idConsigne;
  consigne.hidden = true;
  const bouton = el("button", "btn1", "Copier la commande");
  bouton.type = "button";
  let minuteur = null;

  function repli() {
    const selection = window.getSelection();
    if (selection) {
      selection.selectAllChildren(code);
    }
    consigne.hidden = false;
    code.setAttribute("aria-describedby", idConsigne);
    code.focus();
    annoncer("Ctrl+C pour copier");
  }

  bouton.addEventListener("click", () => {
    const presse = navigator.clipboard;
    if (!presse || typeof presse.writeText !== "function") {
      repli();
      return;
    }
    presse.writeText(commande).then(() => {
      bouton.textContent = "Copié";
      annoncer("Copié");
      if (minuteur !== null) {
        window.clearTimeout(minuteur);
      }
      minuteur = window.setTimeout(() => {
        bouton.textContent = "Copier la commande";
        minuteur = null;
      }, DUREE_COPIE_MS);
    }, repli);
  });

  bloc.append(code, bouton, consigne);
  return bloc;
}

export function ecranClePerdue() {
  const ecran = el("main", "ecran-seul");
  const titre = el("h2", "ecran-titre", "Clé d'accès perdue");
  titre.tabIndex = -1;
  ecran.append(
    titre,
    el("p", null, "Cette page n'a plus de clé valable. Relancez l'appli depuis un terminal."),
    blocCommande(COMMANDE_APPLI),
  );
  return ecran;
}

export function ecranSessionRemplacee() {
  const ecran = el("main", "ecran-seul");
  const titre = el("h2", "ecran-titre", "Une autre fenêtre de l'appli a été ouverte. Fermez cet onglet.");
  titre.tabIndex = -1;
  ecran.append(titre);
  return ecran;
}
