"""Serveur HTTP local de l'appli : périmètre de sécurité (AD-14, AD-15, `securite.md`).

Toute requête, quelle que soit sa méthode HTTP, passe par `verifier_requete` avant tout
routage, dans l'ordre M10 :

1. `Host` ∈ {`127.0.0.1:<port>`, `localhost:<port>`}, sinon 403 (DNS rebinding) ;
2. `Origin` présent et différent de l'appli, sinon 403 ;
3. préfixe `/api/` ⇒ `Authorization: Bearer <jeton>` comparé par `hmac.compare_digest`,
   sinon 401 ;
4. routage : route inconnue 404, méthode non permise 405 avec `Allow` ; un `<id>` ou `<projet>`
   du chemin invalide selon AD-9 rend 400 (`routes.valider_parametres`).

L9 : une requête sans `Origin` est acceptée parce que le jeton protège toute route `/api/` ;
aucune route `/api/` de lecture n'est servie sans jeton. Sans jeton, seuls `/` et les fichiers
statiques de `pilotage/web/` sont servis, avec la CSP d'AD-15 ; ils ne contiennent aucune
donnée de projet.
"""

import hmac
import json
import secrets
import socket
import socketserver
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from pilotage import chemins
from pilotage.noyau import ids
from pilotage.serveur import routes as routes_api
from pilotage.serveur.routes import Reponse, Route

CSP = (
    "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'"
)
TAILLE_MAX_CORPS = 64 * 1024
# Délai (s) d'attente d'une requête ou de son corps : une connexion muette ne retient pas un
# fil indéfiniment.
DELAI_SOCKET = 30
METHODES_STATIQUES = ("GET", "HEAD")
TYPES_STATIQUES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


@dataclass(frozen=True)
class Decision:
    """Issue de `verifier_requete` : un refus, une route `/api/`, ou un fichier statique."""

    refus: Reponse | None = None
    route: Route | None = None
    parametres: dict[str, str] | None = None
    fichier: Path | None = None


class ServeurPilotage(ThreadingHTTPServer):
    """`ThreadingHTTPServer` sur `127.0.0.1:<port>`, port exclusif, jeton en mémoire seulement."""

    # Vrai par défaut dans `http.server` : posé explicitement pour qu'aucun autre processus ne
    # puisse partager le port (AD-14, vol de port).
    allow_reuse_address = False
    allow_reuse_port = False
    daemon_threads = True

    def __init__(
        self,
        port: int,
        racine_web: Path | str,
        table: tuple[Route, ...] = routes_api.TABLE,
    ) -> None:
        self.jeton = secrets.token_urlsafe(32)
        self.racine_web = Path(racine_web)
        self.table = tuple(table)
        self._verrou_journal = threading.Lock()
        super().__init__(("127.0.0.1", port), Requete)

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # `HTTPServer.server_bind` appellerait `socket.getfqdn`, lent et inutile ici.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]

    @property
    def port(self) -> int:
        return self.server_address[1]

    def url(self) -> str:
        """URL ouverte dans le navigateur : le jeton n'est remis que dans le fragment."""
        return f"http://127.0.0.1:{self.port}/#{self.jeton}"

    def hotes_permis(self) -> frozenset[str]:
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})

    def origines_permises(self) -> frozenset[str]:
        return frozenset({f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"})

    def journaliser(self, message: str) -> None:
        """Ajoute une ligne à `attente/journal/serveur-AAAA-MM.log` ; ne lève jamais.

        Le jeton est masqué s'il apparaît, les caractères de contrôle sont échappés.
        """
        try:
            message = message.replace(self.jeton, "***")
            message = "".join(c if c.isprintable() else f"\\x{ord(c):02x}" for c in message)
            horodatage = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            chemin = chemins.journal_serveur(horodatage[:7])
            with self._verrou_journal:
                chemin.parent.mkdir(parents=True, exist_ok=True)
                with open(chemin, "a", encoding="utf-8", newline="") as fichier:
                    fichier.write(f"{horodatage} {message}\n")
        except Exception:  # noqa: BLE001 - le journal ne doit jamais faire échouer une requête
            pass


def _segments(cible: str) -> list[str] | None:
    """Segments décodés du chemin de la requête (`?` et `#` retirés) ; `None` hors forme `/…`."""
    chemin = cible.split("?", 1)[0].split("#", 1)[0]
    if not chemin.startswith("/"):
        return None
    return [unquote(segment) for segment in chemin[1:].split("/")]


def _jeton_valide(serveur: ServeurPilotage, valeurs: list[str]) -> bool:
    if len(valeurs) != 1 or not valeurs[0].startswith("Bearer "):
        return False
    fourni = valeurs[0][len("Bearer "):].encode("latin-1", "replace")
    return hmac.compare_digest(fourni, serveur.jeton.encode("ascii"))


def _fichier_statique(racine: Path, segments: list[str]) -> Path | None:
    if segments == [""]:
        segments = ["index.html"]
    try:
        fichier = chemins.joindre_sous(racine, *segments)
    except (ids.ErreurId, OSError, ValueError):
        return None
    return fichier if fichier.is_file() else None


def verifier_requete(serveur: ServeurPilotage, methode: str, cible: str, entetes) -> Decision:
    """Contrôles M10 puis routage, pour toute méthode HTTP et toute cible."""
    hotes = entetes.get_all("Host") or []
    if len(hotes) != 1 or hotes[0].lower() not in serveur.hotes_permis():
        return Decision(refus=Reponse(403, erreur="hôte refusé"))
    origines = entetes.get_all("Origin") or []
    if origines and (len(origines) != 1 or origines[0] not in serveur.origines_permises()):
        return Decision(refus=Reponse(403, erreur="origine refusée"))
    segments = _segments(cible)
    if segments is None:
        return Decision(refus=Reponse(404, erreur="route inconnue"))
    if segments[0].casefold() == "api":
        if not _jeton_valide(serveur, entetes.get_all("Authorization") or []):
            return Decision(
                refus=Reponse(401, erreur="jeton absent ou invalide",
                              entetes=(("WWW-Authenticate", "Bearer"),))
            )
        route, parametres, permises = routes_api.router(serveur.table, methode, segments)
        if route is not None:
            refus = routes_api.valider_parametres(route, parametres)
            if refus is not None:
                return Decision(refus=refus)
            return Decision(route=route, parametres=parametres)
        if permises:
            return Decision(
                refus=Reponse(405, erreur="méthode non permise",
                              entetes=(("Allow", ", ".join(permises)),))
            )
        return Decision(refus=Reponse(404, erreur="route inconnue"))
    fichier = _fichier_statique(serveur.racine_web, segments)
    if fichier is None:
        return Decision(refus=Reponse(404, erreur="fichier inconnu"))
    if methode not in METHODES_STATIQUES:
        return Decision(
            refus=Reponse(405, erreur="méthode non permise",
                          entetes=(("Allow", ", ".join(METHODES_STATIQUES)),))
        )
    return Decision(fichier=fichier)


class Requete(BaseHTTPRequestHandler):
    """Gestionnaire unique : toute méthode (`do_<METHODE>`) mène à `_traiter`."""

    server: ServeurPilotage
    server_version = "pilotage"
    sys_version = ""
    timeout = DELAI_SOCKET

    def __getattr__(self, nom: str):
        # `http.server` rend 501 pour une méthode sans `do_<METHODE>` : ici, aucune n'y échappe.
        if nom.startswith("do_"):
            return self._traiter
        raise AttributeError(nom)

    def _est_api(self) -> bool:
        segments = _segments(self.path or "")
        return bool(segments) and segments[0].casefold() == "api"

    def _traiter(self) -> None:
        decision = verifier_requete(self.server, self.command, self.path, self.headers)
        if decision.refus is not None:
            if self._est_api():
                self.envoyer_api(decision.refus)
            else:
                self._envoyer_texte(decision.refus)
            return
        if decision.fichier is not None:
            self._envoyer_fichier(decision.fichier)
            return
        assert decision.route is not None and decision.route.gestionnaire is not None
        corps = self._lire_corps()
        if isinstance(corps, Reponse):
            self.envoyer_api(corps)
            return
        try:
            reponse = decision.route.gestionnaire(decision.parametres or {}, corps)
        except chemins.ErreurConfiguration as exc:  # cause lisible : config.json à corriger
            self.server.journaliser(f"erreur {type(exc).__name__} {self.command}")
            reponse = Reponse(500, erreur=f"configuration invalide : {exc}")
        except Exception as exc:  # noqa: BLE001 - réponse 500, type seul au journal
            self.server.journaliser(f"erreur {type(exc).__name__} {self.command}")
            reponse = Reponse(500, erreur="erreur interne")
        self.envoyer_api(reponse)

    def _lire_corps(self) -> bytes | Reponse:
        """Corps lu après contrôle du jeton seulement ; borné à `TAILLE_MAX_CORPS`."""
        if self.headers.get("Transfer-Encoding") is not None:
            self.close_connection = True
            return Reponse(400, erreur="Transfer-Encoding non pris en charge")
        longueurs = self.headers.get_all("Content-Length") or []
        if not longueurs:
            return b""
        valeur = longueurs[0].strip(" 	") if len(longueurs) == 1 else ""
        # Chiffres ASCII seulement (`isdigit` accepte « ² ») ; zéros de tête retirés avant `int`,
        # pour qu'une longueur démesurée rende 413 sans conversion coûteuse.
        if not valeur or not valeur.isascii() or not valeur.isdigit():
            self.close_connection = True
            return Reponse(400, erreur="Content-Length invalide")
        chiffres = valeur.lstrip("0") or "0"
        if len(chiffres) > len(str(TAILLE_MAX_CORPS)) or int(chiffres) > TAILLE_MAX_CORPS:
            self.close_connection = True
            return Reponse(413, erreur="corps trop grand")
        longueur = int(chiffres)
        try:
            corps = self.rfile.read(longueur)
        except OSError:  # délai dépassé ou connexion coupée
            self.close_connection = True
            return Reponse(408, erreur="corps incomplet")
        if len(corps) != longueur:
            self.close_connection = True
            return Reponse(400, erreur="corps incomplet")
        return corps

    def _envoyer(self, statut: int, entetes: list[tuple[str, str]], corps: bytes) -> None:
        self.send_response(statut)
        for nom, valeur in entetes:
            self.send_header(nom, valeur)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def envoyer_api(self, reponse: Reponse) -> None:
        """Seule réponse `/api/`, erreurs comprises : `{"ok", "donnees"?, "erreur"?}`, ou texte
        brut (`Reponse.texte`, brief M11) en `text/plain; charset=utf-8`, mêmes en-têtes."""
        if reponse.texte is not None:
            entetes = [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("X-Content-Type-Options", "nosniff"),
                ("Cache-Control", "no-store"),
                *reponse.entetes,
            ]
            self._envoyer(reponse.statut, entetes, reponse.texte.encode("utf-8"))
            return
        objet: dict[str, object] = {"ok": 200 <= reponse.statut < 300}
        if reponse.donnees is not None:
            objet["donnees"] = reponse.donnees
        if reponse.erreur is not None:
            objet["erreur"] = reponse.erreur
        corps = json.dumps(objet, ensure_ascii=False).encode("utf-8")
        entetes = [
            ("Content-Type", "application/json"),
            ("X-Content-Type-Options", "nosniff"),
            ("Cache-Control", "no-store"),
            *reponse.entetes,
        ]
        self._envoyer(reponse.statut, entetes, corps)

    def _entetes_page(self, type_contenu: str) -> list[tuple[str, str]]:
        return [
            ("Content-Type", type_contenu),
            ("Content-Security-Policy", CSP),
            ("X-Content-Type-Options", "nosniff"),
            ("Cache-Control", "no-store"),
            ("Referrer-Policy", "no-referrer"),
        ]

    def _envoyer_texte(self, reponse: Reponse) -> None:
        corps = f"{reponse.statut} {reponse.erreur or ''}\n".encode()
        entetes = self._entetes_page("text/plain; charset=utf-8") + list(reponse.entetes)
        self._envoyer(reponse.statut, entetes, corps)

    def _envoyer_fichier(self, fichier: Path) -> None:
        try:
            corps = fichier.read_bytes()
        except OSError:
            self._envoyer_texte(Reponse(404, erreur="fichier inconnu"))
            return
        type_contenu = TYPES_STATIQUES.get(fichier.suffix.lower(), "application/octet-stream")
        self._envoyer(200, self._entetes_page(type_contenu), corps)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None):
        """Erreurs de `http.server` (requête mal formée) : même forme, CSP comprise."""
        del explain
        self.close_connection = True
        self._envoyer_texte(Reponse(code, erreur=message or self.responses.get(code, ("",))[0]))

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - signature d'http.server
        """Redirigé vers le journal : ligne de requête et statut, jamais les en-têtes."""
        self.server.journaliser(f"{self.client_address[0]} {format % args}")
