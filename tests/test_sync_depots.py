"""Story 8.3 : copie de l'état du dépôt et du journal de décisions vers `donnees/depots/`."""

import json
import types

from pilotage import chemins
from pilotage.sync import copie, cycle

PC = "pc-ici"
AUTRE = "pc-la"
PROJET = "projet-a"
SESSION = "11111111-1111-4111-8111-111111111111"
SECRET = "ghp_abcdefghijklmnopqrstuvwxyz0123"


def _ligne(texte, **champs):
    objet = {"date": "2026-11-14", "ecrit": "2026-11-14T10:00:00Z", "decision": texte,
             "session": SESSION}
    objet.update(champs)
    return objet


def _etat(pc=PC, **champs):
    objet = {"schema": 1, "projet": PROJET, "pc": pc, "session": SESSION,
             "ecrit": "2026-11-14T10:00:00Z", "etat": {"prochaine": "P"}, "decisions": []}
    objet.update(champs)
    return objet


def _poser(nom, contenu, ou=None, projet=PROJET):
    dossier = (ou or chemins.attente()) / "depots" / projet
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _copier():
    return copie.copier_depots(PC, "C:/GitHub")


def test_copie_les_fichiers_de_ce_pc_seulement(racine_locale_isolee):
    _poser(f"{PC}.json", json.dumps(_etat()))
    _poser(f"{PC}.decisions.jsonl", json.dumps(_ligne("D1")) + "\n")
    _poser(f"{AUTRE}.json", json.dumps(_etat(AUTRE)))
    _poser(f"{AUTRE}.decisions.jsonl", json.dumps(_ligne("D")) + "\n")
    _poser(f"{PC}.json.123.ab.tmp", "{")
    copies, ignores = _copier()
    assert sorted(copies) == [f"depots/{PROJET}/{PC}.decisions.jsonl", f"depots/{PROJET}/{PC}.json"]
    assert ignores == 0
    cible = chemins.donnees() / "depots" / PROJET
    assert sorted(p.name for p in cible.iterdir()) == [f"{PC}.decisions.jsonl", f"{PC}.json"]
    assert json.loads((cible / f"{PC}.json").read_text(encoding="utf-8")) == _etat()


def test_filtre_rejoue(racine_locale_isolee):
    _poser(f"{PC}.json", json.dumps(_etat(
        etat={"prochaine": "P", "blocages": f"jeton {SECRET}", "explore": "C:/GitHub/a.md"},
        decisions=[_ligne(f"x {SECRET}"), _ligne("Saine", pourquoi="KEY=1")],
    )))
    _poser(f"{PC}.decisions.jsonl", json.dumps(_ligne(f"x {SECRET}")) + "\n"
           + json.dumps(_ligne("Saine")) + "\n")
    _copier()
    cible = chemins.donnees() / "depots" / PROJET
    objet = json.loads((cible / f"{PC}.json").read_text(encoding="utf-8"))
    assert objet["etat"] == {"prochaine": "P", "explore": "{{RACINE_GITHUB}}/a.md"}
    assert objet["decisions"] == [_ligne("Saine")]
    texte = "".join(p.read_text(encoding="utf-8") for p in cible.iterdir())
    assert SECRET not in texte and "KEY=1" not in texte
    assert [json.loads(x)["decision"] for x in
            (cible / f"{PC}.decisions.jsonl").read_text(encoding="utf-8").splitlines()] == ["Saine"]


def test_prochaine_suspecte_etat_retire(racine_locale_isolee):
    _poser(f"{PC}.json", json.dumps(_etat(etat={"prochaine": SECRET}, decisions=[_ligne("D")],
                                          etat_ecrit="2026-11-13T10:00:00Z")))
    _copier()
    objet = json.loads((chemins.donnees() / "depots" / PROJET / f"{PC}.json").read_text(
        encoding="utf-8"))
    assert "etat" not in objet and "etat_ecrit" not in objet
    assert objet["decisions"] == [_ligne("D")]


def test_journal_borne_a_200_lignes_ici_et_la(racine_locale_isolee):
    lignes = [json.dumps(_ligne(f"D{i}")) for i in range(250)]
    lignes.insert(100, '{"tronquée')
    lignes.insert(120, json.dumps(_ligne("")))
    source = _poser(f"{PC}.decisions.jsonl", "\n".join(lignes) + "\n")
    copies, ignores = _copier()
    assert ignores == 0 and copies == [f"depots/{PROJET}/{PC}.decisions.jsonl"]
    gardees = source.read_text(encoding="utf-8").splitlines()
    assert len(gardees) == copie.MAX_LIGNES_JOURNAL == 200
    assert gardees[-1] == json.dumps(_ligne("D249"))
    copiees = (chemins.donnees() / "depots" / PROJET / f"{PC}.decisions.jsonl").read_text(
        encoding="utf-8").splitlines()
    # 200 lignes brutes gardées, dont les deux invalides, écartées seules à la copie.
    assert [json.loads(x)["decision"] for x in copiees] == [f"D{i}" for i in range(52, 250)]
    assert not (chemins.attente() / "verrous" / f"depot-{PROJET}.lock").exists()


def test_rotation_attend_si_le_verrou_est_tenu(racine_locale_isolee):
    source = _poser(f"{PC}.decisions.jsonl",
                    "".join(json.dumps(_ligne(f"D{i}")) + "\n" for i in range(201)))
    verrou = chemins.attente() / "verrous" / f"depot-{PROJET}.lock"
    verrou.parent.mkdir(parents=True)
    verrou.write_text("999", encoding="utf-8")
    _copier()
    assert len(source.read_text(encoding="utf-8").splitlines()) == 201  # rotation remise
    assert verrou.read_text(encoding="utf-8") == "999"
    copiees = (chemins.donnees() / "depots" / PROJET / f"{PC}.decisions.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(copiees) == 200


def test_fichiers_invalides_ignores(racine_locale_isolee):
    _poser(f"{PC}.json", json.dumps(_etat(pc=AUTRE)))  # contenu d'un autre PC
    _poser(f"{PC}.decisions.jsonl", "pas du json\n")
    _poser(f"{PC}.json", "{}", projet="Projet_Invalide")
    assert _copier() == ([], 3)
    assert not (chemins.donnees() / "depots").exists()


def test_etat_trop_gros_ignore(racine_locale_isolee):
    _poser(f"{PC}.json", json.dumps(_etat(etat={"prochaine": "P" * 20_000})))
    assert _copier() == ([], 1)


def test_etape_copie_attente_inclut_les_depots(racine_locale_isolee):
    _poser(f"{PC}.json", json.dumps(_etat()))
    ctx = types.SimpleNamespace(pc=PC, racine_github="C:/GitHub", relatifs=[], ignores=0)
    cycle._copier_attente(ctx)
    assert ctx.relatifs == [f"depots/{PROJET}/{PC}.json"]
    assert [nom for nom, _ in cycle.ETAPES].count("copie-attente") == 1


def test_rotation_n_efface_pas_un_verrou_repris(racine_locale_isolee, monkeypatch):
    """Rotation de plus de 2 s : `Stop` juge le verrou périmé et le reprend ; la fin de la
    rotation ne doit pas effacer le verrou de `Stop`."""
    _poser(f"{PC}.decisions.jsonl",
           "".join(json.dumps(_ligne(f"D{i}")) + "\n" for i in range(201)))
    verrou = chemins.attente() / "verrous" / f"depot-{PROJET}.lock"
    ecrire = chemins.ecrire_atomique

    def reprise_pendant_la_rotation(chemin, contenu):
        ecrire(chemin, contenu)
        if chemin.name.endswith(".decisions.jsonl") and "attente" in chemin.parts:
            verrou.write_text("4242 jeton-de-stop", encoding="utf-8")

    monkeypatch.setattr(chemins, "ecrire_atomique", reprise_pendant_la_rotation)
    _copier()
    assert verrou.read_text(encoding="utf-8") == "4242 jeton-de-stop"


def test_verrou_de_rotation_rendu(racine_locale_isolee):
    _poser(f"{PC}.decisions.jsonl",
           "".join(json.dumps(_ligne(f"D{i}")) + "\n" for i in range(201)))
    _copier()
    assert not (chemins.attente() / "verrous" / f"depot-{PROJET}.lock").exists()
