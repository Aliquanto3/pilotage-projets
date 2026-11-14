"""Banc de latence des hooks (AD-1) : N appels par événement, p50 et p95 hors démarrage à froid.

Usage : `uv run python outils/bench_hooks.py [--python CHEMIN] [--appels 50] [--messages 3]
[--etats 20] [--depots 8]`.
Tout se passe sous une racine temporaire (`PILOTAGE_RACINE_LOCALE`) : aucun vrai dossier touché.
Le hook est lancé comme Claude Code le lance : `<python> -I -S <hook>`, payload sur stdin.
SessionStart et SessionEnd lancent pour de vrai la synchro détachée (story 3.6), vers un
`lancer.py` factice qui ne fait que se signaler : le `Popen` est compté dans la mesure.
`--messages N` (story 5.3, défaut 3) : N messages en attente dans `donnees/boite/bench/`, remis et
acquittés à chaque SessionStart (acquittements effacés entre deux appels, hors mesure).
`--etats N` (story 8.1, défaut 20) : N états de session avec note de reprise, d'autres PC, dans
`donnees/etat/bench/` ; SessionStart en relit `MAX_ETATS_LUS` et injecte la plus récente.
`--depots N` (story 8.3, défaut 8) : N états de dépôt d'autres PC (5 décisions chacun) dans
`donnees/depots/bench/`, plus deux journaux de 200 lignes (jamais lus) ; SessionStart en ouvre 8
et injecte le plus récent. Stop déclare un état et une décision par marqueur.
PreCompact (story 8.2) : consigne de compaction en texte brut sur stdout, jamais de JSON.
"""

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

DEPOT = Path(__file__).resolve().parent.parent
MESSAGE_AVEC_MARQUEURS = (
    "Fait.\n"
    '<!-- pilotage: action=attend-utilisateur | type=choix | quoi="Choisir la suite" -->\n'
    "<!-- pilotage: reprise=\"Reprendre a l etape 3\" -->\n"
    '<!-- pilotage: prochaine="Relire la story" | branche=story/x | blocages="aucun" -->\n'
    '<!-- pilotage: decision="Garder le banc" | pourquoi="Mesure stable" -->'
)
HOOKS = {
    "session_start": ("SessionStart", {"source": "startup"}),
    "stop": ("Stop", {"last_assistant_message": MESSAGE_AVEC_MARQUEURS}),
    "prompt": ("UserPromptSubmit", {"prompt": "TEXTE FACTICE"}),
    "notification": (
        "Notification",
        {
            "notification_type": "permission_prompt",
            "message": "Claude needs your permission to use Bash",
        },
    ),
    "pre_compact": ("PreCompact", {"trigger": "auto", "custom_instructions": None}),
    "session_end": ("SessionEnd", {"reason": "other"}),
}
BUDGET_P95_MS = 100.0
DELAI_LANCEMENTS_S = 60.0
MESSAGES_PAR_DEFAUT = 3
ETATS_PAR_DEFAUT = 20
DEPOTS_PAR_DEFAUT = 8
LIGNES_JOURNAL_BANC = 200
PCS_AUTRES = ("bench-a", "bench-b")
NOTE_BANC = "Reprendre la story 8.1 : relire la spec puis lancer les tests ciblés. " * 4
TEXTE_MESSAGE = "Message de banc : relis la story et reprends à l'étape 3. " * 30  # ~1,7 Ko
LANCEUR_FACTICE = (
    "import os, uuid\n"
    "dossier = os.path.join(os.path.dirname(os.getcwd()), 'lancements')\n"
    "os.makedirs(dossier, exist_ok=True)\n"
    "open(os.path.join(dossier, uuid.uuid4().hex), 'w').close()\n"
)


def centile(valeurs: list[float], rang: float) -> float:
    """Centile par interpolation linéaire (méthode inclusive) ; une seule valeur : elle-même."""
    if not valeurs:
        raise ValueError("aucune mesure")
    if len(valeurs) == 1:
        return valeurs[0]
    return statistics.quantiles(valeurs, n=100, method="inclusive")[round(rang) - 1]


def ids_messages(nombre: int) -> list[str]:
    """Identifiants AD-9 des messages du banc, du plus ancien au plus récent."""
    return [f"20261106T1000{i:02d}Z-{i:08x}" for i in range(nombre)]


def deposer_messages(racine: Path, nombre: int) -> None:
    """`nombre` messages valides (schéma `message`) dans `donnees/boite/bench/`."""
    boite = racine / "donnees" / "boite" / "bench"
    boite.mkdir(parents=True, exist_ok=True)
    for identifiant in ids_messages(nombre):
        objet = {"schema": 1, "id": identifiant, "projet": "bench", "texte": TEXTE_MESSAGE}
        (boite / f"{identifiant}.json").write_text(json.dumps(objet), encoding="utf-8")


def deposer_etats(racine: Path, nombre: int) -> None:
    """`nombre` états valides (schéma `session`) avec note, répartis entre deux autres PC dans
    `donnees/etat/bench/<pc>/` ; dates distinctes, la plus récente en dernier.

    `mtime` posé à un jour dans le futur : ces états restent les plus récents sur le disque
    malgré ceux que le banc crée, donc chaque SessionStart ouvre et valide les mêmes `nombre`
    fichiers (pire cas jusqu'à `MAX_ETATS_LUS`) et trouve une note."""
    futur = time.time() + 86_400
    for i in range(nombre):
        pc = PCS_AUTRES[i % len(PCS_AUTRES)]
        dossier = racine / "donnees" / "etat" / "bench" / pc
        dossier.mkdir(parents=True, exist_ok=True)
        session = str(uuid.UUID(int=i + 1))
        heure = f"2026-11-{1 + i // 24:02d}T{i % 24:02d}:00:00Z"
        objet = {
            "schema": 1, "projet": "bench", "pc": pc, "session": session, "pid": 1000 + i,
            "pid_cree": None, "dossier": "bench", "branche": "main", "debut": heure,
            "dernier_tour": heure, "statut": "finie", "fin": heure,
            "reprise": NOTE_BANC[:300],
        }
        chemin = dossier / f"{session}.json"
        chemin.write_text(json.dumps(objet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.utime(chemin, (futur + i, futur + i))


def deposer_depots(racine: Path, nombre: int) -> None:
    """`nombre` états de dépôt valides (schéma `etat_depot`) d'autres PC, 5 décisions chacun,
    dans `donnees/depots/bench/`, et deux journaux de `LIGNES_JOURNAL_BANC` lignes (jamais lus
    par SessionStart). `ecrit` récent (moins que la péremption), `mtime` dans le futur comme
    `deposer_etats` : chaque SessionStart ouvre les mêmes fichiers."""
    if nombre <= 0:
        return
    from datetime import UTC, datetime, timedelta

    dossier = racine / "donnees" / "depots" / "bench"
    dossier.mkdir(parents=True, exist_ok=True)
    futur = time.time() + 86_400
    session = str(uuid.UUID(int=1))
    for i in range(nombre):
        pc = f"bench-d{i}"
        ecrit = (datetime.now(UTC) - timedelta(minutes=nombre - i)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        # Textes sans blanc au bord : le schéma `decision` les refuse.
        decisions = [
            {"date": ecrit[:10], "ecrit": ecrit,
             "decision": (f"Décision {j} du banc " * 6).strip(),
             "pourquoi": ("Parce que le banc le veut " * 4).strip(), "session": session}
            for j in range(5)
        ]
        prochaine = ("Relire la story puis lancer les tests ciblés " * 5).strip()
        objet = {
            "schema": 1, "projet": "bench", "pc": pc, "session": session, "ecrit": ecrit,
            "etat": {"prochaine": prochaine,
                     "branche": "story/bench", "blocages": "aucun", "explore": "docs/a.md",
                     "a_explorer": "module Y"},
            "decisions": decisions,
        }
        chemin = dossier / f"{pc}.json"
        chemin.write_text(json.dumps(objet, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        os.utime(chemin, (futur + i, futur + i))
        if i < 2:
            ligne = json.dumps(decisions[0], ensure_ascii=False) + "\n"
            (dossier / f"{pc}.decisions.jsonl").write_text(
                ligne * LIGNES_JOURNAL_BANC, encoding="utf-8"
            )


def deposer_operations_autres(racine: Path, nombre: int) -> None:
    """`nombre` opérations `deposer_message` d'un autre projet dans `attente/operations/` (le
    hook doit les écarter sans les parser ni les journaliser)."""
    dossier = racine / "attente" / "operations"
    dossier.mkdir(parents=True, exist_ok=True)
    for i in range(nombre):
        identifiant = f"20261106T09{i // 60 % 60:02d}{i % 60:02d}Z-{i:08x}"
        objet = {"schema": 1, "id": identifiant, "verbe": "deposer_message",
                 "projet": "autre-projet", "texte": TEXTE_MESSAGE}
        (dossier / f"{identifiant}.json").write_text(
            json.dumps(objet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def preparer(
    racine: Path, messages: int = 0, operations: int = 0, etats: int = 0, depots: int = 0
) -> Path:
    """Dépôt factice `bench` sous `<racine>/github`, table des dossiers, `messages` messages en
    attente et `etats` états d'autres PC avec note ; rend son dossier."""
    dossier = racine / "github" / "bench"
    (dossier / ".git").mkdir(parents=True)
    (dossier / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    table = {"schema": 1, "dossiers": {"bench": "bench"}}
    (racine / "table-dossiers.json").write_text(json.dumps(table), encoding="utf-8")
    installation = racine / "installation"  # règle du marqueur lue par SessionStart (story 2.5)
    installation.mkdir()
    shutil.copyfile(DEPOT / "regle-marqueur.md", installation / "regle-marqueur.md")
    (installation / "lancer.py").write_text(LANCEUR_FACTICE, encoding="utf-8")
    deposer_messages(racine, messages)
    deposer_operations_autres(racine, operations)
    deposer_etats(racine, etats)
    deposer_depots(racine, depots)
    return dossier


def pythonw_de(python: str) -> str:
    """`pythonw` voisin de l'interpréteur des hooks (Windows), sinon l'interpréteur lui-même."""
    voisin = Path(python).with_name("pythonw.exe")
    return str(voisin) if voisin.is_file() else python


def attendre_lancements(racine: Path, attendus: int) -> int:
    """Attend que les synchros factices lancées se soient signalées ; rend leur nombre."""
    dossier = racine / "lancements"
    limite = time.monotonic() + DELAI_LANCEMENTS_S
    while True:
        vus = len(list(dossier.iterdir())) if dossier.exists() else 0
        if vus >= attendus or time.monotonic() > limite:
            time.sleep(0.5)  # le dernier enfant quitte son dossier courant
            return vus
        time.sleep(0.1)


def mesurer(
    python: str, hook: str, sessions: list[str], racine: Path, dossier: Path, messages: int = 0,
    etats: int = 0, depots: int = 0,
) -> list[float]:
    """Durées (ms) d'un lancement du hook par session (`session_end` clôt celles du début)."""
    evenement, champs = HOOKS[hook]
    env = {
        **os.environ, "PILOTAGE_RACINE_LOCALE": str(racine), "PILOTAGE_PYTHONW": pythonw_de(python)
    }
    env.setdefault("COMPUTERNAME", "bench")
    chemin = DEPOT / "pilotage" / "hooks" / f"{hook}.py"
    durees: list[float] = []
    remis = ids_messages(min(messages, 3)) if hook == "session_start" else []
    avec_note = hook == "session_start" and etats > 0
    avec_depot = hook == "session_start" and depots > 0
    boite = racine / "attente" / "boite"
    for session in sessions:
        shutil.rmtree(boite, ignore_errors=True)  # hors mesure : les messages restent en attente
        payload = {
            "session_id": session, "cwd": str(dossier), "hook_event_name": evenement,
            **champs,
        }
        donnees = json.dumps(payload).encode("utf-8")
        debut = time.perf_counter()
        resultat = subprocess.run(
            [python, "-I", "-S", str(chemin)], input=donnees, capture_output=True, env=env
        )
        durees.append((time.perf_counter() - debut) * 1000)
        # SessionStart émet du JSON (règle, note, messages), PreCompact sa consigne en texte brut
        # (story 8.2) ; tout autre hook reste muet.
        attendu = hook in ("session_start", "pre_compact")
        if resultat.returncode != 0 or bool(resultat.stdout) != attendu:
            raise RuntimeError(f"{hook} : code {resultat.returncode} ou sortie parasite")
        if hook == "pre_compact" and resultat.stdout.lstrip().startswith(b"{"):
            raise RuntimeError(f"{hook} : JSON sur stdout, consigne en texte brut attendue")
        if hook == "session_start" and not resultat.stdout.startswith(b"{"):
            raise RuntimeError(f"{hook} : JSON attendu sur stdout")
        acquittes = sorted(p.name.split(".")[0] for p in boite.glob("bench/*.lu.*"))
        # Délimiteurs de début en tête de ligne (fin de ligne échappée dans le JSON), hors
        # préambule.
        debuts = resultat.stdout.count(rb"\n<<<PILOTAGE-MESSAGE-DEBUT id=")
        note = "## Dernière note de reprise".encode() in resultat.stdout
        # Plafond de 10 000 unités (story 8.1) : règle, note et état du dépôt (8.3) passent avant
        # les messages ; ceux qui ne tiennent plus restent en attente, non acquittés (le hook les
        # lit et les cadre quand même). Les remis sont les plus anciens, au moins un.
        if (
            acquittes != remis[: len(acquittes)]
            or (remis and not acquittes)
            or debuts != len(acquittes) + avec_note + avec_depot
        ):
            raise RuntimeError(f"{hook} : messages non remis ou non acquittés")
        if note != avec_note:
            raise RuntimeError(f"{hook} : note de reprise absente ou inattendue")
        if ("## État du dépôt".encode() in resultat.stdout) != avec_depot:
            raise RuntimeError(f"{hook} : état du dépôt absent ou inattendu")
    return durees


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Interpréteur de base : le `python.exe` d'un venv Windows est un lanceur (processus en plus).
    defaut = getattr(sys, "_base_executable", None) or sys.executable
    parser.add_argument("--python", default=defaut, help="interpréteur des hooks")
    parser.add_argument("--appels", type=int, default=50)
    parser.add_argument(
        "--messages", type=int, default=MESSAGES_PAR_DEFAUT,
        help="messages en attente remis à chaque SessionStart (3 au plus remis)",
    )
    parser.add_argument(
        "--operations-autres", type=int, default=0,
        help="opérations deposer_message d'un autre projet en attente (écartées par le hook)",
    )
    parser.add_argument(
        "--etats", type=int, default=ETATS_PAR_DEFAUT,
        help="états d'autres PC avec note de reprise (SessionStart injecte la plus récente)",
    )
    parser.add_argument(
        "--depots", type=int, default=DEPOTS_PAR_DEFAUT,
        help="états de dépôt d'autres PC (SessionStart injecte le plus récent)",
    )
    args = parser.parse_args(argv)
    if args.appels < 2:
        parser.error("--appels : au moins 2 (le premier appel est écarté)")
    if args.messages < 0:
        parser.error("--messages : 0 ou plus")
    if not 0 <= args.etats <= 24 * 28:
        parser.error(f"--etats : de 0 à {24 * 28}")
    if not 0 <= args.depots <= 100:
        parser.error("--depots : de 0 à 100")
    if not 0 <= args.operations_autres < 3600:
        parser.error("--operations-autres : de 0 à 3599")
    depasse = False
    temporaires = tempfile.TemporaryDirectory(prefix="bench-hooks-", ignore_cleanup_errors=True)
    with temporaires as temporaire:
        racine = Path(temporaire)
        dossier = preparer(
            racine, args.messages, args.operations_autres, args.etats, args.depots
        )
        sessions = [str(uuid.uuid4()) for _ in range(args.appels)]
        for hook in HOOKS:
            chaud = mesurer(
                args.python, hook, sessions, racine, dossier, args.messages, args.etats,
                args.depots,
            )[1:]
            p50, p95 = centile(chaud, 50), centile(chaud, 95)
            depasse |= p95 > BUDGET_P95_MS
            print(f"{hook} : p50 {p50:.1f} ms, p95 {p95:.1f} ms ({len(chaud)} appels à chaud)")
        lancements = attendre_lancements(racine, 2 * len(sessions))
        if lancements != 2 * len(sessions):
            print(f"synchros lancées : {lancements} sur {2 * len(sessions)} attendues")
            return 1
        journal = racine / "attente" / "journal"
        # « SyncSansBreakaway » n'est pas une erreur : le job parent (runner de CI) refuse le
        # breakaway et le nouvel essai sans ce drapeau a réussi.
        erreurs = [
            ligne
            for fichier in (journal.iterdir() if journal.exists() else [])
            for ligne in fichier.read_text(encoding="utf-8").splitlines()
            if ligne.strip() and not ligne.endswith(" SyncSansBreakaway")
        ]
        if erreurs:
            print("erreurs journalisées par les hooks pendant le banc")
            return 1
        # Le hook a bien agi : un état par session, créé puis clos (pas un hook sans effet).
        etats = list((racine / "attente" / "etat").rglob("*.json"))
        finies = [
            e for e in etats if json.loads(e.read_text(encoding="utf-8"))["statut"] == "finie"
        ]
        if len(etats) != len(sessions) or len(finies) != len(sessions):
            print("les hooks n'ont pas créé puis clos un état par session")
            return 1
    if depasse:
        print(f"p95 au-delà de {BUDGET_P95_MS:.0f} ms : AD-1 à revoir")
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
