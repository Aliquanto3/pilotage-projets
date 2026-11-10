"""Texte libre : filtre de secrets, troncature, normalisation de chemins, bornes (AD-10).

`nettoyer` porte toute la séquence d'écriture : normalisation de la racine GitHub, filtre de
secrets, troncature à la borne en points de code Unicode, second filtre. Un texte suspect est
supprimé entièrement (rendu `""`), jamais masqué. Les validateurs de borne ne tronquent pas :
la troncature n'existe qu'à l'écriture, via `nettoyer`.
"""

import html
import re
import unicodedata

BORNE_QUOI = 200  # points de code
BORNE_NOTE = 300  # points de code
BORNE_MESSAGE_OCTETS = 2048  # octets UTF-8

RACINE_GITHUB = "{{RACINE_GITHUB}}"

# Recherche insensible à la casse (choix le plus sûr : `Bearer`, `bearer`, `BEARER`).
MOTIFS_SECRETS = (
    "sk-", "ghp_", "gho_", "ghu_", "ghs_", "github_pat_", "AKIA", "-----BEGIN", "Bearer", "KEY=",
    "sk_live_", "sk_test_", "xoxb-", "xoxp-", "glpat-", "hf_", "TOKEN=", "SECRET=", "PASSWORD=",
)
_SECRETS = re.compile("|".join(re.escape(m) for m in MOTIFS_SECRETS), re.IGNORECASE)


class ErreurTexte(ValueError):
    """Texte hors borne ou de type invalide."""


_RETIRES = frozenset({"Cf", "Mn", "Me"})  # format, combinants, sélecteurs de variante
_ECHAPPEMENT_MD = re.compile(r"\\([!-/:-@\[-`{-~])")  # `\_`, `\-` : rendus sans `\` par GitHub
_BLANCS_EGAL = re.compile(r"\s*=\s*")


def _forme_de_recherche(texte: str) -> str:
    """Forme comparée aux motifs, pour la détection seule (le texte gardé n'est pas modifié).

    Entités HTML décodées (deux fois : `&amp;#115;`), échappements Markdown retirés, NFKD
    (pleine chasse, ligatures), puis retrait des caractères de format (Cf), combinants (Mn, Me),
    tirets Unicode (Pd) ramenés à `-`, connecteurs (Pc) à `_`, blancs autour de `=` retirés.
    Ainsi `s` + U+200B + `k-`, `sk` + U+0301 + `-`, `sk‐`, `&#115;k-` ou `ghp\\_` sont vus.
    """
    forme = html.unescape(html.unescape(texte))
    forme = _ECHAPPEMENT_MD.sub(r"\1", unicodedata.normalize("NFKD", forme))
    sortie = []
    for c in forme:
        categorie = unicodedata.category(c)
        if categorie in _RETIRES:
            continue
        sortie.append("-" if categorie == "Pd" else "_" if categorie == "Pc" else c)
    return _BLANCS_EGAL.sub("=", "".join(sortie))


def est_suspect(texte: str) -> bool:
    """Vrai si le texte contient un motif de secret (casse ignorée, NFKC, sans Cf)."""
    return (
        _SECRETS.search(texte) is not None
        or _SECRETS.search(_forme_de_recherche(texte)) is not None
    )


BORNE_NOM_AFFICHE = 64  # points de code, après NFC
_PONCTUATION_NOM = frozenset(" -'.’")
_MARQUES_NOM = frozenset({"Mn", "Mc"})  # combinants restés après NFC (écritures indiennes…)


def nom_affiche(valeur: object) -> str:
    """Nom affiché de la personne (`config.json`, clé `utilisateur`), sinon `""`.

    Règle unique des trois surfaces (web, `TABLEAU.md`, préambule injecté dans Claude) : forme
    NFC (un nom saisi décomposé, NFD, est recomposé), blancs des bords retirés, espaces internes
    resserrés ; lettres, chiffres, marques combinantes, espace et `-'.’` seulement (ni balisage
    Markdown ou HTML, ni contrôle, ni saut de ligne) ; 64 points de code au plus ; aucun motif
    de secret. Tout autre nom vaut `""` (formulation neutre), jamais une version retouchée.
    """
    if not isinstance(valeur, str):
        return ""
    nom = unicodedata.normalize("NFC", valeur).strip()
    if not all(
        c.isalnum() or c in _PONCTUATION_NOM or unicodedata.category(c) in _MARQUES_NOM
        for c in nom
    ):
        return ""
    nom = " ".join(nom.split())  # seul blanc restant : l'espace
    if not nom or len(nom) > BORNE_NOM_AFFICHE or est_suspect(nom):
        return ""
    return nom


def normaliser_racine(texte: str, racine_github: str) -> str:
    """Remplace la racine GitHub (absolue, `\\` ou `/`, casse indifférente) par `{{RACINE_GITHUB}}`.

    La racine est passée en paramètre (le noyau ne lit pas `chemins`). La casse est ignorée
    (lettre de lecteur comprise : Windows). Les séparateurs de la suite du chemin sont conservés.
    """
    segments = [s for s in re.split(r"[\\/]+", racine_github) if s]
    if not segments:
        raise ErreurTexte("racine GitHub vide")
    corps = r"[\\/]+".join(re.escape(s) for s in segments)
    debut = r"[\\/]+" if racine_github.startswith(("/", "\\")) else ""
    motif = re.compile(rf"(?<![\w/\\.-]){debut}{corps}(?![\w-]|\.\w)", re.IGNORECASE)
    return motif.sub(lambda _: RACINE_GITHUB, texte)


def nettoyer(texte: str, borne: int, racine_github: str | None = None) -> str:
    """Séquence d'écriture : racine, filtre, troncature à `borne` points de code, filtre.

    Rend `""` si le texte (avant ou après troncature) contient un motif de secret.
    Sans `racine_github`, aucun chemin n'est normalisé : l'appelant d'écriture doit la passer.
    """
    if not isinstance(texte, str):
        raise ErreurTexte(f"une chaîne est attendue, pas {type(texte).__name__}")
    if isinstance(borne, bool) or not isinstance(borne, int) or borne < 0:
        raise ErreurTexte(f"borne invalide : {borne!r}")
    if racine_github:
        texte = normaliser_racine(texte, racine_github)
    if est_suspect(texte):
        return ""
    texte = texte[:borne]
    return "" if est_suspect(texte) else texte


def _sans_substitut_isole(texte: object, nom: str) -> str:
    if not isinstance(texte, str):
        raise ErreurTexte(f"{nom} : une chaîne est attendue, pas {type(texte).__name__}")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in texte):
        raise ErreurTexte(f"{nom} : substitut UTF-16 isolé (pas de l'UTF-8 valide)")
    return texte


def _valider_points_de_code(texte: object, borne: int, nom: str) -> str:
    texte = _sans_substitut_isole(texte, nom)
    if len(texte) > borne:
        raise ErreurTexte(f"{nom} : {len(texte)} points de code, {borne} au plus")
    return texte


def valider_quoi(texte: object) -> str:
    """Un *quoi* : 200 points de code au plus. Ne filtre pas les secrets (rôle de `nettoyer`)."""
    return _valider_points_de_code(texte, BORNE_QUOI, "quoi")


def valider_note(texte: object) -> str:
    """Une note : 300 points de code au plus. Ne filtre pas les secrets (rôle de `nettoyer`)."""
    return _valider_points_de_code(texte, BORNE_NOTE, "note")


def valider_message(texte: object) -> str:
    """Un message : 2048 octets UTF-8 au plus. Ne filtre pas les secrets (rôle de `nettoyer`)."""
    texte = _sans_substitut_isole(texte, "message")
    taille = len(texte.encode("utf-8"))
    if taille > BORNE_MESSAGE_OCTETS:
        raise ErreurTexte(f"message : {taille} octets, {BORNE_MESSAGE_OCTETS} au plus")
    return texte
