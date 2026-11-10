"""Patch ciblé du texte de `projets.yaml` (story 5.1, M7) : jamais de `yaml.dump`.

Chaque modification remplace, insère ou retire le texte d'une ligne ou d'un bloc, situé par les
marques de `yaml.compose` (SafeLoader) : commentaires, ordre et autres lignes sont conservés. Une
forme non prise en charge lève `PatchImpossible` ; l'appelant revalide le texte obtenu.

Champs d'un projet : `chantier` (nom du chantier dont la liste `projets` le contient, ou None),
`exclu` (présent dans `exclus`), `pause` (date `revue` de `pauses.<projet>`, ou None).
"""

import re
from datetime import date

import yaml

CHAMPS = ("chantier", "exclu", "pause")
DEFAUT = {"chantier": None, "exclu": False, "pause": None}  # projet absent de projets.yaml
_TIRET = re.compile(r"[ \t]*-[ \t]+")
_BLANC = re.compile(r"[ \t]*")
_FIN = re.compile(r"[ \t]*(#.*)?\r?")
_APRES_CLE = re.compile(r"[ \t]*:[ \t]*(#.*)?\r?")
_NUL = "tag:yaml.org,2002:null"


class PatchImpossible(Exception):
    """Le texte n'a pas une forme que le patch ciblé sait modifier sans risque."""


def valeurs(config: dict, projet: str) -> dict:
    """Valeurs courantes des champs de `projet` dans un `projets.yaml` validé."""
    chantier = None
    for nom, contenu in (config.get("chantiers") or {}).items():
        if projet in ((contenu or {}).get("projets") or []):
            chantier = nom
    pause = (config.get("pauses") or {}).get(projet)
    revue = None
    if pause is not None:
        revue = pause["revue"]
        revue = revue.isoformat() if isinstance(revue, date) else str(revue)
    return {
        "chantier": chantier,
        "exclu": projet in (config.get("exclus") or []),
        "pause": revue,
    }


def projection(config: dict) -> dict:
    """Vue comparable d'un `projets.yaml` validé : tout ce qu'un patch peut toucher ou non."""
    projets: set[str] = set(config.get("exclus") or []) | set(config.get("pauses") or {})
    for contenu in (config.get("chantiers") or {}).values():
        projets |= set((contenu or {}).get("projets") or [])
    return {
        "chantiers": sorted(config.get("chantiers") or {}),
        "dependances": list(config.get("dependances") or []),
        "projets": {
            p: v for p in sorted(projets) if (v := valeurs(config, p)) != DEFAUT
        },
    }


def _nl(texte: str) -> str:
    return "\r\n" if "\r\n" in texte else "\n"


def _debut_ligne(texte: str, i: int) -> int:
    return texte.rfind("\n", 0, i) + 1


def _fin_ligne(texte: str, i: int) -> int:
    """Indice qui suit le saut de ligne de la ligne de `i` (ou la fin du texte)."""
    j = texte.find("\n", i)
    return len(texte) if j < 0 else j + 1


def _rendu(nom: str) -> str:
    """Scalaire YAML qui se relit en `nom` (identifiant AD-9 : jamais d'apostrophe)."""
    try:
        if yaml.safe_load(nom) == nom:
            return nom
    except yaml.YAMLError:
        pass
    return f"'{nom}'"


def _racine(texte: str) -> yaml.MappingNode:
    try:
        noeud = yaml.compose(texte, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        raise PatchImpossible("YAML invalide") from None
    if not isinstance(noeud, yaml.MappingNode) or noeud.flow_style:
        raise PatchImpossible("racine : objet en bloc attendu")
    return noeud


def _paire(mapping: yaml.MappingNode, cle: str):
    for k, v in mapping.value:
        if isinstance(k, yaml.ScalarNode) and k.value == cle:
            return k, v
    return None


def _est_vide(noeud) -> bool:
    return isinstance(noeud, yaml.ScalarNode) and noeud.tag == _NUL


def _seul_sur_sa_ligne(texte: str, noeud, motif: re.Pattern) -> None:
    debut = _debut_ligne(texte, noeud.start_mark.index)
    if not motif.fullmatch(texte[debut:noeud.start_mark.index]):
        raise PatchImpossible("élément qui ne commence pas sa ligne")


def _fin_de_ligne_libre(texte: str, i: int) -> None:
    fin = texte.find("\n", i)
    reste = texte[i:] if fin < 0 else texte[i:fin]
    if not _FIN.fullmatch(reste):
        raise PatchImpossible("ligne qui porte autre chose après l'élément")


def _derniere_fin(cle, valeur) -> int:
    """Indice de fin du dernier caractère d'une entrée `cle: valeur` en bloc."""
    if isinstance(valeur, yaml.ScalarNode):
        if valeur.start_mark.index == valeur.end_mark.index:  # valeur vide
            return cle.end_mark.index
        if valeur.start_mark.line != valeur.end_mark.line:
            raise PatchImpossible("scalaire sur plusieurs lignes")
        return valeur.end_mark.index
    if valeur.flow_style or not valeur.value:
        if valeur.start_mark.line != valeur.end_mark.line:
            raise PatchImpossible("collection en flux sur plusieurs lignes")
        return valeur.end_mark.index
    if isinstance(valeur, yaml.SequenceNode):
        dernier = valeur.value[-1]
        return _derniere_fin(dernier, dernier)
    k, v = valeur.value[-1]
    return _derniere_fin(k, v)


def _inserer(texte: str, position: int, lignes: list[str]) -> str:
    nl = _nl(texte)
    bloc = "".join(ligne + nl for ligne in lignes)
    if position == len(texte) and texte and not texte.endswith("\n"):
        bloc = nl + bloc
    return texte[:position] + bloc + texte[position:]


def _flux_une_ligne(noeud) -> None:
    if noeud.start_mark.line != noeud.end_mark.line:
        raise PatchImpossible("collection en flux sur plusieurs lignes")


def _remplacer(texte: str, noeud, nouveau: str) -> str:
    return texte[:noeud.start_mark.index] + nouveau + texte[noeud.end_mark.index:]


def _cle_seule(texte: str, cle) -> None:
    """`cle:` seule sur sa ligne (valeur vide, commentaire permis)."""
    _seul_sur_sa_ligne(texte, cle, _BLANC)
    fin = texte.find("\n", cle.end_mark.index)
    reste = texte[cle.end_mark.index:] if fin < 0 else texte[cle.end_mark.index:fin]
    if not _APRES_CLE.fullmatch(reste):
        raise PatchImpossible("clé suivie d'autre chose")


# --- Séquences (listes `exclus` et `chantiers.<nom>.projets`) ---


def _retirer_de_liste(texte: str, liste, projet: str) -> str:
    if not isinstance(liste, yaml.SequenceNode):
        raise PatchImpossible("liste attendue")
    items = [n for n in liste.value if isinstance(n, yaml.ScalarNode) and n.value == projet]
    if len(items) != 1:
        raise PatchImpossible("élément introuvable ou en double")
    item = items[0]
    if liste.flow_style:
        _flux_une_ligne(liste)
        if any(not isinstance(n, yaml.ScalarNode) for n in liste.value):
            raise PatchImpossible("liste en flux non plate")
        restes = [texte[n.start_mark.index:n.end_mark.index] for n in liste.value if n is not item]
        return _remplacer(texte, liste, "[" + ", ".join(restes) + "]")
    if item.start_mark.line != item.end_mark.line:
        raise PatchImpossible("élément sur plusieurs lignes")
    _seul_sur_sa_ligne(texte, item, _TIRET)
    _fin_de_ligne_libre(texte, item.end_mark.index)
    debut = _debut_ligne(texte, item.start_mark.index)
    return texte[:debut] + texte[_fin_ligne(texte, item.end_mark.index):]


def _ajouter_a_liste(texte: str, parent: yaml.MappingNode, cle: str, projet: str,
                     creer: bool) -> str:
    rendu = _rendu(projet)
    paire = _paire(parent, cle)
    if paire is None:
        if not creer:
            raise PatchImpossible(f"{cle} absent")
        return _inserer(texte, len(texte), [f"{cle}:", f"  - {rendu}"])
    k, v = paire
    if isinstance(v, yaml.SequenceNode):
        if v.flow_style:
            _flux_une_ligne(v)
            if any(not isinstance(n, yaml.ScalarNode) for n in v.value):
                raise PatchImpossible("liste en flux non plate")
            items = [texte[n.start_mark.index:n.end_mark.index] for n in v.value]
            return _remplacer(texte, v, "[" + ", ".join([*items, rendu]) + "]")
        dernier = v.value[-1]
        if not isinstance(dernier, yaml.ScalarNode) or dernier.start_mark.line != (
            dernier.end_mark.line
        ):
            raise PatchImpossible("dernier élément sur plusieurs lignes")
        _seul_sur_sa_ligne(texte, dernier, _TIRET)
        _fin_de_ligne_libre(texte, dernier.end_mark.index)
        prefixe = texte[_debut_ligne(texte, dernier.start_mark.index):dernier.start_mark.index]
        return _inserer(texte, _fin_ligne(texte, dernier.end_mark.index), [prefixe + rendu])
    if _est_vide(v):
        if v.start_mark.index != v.end_mark.index:  # `null` ou `~` explicite
            return _remplacer(texte, v, f"[{rendu}]")
        if parent.flow_style:
            raise PatchImpossible("objet en flux")
        _cle_seule(texte, k)
        retrait = " " * (k.start_mark.column + 2)
        return _inserer(texte, _fin_ligne(texte, k.end_mark.index), [f"{retrait}- {rendu}"])
    raise PatchImpossible(f"{cle} : liste attendue")


# --- Pauses (`pauses.<projet>.revue`) ---


def _poser_pause(texte: str, racine: yaml.MappingNode, projet: str, revue: str) -> str:
    rendu = _rendu(projet)
    paire = _paire(racine, "pauses")
    if paire is None:
        return _inserer(texte, len(texte), ["pauses:", f"  {rendu}:", f"    revue: {revue}"])
    k, v = paire
    if _est_vide(v):
        if v.start_mark.index != v.end_mark.index:
            return _remplacer(texte, v, f"{{{rendu}: {{revue: {revue}}}}}")
        _cle_seule(texte, k)
        col = k.start_mark.column + 2
        lignes = [f"{' ' * col}{rendu}:", f"{' ' * (col + 2)}revue: {revue}"]
        return _inserer(texte, _fin_ligne(texte, k.end_mark.index), lignes)
    if not isinstance(v, yaml.MappingNode):
        raise PatchImpossible("pauses : objet attendu")
    entree = _paire(v, projet)
    if entree is not None:  # pause existante : seule la date change
        pause = entree[1]
        revue_paire = _paire(pause, "revue") if isinstance(pause, yaml.MappingNode) else None
        if revue_paire is None or not isinstance(revue_paire[1], yaml.ScalarNode):
            raise PatchImpossible("pause sans revue")
        _flux_une_ligne(revue_paire[1])
        return _remplacer(texte, revue_paire[1], revue)
    if v.flow_style:
        if v.value:
            raise PatchImpossible("pauses en flux non vide")
        return _remplacer(texte, v, f"{{{rendu}: {{revue: {revue}}}}}")
    dk, dv = v.value[-1]
    _seul_sur_sa_ligne(texte, dk, _BLANC)
    fin = _derniere_fin(dk, dv)
    _fin_de_ligne_libre(texte, fin)
    col = dk.start_mark.column
    retrait = 2
    if isinstance(dv, yaml.MappingNode) and not dv.flow_style and dv.value:
        retrait = max(1, dv.value[0][0].start_mark.column - col)
    lignes = [f"{' ' * col}{rendu}:", f"{' ' * (col + retrait)}revue: {revue}"]
    return _inserer(texte, _fin_ligne(texte, fin), lignes)


def _lever_pause(texte: str, racine: yaml.MappingNode, projet: str) -> str:
    paire = _paire(racine, "pauses")
    if paire is None or not isinstance(paire[1], yaml.MappingNode):
        raise PatchImpossible("pauses absent")
    pauses = paire[1]
    entree = _paire(pauses, projet)
    if entree is None:
        raise PatchImpossible("pause introuvable")
    k, v = entree
    if pauses.flow_style:
        _flux_une_ligne(pauses)
        restes = [texte[a.start_mark.index:b.end_mark.index] for a, b in pauses.value if a is not k]
        return _remplacer(texte, pauses, "{" + ", ".join(restes) + "}")
    _seul_sur_sa_ligne(texte, k, _BLANC)
    fin = _derniere_fin(k, v)
    _fin_de_ligne_libre(texte, fin)
    return texte[:_debut_ligne(texte, k.start_mark.index)] + texte[_fin_ligne(texte, fin):]


# --- Point d'entrée ---


def _liste_de_chantier(racine: yaml.MappingNode, nom: str) -> yaml.MappingNode:
    chantiers = _paire(racine, "chantiers")
    if chantiers is None or not isinstance(chantiers[1], yaml.MappingNode):
        raise PatchImpossible("chantiers absent")
    chantier = _paire(chantiers[1], nom)
    if chantier is None:
        raise PatchImpossible("chantier voulu absent")
    if not isinstance(chantier[1], yaml.MappingNode):
        raise PatchImpossible("chantier sans liste projets")
    return chantier[1]


def appliquer(texte: str, projet: str, champ: str, courant, voulu) -> str:
    """Texte de `projets.yaml` où `champ` de `projet` passe de `courant` à `voulu`.

    Lève `PatchImpossible` si la forme du texte ne s'y prête pas.
    """
    if champ == "chantier":
        if courant is not None:
            liste = _paire(_liste_de_chantier(_racine(texte), courant), "projets")
            if liste is None:
                raise PatchImpossible("liste projets absente")
            texte = _retirer_de_liste(texte, liste[1], projet)
        if voulu is not None:
            parent = _liste_de_chantier(_racine(texte), voulu)
            if _paire(parent, "projets") is None:
                raise PatchImpossible("liste projets absente")
            texte = _ajouter_a_liste(texte, parent, "projets", projet, creer=False)
        return texte
    if champ == "exclu":
        racine = _racine(texte)
        if voulu:
            return _ajouter_a_liste(texte, racine, "exclus", projet, creer=True)
        paire = _paire(racine, "exclus")
        if paire is None:
            raise PatchImpossible("exclus absent")
        return _retirer_de_liste(texte, paire[1], projet)
    if champ == "pause":
        racine = _racine(texte)
        if voulu is None:
            return _lever_pause(texte, racine, projet)
        return _poser_pause(texte, racine, projet, voulu)
    raise PatchImpossible(f"champ inconnu : {champ}")
