"""`POST /api/message` et `POST /api/projets` : opérations déposées par création seule, puis
`sync` (story 5.2, AD-9, AD-14, M10, M12). `Popen` et minuteur simulés : aucun vrai `sync`."""

import json
import os
import shutil

import pytest

from pilotage import chemins
from pilotage.noyau import ids, schemas
from pilotage.scan import cli as scan_cli
from pilotage.scan import faits_gh
from pilotage.scan import verrou as impl
from pilotage.serveur import enfants, mutations, relance, routes
from tests.test_faits_gh import faux_gh
from tests.test_inventaire import faux_depot
from tests.test_serveur import _demarrer, _json, requete
from tests.test_serveur_enfants import FauxProcessus, attendre
from tests.test_serveur_etat import empreinte
from tests.test_serveur_relance import FauxMinuteur

EMOJI = "\U0001f600"  # 4 octets UTF-8


@pytest.fixture(autouse=True)
def isole(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPUTERNAME", "PC-Test")
    monkeypatch.setenv(impl.VARIABLE_NOM, rf"Local\pilotage-test-mut-{abs(hash(str(tmp_path)))}")
    enfants.reinitialiser()
    relance.reinitialiser()
    yield
    relance.reinitialiser()
    enfants.reinitialiser()


@pytest.fixture
def lances(monkeypatch):
    appels = []

    def faux(commande, **options):
        processus = FauxProcessus()
        appels.append(commande)
        processus.finir(0)
        return processus

    monkeypatch.setattr(enfants, "popen", faux)
    yield appels
    attendre(lambda: enfants._etat[0] is None, delai=2)


@pytest.fixture
def minuteurs(monkeypatch):
    crees = []
    monkeypatch.setattr(
        relance, "minuteur", lambda d, f: crees.append(FauxMinuteur(d, f)) or crees[-1]
    )
    return crees


@pytest.fixture
def scanne(monkeypatch):
    """Dépôt `demo` scanné (gh simulé) : état chargé, table des dossiers, instantané `pc-test`."""
    github = chemins.racine_github()
    faux_depot(github / "demo", url="https://github.com/Proprio-Test/demo.git")
    monkeypatch.setattr(faits_gh, "executeur_gh", faux_gh())
    assert scan_cli.main(["--racine-github", str(github), "--pc", "pc-test"]) == 0
    (chemins.donnees() / "instantanes").mkdir(parents=True)
    shutil.copy(chemins.instantanes() / "pc-test.json",
                chemins.donnees() / "instantanes" / "pc-autre.json")
    return github


@pytest.fixture
def serveur(tmp_path, scanne, lances, minuteurs):
    web = tmp_path / "web"
    web.mkdir()
    serveur = _demarrer(web, routes.TABLE)
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def poster(serveur, route, objet=None, brut=None, **options):
    corps = brut if brut is not None else json.dumps(objet).encode("utf-8")
    reponse, contenu = requete(
        serveur, "POST", route, corps=corps, jeton=options.pop("jeton", serveur.jeton), **options
    )
    return reponse.status, _json(contenu)


def deposees():
    dossier = chemins.operations()
    return sorted(os.listdir(dossier)) if dossier.exists() else []


def lire_operation(id_):
    return json.loads((chemins.operations() / f"{id_}.json").read_text("utf-8"))


# --- Dépôt -----------------------------------------------------------------------------------


def test_message_depose_puis_sync_sans_toucher_donnees(serveur, lances):
    avant = {k: v for k, v in empreinte().items() if k[0] == "donnees"}
    statut, objet = poster(serveur, "/api/message",
                           {"projet": "demo", "texte": "Relance la story 3.2", "pc": "pc-autre"})
    assert statut == 202
    donnees = objet["donnees"]
    id_ = ids.valider_id(donnees["id"])
    assert donnees == {"id": id_, "verbe": "deposer_message", "projet": "demo", "sync": "lance"}
    assert deposees() == [f"{id_}.json"]
    operation = lire_operation(id_)
    assert operation == {"schema": 1, "id": id_, "verbe": "deposer_message", "projet": "demo",
                         "texte": "Relance la story 3.2", "pc": "pc-autre"}
    schemas.valider("operation", operation)
    ((commande),) = lances
    assert commande[1:2] == ["-I"] and commande[-1] == "sync"
    assert {k: v for k, v in empreinte().items() if k[0] == "donnees"} == avant


def test_projets_depose_un_patch(serveur, lances):
    patch = {"pause": {"attendu": None, "voulu": "2026-12-01"}}
    statut, objet = poster(serveur, "/api/projets", {"projet": "demo", "patch": patch})
    assert statut == 202
    id_ = objet["donnees"]["id"]
    assert lire_operation(id_) == {
        "schema": 1, "id": id_, "verbe": "modifier_projets", "projet": "demo", "patch": patch,
    }
    assert len(lances) == 1


def test_cycle_occupe_operation_deposee_relance_en_file(serveur, lances, minuteurs):
    with impl.Verrou():
        statut, objet = poster(serveur, "/api/message", {"projet": "demo", "texte": "x"})
    assert (statut, objet["donnees"]["sync"]) == (202, "en_file")
    assert len(deposees()) == 1 and lances == []
    assert [m.delai for m in minuteurs] == [2]


def test_deux_messages_deux_operations_distinctes(serveur):
    for texte in ("un", "deux"):
        assert poster(serveur, "/api/message", {"projet": "demo", "texte": texte})[0] == 202
    assert len(deposees()) == 2


# --- Refus sans écriture ---------------------------------------------------------------------


def refuse(serveur, route, objet=None, brut=None):
    statut, reponse = poster(serveur, route, objet, brut)
    assert statut == 400, reponse
    assert reponse["ok"] is False
    assert deposees() == []
    return reponse["erreur"]


INJECTIONS = ["'; calc; '", "$(calc)", '"demo"', "demo\n", "demo\r\nx", "Demo", "..", "a/b"]


@pytest.mark.parametrize("valeur", INJECTIONS)
def test_identifiants_injectes_refuses(serveur, lances, valeur):
    assert refuse(serveur, "/api/message", {"projet": valeur, "texte": "x"}) == "projet invalide."
    assert refuse(serveur, "/api/message", {"projet": "demo", "texte": "x", "pc": valeur}) == (
        "pc invalide."
    )
    patch = {"exclu": {"attendu": False, "voulu": True}}
    assert refuse(serveur, "/api/projets", {"projet": valeur, "patch": patch}) == (
        "projet invalide."
    )
    assert lances == []


def test_message_de_2048_octets_accepte_2049_refuse(serveur):
    limite = EMOJI * 512
    assert len(limite.encode("utf-8")) == 2048
    trop = EMOJI * 511 + "abcde"
    assert len(trop.encode("utf-8")) == 2049
    assert refuse(serveur, "/api/message", {"projet": "demo", "texte": trop}) == (
        "Le message dépasse 2 048 octets UTF-8."
    )
    assert refuse(serveur, "/api/message", {"projet": "demo", "texte": EMOJI * 513}) == (
        "Le message dépasse 2 048 octets UTF-8."
    )
    statut, objet = poster(serveur, "/api/message", {"projet": "demo", "texte": limite})
    assert statut == 202
    assert lire_operation(objet["donnees"]["id"])["texte"] == limite


@pytest.mark.parametrize("texte", ["mon jeton ghp_abcdef123", "Bearer xyz", "s​k-123",
                                   "PASSWORD = hunter2"])
def test_message_avec_secret_refuse_jamais_altere(serveur, lances, texte):
    assert refuse(serveur, "/api/message", {"projet": "demo", "texte": texte}) == (
        "Le message contient ce qui ressemble à un secret."
    )
    assert lances == []


@pytest.mark.parametrize("texte", ["", "  \n\t", 12, None, ["x"]])
def test_message_vide_ou_non_texte_refuse(serveur, texte):
    assert refuse(serveur, "/api/message", {"projet": "demo", "texte": texte}) == (
        "Le message est vide."
    )


@pytest.mark.parametrize("brut,erreur", [
    (b"pas du json", "Corps JSON invalide."),
    (b"", "Corps JSON invalide."),
    (b"[]", "Corps JSON invalide."),
    (b"\xff\xfe", "Corps JSON invalide."),
    (b'{"projet": "demo", "projet": "demo", "texte": "x"}', "Corps JSON invalide."),
    (b'{"projet": "demo", "texte": NaN}', "Corps JSON invalide."),
    (b'{"projet": "demo"}', "Champ manquant : texte."),
    (b'{"projet": "demo", "texte": "x", "id": "20261106T101500Z-0a1b2c3d"}',
     "Champ inconnu : id."),
    (b'{"projet": "demo", "texte": "x", "verbe": "modifier_projets"}', "Champ inconnu : verbe."),
])
def test_corps_invalide_refuse(serveur, brut, erreur):
    assert refuse(serveur, "/api/message", brut=brut) == erreur


@pytest.mark.parametrize("patch", [
    {}, {"pause": {"attendu": None, "voulu": None}}, {"inconnu": {"attendu": 1, "voulu": 2}},
    {"exclu": {"attendu": "non", "voulu": True}}, "pause",
])
def test_patch_invalide_refuse(serveur, lances, patch):
    erreur = refuse(serveur, "/api/projets", {"projet": "demo", "patch": patch})
    assert erreur.startswith("Opération invalide : operation : ")
    assert lances == []


def test_projet_inconnu_refuse(serveur):
    assert refuse(serveur, "/api/message", {"projet": "fantome", "texte": "x"}) == (
        "Projet inconnu."
    )


def test_m10_etat_et_projets_yaml_ou_table(serveur):
    chemins.table_dossiers().unlink()  # `demo` reste dans l'état chargé, plus dans la table
    assert refuse(serveur, "/api/message", {"projet": "demo", "texte": "x"}) == "Projet inconnu."
    (chemins.donnees() / "projets.yaml").write_text(
        "schema: 1\nchantiers:\n  outils:\n    projets: [demo, fantome]\n", "utf-8"
    )
    # `fantome` est dans projets.yaml mais pas dans l'état chargé
    assert refuse(serveur, "/api/message", {"projet": "fantome", "texte": "x"}) == (
        "Projet inconnu."
    )
    assert poster(serveur, "/api/message", {"projet": "demo", "texte": "x"})[0] == 202


def test_pc_inconnu_refuse(serveur):
    assert refuse(serveur, "/api/message", {"projet": "demo", "texte": "x", "pc": "pc-x"}) == (
        "PC inconnu."
    )
    assert poster(serveur, "/api/message", {"projet": "demo", "texte": "x", "pc": "pc-test"})[0] \
        == 202


# --- Création seule --------------------------------------------------------------------------


def test_creer_n_ecrase_jamais(tmp_path):
    cible = tmp_path / "op" / "20261106T101500Z-0a1b2c3d.json"
    mutations.creer(cible, "premier")
    with pytest.raises(FileExistsError):
        mutations.creer(cible, "second")
    assert cible.read_text("utf-8") == "premier"
    assert sorted(p.name for p in cible.parent.iterdir()) == [cible.name]  # aucun .tmp laissé


def test_creer_sans_lien_physique_creation_exclusive(tmp_path, monkeypatch):
    def sans_lien(source, cible):
        raise OSError("liens physiques non pris en charge")

    monkeypatch.setattr(os, "link", sans_lien)
    cible = tmp_path / "20261106T101500Z-0a1b2c3d.json"
    mutations.creer(cible, "premier")
    with pytest.raises(FileExistsError):
        mutations.creer(cible, "second")
    assert cible.read_text("utf-8") == "premier"
    assert [p.name for p in tmp_path.iterdir()] == [cible.name]


# --- Matrice AD-14 des nouvelles routes ------------------------------------------------------


NOUVELLES = [("POST", "/api/message"), ("POST", "/api/projets"), ("GET", "/api/operations")]


@pytest.mark.parametrize("methode,route", NOUVELLES)
def test_matrice_ad14_nouvelles_routes(serveur, lances, methode, route):
    corps = json.dumps({"projet": "demo", "texte": "x"}).encode()
    cas = [
        ({}, 401),
        ({"jeton": "perime"}, 401),
        ({"jeton": serveur.jeton, "hote": "evil.example"}, 403),
        ({"jeton": serveur.jeton, "entetes": {"Origin": "http://evil.example"}}, 403),
    ]
    for options, attendu in cas:
        reponse, contenu = requete(serveur, methode, route, corps=corps, **options)
        assert reponse.status == attendu, options
        assert _json(contenu)["ok"] is False
    autre = "GET" if methode == "POST" else "POST"
    reponse, _ = requete(serveur, autre, route, corps=corps, jeton=serveur.jeton)
    assert (reponse.status, reponse.getheader("Allow")) == (405, methode)
    reponse, _ = requete(serveur, methode, route, corps=b"x" * (64 * 1024 + 1),
                         jeton=serveur.jeton)
    assert reponse.status == 413
    assert deposees() == [] and lances == []


# --- Revue : écriture en échec, substitut, chantier ------------------------------------------


def _fsync_en_echec(descripteur):
    raise OSError("disque plein")


@pytest.mark.parametrize("avec_lien", [True, False])
def test_creer_ecriture_en_echec_ne_laisse_rien(tmp_path, monkeypatch, avec_lien):
    if not avec_lien:
        monkeypatch.setattr(os, "link", lambda s, c: (_ for _ in ()).throw(OSError("sans lien")))
    monkeypatch.setattr(os, "fsync", _fsync_en_echec)
    cible = tmp_path / "20261106T101500Z-0a1b2c3d.json"
    with pytest.raises(OSError):
        mutations.creer(cible, "contenu")
    assert list(tmp_path.iterdir()) == []


def test_creer_sans_lien_remplacement_en_echec_retire_la_reservation(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "link", lambda s, c: (_ for _ in ()).throw(OSError("sans lien")))

    def replace_en_echec(source, cible):
        assert os.path.getsize(cible) == 0  # réservation vide, jamais un contenu tronqué
        raise PermissionError("verrouillé")

    monkeypatch.setattr(os, "replace", replace_en_echec)
    cible = tmp_path / "20261106T101500Z-0a1b2c3d.json"
    with pytest.raises(PermissionError):
        mutations.creer(cible, "contenu")
    assert list(tmp_path.iterdir()) == []


def test_creer_sans_lien_reservation_lue_par_sync_reessaie(tmp_path, monkeypatch):
    # Sous Windows, `sync` qui lit la réservation vide la verrouille : `os.replace` est refusé
    # un instant (PermissionError, constaté sur NTFS) ; l'opération est publiée quand même.
    monkeypatch.setattr(os, "link", lambda s, c: (_ for _ in ()).throw(OSError("sans lien")))
    monkeypatch.setattr(mutations.time, "sleep", lambda _s: None)
    vrai_replace, refus = os.replace, []

    def replace_verrouille_une_fois(source, cible):
        if not refus:
            refus.append(cible)
            raise PermissionError("ouvert par sync")
        vrai_replace(source, cible)

    monkeypatch.setattr(os, "replace", replace_verrouille_une_fois)
    cible = tmp_path / "20261106T101500Z-0a1b2c3d.json"
    mutations.creer(cible, "contenu")
    assert refus and cible.read_text(encoding="utf-8") == "contenu"
    assert list(tmp_path.iterdir()) == [cible]


def test_ecriture_impossible_rend_503_sans_trace_ni_sync(serveur, lances, monkeypatch):
    monkeypatch.setattr(os, "fsync", _fsync_en_echec)
    statut, reponse = poster(serveur, "/api/message", {"projet": "demo", "texte": "x"})
    assert (statut, reponse["erreur"]) == (503, mutations.ERREUR_ECRITURE)
    assert deposees() == [] and lances == []
    journal = chemins.journal_enfants(enfants._maintenant()[:7]).read_text("utf-8")
    assert "opération non écrite : OSError" in journal


def test_substitut_isole_message_exact(serveur):
    brut = rb'{"projet": "demo", "texte": "a\ud800b"}'
    assert refuse(serveur, "/api/message", brut=brut) == mutations.ERREUR_CARACTERE


def test_chantier_inconnu_refuse_tot(serveur, lances):
    (chemins.donnees() / "projets.yaml").write_text(
        "schema: 1\nchantiers:\n  outils:\n    projets: [demo]\n", "utf-8"
    )
    patch = {"chantier": {"attendu": "outils", "voulu": "fantome"}}
    assert refuse(serveur, "/api/projets", {"projet": "demo", "patch": patch}) == (
        "Chantier inconnu."
    )
    patch = {"chantier": {"attendu": "outils", "voulu": None}}
    assert poster(serveur, "/api/projets", {"projet": "demo", "patch": patch})[0] == 202
