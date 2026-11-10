"""Story 2.7 : fusion ciblée de `settings.json` (AD-7). Aucun test ne vise le vrai profil."""

import ast
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

import lancer
from pilotage import chemins
from pilotage.installation import cli, fusion
from tests.test_imports import RACINE_DEPOT

RACINE = "C:/Users/Moi/.claude/pilotage"
PYTHON = "C:/Users/Moi/.claude/pilotage/.venv/Scripts/python.exe"
ANTISLASH = "C:\\Users\\Moi\\.claude\\pilotage"
PY_REEL = Path(sys.executable).as_posix()  # interpréteur existant : `installer` le contrôle
HEURE = datetime(2026, 11, 6, 9, 5, 7)


def _modele() -> dict:
    return json.loads((RACINE_DEPOT / "hooks-pilotage.json").read_text(encoding="utf-8"))


def _entree(script: str, python: str = PYTHON) -> dict:
    return {"type": "command", "command": python, "args": ["-I", "-S", script]}


def _tiers(commande: str) -> dict:
    return {"type": "command", "command": commande}


def _settings_realiste() -> dict:
    """Autres clés, hooks tiers avec et sans matcher, anciennes entrées du pilotage."""
    return {
        "model": "opus",
        "permissions": {"allow": ["Bash(git status)"], "deny": []},
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [_tiers("controle.sh")]}],
            "Stop": [
                {"hooks": [_tiers("notifier.exe")]},
                {
                    "matcher": "",
                    "hooks": [_entree(ANTISLASH + "\\pilotage\\hooks\\stop.py")],
                },
            ],
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [
                        _tiers("bonjour.sh"),
                        _entree("c:/USERS/moi/.CLAUDE/Pilotage/pilotage/hooks/session_start.py"),
                    ],
                }
            ],
            "SubagentStop": [{"hooks": [_entree(RACINE + "/pilotage/hooks/stop.py")]}],
        },
        "statusLine": {"type": "command", "command": "ligne.sh"},
        "théme": "sombre é",
    }


def _ecrire(chemin: Path, objet: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(fusion.serialiser(objet))


def _installer(cible: Path, **kw):
    return fusion.installer(cible, PY_REEL, RACINE, maintenant=lambda: HEURE, **kw)


# --- Modèle `hooks-pilotage.json` -------------------------------------------------------------


def _evenements_des_hooks() -> dict[str, str]:
    """`EVENEMENT` déclaré par chaque point d'entrée de `pilotage/hooks/` → nom du fichier."""
    trouves = {}
    for fichier in sorted((RACINE_DEPOT / "pilotage" / "hooks").glob("*.py")):
        for noeud in ast.parse(fichier.read_text(encoding="utf-8")).body:
            if isinstance(noeud, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == "EVENEMENT" for c in noeud.targets
            ):
                trouves[ast.literal_eval(noeud.value)] = fichier.name
    return trouves


def test_modele_une_entree_exec_par_evenement_des_hooks():
    modele = _modele()
    fusion.controler_modele(modele)
    declares = _evenements_des_hooks()
    assert set(modele["hooks"]) == set(declares) == set(fusion.EVENEMENTS)
    for evenement, groupes in modele["hooks"].items():
        assert groupes == [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "{{PYTHON_PILOTAGE}}",
                        "args": [
                            "-I", "-S", "{{RACINE_PILOTAGE}}/pilotage/hooks/" + declares[evenement]
                        ],
                    }
                ]
            }
        ]
    assert "SubagentStart" not in modele["hooks"] and "SubagentStop" not in modele["hooks"]


def test_modele_octets_canoniques():
    octets = (RACINE_DEPOT / "hooks-pilotage.json").read_bytes()
    assert octets == fusion.serialiser(_modele())


@pytest.mark.parametrize(
    "alteration",
    [
        lambda m: m["hooks"].pop("Notification"),
        lambda m: m["hooks"].__setitem__("SubagentStop", m["hooks"]["Stop"]),
        lambda m: m["hooks"]["Stop"][0].__setitem__("matcher", ""),
        lambda m: m["hooks"]["Stop"].append(m["hooks"]["Stop"][0]),
        lambda m: m["hooks"]["Stop"][0]["hooks"][0].__setitem__("command", "bash"),
        lambda m: m["hooks"]["Stop"][0]["hooks"][0]["args"].pop(0),
    ],
    ids=["evenement-absent", "subagent", "matcher", "doublon", "pas-exec", "sans-I"],
)
def test_modele_altere_refuse(alteration):
    modele = _modele()
    alteration(modele)
    with pytest.raises(fusion.ErreurInstallation, match="modèle"):
        fusion.controler_modele(modele)


# --- Marque d'appartenance --------------------------------------------------------------------


@pytest.mark.parametrize(
    "script",
    [
        RACINE + "/pilotage/hooks/stop.py",
        "C:\\Users\\Moi\\.claude\\pilotage\\pilotage\\hooks\\stop.py",
        "c:/users/MOI/.Claude/PILOTAGE/Pilotage/Hooks/Stop.py",
        "C:\\USERS\\moi\\.claude/pilotage\\pilotage/hooks\\stop.py",
    ],
    ids=["slash", "antislash", "casse", "mixte"],
)
def test_marque_reconnue_par_graphie(script):
    assert fusion.est_du_pilotage(_entree(script), RACINE)
    assert fusion.est_du_pilotage(_entree(script), RACINE + "/")
    assert fusion.est_du_pilotage(_entree(script), RACINE.replace("/", "\\") + "\\")


@pytest.mark.parametrize(
    "entree",
    [
        _tiers("C:/outils/python.exe -I -S C:/outils/stop.py " + RACINE + "-dev/pilotage/hooks"),
        _entree(RACINE + "/pilotage/autre/stop.py"),
        _entree(RACINE + "-dev/pilotage/hooks/stop.py"),
        _entree("D:/ailleurs/pilotage/hooks/stop.py"),
        {"type": "command", "command": PYTHON, "args": ["-I", "-S"]},
        {"type": "command", "command": PYTHON, "args": "pas une liste"},
        "pas un objet",
        _tiers(f"mon-outil --log {RACINE}/pilotage/hooks/journal.txt"),
        _tiers(f"node {RACINE}/pilotage/hooks/stop.py"),
        _tiers(f"{PYTHON} -I outil.py {RACINE}/pilotage/hooks/stop.py"),
        _tiers(f"{PYTHON} {RACINE}/pilotage/hooks/notes.txt"),
        _tiers("python pilotage/hooks/stop.py"),
        _entree("pilotage/hooks/stop.py"),
    ],
    ids=["shell-tiers", "hors-hooks", "racine-voisine", "autre-racine", "que-options",
         "args-chaine", "non-objet", "outil-tiers-argument", "interprete-non-python",
         "script-tiers-puis-chemin", "non-py", "shell-relatif", "exec-relatif"],
)
def test_marque_absente(entree):
    assert not fusion.est_du_pilotage(entree, RACINE)


def test_marque_relative_jamais_resolue_contre_le_dossier_courant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not fusion.est_du_pilotage(_entree("pilotage/hooks/stop.py"), str(tmp_path))
    assert not fusion.est_du_pilotage(_tiers("python pilotage/hooks/stop.py"), str(tmp_path))


@pytest.mark.parametrize(
    "commande",
    [
        f"{PYTHON} -I -S {RACINE}/pilotage/hooks/stop.py",
        f'"{PYTHON}" -I -S "{ANTISLASH}\\pilotage\\hooks\\stop.py"',
        f"{RACINE}/pilotage/hooks/stop.py",
    ],
    ids=["shell", "shell-guillemets", "script-seul"],
)
def test_marque_ancienne_forme_shell_reconnue(commande):
    assert fusion.est_du_pilotage(_tiers(commande), RACINE)


def test_marque_resout_points_et_doubles_barres():
    assert not fusion.est_du_pilotage(_entree(RACINE + "/pilotage/hooks/../../tiers.py"), RACINE)
    assert fusion.est_du_pilotage(_entree("C://Users//Moi/.claude/pilotage/pilotage/hooks/stop.py"),
                                  RACINE)
    assert fusion.est_du_pilotage(_entree(RACINE + "/pilotage/x/../hooks/stop.py"), RACINE)


def _nom_court(chemin: Path) -> str:
    import ctypes

    tampon = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(chemin), tampon, 1024):
        return str(chemin)
    return tampon.value


@pytest.mark.skipif(os.name != "nt", reason="noms courts 8.3 : Windows seulement")
def test_marque_reconnue_en_nom_court(tmp_path):
    racine = tmp_path / "Racine Longue Du Pilotage"
    (racine / "pilotage" / "hooks").mkdir(parents=True)
    (racine / "pilotage" / "hooks" / "stop.py").write_bytes(b"")
    court = _nom_court(racine / "pilotage" / "hooks" / "stop.py")
    if "~" not in court:
        pytest.skip("noms courts 8.3 désactivés sur ce volume")
    assert fusion.est_du_pilotage(_entree(court), str(racine))
    assert fusion.est_du_pilotage(_entree(str(racine / "pilotage/hooks/stop.py")),
                                  _nom_court(racine))


def test_fusion_retire_l_ancienne_forme_shell_sans_doublon():
    settings = {"hooks": {"Stop": [{"hooks": [
        _tiers(f"{PYTHON} -I -S {RACINE}/pilotage/hooks/stop.py")]}]}}
    stop = fusion.fusionner(settings, _modele(), PYTHON, RACINE)["hooks"]["Stop"]
    assert stop == [{"hooks": [_entree(RACINE + "/pilotage/hooks/stop.py")]}]


def test_fusion_chemin_a_espaces_garde_en_un_seul_args():
    """Forme exec, sans shell (AD-1, capture 2.1) : un espace n'a pas à être quoté."""
    racine = "C:/Users/Jean Dupont/.claude/pilotage"
    stop = fusion.fusionner(None, _modele(), racine + "/.venv/Scripts/python.exe", racine)
    entree = stop["hooks"]["Stop"][0]["hooks"][0]
    assert entree["command"] == racine + "/.venv/Scripts/python.exe"
    assert entree["args"] == ["-I", "-S", racine + "/pilotage/hooks/stop.py"]
    assert fusion.est_du_pilotage(entree, racine)


# --- Fusion -----------------------------------------------------------------------------------


def test_fusion_retire_ajoute_et_conserve_le_reste():
    resultat = fusion.fusionner(_settings_realiste(), _modele(), PYTHON, RACINE)
    assert list(resultat) == ["model", "permissions", "hooks", "statusLine", "théme"]
    assert resultat["permissions"] == {"allow": ["Bash(git status)"], "deny": []}
    hooks = resultat["hooks"]
    # SubagentStop ne portait que du pilotage : retiré ; les nouveaux événements à la fin.
    assert list(hooks) == ["PreToolUse", "Stop", "SessionStart", "UserPromptSubmit",
                           "Notification", "SessionEnd"]
    assert hooks["PreToolUse"] == [{"matcher": "Bash", "hooks": [_tiers("controle.sh")]}]
    assert hooks["Stop"] == [
        {"hooks": [_tiers("notifier.exe")]},
        {"hooks": [_entree(RACINE + "/pilotage/hooks/stop.py")]},
    ]
    assert hooks["SessionStart"] == [
        {"matcher": "startup", "hooks": [_tiers("bonjour.sh")]},
        {"hooks": [_entree(RACINE + "/pilotage/hooks/session_start.py")]},
    ]
    notification = _entree(RACINE + "/pilotage/hooks/notification.py")
    assert hooks["Notification"] == [{"hooks": [notification]}]


def test_fusion_ne_modifie_pas_l_entree():
    settings = _settings_realiste()
    fusion.fusionner(settings, _modele(), PYTHON, RACINE)
    assert settings == _settings_realiste()


def test_fusion_garde_groupe_vide_d_origine():
    settings = {"hooks": {"PreCompact": [], "Stop": [{"matcher": "x", "hooks": []}]}}
    hooks = fusion.fusionner(settings, _modele(), PYTHON, RACINE)["hooks"]
    assert hooks["PreCompact"] == []
    assert hooks["Stop"][0] == {"matcher": "x", "hooks": []}


def test_fusion_chemins_antislash_ecrits_en_slash():
    racine = "C:\\Users\\Moi\\.claude\\pilotage\\"
    python = "C:\\Users\\Moi\\.claude\\pilotage\\.venv\\Scripts\\python.exe"
    hooks = fusion.fusionner(None, _modele(), python, racine)["hooks"]
    assert hooks["Stop"] == [{"hooks": [_entree(RACINE + "/pilotage/hooks/stop.py")]}]


@pytest.mark.parametrize(
    ("python", "racine"),
    [
        (PYTHON, 'C:/a"b'),
        (PYTHON, "C:/a\nb"),
        ('C:/py"thon.exe', RACINE),
        ("C:/python\r.exe", RACINE),
        (PYTHON, "C:/{{RACINE_PILOTAGE}}"),
        (PYTHON, ""),
        ("python.exe", RACINE),
        (PYTHON, "relatif/pilotage"),
    ],
    ids=["guillemet", "saut-ligne", "python-guillemet", "python-cr", "jeton", "vide",
         "python-relatif", "racine-relative"],
)
def test_chemin_refuse(python, racine):
    with pytest.raises(fusion.ErreurInstallation, match="refusé"):
        fusion.fusionner({}, _modele(), python, racine)


def test_jeton_inconnu_non_substitue_refuse():
    modele = _modele()
    modele["hooks"]["Stop"][0]["hooks"][0]["timeout"] = "{{INCONNU}}"
    with pytest.raises(fusion.ErreurInstallation, match="jeton non substitué"):
        fusion.fusionner({}, modele, PYTHON, RACINE)


@pytest.mark.parametrize(
    "settings",
    [
        {"hooks": []},
        {"hooks": {"Stop": {"hooks": []}}},
        {"hooks": {"Stop": ["texte"]}},
        {"hooks": {"Stop": [{"matcher": "x"}]}},
    ],
    ids=["hooks-liste", "evenement-objet", "groupe-texte", "groupe-sans-hooks"],
)
def test_hooks_mal_formes_refuses(settings):
    with pytest.raises(fusion.ErreurInstallation):
        fusion.fusionner(settings, _modele(), PYTHON, RACINE)


# --- Installation sur fichier -----------------------------------------------------------------


def test_absent_cree_avec_les_seuls_hooks(tmp_path):
    cible = tmp_path / "claude" / "settings.json"
    assert _installer(cible) == (True, None)
    attendu = fusion.fusionner(None, _modele(), PY_REEL, RACINE)
    assert list(attendu) == ["hooks"]
    assert cible.read_bytes() == fusion.serialiser(attendu)
    assert list(cible.parent.iterdir()) == [cible]


def test_idempotence_a_l_octet_et_copie(tmp_path):
    cible = tmp_path / "settings.json"
    origine = json.dumps(_settings_realiste(), indent=4).encode("utf-8")  # autre format
    cible.write_bytes(origine)
    ecrit, copie = _installer(cible)
    assert ecrit
    assert copie == tmp_path / "settings.json.avant-pilotage-20261106-090507"
    assert copie.read_bytes() == origine
    premier = cible.read_bytes()
    assert not premier.startswith(fusion.BOM) and b"\r\n" not in premier
    assert "théme".encode() in premier and premier.endswith(b"}\n")
    assert _installer(cible) == (False, None)
    assert cible.read_bytes() == premier
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "settings.json", "settings.json.avant-pilotage-20261106-090507"]


def test_copie_existante_jamais_ecrasee(tmp_path):
    cible = tmp_path / "settings.json"
    _ecrire(cible, {"model": "opus"})
    ancienne = tmp_path / "settings.json.avant-pilotage-20261106-090507"
    ancienne.write_bytes(b"ancienne copie")
    ecrit, copie = _installer(cible)
    assert ecrit and copie == tmp_path / "settings.json.avant-pilotage-20261106-090507-2"
    assert ancienne.read_bytes() == b"ancienne copie"
    assert copie.read_bytes() == fusion.serialiser({"model": "opus"})


@pytest.mark.parametrize(
    ("octets", "message"),
    [
        (b'{"model": "opus",}', "JSON invalide"),
        (b"", "JSON invalide"),
        (fusion.BOM + b'{"model": "opus"}', "BOM"),
        ('{"model": "é"}'.encode("cp1252"), "non UTF-8"),
        ('{"m": "x"}'.encode("utf-16"), "BOM|non UTF-8"),
        (b'["liste"]', "objet JSON"),
        (b'{"model": "a", "model": "b"}', "en double"),
        (b'{"hooks": "texte"}', "'hooks' doit"),
    ],
    ids=["json", "vide", "bom", "cp1252", "utf16", "racine-liste", "cle-double", "hooks-texte"],
)
def test_illisible_jamais_ecrase(tmp_path, octets, message):
    cible = tmp_path / "settings.json"
    cible.write_bytes(octets)
    with pytest.raises(fusion.ErreurInstallation, match=message):
        _installer(cible)
    assert cible.read_bytes() == octets
    assert list(tmp_path.iterdir()) == [cible]


@pytest.mark.parametrize(
    "octets",
    [b'{"seuil": 1e400}', b'{"seuil": NaN}', b'{"nom": "\\ud800"}'],
    ids=["infini", "nan", "surrogate"],
)
def test_valeur_non_json_refusee_sans_ecrire(tmp_path, octets):
    cible = tmp_path / "settings.json"
    cible.write_bytes(octets)
    with pytest.raises(fusion.ErreurInstallation, match="non représentable"):
        _installer(cible)
    assert cible.read_bytes() == octets
    assert list(tmp_path.iterdir()) == [cible]


def test_python_absent_refuse_sans_ecrire(tmp_path):
    cible = tmp_path / "settings.json"
    _ecrire(cible, {"model": "opus"})
    avant = cible.read_bytes()
    with pytest.raises(fusion.ErreurInstallation, match="python introuvable"):
        fusion.installer(cible, (tmp_path / "absent" / "python.exe").as_posix(), RACINE)
    assert cible.read_bytes() == avant
    assert list(tmp_path.iterdir()) == [cible]


def test_lien_symbolique_suivi(tmp_path):
    reel = tmp_path / "dotfiles" / "settings.json"
    _ecrire(reel, {"model": "opus"})
    lien = tmp_path / "claude" / "settings.json"
    lien.parent.mkdir()
    try:
        lien.symlink_to(reel)
    except OSError:
        pytest.skip("création de lien symbolique non permise")
    ecrit, copie = _installer(lien)
    assert ecrit and copie.parent == reel.parent
    assert lien.is_symlink()
    assert "hooks" in json.loads(reel.read_text(encoding="utf-8"))
    assert list(lien.parent.iterdir()) == [lien]


# --- Commande ---------------------------------------------------------------------------------


def test_cible_par_defaut_sous_la_racine_de_test(racine_locale_isolee, tmp_path):
    cible = fusion.settings_par_defaut()
    assert cible == racine_locale_isolee / "claude" / "settings.json"
    assert cible.is_relative_to(tmp_path)
    assert chemins.racine_installation().is_relative_to(tmp_path)


def test_cible_sans_surcharge_dans_le_profil(monkeypatch, tmp_path):
    monkeypatch.delenv(chemins.VARIABLE_RACINE)
    assert fusion.settings_par_defaut() == Path.home() / ".claude" / "settings.json"
    assert fusion.settings_par_defaut().is_relative_to(tmp_path)


def test_commande_par_defaut_python_absent_rend_1(racine_locale_isolee, capsys):
    assert lancer.main(["installer-reglages"]) == 1
    assert "python introuvable" in capsys.readouterr().err
    assert not (racine_locale_isolee / "claude" / "settings.json").exists()


def test_commande_par_defaut(racine_locale_isolee, capsys):
    interpreteur = fusion.python_par_defaut(chemins.racine_installation())
    interpreteur.parent.mkdir(parents=True)
    interpreteur.write_bytes(b"")
    assert lancer.main(["installer-reglages"]) == 0
    cible = racine_locale_isolee / "claude" / "settings.json"
    assert capsys.readouterr().out == f"{cible} : créé\n"
    racine = chemins.racine_installation()
    stop = json.loads(cible.read_text(encoding="utf-8"))["hooks"]["Stop"][0]["hooks"][0]
    assert stop["command"] == fusion.python_par_defaut(racine).as_posix()
    assert stop["args"] == ["-I", "-S", racine.as_posix() + "/pilotage/hooks/stop.py"]
    assert lancer.main(["installer-reglages"]) == 0
    assert capsys.readouterr().out == f"{cible} : déjà à jour\n"


def test_commande_options_et_mise_a_jour(tmp_path, capsys):
    cible = tmp_path / "s.json"
    _ecrire(cible, _settings_realiste())
    code = cli.main(["--settings", str(cible), "--racine", RACINE, "--python", PY_REEL])
    assert code == 0
    sortie = capsys.readouterr().out
    assert sortie.startswith(f"{cible} : mis à jour (copie : s.json.avant-pilotage-")
    assert json.loads(cible.read_text(encoding="utf-8")) == fusion.fusionner(
        _settings_realiste(), _modele(), PY_REEL, RACINE)


def test_commande_fichier_illisible_rend_1(tmp_path, capsys):
    cible = tmp_path / "settings.json"
    cible.write_bytes(b"{pas du json")
    assert cli.main(["--settings", str(cible), "--racine", RACINE, "--python", PY_REEL]) == 1
    sortie = capsys.readouterr()
    assert sortie.out == ""
    assert sortie.err.startswith("lancer.py installer-reglages : ")
    assert "JSON invalide" in sortie.err and sortie.err.endswith("rien n'a été écrit\n")
    assert cible.read_bytes() == b"{pas du json"


def test_commande_chemin_refuse_rend_1(tmp_path, capsys):
    cible = tmp_path / "settings.json"
    assert cli.main(["--settings", str(cible), "--racine", 'C:/a"b', "--python", PY_REEL]) == 1
    assert "racine refusé" in capsys.readouterr().err
    assert not cible.exists()


def test_commande_option_inconnue_rend_2(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--option", "x"])
    assert exc.value.code == 2
    assert "usage: lancer.py installer-reglages" in capsys.readouterr().err


@pytest.mark.parametrize(
    "commande",
    [
        f'"{PYTHON}" -X utf8 -W ignore -I "{RACINE}/pilotage/hooks/stop.py"',
        f'py -3.14 "{ANTISLASH}\\pilotage\\hooks\\stop.py"',
        f"python3.14t {RACINE}/pilotage/hooks/stop.py",
    ],
    ids=["options-a-argument", "lanceur-py", "free-threaded"],
)
def test_marque_forme_shell_options_reconnue(commande):
    assert fusion.est_du_pilotage(_tiers(commande), RACINE)


@pytest.mark.parametrize(
    "commande",
    [
        f'"{PYTHON}" "{RACINE}/pilotage/hooks/stop.py" && mon-outil',
        f'"{RACINE}/pilotage/hooks/stop.py" | tee journal.txt',
    ],
    ids=["interprete-chaine", "script-seul-chaine"],
)
def test_marque_commande_chainee_reste_tierce(commande):
    assert not fusion.est_du_pilotage(_tiers(commande), RACINE)


# --- Story 2.8 : `sauver`, `restaurer` et `config.json` -----------------------------------------


def test_sans_pilotage_retire_tout_et_n_ajoute_rien():
    resultat = fusion.sans_pilotage(_settings_realiste(), RACINE)
    assert resultat["hooks"] == {
        "PreToolUse": [{"matcher": "Bash", "hooks": [_tiers("controle.sh")]}],
        "Stop": [{"hooks": [_tiers("notifier.exe")]}],
        "SessionStart": [{"matcher": "startup", "hooks": [_tiers("bonjour.sh")]}],
    }
    assert list(resultat) == list(_settings_realiste())
    assert resultat["théme"] == "sombre é"
    assert "pilotage/hooks" not in json.dumps(resultat).replace("\\\\", "/").casefold()


def test_sans_pilotage_sans_cle_hooks_reste_sans():
    assert fusion.sans_pilotage({"model": "opus"}, RACINE) == {"model": "opus"}


def test_sans_pilotage_apres_fusion_rend_l_original():
    base = {"model": "opus", "hooks": {"PreToolUse": [{"hooks": [_tiers("a.sh")]}]}}
    fusionne = fusion.fusionner(base, _modele(), PYTHON, RACINE)
    assert fusion.sans_pilotage(fusionne, RACINE) == base


def test_commande_exporter_sans_pilotage(tmp_path, capsys):
    cible = tmp_path / "settings.json"
    _ecrire(cible, _settings_realiste())
    avant = cible.read_bytes()
    sortie = tmp_path / "export.json"
    code = cli.main(["--settings", str(cible), "--racine", ANTISLASH,
                     "--exporter-sans-pilotage", str(sortie)])
    assert code == 0
    assert capsys.readouterr().out == f"{sortie} : réglages sans le pilotage\n"
    assert cible.read_bytes() == avant
    attendu = fusion.serialiser(fusion.sans_pilotage(_settings_realiste(), RACINE))
    assert sortie.read_bytes() == attendu
    assert sorted(tmp_path.iterdir()) == sorted([sortie, cible])


def test_commande_exporter_settings_absent_rend_1(tmp_path, capsys):
    sortie = tmp_path / "export.json"
    code = cli.main(["--settings", str(tmp_path / "absent.json"), "--racine", RACINE,
                     "--exporter-sans-pilotage", str(sortie)])
    assert code == 1
    assert "absent" in capsys.readouterr().err
    assert not sortie.exists()


def test_installer_depuis_ecrit_la_cible_seulement(tmp_path):
    depot = tmp_path / "depot.json"
    _ecrire(depot, {"model": "opus", "hooks": {"Stop": [{"hooks": [_tiers("n.exe")]}]}})
    avant_depot = depot.read_bytes()
    cible = tmp_path / "settings.json"
    _ecrire(cible, {"model": "ancien"})
    ecrit, copie = _installer(cible, depuis=depot)
    assert ecrit and copie.name == "settings.json.avant-pilotage-20261106-090507"
    assert copie.read_bytes() == fusion.serialiser({"model": "ancien"})
    resultat = json.loads(cible.read_text(encoding="utf-8"))
    assert resultat["model"] == "opus"
    assert resultat["hooks"]["Stop"][0] == {"hooks": [_tiers("n.exe")]}
    assert depot.read_bytes() == avant_depot
    # deuxième passage : mêmes octets, rien écrit
    octets = cible.read_bytes()
    assert _installer(cible, depuis=depot) == (False, None)
    assert cible.read_bytes() == octets


def test_installer_depuis_absent_refuse(tmp_path):
    cible = tmp_path / "settings.json"
    with pytest.raises(fusion.ErreurInstallation, match="réglages source absents"):
        _installer(cible, depuis=tmp_path / "absent.json")
    assert not cible.exists()


def test_ecrire_config_garde_les_autres_cles(tmp_path):
    config = tmp_path / "config.json"
    _ecrire(config, {"racine_locale": "D:/locale", "port": 50000, "python": "C:/vieux/python.exe"})
    assert fusion.ecrire_config(config, r"C:\inst\.venv\Scripts\python.exe", r"D:\GitHub")
    assert json.loads(config.read_text(encoding="utf-8")) == {
        "racine_locale": "D:/locale",
        "port": 50000,
        "python": "C:/inst/.venv/Scripts/python.exe",
        "pythonw": "C:/inst/.venv/Scripts/pythonw.exe",
        "racine_github": "D:/GitHub",
    }
    assert not fusion.ecrire_config(config, "C:/inst/.venv/Scripts/python.exe", "D:/GitHub")


def test_ecrire_config_absent_port_par_defaut(tmp_path):
    config = tmp_path / "pilotage" / "config.json"
    assert fusion.ecrire_config(config, "C:/i/.venv/bin/python", "C:/G")
    assert config.read_bytes() == fusion.serialiser({
        "python": "C:/i/.venv/bin/python", "pythonw": "C:/i/.venv/bin/pythonw",
        "racine_github": "C:/G", "port": 47615,
    })


def test_ecrire_config_illisible_jamais_ecrase(tmp_path):
    config = tmp_path / "config.json"
    config.write_bytes(b"{pas du json")
    with pytest.raises(fusion.ErreurInstallation, match="JSON invalide"):
        fusion.ecrire_config(config, "C:/p/python.exe", "C:/G")
    assert config.read_bytes() == b"{pas du json"


def test_commande_restaurer_config_puis_fusion(tmp_path, capsys):
    depot = tmp_path / "depot.json"
    _ecrire(depot, {"model": "opus"})
    cible = tmp_path / "settings.json"
    config = tmp_path / "config.json"
    args = ["--settings", str(cible), "--depuis", str(depot), "--racine", RACINE,
            "--python", PY_REEL, "--config", str(config), "--racine-github", "D:/GitHub"]
    assert cli.main(args) == 0
    assert capsys.readouterr().out == f"{config} : écrit\n{cible} : créé\n"
    assert json.loads(config.read_text(encoding="utf-8"))["python"] == PY_REEL
    octets = cible.read_bytes()
    assert cli.main(args) == 0
    assert capsys.readouterr().out == f"{cible} : déjà à jour\n"
    assert cible.read_bytes() == octets


def test_commande_config_python_absent_rend_1_sans_rien_ecrire(tmp_path, capsys):
    config = tmp_path / "config.json"
    cible = tmp_path / "settings.json"
    code = cli.main(["--settings", str(cible), "--racine", RACINE, "--python",
                     str(tmp_path / "absent.exe"), "--config", str(config),
                     "--racine-github", "D:/G"])
    assert code == 1
    assert "python introuvable" in capsys.readouterr().err
    assert not config.exists() and not cible.exists()


@pytest.mark.parametrize("args", [
    ["--config", "c.json"],
    ["--racine-github", "D:/G"],
    ["--exporter-sans-pilotage", "e.json", "--depuis", "d.json"],
])
def test_commande_options_incompatibles_rend_2(args, capsys):
    with pytest.raises(SystemExit) as sortie:
        cli.main(args)
    assert sortie.value.code == 2


def test_python_par_defaut_lu_dans_config(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(chemins.VARIABLE_RACINE)
    config = chemins.chemin_config()
    assert config.is_relative_to(tmp_path)
    _ecrire(config, {"python": PY_REEL})
    cible = tmp_path / "settings.json"
    assert cli.main(["--settings", str(cible), "--racine", RACINE]) == 0
    stop = json.loads(cible.read_text(encoding="utf-8"))["hooks"]["Stop"][0]["hooks"][0]
    assert stop["command"] == PY_REEL


# --- Revue 2.8 : hook du clone de dev, config.json après la fusion -----------------------------

CLONE_DEV = [
    "C:/Users/Moi/Documents/GitHub/pilotage-projets/pilotage/hooks/stop.py",
    r"C:\Users\Moi\Documents\GitHub\pilotage-projets\Pilotage\Hooks\stop.py",
    r"D:\\dev\\pilotage\\hooks\\stop.py",
]


@pytest.mark.parametrize("script", CLONE_DEV, ids=["slash", "antislash-casse", "double"])
def test_sans_pilotage_retire_le_hook_du_clone_de_dev(script):
    dev = _entree(script, python="C:/dev/.venv/Scripts/python.exe")
    shell = _tiers(f'python "{script}"')
    settings = {"hooks": {"Stop": [{"hooks": [dev, shell, _tiers("notifier.exe")]}],
                          "SessionEnd": [{"hooks": [dev]}]}}
    resultat = fusion.sans_pilotage(settings, RACINE)
    assert resultat == {"hooks": {"Stop": [{"hooks": [_tiers("notifier.exe")]}]}}
    # l'installation garde la règle stricte de 2.7 : un hook d'une autre racine est conservé
    fusionne = fusion.fusionner(settings, _modele(), PYTHON, RACINE)
    assert dev in fusionne["hooks"]["Stop"][0]["hooks"]


def test_sans_pilotage_garde_un_tiers_nomme_hooks():
    tiers = _tiers('python "C:/outils/mes-hooks/pilotage.py"')
    autre = _entree("C:/outils/copilotage-hooks/stop.py")
    settings = {"hooks": {"Stop": [{"hooks": [tiers, autre]}]}}
    assert fusion.sans_pilotage(settings, RACINE) == settings


def test_commande_config_pas_ecrit_si_la_fusion_echoue(tmp_path, capsys):
    config = tmp_path / "config.json"
    _ecrire(config, {"racine_locale": "D:/locale"})
    avant = config.read_bytes()
    depot = tmp_path / "depot.json"
    depot.write_bytes(b"{pas du json")
    cible = tmp_path / "settings.json"
    code = cli.main(["--settings", str(cible), "--depuis", str(depot), "--racine", RACINE,
                     "--python", PY_REEL, "--config", str(config), "--racine-github", "D:/G"])
    assert code == 1
    assert "rien n'a été écrit" in capsys.readouterr().err
    assert config.read_bytes() == avant and not cible.exists()


def test_ecrire_config_bom_accepte_reecrit_sans_bom(tmp_path):
    config = tmp_path / "config.json"
    config.write_bytes(fusion.BOM + b'{"port": 8123, "autre": 1}')
    assert fusion.ecrire_config(config, "C:/i/.venv/Scripts/python.exe", "C:/G")
    octets = config.read_bytes()
    assert not octets.startswith(fusion.BOM)
    donnees = json.loads(octets)
    assert donnees["port"] == 8123 and donnees["autre"] == 1
    assert donnees["racine_github"] == "C:/G"


def _commande_config(tmp_path, *identite):
    config = tmp_path / "config.json"
    args = ["--settings", str(tmp_path / "settings.json"), "--racine", RACINE, "--python",
            PY_REEL, "--config", str(config), "--racine-github", "D:/G", *identite]
    return config, cli.main(args)


def test_commande_identite_ecrite_puis_conservee(tmp_path, capsys):
    config, code = _commande_config(
        tmp_path, "--proprietaire", "Proprio-Test", "--depot-donnees",
        "Proprio-Test/donnees.test_1", "--utilisateur", "  Anaïs Test  ",
    )
    assert code == 0
    ecrit = json.loads(config.read_text(encoding="utf-8"))
    assert {k: ecrit[k] for k in ("proprietaire_github", "depot_donnees", "utilisateur")} == {
        "proprietaire_github": "Proprio-Test",
        "depot_donnees": "Proprio-Test/donnees.test_1",
        "utilisateur": "Anaïs Test",
    }
    _, code = _commande_config(tmp_path)  # appel de l'ancien sync.ps1 : sans les arguments
    assert code == 0
    assert json.loads(config.read_text(encoding="utf-8")) == ecrit
    _, code = _commande_config(tmp_path, "--depot-donnees", "Proprio-Test/autre")
    assert code == 0
    assert json.loads(config.read_text(encoding="utf-8")) == {**ecrit, "depot_donnees":
                                                                 "Proprio-Test/autre"}


def test_commande_sans_identite_reussit_sans_l_ecrire(tmp_path, capsys):
    config, code = _commande_config(tmp_path)
    assert code == 0
    assert not {"proprietaire_github", "depot_donnees", "utilisateur"} & json.loads(
        config.read_text(encoding="utf-8")).keys()


@pytest.mark.parametrize(("option", "valeur", "message"), [
    ("--proprietaire", "", "propriétaire GitHub invalide"),
    ("--proprietaire", "-option", "propriétaire GitHub invalide"),
    ("--proprietaire", "fin-", "propriétaire GitHub invalide"),
    ("--proprietaire", "a" * 40, "propriétaire GitHub invalide"),
    ("--proprietaire", "a_b", "propriétaire GitHub invalide"),
    ("--depot-donnees", "sans-barre", "dépôt de données invalide"),
    ("--depot-donnees", "a/b/c", "dépôt de données invalide"),
    ("--depot-donnees", "-a/b", "dépôt de données invalide"),
    ("--depot-donnees", "a/-b", "dépôt de données invalide"),
    ("--depot-donnees", "a/b.git", "dépôt de données invalide"),
    ("--depot-donnees", "a/B.GIT", "dépôt de données invalide"),
    ("--depot-donnees", "a/..", "dépôt de données invalide"),
    ("--depot-donnees", "a/x..y", "dépôt de données invalide"),
    ("--depot-donnees", "a/b c", "dépôt de données invalide"),
    ("--utilisateur", "", "utilisateur invalide"),
    ("--utilisateur", "x" * 65, "utilisateur invalide"),
    ("--utilisateur", "deux\nlignes", "utilisateur invalide"),
    ("--utilisateur", "tab\tulation", "utilisateur invalide"),
    ("--utilisateur", "ghp_abcdef", "utilisateur invalide"),
])
def test_commande_identite_invalide_rend_1_sans_rien_ecrire(tmp_path, capsys, option, valeur,
                                                             message):
    config = tmp_path / "config.json"
    _ecrire(config, {"depot_donnees": "garde/ceci"})
    avant = config.read_bytes()
    _, code = _commande_config(tmp_path, f"{option}={valeur}")  # `=` : `-x` reste une valeur
    assert code == 1
    assert message in capsys.readouterr().err
    assert config.read_bytes() == avant
    assert not (tmp_path / "settings.json").exists()


@pytest.mark.parametrize("option", ["--proprietaire", "--depot-donnees", "--utilisateur"])
def test_commande_identite_sans_config_rend_2(option, capsys):
    with pytest.raises(SystemExit) as sortie:
        cli.main([option, "x"])
    assert sortie.value.code == 2


def test_preparer_config_identite_limites(tmp_path):
    config = tmp_path / "config.json"
    octets = fusion.preparer_config(config, "C:/p/python.exe", "C:/G", "a" * 39,
                                    "a" * 39 + "/" + "n" * 100, "u" * 64)
    objet = json.loads(octets)
    assert objet["proprietaire_github"] == "a" * 39
    assert objet["utilisateur"] == "u" * 64
    with pytest.raises(fusion.ErreurInstallation):
        fusion.preparer_config(config, "C:/p/python.exe", "C:/G", depot_donnees="a/" + "n" * 101)
