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


MAITRE = "MotDePasse!2026x"
EXPORT = "ExportSecret!2027z"


def test_sauvegarde_avant_chaque_ecriture(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer(MAITRE)
    # Premier enregistrement : rien à sauvegarder encore.
    assert not c.a_une_sauvegarde()

    c.ajouter("netflix", "moi", "abc")
    avant = chemin.read_text()
    c.ajouter("Amazon", "moi", "def")

    # La copie contient la version d'avant la dernière écriture, toujours chiffrée.
    assert c.chemin_sauvegarde.read_text() == avant
    assert b"netflix" not in c.chemin_sauvegarde.read_bytes()
    copie = Coffre(c.chemin_sauvegarde)
    copie.ouvrir(MAITRE)
    assert [e["site"] for e in copie.entrees] == ["netflix"]


def test_sauvegarde_permissions_privees(tmp_path):
    if module.sys.platform == "win32":
        pytest.skip("permissions POSIX")
    c = Coffre(tmp_path / "c.vault")
    c.creer(MAITRE)
    c.ajouter("site", "u", "p")
    assert c.chemin_sauvegarde.stat().st_mode & 0o777 == 0o600


def test_restaurer_sauvegarde(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer(MAITRE)
    c.ajouter("site", "u", "p")
    c.supprimer(c.entrees[0]["id"])  # erreur de manipulation

    c.restaurer_sauvegarde(MAITRE)
    assert [e["site"] for e in c.entrees] == ["site"]
    rouvert = Coffre(chemin)
    rouvert.ouvrir(MAITRE)
    assert [e["site"] for e in rouvert.entrees] == ["site"]

    # Restaurer une seconde fois annule la restauration.
    c.restaurer_sauvegarde(MAITRE)
    assert c.entrees == []


def test_restaurer_sauvegarde_mauvais_mot_de_passe_ne_touche_a_rien(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer(MAITRE)
    c.ajouter("site", "u", "p")
    avant = chemin.read_text()
    with pytest.raises(MotDePasseIncorrect):
        c.restaurer_sauvegarde("mauvais")
    assert chemin.read_text() == avant


def test_export_import_aller_retour(tmp_path):
    source = Coffre(tmp_path / "a.vault")
    source.creer(MAITRE)
    source.ajouter("netflix", "moi", "abc", notes="perso", email="moi@mail.com")
    source.ajouter("Amazon", "moi", "def")
    export = tmp_path / "export.secretlin"
    source.exporter(export, EXPORT)

    # Le fichier exporté est chiffré et ne s'ouvre pas avec le mot de passe maître.
    assert b"netflix" not in export.read_bytes()
    with pytest.raises(MotDePasseIncorrect):
        Coffre(export).ouvrir(MAITRE)

    cible = Coffre(tmp_path / "b.vault")
    cible.creer("AutreMaitre!2028w")
    assert cible.importer(export, EXPORT) == 2
    rouvert = Coffre(tmp_path / "b.vault")
    rouvert.ouvrir("AutreMaitre!2028w")
    assert [(e["site"], e["mot_de_passe"], e["email"], e["notes"]) for e in rouvert.entrees] == [
        ("Amazon", "def", "", ""), ("netflix", "abc", "moi@mail.com", "perso")]


def test_import_ignore_les_doublons_et_fusionne(tmp_path):
    c = Coffre(tmp_path / "c.vault")
    c.creer(MAITRE)
    c.ajouter("netflix", "moi", "abc")
    export = tmp_path / "export.secretlin"
    c.exporter(export, EXPORT)

    # Réimporter dans le même coffre n'ajoute rien.
    assert c.importer(export, EXPORT) == 0
    # Une entrée modifiée depuis l'export est conservée, l'ancienne version revient à côté.
    c.modifier(c.entrees[0]["id"], mot_de_passe="nouveau")
    assert c.importer(export, EXPORT) == 1
    assert sorted(e["mot_de_passe"] for e in c.entrees) == ["abc", "nouveau"]
    assert len({e["id"] for e in c.entrees}) == 2


def test_import_mauvais_mot_de_passe(tmp_path):
    c = Coffre(tmp_path / "c.vault")
    c.creer(MAITRE)
    c.ajouter("site", "u", "p")
    export = tmp_path / "export.secretlin"
    c.exporter(export, EXPORT)
    with pytest.raises(MotDePasseIncorrect):
        c.importer(export, "Mauvais!2026xx")
    assert len(c.entrees) == 1


def test_import_fichier_corrompu(tmp_path):
    c = Coffre(tmp_path / "c.vault")
    c.creer(MAITRE)
    faux = tmp_path / "faux.secretlin"
    faux.write_text("pas du json")
    with pytest.raises(module.CoffreCorrompu):
        c.importer(faux, EXPORT)


def test_export_refuse_mot_de_passe_faible_et_coffre_verrouille(tmp_path):
    c = Coffre(tmp_path / "c.vault")
    c.creer(MAITRE)
    with pytest.raises(ValueError):
        c.exporter(tmp_path / "e.secretlin", "faible")
    assert not (tmp_path / "e.secretlin").exists()
    c.verrouiller()
    with pytest.raises(RuntimeError):
        c.exporter(tmp_path / "e.secretlin", EXPORT)
    with pytest.raises(RuntimeError):
        c.importer(tmp_path / "e.secretlin", EXPORT)


def test_copie_a_chaque_deverrouillage(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer(MAITRE)
    c.ajouter("site", "u", "p")
    assert c.copies_ouverture() == []

    Coffre(chemin).ouvrir(MAITRE)
    copies = c.copies_ouverture()
    assert len(copies) == 1
    assert copies[0].read_text() == chemin.read_text()
    assert c.date_copie(copies[0]) is not None
    if module.sys.platform != "win32":
        assert copies[0].stat().st_mode & 0o777 == 0o600
        assert c.dossier_copies.stat().st_mode & 0o777 == 0o700

    # Coffre inchangé depuis la dernière copie : pas de doublon.
    Coffre(chemin).ouvrir(MAITRE)
    assert len(c.copies_ouverture()) == 1


def test_copies_ouverture_limitees(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer(MAITRE)
    for i in range(module.NB_COPIES_OUVERTURE + 3):
        c.ajouter(f"site{i}", "u", "p")
        Coffre(chemin).ouvrir(MAITRE)
    copies = c.copies_ouverture()
    assert len(copies) == module.NB_COPIES_OUVERTURE
    # La plus récente correspond au coffre actuel.
    recente = Coffre(copies[0])
    recente.ouvrir(MAITRE)
    assert len(recente.entrees) == module.NB_COPIES_OUVERTURE + 3


def test_pas_de_copie_si_mot_de_passe_incorrect(tmp_path):
    chemin = tmp_path / "c.vault"
    Coffre(chemin).creer(MAITRE)
    with pytest.raises(MotDePasseIncorrect):
        Coffre(chemin).ouvrir("mauvais")
    assert Coffre(chemin).copies_ouverture() == []


def test_restaurer_copie_ouverture(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer(MAITRE)
    c.ajouter("garder", "u", "p")
    c = Coffre(chemin)
    c.ouvrir(MAITRE)  # copie faite ici
    copie = c.copies_ouverture()[0]
    c.supprimer(c.entrees[0]["id"])
    c.ajouter("autre", "u", "p")  # la copie .bak ne contient plus « garder »

    c.restaurer_sauvegarde(MAITRE, copie)
    assert [e["site"] for e in c.entrees] == ["garder"]
    # Le coffre d'avant la restauration reste récupérable.
    c.restaurer_sauvegarde(MAITRE)
    assert [e["site"] for e in c.entrees] == ["autre"]


def test_changer_mot_de_passe_rechiffre_les_copies(tmp_path):
    chemin = tmp_path / "c.vault"
    c = Coffre(chemin)
    c.creer(MAITRE)
    c.ajouter("site1", "u", "p")
    Coffre(chemin).ouvrir(MAITRE)  # copie dans sauvegardes/
    c.ajouter("site2", "u", "p")   # .bak = coffre avec site1 seulement
    # Copie d'un ancien mot de passe, dont la clé n'est plus connue.
    autre = Coffre(tmp_path / "autre.vault")
    autre.creer("TresAncien!2020z")
    vieille = c.dossier_copies / "coffre-20200101-000000-000000.vault"
    vieille.write_text((tmp_path / "autre.vault").read_text())

    c.changer_mot_de_passe("NouveauPass!2027y")

    copies = c.copies_ouverture()
    assert vieille not in copies
    assert len(copies) == 1
    for copie in [c.chemin_sauvegarde, *copies]:
        with pytest.raises(MotDePasseIncorrect):
            Coffre(copie).ouvrir(MAITRE)
        if module.sys.platform != "win32":
            assert copie.stat().st_mode & 0o777 == 0o600
    # Les copies gardent leur contenu et s'ouvrent avec le nouveau mot de passe.
    bak = Coffre(c.chemin_sauvegarde)
    bak.ouvrir("NouveauPass!2027y")
    assert [e["site"] for e in bak.entrees] == ["site1", "site2"]
    c.restaurer_sauvegarde("NouveauPass!2027y", copies[0])
    assert [e["site"] for e in c.entrees] == ["site1"]


def test_compteur_echecs_garde_entre_deux_lancements(tmp_path):
    import time
    c = Coffre(tmp_path / "c.vault")
    assert c.lire_echecs() == (0, 0.0)
    fin = time.time() + 8
    c.noter_echecs(4, fin)
    assert Coffre(tmp_path / "c.vault").lire_echecs() == (4, fin)
    c.noter_echecs(0)
    assert not c.chemin_echecs.exists()
    assert c.lire_echecs() == (0, 0.0)


def test_compteur_echecs_illisible_ou_horloge_reculee(tmp_path):
    import time
    c = Coffre(tmp_path / "c.vault")
    c.chemin_echecs.write_text("pas du json")
    assert c.lire_echecs() == (0, 0.0)
    c.noter_echecs(9, time.time() + 10_000)
    _echecs, fin = c.lire_echecs()
    assert fin <= time.time() + module.ATTENTE_MAX
