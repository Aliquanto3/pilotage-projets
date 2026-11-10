// Vue Chantiers : état neutre posé par la story 4.4, remplacé par la story 4.7.

import { el, vider } from "./dom.js";

export function rendreChantiers(conteneur, etat) {
  vider(conteneur);
  conteneur.append(el("h2", "masque", "Chantiers"));
  if (etat === null) {
    conteneur.append(el("p", "neutre", "Chargement…"));
  }
}
