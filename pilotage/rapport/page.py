"""Page HTML du rapport de la semaine (story 9.2, FR44) : pure, stdlib seule, sans E/S.

Tout texte venu des données passe par `_texte` (nettoyé, borné, échappé) et ne va que dans un
nœud texte : aucun attribut dynamique, aucun script, aucun lien, aucune ressource externe. La
CSP de la `<meta>` est la vraie barrière ; la feuille de la charte est passée par l'appelant et
refusée si elle pourrait ouvrir une ressource ou sortir du `<style>`.
"""

import html
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import datetime

from pilotage.rapport.semaine import SANS_COMPARAISON, Synthese

BORNE_TEXTE = 300  # points de code : texte libre (alerte), « … » compris
BORNE_QUOI = 200  # comme le marqueur
BORNE_COURTE = 50  # identifiants : projet, PC, type, code, tag, horodatage
BORNE_PHASES = 128  # liste de topics `status-*` jointe
MAX_LIGNES = 200  # par table (et par liste), puis « … et N de plus »
RIEN = "Rien cette semaine."
SANS_VALEUR = "—"
CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
_CSS_INTERDIT = re.compile(r"<|\\|url\(|@import|expression\(", re.IGNORECASE)
_THEME_CLAIR = re.compile(r'\[data-theme="light"\]\s*\{([^{}]*)\}')
_TITRES = (
    "Actions", "Changements d'action", "Attentes de l'utilisateur", "Livraisons", "Sessions",
    "Alertes ouvertes",
)
_FEUILLE = """
body { margin: 0; background: var(--fond); color: var(--texte);
  font-family: var(--police-texte); font-size: var(--taille-base); line-height: 1.5; }
header, main { max-width: 64rem; margin: 0 auto; padding: var(--espacement-4); }
h1, h2 { font-family: var(--police-titres); font-weight: var(--graisse-titres); }
h1 { font-size: var(--taille-titre-3); margin: 0; }
h2 { font-size: var(--taille-titre-4); margin: var(--espacement-6) 0 var(--espacement-3); }
table { border-collapse: collapse; width: 100%; }
th, td { border: var(--trait-largeur) solid var(--trait); padding: var(--espacement-2);
  text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th { background: var(--surface-alt); }
small { color: var(--texte-attenue); font-size: var(--taille-petit); }
"""
_IMPRESSION = """
@media print {
  :root {%s}
  body { background: var(--fond); color: var(--texte); }
  section { break-inside: avoid-page; }
}
"""


def _texte(valeur: object, borne: int = BORNE_TEXTE) -> str:
    """Seule entrée des données dans la page : nettoyé, coupé à `borne` (« … » compris), échappé."""
    brut = str(valeur)
    propre = "".join(
        "�" if 0xD800 <= ord(c) <= 0xDFFF else c
        for c in brut
        if c == " " or unicodedata.category(c) not in ("Cc", "Cf")
    )
    if len(propre) > borne:
        propre = propre[: max(borne - 1, 0)] + "…"
    return html.escape(propre, quote=True)


def _ou_tiret(valeur: object, borne: int = BORNE_COURTE) -> str:
    return SANS_VALEUR if valeur is None or valeur == "" else _texte(valeur, borne)


def _plus(reste: int) -> str:
    return f"… et {reste} de plus"


def _table(entetes: Sequence[str], lignes: Sequence[Sequence[str]]) -> str:
    """Table de cellules déjà passées par `_texte` ; au plus `MAX_LIGNES` lignes."""
    tete = "".join(f"<th>{e}</th>" for e in entetes)
    corps = ["<tr>" + "".join(f"<td>{c}</td>" for c in ligne) + "</tr>"
             for ligne in lignes[:MAX_LIGNES]]
    if len(lignes) > MAX_LIGNES:
        reste = _plus(len(lignes) - MAX_LIGNES)
        corps.append(f'<tr><td colspan="{len(entetes)}">{reste}</td></tr>')
    return f"<table><thead><tr>{tete}</tr></thead><tbody>{''.join(corps)}</tbody></table>"


def _section(titre: str, contenu: str) -> str:
    return f"<section><h2>{titre}</h2>{contenu}</section>"


def _ou_rien(lignes: Sequence, rendu: str) -> str:
    return rendu if lignes else f"<p>{RIEN}</p>"


def _actions(s: Synthese) -> str:
    debut = s.comptes_debut or {}
    lignes = [
        [_texte(cle, BORNE_COURTE),
         _texte(debut[cle], BORNE_COURTE) if s.comparaison and cle in debut else SANS_VALEUR,
         _texte(n, BORNE_COURTE)]
        for cle, n in s.comptes_fin.items()
    ]
    note = "" if s.comparaison else f"<p>{_texte(SANS_COMPARAISON)}</p>"
    return note + _table(("Action", "Début", "Fin"), lignes)


def _changements(s: Synthese) -> str:
    lignes = [[_texte(c.get("projet"), BORNE_COURTE), _texte(c.get("avant"), BORNE_COURTE),
               _texte(c.get("apres"), BORNE_COURTE), _texte(c.get("code"), BORNE_COURTE)]
              for c in s.changements]
    return _ou_rien(lignes, _table(("Projet", "Avant", "Après", "Code"), lignes))


def _age(age: object) -> str:
    return SANS_VALEUR if age is None else f"{_texte(age, BORNE_COURTE)} j"


def _attentes(s: Synthese) -> str:
    lignes = [[_texte(a.get("projet"), BORNE_COURTE), _texte(a.get("type"), BORNE_COURTE),
               _texte(a.get("quoi") or "", BORNE_QUOI), _age(a.get("age_jours"))]
              for a in s.attentes]
    return _ou_rien(lignes, _table(("Projet", "Type", "Quoi", "Âge"), lignes))


def _phases(valeur: object) -> str:
    if isinstance(valeur, list | tuple):
        valeur = ", ".join(str(v) for v in valeur)
    return _ou_tiret(valeur, BORNE_PHASES)


def _livraison(entree: dict) -> list[str]:
    projet, type_ = _texte(entree.get("projet"), BORNE_COURTE), entree.get("type")
    if type_ == "release":
        return [projet, "release", _ou_tiret(entree.get("avant")), _ou_tiret(entree.get("tag"))]
    return [projet, _texte(type_, BORNE_COURTE), _phases(entree.get("avant")),
            _phases(entree.get("apres"))]


def _livraisons(s: Synthese) -> str:
    lignes = [_livraison(e) for e in s.livraisons]
    note = f"<p><small>{_texte(s.note_livraisons)}</small></p>"
    return _ou_rien(lignes, _table(("Projet", "Type", "Avant", "Après"), lignes)) + note


def _sessions(s: Synthese) -> str:
    lignes = [[_texte(x.get(cle), BORNE_COURTE)
               for cle in ("projet", "pc", "nombre", "premiere", "derniere")]
              for x in s.sessions]
    entetes = ("Projet", "PC", "Sessions", "Première activité", "Dernière activité")
    return _ou_rien(lignes, _table(entetes, lignes))


def _liste(textes: Iterable[str]) -> str:
    textes = list(textes)
    items = [f"<li>{t}</li>" for t in textes[:MAX_LIGNES]]
    if len(textes) > MAX_LIGNES:
        items.append(f"<li>{_plus(len(textes) - MAX_LIGNES)}</li>")
    return f"<ul>{''.join(items)}</ul>"


def _alertes(s: Synthese) -> str:
    return _ou_rien(s.alertes, _liste(_texte(a) for a in s.alertes))


def _feuille(css: str) -> str:
    if _CSS_INTERDIT.search(css):
        raise ValueError("feuille de style refusée : ressource externe ou balise possible")
    clair = _THEME_CLAIR.search(css)
    return css + _FEUILLE + _IMPRESSION % (clair[1] if clair else "")


def rendre_page(synthese: Synthese, *, css: str = "", genere: datetime | None = None) -> str:
    """Page HTML autonome de `synthese` ; `css` : contenu de `charte.css` ; `genere` : heure
    locale de génération (pied de page). Lève ValueError si `css` est refusée."""
    feuille = _feuille(css)
    titre = f"Semaine {_texte(synthese.semaine, BORNE_COURTE)}"
    periode = (f"Du {_texte(synthese.debut[:10], BORNE_COURTE)} au "
               f"{_texte(synthese.fin[:10], BORNE_COURTE)} (exclu)")
    rendus = (_actions, _changements, _attentes, _livraisons, _sessions, _alertes)
    sections = "".join(_section(t, f(synthese)) for t, f in zip(_TITRES, rendus, strict=True))
    pied = ("" if genere is None
            else f"<p><small>généré le {genere.strftime('%Y-%m-%d %H:%M')}</small></p>")
    return (
        "<!doctype html>\n"
        '<html lang="fr">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{titre}</title>\n<style>\n{feuille}</style>\n</head>\n<body>\n"
        f"<header><h1>{titre}</h1><p>{periode}</p></header>\n"
        f"<main>\n{sections}\n{pied}</main>\n</body>\n</html>\n"
    )
