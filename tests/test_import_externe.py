import pytest

from gestionnaire import import_externe
from gestionnaire.coffre import Coffre

EXEMPLES = {
    "Firefox": ('"url","username","password","httpRealm","formActionOrigin","guid",'
                '"timeCreated","timeLastUsed","timePasswordChanged"\n'
                '"https://www.netflix.com","moi@mail.fr","Secret-1","","https://www.netflix.com",'
                '"{1}","1","1","1"\n'),
    "Chrome": ("name,url,username,password,note\n"
               "netflix.com,https://www.netflix.com/login,moi@mail.fr,Secret-1,\n"),
    "Bitwarden": ("folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
                  "login_password,login_totp\n"
                  ",,login,Netflix,ma note,,0,https://www.netflix.com,moi@mail.fr,Secret-1,\n"
                  ",,note,Note sécurisée,texte,,0,,,,\n"),
    "KeePass": ('"Group","Title","Username","Password","URL","Notes","TOTP","Icon",'
                '"Last Modified","Created"\n'
                '"Racine","Netflix","moi@mail.fr","Secret-1","https://www.netflix.com","","","0",'
                '"",""\n'),
    "1Password": ("Title,Url,Username,Password,OTPAuth,Favorite,Archived,Tags,Notes\n"
                  "Netflix,https://www.netflix.com,moi@mail.fr,Secret-1,,false,false,,\n"),
    "LastPass": ("url,username,password,totp,extra,name,grouping,fav\n"
                 "https://www.netflix.com,moi@mail.fr,Secret-1,,,Netflix,Divertissement,0\n"),
}


@pytest.mark.parametrize("source", EXEMPLES)
def test_chaque_source_est_reconnue(tmp_path, source):
    chemin = tmp_path / "export.csv"
    chemin.write_text("﻿" + EXEMPLES[source], encoding="utf-8")
    trouvee, entrees = import_externe.lire(chemin)
    assert trouvee == source
    assert len(entrees) == 1
    e = entrees[0]
    assert e["site"].casefold() in ("netflix", "netflix.com")
    assert (e["utilisateur"], e["email"], e["mot_de_passe"]) == ("", "moi@mail.fr", "Secret-1")


def test_adresse_gardee_dans_les_notes(tmp_path):
    chemin = tmp_path / "bw.csv"
    chemin.write_text(EXEMPLES["Bitwarden"], encoding="utf-8")
    _, [e] = import_externe.lire(chemin)
    assert e["notes"] == "https://www.netflix.com\nma note"


def test_fichier_non_reconnu(tmp_path):
    chemin = tmp_path / "autre.csv"
    chemin.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(import_externe.FormatInconnu):
        import_externe.lire(chemin)
    chemin.write_text("", encoding="utf-8")
    with pytest.raises(import_externe.FormatInconnu):
        import_externe.lire(chemin)


def test_nom_depuis_url():
    assert import_externe.nom_depuis_url("https://www.netflix.com/login") == "netflix.com"
    assert import_externe.nom_depuis_url("accounts.google.com") == "accounts.google.com"
    assert import_externe.nom_depuis_url("") == ""


def test_ajout_au_coffre_sans_doublons(tmp_path):
    c = Coffre(tmp_path / "coffre.vault")
    c.creer("Maitre-Tres-Solide-42!")
    c.ajouter("Netflix", "", "Secret-1", email="moi@mail.fr")
    entrees = [dict(site="netflix", utilisateur="", email="MOI@mail.fr", mot_de_passe="Secret-1"),
               dict(site="Steam", utilisateur="joueur", email="", mot_de_passe="Autre-2", notes=""),
               dict(site="Steam", utilisateur="joueur", email="", mot_de_passe="Autre-2", notes="")]
    assert c.ajouter_externes(entrees) == (1, 2)
    assert [e["site"] for e in c.entrees] == ["Netflix", "Steam"]
    c.verrouiller()
    c.ouvrir("Maitre-Tres-Solide-42!")
    assert c.entrees[1]["utilisateur"] == "joueur" and c.entrees[1]["change_le"]


def test_cle_2fa_importee(tmp_path):
    chemin = tmp_path / "bw.csv"
    chemin.write_text("folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
                      "login_password,login_totp\n"
                      "Jeux,1,login,Steam,,,0,,joueur,Secret-1,JBSWY3DPEHPK3PXP\n"
                      ",,login,Autre,,,0,,moi,Secret-2,steam://pas-pris-en-charge\n", encoding="utf-8")
    _, (steam, autre) = import_externe.lire(chemin)
    assert (steam["totp"], steam["categorie"], steam["favori"]) == ("JBSWY3DPEHPK3PXP", "Jeux", True)
    assert autre["totp"] == ""
