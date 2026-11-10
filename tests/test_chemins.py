import json
import os
from pathlib import Path

import pytest

from pilotage import chemins


def test_racine_locale_redirige_tout(racine_locale_isolee):
    r = racine_locale_isolee
    assert chemins.racine_locale() == r
    assert chemins.attente() == r / "attente"
    assert chemins.donnees() == r / "donnees"
    assert chemins.table_dossiers() == r / "table-dossiers.json"
    assert chemins.racine_installation() == r / "installation"
    assert chemins.chemin_config() == r / "installation" / "config.json"


def test_racine_locale_ignore_config(racine_locale_isolee):
    config = racine_locale_isolee / "installation" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"attente": "C:/ailleurs"}), encoding="utf-8")
    assert chemins.lire_config() == {}
    assert chemins.attente() == racine_locale_isolee / "attente"


@pytest.fixture
def sans_racine(monkeypatch, tmp_path):
    monkeypatch.delenv("PILOTAGE_RACINE_LOCALE")
    return tmp_path / "profil"


def test_defauts_sans_config(sans_racine):
    locale = sans_racine / "AppData" / "Local" / "pilotage-projets"
    installation = sans_racine / ".claude" / "pilotage"
    assert chemins.chemin_config() == installation / "config.json"
    assert chemins.racine_locale() == locale
    assert chemins.attente() == locale / "attente"
    assert chemins.donnees() == locale / "donnees"
    assert chemins.table_dossiers() == locale / "table-dossiers.json"
    assert chemins.racine_installation() == installation


def test_variable_vide_vaut_absente(monkeypatch, sans_racine):
    monkeypatch.setenv("PILOTAGE_RACINE_LOCALE", "")
    assert chemins.racine_locale() == sans_racine / "AppData" / "Local" / "pilotage-projets"


def test_localappdata_absent(monkeypatch, sans_racine):
    monkeypatch.delenv("LOCALAPPDATA")
    assert chemins.racine_locale() == sans_racine / "AppData" / "Local" / "pilotage-projets"


def _ecrire_config(profil: Path, contenu: str) -> None:
    config = profil / ".claude" / "pilotage" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(contenu, encoding="utf-8")


def test_config_lue(sans_racine, tmp_path):
    locale, inst, att = tmp_path / "L", tmp_path / "I", tmp_path / "A"
    _ecrire_config(
        sans_racine,
        json.dumps(
            {
                "racine_locale": str(locale),
                "racine_installation": str(inst),
                "attente": str(att),
                "inconnue": 3,
            }
        ),
    )
    assert chemins.racine_locale() == locale
    assert chemins.racine_installation() == inst
    assert chemins.attente() == att
    assert chemins.donnees() == locale / "donnees"
    assert chemins.table_dossiers() == locale / "table-dossiers.json"


@pytest.mark.parametrize(
    ("contenu", "attendu"),
    [
        ("{pas du json", "JSON invalide"),
        ("[1, 2]", "un objet JSON est attendu"),
        ('{"donnees": 3}', "'donnees' doit être un chemin non vide"),
        ('{"attente": ""}', "'attente' doit être un chemin non vide"),
    ],
)
def test_config_invalide(sans_racine, contenu, attendu):
    _ecrire_config(sans_racine, contenu)
    with pytest.raises(chemins.ErreurConfiguration, match=attendu) as exc:
        chemins.attente()
    assert "config.json" in str(exc.value)


CLES_CHEMIN = sorted(chemins.CLES_CONFIG)


@pytest.mark.parametrize("cle", CLES_CHEMIN)
@pytest.mark.parametrize("valeur", ["attente", "./x", "../x"])
def test_config_chemin_relatif_refuse(sans_racine, cle, valeur):
    _ecrire_config(sans_racine, json.dumps({cle: valeur}))
    with pytest.raises(chemins.ErreurConfiguration) as exc:
        chemins.lire_config()
    assert f"{cle!r} doit être un chemin absolu" in str(exc.value)
    assert "config.json" in str(exc.value)


@pytest.mark.skipif(os.name != "nt", reason="chemins Windows")
@pytest.mark.parametrize("valeur", ["C:foo", "\\foo", "/foo"])
def test_config_chemin_windows_non_absolu_refuse(sans_racine, valeur):
    _ecrire_config(sans_racine, json.dumps({"attente": valeur}))
    with pytest.raises(chemins.ErreurConfiguration, match="'attente' doit être un chemin absolu"):
        chemins.attente()


@pytest.mark.parametrize("cle", CLES_CHEMIN)
def test_config_chemin_absolu_accepte(sans_racine, tmp_path, cle):
    _ecrire_config(sans_racine, json.dumps({cle: str(tmp_path / "x")}))
    assert chemins.lire_config() == {cle: str(tmp_path / "x")}


@pytest.mark.parametrize("cle", CLES_CHEMIN)
def test_config_tilde_developpe(sans_racine, cle):
    _ecrire_config(sans_racine, json.dumps({cle: "~/x"}))
    assert chemins.lire_config() == {cle: str(Path.home() / "x")}


def test_config_tilde_sous_racine(sans_racine):
    _ecrire_config(sans_racine, json.dumps({"attente": "~/att"}))
    assert chemins.attente() == Path.home() / "att"


def test_config_utf16_refusee(sans_racine):
    config = sans_racine / ".claude" / "pilotage" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"attente": "C:/a"}', encoding="utf-16")
    with pytest.raises(chemins.ErreurConfiguration, match="encodage non UTF-8"):
        chemins.attente()


def test_config_dossier_refuse(sans_racine):
    (sans_racine / ".claude" / "pilotage" / "config.json").mkdir(parents=True)
    with pytest.raises(chemins.ErreurConfiguration, match="illisible"):
        chemins.attente()


def test_config_utf8_avec_bom_acceptee(sans_racine):
    config = sans_racine / ".claude" / "pilotage" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"attente": "C:/a"}', encoding="utf-8-sig")
    assert chemins.attente() == Path("C:/a")


def _restes_tmp(dossier: Path) -> list[Path]:
    return [p for p in dossier.rglob("*") if p.name.endswith(".tmp")]


def test_ecrire_atomique_utf8_sans_bom_lf(racine_locale_isolee):
    cible = chemins.attente() / "etat" / "projet" / "pc" / "s.json"
    chemins.ecrire_atomique(cible, "élan\nligne 2\n")
    assert cible.read_bytes() == "élan\nligne 2\n".encode()
    assert not cible.read_bytes().startswith(b"\xef\xbb\xbf")
    assert _restes_tmp(racine_locale_isolee) == []


def test_ecrire_atomique_remplace(racine_locale_isolee):
    cible = racine_locale_isolee / "f.json"
    chemins.ecrire_atomique(cible, "un")
    chemins.ecrire_atomique(cible, "deux")
    assert cible.read_text(encoding="utf-8") == "deux"
    assert sorted(p.name for p in racine_locale_isolee.iterdir()) == ["f.json"]


def test_ecrire_atomique_echec_sans_tmp(racine_locale_isolee):
    cible = racine_locale_isolee / "dossier"
    (cible / "occupe").mkdir(parents=True)
    with pytest.raises(OSError):
        chemins.ecrire_atomique(cible, "x")
    assert _restes_tmp(racine_locale_isolee) == []
    assert cible.is_dir()


def test_racine_github_et_interrupteur_sous_racine(racine_locale_isolee):
    assert chemins.racine_github() == racine_locale_isolee / "github"
    assert chemins.fichier_desactive() == racine_locale_isolee / "installation" / "desactive"


def test_racine_github_par_defaut(sans_racine):
    assert chemins.racine_github() == sans_racine / "Documents" / "GitHub"
    assert chemins.fichier_desactive() == sans_racine / ".claude" / "pilotage" / "desactive"


def test_racine_github_configuree(sans_racine, tmp_path):
    _ecrire_config(sans_racine, json.dumps({"racine_github": str(tmp_path / "depots")}))
    assert chemins.racine_github() == tmp_path / "depots"
    # L'interrupteur ne dépend pas de la config (vérifié avant toute lecture).
    assert chemins.fichier_desactive() == sans_racine / ".claude" / "pilotage" / "desactive"


def test_racine_github_configuree_tilde(sans_racine):
    _ecrire_config(sans_racine, json.dumps({"racine_github": "~/depots"}))
    assert chemins.racine_github() == Path.home() / "depots"


def test_port_par_defaut(racine_locale_isolee, sans_racine):
    assert chemins.port_serveur() == chemins.PORT_PAR_DEFAUT == 47615


def test_port_lu_dans_la_config(sans_racine):
    _ecrire_config(sans_racine, json.dumps({"port": 8123}))
    assert chemins.lire_config() == {"port": 8123}
    assert chemins.port_serveur() == 8123


@pytest.mark.parametrize("port", ["8123", 0, 65536, True, 12.5, None])
def test_port_invalide(sans_racine, port):
    _ecrire_config(sans_racine, json.dumps({"port": port}))
    with pytest.raises(chemins.ErreurConfiguration, match="'port' doit être un entier"):
        chemins.port_serveur()


def test_port_ignore_sous_racine_locale(racine_locale_isolee):
    config = racine_locale_isolee / "installation" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"port": 8123}), encoding="utf-8")
    assert chemins.port_serveur() == chemins.PORT_PAR_DEFAUT


def test_chemins_du_serveur(racine_locale_isolee):
    r = racine_locale_isolee
    assert chemins.appli_pid() == r / "attente" / "appli.pid"
    assert chemins.journal_serveur("2026-11") == r / "attente" / "journal" / "serveur-2026-11.log"
    assert chemins.racine_web() == Path(chemins.__file__).resolve().parent / "web"
    assert (chemins.racine_web() / "charte.css").is_file()


def test_creer_exclusif_cree_sans_ecraser(tmp_path):
    chemin = tmp_path / "boite" / "p" / "x.lu.pc"
    assert chemins.creer_exclusif(chemin, "é\n") is True
    assert chemin.read_bytes() == "é\n".encode()  # UTF-8, sans BOM ni CRLF
    assert chemins.creer_exclusif(chemin, "autre") is False
    assert chemin.read_bytes() == "é\n".encode()
    assert sorted(p.name for p in chemin.parent.iterdir()) == ["x.lu.pc"]  # aucun .tmp


def test_boites_sous_la_racine(racine_locale_isolee):
    assert chemins.boite_attente() == racine_locale_isolee / "attente" / "boite"
    assert chemins.boite_donnees() == racine_locale_isolee / "donnees" / "boite"


@pytest.mark.parametrize("valeur", ["~bob", "~bob/x", r"~x\y"])
def test_config_tilde_utilisateur_refuse(sans_racine, valeur):
    _ecrire_config(sans_racine, json.dumps({"attente": valeur}))
    with pytest.raises(chemins.ErreurConfiguration, match="seul `~` ou `~/`"):
        chemins.lire_config()


@pytest.mark.parametrize("valeur", ["~", pytest.param(r"~\x", marks=pytest.mark.skipif(
    os.name != "nt", reason="séparateur Windows"))])
def test_config_tilde_seul_ou_antislash_accepte(sans_racine, valeur):
    _ecrire_config(sans_racine, json.dumps({"racine_github": valeur}))
    assert chemins.racine_github() == Path.home() / valeur[2:]


def test_attente_de_secours_ne_lit_pas_la_config(sans_racine):
    _ecrire_config(sans_racine, json.dumps({"attente": "relatif"}))
    locale = sans_racine / "AppData" / "Local" / "pilotage-projets"
    assert chemins.attente_de_secours() == locale / "attente"
