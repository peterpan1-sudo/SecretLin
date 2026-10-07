import pytest

import json

from gestionnaire import coffre as module
from gestionnaire.coffre import Coffre, MotDePasseIncorrect, generer_mot_de_passe, verifier_force


@pytest.fixture(autouse=True)
def argon2_rapide(monkeypatch):
    monkeypatch.setattr(module, "ARGON2_MEMOIRE_KIO", 8 * 1024)
    monkeypatch.setattr(module, "ARGON2_ITERATIONS", 1)


def test_creer_ajouter_rouvrir(tmp_path):
    c = Coffre(tmp_path / "c.vault")
    c.creer("MotDePasse!2026x")
    c.ajouter("netflix", "moi@mail.com", "abc")
    c.ajouter("Amazon", "moi", "def")
    c2 = Coffre(tmp_path / "c.vault")
    c2.ouvrir("MotDePasse!2026x")
    assert [e["site"] for e in c2.entrees] == ["Amazon", "netflix"]
    assert b"netflix" not in (tmp_path / "c.vault").read_bytes()


def test_mauvais_mot_de_passe(tmp_path):
    c = Coffre(tmp_path / "c.vault")
    c.creer("MotDePasse!2026x")
    with pytest.raises(MotDePasseIncorrect):
        Coffre(tmp_path / "c.vault").ouvrir("mauvais")


def test_modification_du_fichier_detectee(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer("MotDePasse!2026x")
    c.ajouter("site", "u", "p")
    contenu = chemin.read_text().replace('"iterations": 1', '"iterations": 2')
    chemin.write_text(contenu)
    with pytest.raises(MotDePasseIncorrect):
        Coffre(chemin).ouvrir("MotDePasse!2026x")


def test_changer_mot_de_passe_preserve_les_entrees(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer("MotDePasse!2026x")
    c.ajouter("netflix", "moi@mail.com", "abc")
    c.ajouter("Amazon", "moi", "def")

    c.changer_mot_de_passe("NouveauPass!2027y")

    # Les entrées sont intactes et lisibles avec le nouveau mot de passe.
    rouvert = Coffre(chemin)
    rouvert.ouvrir("NouveauPass!2027y")
    assert [(e["site"], e["mot_de_passe"]) for e in rouvert.entrees] == [
        ("Amazon", "def"), ("netflix", "abc")]
    # L'ancien mot de passe ne déverrouille plus rien.
    with pytest.raises(MotDePasseIncorrect):
        Coffre(chemin).ouvrir("MotDePasse!2026x")


def test_alteration_des_donnees_detectee(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer("MotDePasse!2026x")
    c.ajouter("site", "u", "p")

    # On retourne un octet du corps chiffré : l'authentification GCM doit échouer.
    contenu = json.loads(chemin.read_text())
    brut = bytearray(module._deb64(contenu["donnees"]))
    brut[0] ^= 0x01
    contenu["donnees"] = module._b64(bytes(brut))
    chemin.write_text(json.dumps(contenu))

    with pytest.raises(MotDePasseIncorrect):
        Coffre(chemin).ouvrir("MotDePasse!2026x")


def test_modifier_supprimer(tmp_path):
    c = Coffre(tmp_path / "c.vault")
    c.creer("MotDePasse!2026x")
    c.ajouter("site", "u", "p")
    id_ = c.entrees[0]["id"]
    c.modifier(id_, mot_de_passe="nouveau")
    assert c.entrees[0]["mot_de_passe"] == "nouveau"
    c.supprimer(id_)
    assert c.entrees == []


def test_generateur_et_force():
    mdp = generer_mot_de_passe()
    assert len(mdp) == 20 and verifier_force(mdp) == []
    assert verifier_force("court") != []


def test_email_separe_des_anciennes_entrees(tmp_path):
    c = Coffre(tmp_path / "c.vault")
    c.creer("MotDePasse!2026x")
    c.entrees = [{"id": "1", "site": "a", "utilisateur": "moi@mail.com", "mot_de_passe": "p", "notes": ""},
                 {"id": "2", "site": "b", "utilisateur": "pseudo", "mot_de_passe": "p", "notes": ""}]
    c.sauvegarder()
    c.ouvrir("MotDePasse!2026x")
    assert (c.entrees[0]["utilisateur"], c.entrees[0]["email"]) == ("", "moi@mail.com")
    assert (c.entrees[1]["utilisateur"], c.entrees[1]["email"]) == ("pseudo", "")
    c.ajouter("c", "joueur", "p", email="j@mail.com")
    assert c.entrees[2]["email"] == "j@mail.com"
