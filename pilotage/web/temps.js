// Logique pure de la ligne de fraîcheur et des heures (UX-DR5, UX-DR20) : aucun DOM, testée par
// tests/test_web_temps.py sous node. Heures locales du navigateur.

// Seuil de la règle « sans nouvelles » du noyau (noyau.assemblage.FRAICHEUR_MAX).
export const SEUIL_SANS_NOUVELLES_MIN = 45;

const MINUTE = 60 * 1000;

function deuxChiffres(n) {
  return String(n).padStart(2, "0");
}

function memeJour(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

// Date d'un horodatage ISO ; null s'il est absent ou illisible.
export function lireInstant(valeur) {
  if (typeof valeur !== "string" || valeur === "") {
    return null;
  }
  const instant = new Date(valeur);
  return Number.isNaN(instant.getTime()) ? null : instant;
}

// `HH:MM` aujourd'hui, `hier HH:MM` la veille, sinon `JJ/MM` (UX-DR20).
export function heureCourte(instant, maintenant) {
  const hm = `${deuxChiffres(instant.getHours())}:${deuxChiffres(instant.getMinutes())}`;
  if (memeJour(instant, maintenant)) {
    return hm;
  }
  const veille = new Date(maintenant.getTime());
  veille.setDate(veille.getDate() - 1);
  if (memeJour(instant, veille)) {
    return `hier ${hm}`;
  }
  return `${deuxChiffres(instant.getDate())}/${deuxChiffres(instant.getMonth() + 1)}`;
}

// Étiquette d'une ligne `{pc, genere_a}` de `fraicheur` : `{texte, vieux}`.
export function etiquetteFraicheur(ligne, maintenant) {
  const pc = String(ligne && ligne.pc ? ligne.pc : "");
  const instant = lireInstant(ligne ? ligne.genere_a : null);
  if (instant === null) {
    return { texte: `${pc} · aucun instantané`, vieux: true };
  }
  const minutes = Math.max(0, Math.floor((maintenant.getTime() - instant.getTime()) / MINUTE));
  const ecart = maintenant.getTime() - instant.getTime();
  if (ecart > SEUIL_SANS_NOUVELLES_MIN * MINUTE) {
    return { texte: `${pc} · sans nouvelles depuis ${heureCourte(instant, maintenant)}`, vieux: true };
  }
  if (minutes < 1) {
    return { texte: `${pc} · à l'instant`, vieux: false };
  }
  return { texte: `${pc} · il y a ${minutes} min`, vieux: false };
}

const HEURE = 60 * MINUTE;
// Seuil de l'attente vieillissante (noyau.etat.SEUIL_VIEILLISSANTE) et fin de la forme en heures.
export const SEUIL_VIEILLISSANTE_H = 8;
const FIN_FORME_HEURES_H = 24;

// « depuis HH:MM », « depuis hier HH:MM », puis « depuis le JJ/MM » (EXPERIENCE § Voice and Tone).
export function depuisCourt(instant, maintenant) {
  const court = heureCourte(instant, maintenant);
  return /^\d{2}\/\d{2}$/.test(court) ? `depuis le ${court}` : `depuis ${court}`;
}

// Ligne méta d'une attente vieillissante : « depuis plus de N h » de 8 à 24 h (N arrondi à
// l'heure inférieure), la règle des heures au-delà ; PC sans nouvelles : l'heure de début seule.
export function depuisVieillissante(instant, maintenant, sansNouvelles) {
  const heures = (maintenant.getTime() - instant.getTime()) / HEURE;
  if (!sansNouvelles && heures >= SEUIL_VIEILLISSANTE_H && heures <= FIN_FORME_HEURES_H) {
    return `depuis plus de ${Math.floor(heures)} h`;
  }
  return depuisCourt(instant, maintenant);
}
