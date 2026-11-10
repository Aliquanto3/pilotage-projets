"""Outil `outils/extraire_jeu.py` : transcriptions synthétiques sous `tmp_path` seulement."""

import importlib.util
import json
from pathlib import Path

CHEMIN = Path(__file__).resolve().parent.parent / "outils" / "extraire_jeu.py"
_spec = importlib.util.spec_from_file_location("extraire_jeu", CHEMIN)
outil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(outil)


def _u(contenu, **extra):
    return {"type": "user", "message": {"role": "user", "content": contenu}, **extra}


def _a(*textes, **extra):
    blocs = [{"type": "text", "text": t} for t in textes]
    return {"type": "assistant", "message": {"role": "assistant", "content": blocs}, **extra}


def _ecrire(chemin, entrees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    lignes = [json.dumps(e) if isinstance(e, dict) else e for e in entrees]
    chemin.write_text("\n".join(lignes), encoding="utf-8")


def _session(tmp_path, n=1):
    base = tmp_path / "projets"
    _ecrire(base / "p1" / "s1.jsonl", [
        _u("Premier message"),
        _a("Je regarde."),
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Bash"}]}},
        _u([{"type": "tool_result", "content": "ok"}]),
        _a("Quelle option préfères-tu ?"),
        "ligne cassée",
        _u("Option B"),
        _a("Fait."),
        _u("<task-notification>x</task-notification>"),
        _a("Rapport du sous-agent."),
    ])
    return base


def test_fins_de_tour(tmp_path):
    base = _session(tmp_path)
    fins = outil.fins_de_tour(base / "p1" / "s1.jsonl")
    assert fins == [
        ("Quelle option préfères-tu ?", "Premier message"),
        ("Fait.", "Option B"),  # la notification système clôt le tour sans en être le contexte
        ("Rapport du sous-agent.", "Option B"),
    ]


def test_interruption_et_prompt_commencant_par_un_chevron(tmp_path):
    chemin = tmp_path / "p" / "s.jsonl"
    _ecrire(chemin, [
        _u("Lance la migration"),
        _a("Je commence par la table A."),
        _u([{"type": "text", "text": "[Request interrupted by user for tool use]"}]),
        _u("<div> ne s'affiche pas"),
        _a("Corrigé ?"),
        _u("<command-name>/clear</command-name>"),
    ])
    assert outil.fins_de_tour(chemin) == [("Corrigé ?", "<div> ne s'affiche pas")]


def test_depuis_sous_un_dossier_subagents(tmp_path):
    base = tmp_path / "subagents" / "projets"
    _ecrire(base / "p1" / "s1.jsonl", [_u("a"), _a("b")])
    assert outil.transcriptions(base) == [base / "p1" / "s1.jsonl"]


def test_secret_coupe_au_bord_de_la_troncature():
    assert outil.construire_cas("gh" + "p_" + "x" * 1999 + " Fin ?", "ok") is None
    assert outil.construire_cas("y" * 3000 + " sk-" + "a" * 10, "ok") is None


def test_sidechain_et_sous_agents_ignores(tmp_path):
    base = tmp_path / "projets"
    _ecrire(base / "p1" / "s1.jsonl", [_u("Salut"), _a("Réponse.", isSidechain=True)])
    _ecrire(base / "p1" / "s1" / "subagents" / "x.jsonl", [_u("a"), _a("b")])
    _ecrire(base / "p1" / "s2" / "subagents" / "y.jsonl", [_u("a"), _a("b")])
    assert outil.fins_de_tour(base / "p1" / "s1.jsonl") == []
    assert outil.transcriptions(base) == [base / "p1" / "s1.jsonl"]


def test_cas_filtre_les_secrets_et_tronque(tmp_path):
    cas = outil.construire_cas("x" * 5000 + "Fin ?", "y" * 900)
    assert cas["payload"]["hook_event_name"] == "Stop"
    assert cas["payload"]["last_assistant_message"] == ("x" * 5000 + "Fin ?")[-2000:]
    assert cas["contexte"] == "y" * 600
    assert cas["attente"] is None
    assert outil.construire_cas("clé sk-abcdef123 ?", "ok") is None
    avec_secret = outil.construire_cas("Bien ?", "mon ghp_secret")
    assert avec_secret["contexte"] == ""


def test_extraction_ecrit_sous_racine_locale(tmp_path, racine_locale_isolee, capsys):
    base = _session(tmp_path)
    assert outil.main(["--depuis", str(base)]) == 0
    dossier = racine_locale_isolee / "jeu-etiquete"
    lignes = (dossier / "a-etiqueter.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["payload"]["last_assistant_message"] for x in lignes] == [
        "Quelle option préfères-tu ?", "Fait.", "Rapport du sous-agent."]
    assert json.loads(lignes[0])["contexte"] == "Premier message"
    assert "true" in (dossier / "LISEZMOI.txt").read_text(encoding="utf-8")
    assert "3 fin(s) de tour" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.rglob("*.jsonl") if "projets" not in p.parts) == [
        "a-etiqueter.jsonl"]


def test_echantillon_borne_et_deterministe(tmp_path):
    base = tmp_path / "projets"
    entrees = []
    for i in range(30):
        entrees += [_u(f"q{i}"), _a(f"r{i}")]
    _ecrire(base / "p1" / "s1.jsonl", entrees)
    a = outil.extraire(base, 5, 7)
    b = outil.extraire(base, 5, 7)
    c = outil.extraire(base, 5, 8)
    assert len(a) == 5
    assert a == b
    assert a != c
    numeros = [int(x["payload"]["last_assistant_message"][1:]) for x in a]
    assert numeros == sorted(numeros)


def test_refuse_de_reecraser_sans_force(tmp_path, racine_locale_isolee, capsys):
    base = _session(tmp_path)
    jeu = racine_locale_isolee / "jeu-etiquete" / "a-etiqueter.jsonl"
    jeu.parent.mkdir(parents=True)
    jeu.write_text("etiquettes\n", encoding="utf-8")
    assert outil.main(["--depuis", str(base)]) == 1
    assert "--force" in capsys.readouterr().out
    assert jeu.read_text(encoding="utf-8") == "etiquettes\n"
    assert outil.main(["--depuis", str(base), "--force"]) == 0
    assert jeu.read_text(encoding="utf-8") != "etiquettes\n"
    copies = list(jeu.parent.glob("a-etiqueter.*.jsonl"))
    assert [c.read_text(encoding="utf-8") for c in copies] == ["etiquettes\n"]


def test_refuse_sortie_sous_racine_github(tmp_path, monkeypatch, capsys):
    github = tmp_path / "gh"
    github.mkdir()
    (tmp_path / "config.json").write_text(
        json.dumps({"racine_github": str(github), "racine_locale": str(github / "x")}),
        encoding="utf-8")
    monkeypatch.delenv("PILOTAGE_RACINE_LOCALE")
    monkeypatch.setattr(outil.chemins, "racine_locale", lambda: github / "x")
    monkeypatch.setattr(outil.chemins, "racine_github", lambda: github)
    assert outil.main(["--depuis", str(_session(tmp_path))]) == 1
    assert "racine GitHub" in capsys.readouterr().out
    assert not (github / "x").exists()


def test_refuse_sortie_dans_un_depot_git(tmp_path, monkeypatch, capsys):
    depot = tmp_path / "depot"
    (depot / ".git").mkdir(parents=True)
    monkeypatch.setattr(outil.chemins, "racine_locale", lambda: depot / "local")
    assert outil.main(["--depuis", str(_session(tmp_path))]) == 1
    assert "dépôt git" in capsys.readouterr().out
    assert not (depot / "local").exists()


def test_dossier_source_absent_et_max_invalide(tmp_path, capsys):
    assert outil.main(["--depuis", str(tmp_path / "absent")]) == 1
    assert "introuvable" in capsys.readouterr().out
    assert outil.main(["--depuis", str(tmp_path), "--max", "0"]) == 1


def test_jeu_produit_compatible_avec_l_evaluation(tmp_path, racine_locale_isolee, capsys):
    spec = importlib.util.spec_from_file_location(
        "evaluer_heuristique", CHEMIN.with_name("evaluer_heuristique.py"))
    evaluateur = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluateur)
    assert outil.main(["--depuis", str(_session(tmp_path))]) == 0
    jeu = racine_locale_isolee / "jeu-etiquete" / "a-etiqueter.jsonl"
    assert evaluateur.lire_jeu_complet(jeu) == ([], 3)
