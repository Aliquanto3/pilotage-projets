# ruff: noqa: F401, F811
"""Étape 4 de `sync` : opérations appliquées une fois et une seule (story 5.1, AD-5 §7, §11).

Cycle complet contre un dépôt nu local, `gh` simulé (fixtures de `test_sync_cli`), aucun GitHub.
"""

import json
import os
from datetime import UTC, datetime

import pytest

from pilotage import chemins
from pilotage.noyau import alertes as catalogue
from pilotage.sync import cycle, operations
from tests.test_sync_cli import (  # fixtures autouse et partagées
    INSTANT,
    PC,
    alertes_sync,
    arbre,
    distant,
    g,
    gh,
    github,
    horloge,
    nb_commits,
    nom_propre,
    poser,
    synchro,
)
from tests.test_sync_reprise import Tue

ID1 = "20261106T090000Z-0000000a"
ID2 = "20261106T090100Z-0000000b"
ID3 = "20261106T090200Z-0000000c"
PROJETS = """\
# réglages de l'utilisateur
schema: 1
chantiers:
  Pilotage:  # principal
    projets:
      - demo
exclus:
  - vieux   # abandonné
pauses:
# fin
"""
VOULU = """\
# réglages de l'utilisateur
schema: 1
chantiers:
  Pilotage:  # principal
    projets:
      - demo
exclus:
  - vieux   # abandonné
pauses:
  demo:
    revue: 2026-12-01
# fin
"""


@pytest.fixture(autouse=True)
def horloge_operations(monkeypatch):
    """Âge des traces mesuré à l'instant figé du cycle (purge à 30 jours)."""
    monkeypatch.setattr(operations, "_maintenant", lambda: INSTANT.astimezone(UTC))


def vieillir(chemin):
    """Fichier écrit il y a plus de `DELAI_ECRITURE` : plus en cours d'écriture."""
    passe = chemin.stat().st_mtime - 10 * operations.DELAI_ECRITURE
    os.utime(chemin, (passe, passe))
    return chemin


def trace(id_):
    return f"operations/appliquees/{PC}/{id_}.json"


def autre_pc(distant, tmp_path, relatif, texte):
    """Un autre PC commite et pousse `relatif` (ou le supprime si `texte` est None)."""
    clone = tmp_path / "autre-pc"
    if not clone.exists():
        g(["clone", "--quiet", "--branch", "donnees", str(distant), str(clone)])
    g(["pull", "--quiet"], clone)
    if texte is None:
        g(["rm", "--quiet", "--", relatif], clone)
    else:
        poser(clone, relatif, texte)
        g(["add", "--", relatif], clone)
    g(["commit", "--quiet", "-m", "autre"], clone)
    g(["push", "--quiet", "origin", "donnees"], clone)


def message(id_=ID1, texte="Reprends la story 5.2", **champs):
    return {"schema": 1, "id": id_, "verbe": "deposer_message", "projet": "demo",
            "texte": texte, **champs}


def pause(id_=ID2, attendu=None, voulu="2026-12-01", projet="demo"):
    return {"schema": 1, "id": id_, "verbe": "modifier_projets", "projet": projet,
            "patch": {"pause": {"attendu": attendu, "voulu": voulu}}}


def deposer(objet, nom=None):
    return poser(chemins.operations(), nom or f"{objet['id']}.json", objet)


def en_attente():
    dossier = chemins.operations()
    return sorted(p.name for p in dossier.iterdir() if p.is_file()) if dossier.is_dir() else []


def rejetees():
    dossier = chemins.operations() / "rejetees"
    return sorted(p.name for p in dossier.iterdir()) if dossier.is_dir() else []


def alertes_operation():
    objet = json.loads(chemins.alertes_json().read_text("utf-8"))
    return [(a["code"], a["params"]) for a in objet["alertes"] if a["source"] == "operation"]


def distant_texte(nu, relatif):
    return g(["--git-dir", str(nu), "show", f"donnees:{relatif}"])


@pytest.fixture
def base(distant, github, gh):
    """Premier cycle fait, puis `projets.yaml` commenté édité à la main et commité."""
    assert synchro(github) == 0
    poser(chemins.donnees(), "projets.yaml", PROJETS)
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == PROJETS
    return nb_commits(distant)


def test_message_depose_une_fois_puis_operation_supprimee(distant, github, base):
    deposer(message(pc="pc-bureau"))
    assert synchro(github) == 0
    relatif = f"boite/demo/{ID1}.json"
    assert relatif in arbre(distant)
    assert json.loads(distant_texte(distant, relatif)) == {
        "schema": 1, "id": ID1, "projet": "demo", "texte": "Reprends la story 5.2",
        "pc": "pc-bureau",
    }
    assert en_attente() == [] and rejetees() == []
    assert nb_commits(distant) == base + 1
    assert alertes_operation() == []
    deposer(message())  # même opération rejouée : rien ne change
    assert synchro(github) == 0
    assert nb_commits(distant) == base + 1
    assert en_attente() == []


def test_patch_cible_garde_commentaires_et_ordre(distant, github, base):
    deposer(pause())
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == VOULU
    assert (chemins.donnees() / "projets.yaml").read_text("utf-8") == VOULU
    assert en_attente() == []
    assert nb_commits(distant) == base + 1


def test_valeur_deja_voulue_compte_comme_appliquee(distant, github, base):
    deposer(pause())
    assert synchro(github) == 0
    deposer(pause(id_=ID3))  # même demande venue d'ailleurs : déjà appliquée
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == VOULU
    assert en_attente() == [] and rejetees() == []
    assert nb_commits(distant) == base + 2  # seule sa trace est commitée
    assert trace(ID3) in arbre(distant)


def test_valeur_differente_rejette_et_garde_l_operation(distant, github, base):
    deposer(pause(attendu="2026-11-01", voulu="2026-12-01"))
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == PROJETS
    assert en_attente() == []
    assert rejetees() == [f"{ID2}.json", f"{ID2}.raison.json"]
    raison = json.loads((chemins.operations() / "rejetees" / f"{ID2}.raison.json").read_text())
    assert raison == {"schema": 1, "id": ID2, "raison": "valeur-differente", "projet": "demo",
                      "champ": "pause"}
    attendue = ("operation-valeur-differente", {"id": ID2, "projet": "demo", "champ": "pause"})
    assert alertes_operation() == [attendue]
    assert catalogue.texte({"code": attendue[0], "params": attendue[1]}) == (
        "Modification refusée : projets.yaml a changé ailleurs (champ pause de demo)."
    )
    assert synchro(github) == 0  # l'alerte reste tant que le rejet est gardé
    assert alertes_operation() == [attendue]
    assert nb_commits(distant) == base


def test_valeur_differente_sur_un_champ_rejette_toute_l_operation(distant, github, base):
    op = pause()
    # demo est dans Pilotage, ni l'attendu ni le voulu
    op["patch"]["chantier"] = {"attendu": None, "voulu": "Recherche"}
    deposer(op)
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == PROJETS  # pause non posée non plus
    assert alertes_operation() == [
        ("operation-valeur-differente", {"id": ID2, "projet": "demo", "champ": "chantier"})
    ]


def test_resultat_invalide_rejete(distant, github, base):
    op = {"schema": 1, "id": ID2, "verbe": "modifier_projets", "projet": "demo",
          "patch": {"exclu": {"attendu": False, "voulu": True}}}  # exclu et dans un chantier
    deposer(op)
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == PROJETS
    assert alertes_operation() == [("operation-resultat-invalide", {"id": ID2, "projet": "demo"})]


def test_patch_impossible_rejete(distant, github, base):
    op = {"schema": 1, "id": ID2, "verbe": "modifier_projets", "projet": "projet-a",
          "patch": {"chantier": {"attendu": None, "voulu": "Absent"}}}
    deposer(op)
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == PROJETS
    assert alertes_operation() == [
        ("operation-patch-impossible", {"id": ID2, "projet": "projet-a", "champ": "chantier"})
    ]


def test_schema_plus_recent_rejete_avec_alerte_de_version(distant, github, base):
    deposer({**message(), "schema": 2, "nouveau": 1})
    assert synchro(github) == 0
    assert alertes_operation() == [("operation-version-recente", {"id": ID1})]
    assert not any(p.startswith("boite/") for p in arbre(distant))


def test_projets_yaml_plus_recent_en_lecture_seule(distant, github, base):
    recent = PROJETS.replace("schema: 1", "schema: 2") + "nouveau: oui\n"
    poser(chemins.donnees(), "projets.yaml", recent)
    deposer(pause())
    assert synchro(github) == 0
    # M7 : jamais patché, et jamais commité depuis un PC qui ne connaît pas son schema
    assert distant_texte(distant, "projets.yaml") == PROJETS
    assert alertes_operation() == [
        ("operation-projets-version-recente", {"id": ID2, "projet": "demo"})
    ]
    assert catalogue.PROJETS_NON_COMMITE in dict(alertes_sync())


def test_projets_yaml_invalide_rejette(distant, github, base):
    poser(chemins.donnees(), "projets.yaml", "schema: [\n")
    deposer(pause())
    assert synchro(github) == 0
    assert alertes_operation() == [("operation-projets-invalide", {"id": ID2, "projet": "demo"})]
    assert distant_texte(distant, "projets.yaml") == PROJETS  # M7 : jamais commité invalide
    assert catalogue.PROJETS_NON_COMMITE in dict(alertes_sync())
    poser(chemins.donnees(), "projets.yaml", PROJETS)  # corrigé à la main : alerte levée
    assert synchro(github) == 0
    assert catalogue.PROJETS_NON_COMMITE not in dict(alertes_sync())


def test_message_different_au_meme_id_jamais_ecrase(distant, github, base):
    deposer(message())
    assert synchro(github) == 0
    deposer(message(texte="Autre texte"))
    assert synchro(github) == 0
    assert json.loads(distant_texte(distant, f"boite/demo/{ID1}.json"))["texte"] == (
        "Reprends la story 5.2"
    )
    assert alertes_operation() == [("operation-message-different", {"id": ID1, "projet": "demo"})]


@pytest.mark.parametrize("contenu", [
    "pas du json",
    json.dumps(message(projet="..")),
    json.dumps(message(projet="../../hors")),
    json.dumps({**message(), "verbe": "supprimer"}),
    json.dumps(message(id_=ID3)),  # id du contenu différent du nom
])
def test_operation_invalide_rejetee_sans_ecrire(distant, github, base, contenu):
    vieillir(poser(chemins.operations(), f"{ID1}.json", contenu))
    assert synchro(github) == 0
    assert alertes_operation() == [("operation-invalide", {"id": ID1})]
    assert rejetees() == [f"{ID1}.json", f"{ID1}.raison.json"]
    assert (chemins.operations() / "rejetees" / f"{ID1}.json").read_text("utf-8") == contenu
    assert nb_commits(distant) == base
    assert not (chemins.racine_locale() / "hors").exists()


def test_noms_invalides_et_temporaires_ignores(distant, github, base):
    deposer(message(), nom="pas-un-id.json")
    deposer(message(), nom=f"{ID1}.json.123.abcd.tmp")
    assert synchro(github) == 0
    assert alertes_operation() == [("operation-nom-invalide", {"nombre": 1})]
    assert en_attente() == [f"{ID1}.json.123.abcd.tmp", "pas-un-id.json"]  # jamais supprimés
    assert nb_commits(distant) == base


def test_operation_deposee_pendant_le_cycle_attend_le_suivant(distant, github, base, monkeypatch):
    deposer(message())
    reelles = list(cycle.ETAPES)

    def scan_et_depot(ctx):
        dict(reelles)["scan"](ctx)
        deposer(message(id_=ID3, texte="Arrivé pendant le cycle"))

    monkeypatch.setattr(
        cycle, "ETAPES", [(n, scan_et_depot if n == "scan" else f) for n, f in reelles]
    )
    assert synchro(github) == 0
    assert en_attente() == [f"{ID3}.json"]
    assert f"boite/demo/{ID3}.json" not in arbre(distant)
    monkeypatch.setattr(cycle, "ETAPES", reelles)
    assert synchro(github) == 0
    assert en_attente() == []
    assert f"boite/demo/{ID3}.json" in arbre(distant)


@pytest.mark.parametrize("etape", [nom for nom, _ in cycle.ETAPES])
def test_rejeu_apres_cycle_interrompu_sans_doublon(distant, github, base, monkeypatch, etape):
    deposer(message())
    deposer(pause())
    reelles = list(cycle.ETAPES)

    def tuer(nom, fonction):
        def jouer(ctx):
            fonction(ctx)
            if nom == etape:
                raise Tue
        return jouer

    monkeypatch.setattr(cycle, "ETAPES", [(n, tuer(n, f)) for n, f in reelles])
    with pytest.raises(Tue):
        synchro(github)
    monkeypatch.setattr(cycle, "ETAPES", reelles)
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == VOULU
    boites = [p for p in arbre(distant) if p.startswith("boite/")]
    assert boites == [f"boite/demo/{ID1}.json"]
    assert nb_commits(distant) == base + 1
    assert en_attente() == [] and rejetees() == []
    assert alertes_operation() == []
    assert synchro(github) == 0  # un cycle de plus : rien ne change
    assert nb_commits(distant) == base + 1
    assert g(["status", "--porcelain"], chemins.donnees()) == ""


def test_push_refuse_garde_les_operations(distant, github, base, monkeypatch):
    from pilotage.sync import depot

    def refuser(donnees):
        raise depot.ErreurGit("git push a échoué")

    deposer(message())
    vrai = depot.pousser
    monkeypatch.setattr(depot, "pousser", refuser)
    assert synchro(github) == 1
    assert en_attente() == [f"{ID1}.json"]  # rien supprimé sans push réussi
    # Jamais `undo` du monkeypatch : il retirerait aussi l'isolement (racine locale, git, gh).
    monkeypatch.setattr(depot, "pousser", vrai)
    assert synchro(github) == 0
    assert en_attente() == []
    assert f"boite/demo/{ID1}.json" in arbre(distant)


def test_lien_vers_rejetees_refuse(distant, github, base, tmp_path):
    import os
    import sys

    dehors = tmp_path / "dehors"
    dehors.mkdir()
    chemins.operations().mkdir(parents=True, exist_ok=True)
    lien = chemins.operations() / "rejetees"
    if sys.platform == "win32":
        import subprocess
        subprocess.run(["cmd", "/c", "mklink", "/J", str(lien), str(dehors)], check=True,
                       capture_output=True)
    else:
        os.symlink(dehors, lien, target_is_directory=True)
    deposer(pause(attendu="2026-11-01"))
    assert synchro(github) == 1  # étape `operations-nettoyage` en échec
    assert list(dehors.iterdir()) == []
    assert (chemins.operations() / f"{ID2}.json").is_file()


def test_operations_etape_quatre_figee_dans_le_contexte(distant, github, base):
    deposer(message())
    ctx = cycle.Contexte(pc=PC, racine_github=github)
    operations.appliquer(ctx)
    assert [(f.id, f.projet, f.raison) for f in ctx.operations] == [(ID1, "demo", None)]
    assert ctx.relatifs == [f"boite/demo/{ID1}.json", trace(ID1)]  # même commit
    operations.nettoyer(ctx)
    assert en_attente() == [] and ctx.operations == []


@pytest.mark.parametrize("op", ["message", "pause"])
def test_arret_apres_push_puis_changement_d_un_autre_pc_jamais_reapplique(
    distant, github, base, monkeypatch, tmp_path, op
):
    """« Une fois et une seule » : la trace commitée avec l'effet empêche tout second effet."""
    deposer(message() if op == "message" else pause())
    reelles = list(cycle.ETAPES)

    def arret(nom, fonction):
        def jouer(ctx):
            if nom == "operations-nettoyage":
                raise Tue  # arrêt entre le push et le nettoyage
            fonction(ctx)
        return jouer

    monkeypatch.setattr(cycle, "ETAPES", [(n, arret(n, f)) for n, f in reelles])
    with pytest.raises(Tue):
        synchro(github)
    monkeypatch.setattr(cycle, "ETAPES", reelles)
    id_ = ID1 if op == "message" else ID2
    assert trace(id_) in arbre(distant)  # même commit que l'effet
    if op == "message":  # l'autre PC a lu et retiré le message
        autre_pc(distant, tmp_path, f"boite/demo/{ID1}.json", None)
    else:  # l'autre PC a levé la pause : valeur revenue à `attendu`
        autre_pc(distant, tmp_path, "projets.yaml", PROJETS)
    commits = nb_commits(distant)
    assert synchro(github) == 0
    assert en_attente() == [] and rejetees() == []
    assert distant_texte(distant, "projets.yaml") == PROJETS
    assert not any(p.startswith("boite/") for p in arbre(distant))
    assert nb_commits(distant) == commits


def test_traces_purgees_apres_trente_jours(distant, github, base, monkeypatch):
    deposer(message())
    assert synchro(github) == 0
    assert trace(ID1) in arbre(distant)
    monkeypatch.setattr(
        operations, "_maintenant", lambda: datetime(2026, 12, 7, 9, 1, tzinfo=UTC)
    )
    assert synchro(github) == 0
    assert trace(ID1) not in arbre(distant)
    assert f"boite/demo/{ID1}.json" in arbre(distant)


def arreter_avant_nettoyage(github, monkeypatch):
    """Cycle tué avant `operations-nettoyage` : effet et trace poussés, opération gardée."""
    reelles = list(cycle.ETAPES)

    def arret(nom, fonction):
        def jouer(ctx):
            if nom == "operations-nettoyage":
                raise Tue
            fonction(ctx)
        return jouer

    monkeypatch.setattr(cycle, "ETAPES", [(n, arret(n, f)) for n, f in reelles])
    with pytest.raises(Tue):
        synchro(github)
    monkeypatch.setattr(cycle, "ETAPES", reelles)
    return reelles


def test_trace_d_une_operation_en_attente_jamais_purgee(distant, github, base, monkeypatch):
    deposer(message())
    arreter_avant_nettoyage(github, monkeypatch)
    monkeypatch.setattr(
        operations, "_maintenant", lambda: datetime(2026, 12, 7, 9, 1, tzinfo=UTC)
    )
    arreter_avant_nettoyage(github, monkeypatch)  # 31 jours plus tard, toujours en attente
    assert en_attente() == [f"{ID1}.json"]
    assert trace(ID1) in arbre(distant)
    assert synchro(github) == 0  # nettoyée : la trace part au cycle suivant
    assert en_attente() == []
    assert synchro(github) == 0
    assert trace(ID1) not in arbre(distant)


def test_meme_identifiant_autre_contenu_rejete(distant, github, base, monkeypatch, tmp_path):
    deposer(message())
    arreter_avant_nettoyage(github, monkeypatch)
    autre_pc(distant, tmp_path, f"boite/demo/{ID1}.json", None)  # message lu et retiré
    deposer(message(texte="Autre texte"))  # même identifiant, contenu différent
    commits = nb_commits(distant)
    assert synchro(github) == 0
    assert alertes_operation() == [("operation-message-different", {"id": ID1, "projet": "demo"})]
    assert rejetees() == [f"{ID1}.json", f"{ID1}.raison.json"]
    assert not any(p.startswith("boite/") for p in arbre(distant))
    assert nb_commits(distant) == commits


def test_meme_identifiant_autre_patch_jamais_applique(distant, github, base, monkeypatch):
    deposer(pause())
    arreter_avant_nettoyage(github, monkeypatch)
    deposer(pause(attendu="2026-12-01", voulu="2027-01-15"))  # applicable, mais id déjà tracé
    assert synchro(github) == 0
    assert alertes_operation() == [("operation-deja-appliquee", {"id": ID2, "projet": "demo"})]
    assert distant_texte(distant, "projets.yaml") == VOULU


def test_projets_yaml_avec_bom_garde_le_bom(distant, github, base):
    poser(chemins.donnees(), "projets.yaml", "﻿exclus:\n  - vieux\nschema: 1\n")
    assert synchro(github) == 0
    deposer(pause())
    assert synchro(github) == 0
    assert alertes_operation() == []
    texte = (chemins.donnees() / "projets.yaml").read_text("utf-8")
    assert texte.startswith("﻿exclus:\n  - vieux\n") and "revue: 2026-12-01" in texte


def test_projets_yaml_modifie_pendant_l_etape_attend_le_cycle_suivant(
    distant, github, base, monkeypatch
):
    deposer(pause())
    vrai = operations._Projets.modifier
    edite = PROJETS + "# édité pendant le cycle\n"

    def modifier_puis_edition(self, op, figee):
        vrai(self, op, figee)
        poser(chemins.donnees(), "projets.yaml", edite)

    monkeypatch.setattr(operations._Projets, "modifier", modifier_puis_edition)
    assert synchro(github) == 0
    assert distant_texte(distant, "projets.yaml") == edite  # jamais écrasé
    assert en_attente() == [f"{ID2}.json"] and rejetees() == []  # ni appliquée ni rejetée
    monkeypatch.setattr(operations._Projets, "modifier", vrai)
    assert synchro(github) == 0
    assert "revue: 2026-12-01" in distant_texte(distant, "projets.yaml")
    assert en_attente() == []


def test_operation_illisible_recente_attend_le_cycle_suivant(distant, github, base):
    poser(chemins.operations(), f"{ID1}.json", '{"schema": 1, "id"')  # écriture en cours
    assert synchro(github) == 0
    assert en_attente() == [f"{ID1}.json"] and rejetees() == []
    assert alertes_operation() == []
    vieillir(chemins.operations() / f"{ID1}.json")
    assert synchro(github) == 0
    assert rejetees() == [f"{ID1}.json", f"{ID1}.raison.json"]


def test_alertes_illisibles_non_effacees_par_l_etape(distant, github, base):
    deposer(pause(attendu="2026-11-01"))
    chemins.alertes_json().write_text("pas du json", encoding="utf-8")
    ctx = cycle.Contexte(pc=PC, racine_github=github)
    operations.appliquer(ctx)
    assert chemins.alertes_json().read_text("utf-8") == "pas du json"
    assert [f.raison for f in ctx.operations] == ["valeur-differente"]


def test_raison_rejetee_par_un_lien_jamais_lue(distant, github, base, tmp_path):
    import subprocess
    import sys

    dehors = tmp_path / "dehors"
    poser(dehors, f"{ID1}.raison.json", {"schema": 1, "id": ID1, "raison": "invalide"})
    chemins.operations().mkdir(parents=True, exist_ok=True)
    lien = chemins.operations() / "rejetees"
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(lien), str(dehors)], check=True,
                       capture_output=True)
    else:
        os.symlink(dehors, lien, target_is_directory=True)
    assert synchro(github) == 0
    assert alertes_operation() == []
