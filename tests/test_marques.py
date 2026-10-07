from gestionnaire.marques import trouver


def test_noms_reconnus():
    assert trouver("Discord")[0] == "discord"
    assert trouver("https://www.netflix.com/login")[0] == "netflix"
    assert trouver("Compte Steam perso")[0] == "steam"
    assert trouver("Twitter")[0] == "x"


def test_marque_sans_logo_garde_sa_couleur():
    assert trouver("Amazon") == (None, "FF9900")


def test_nom_inconnu():
    assert trouver("Mon site perso") is None
    assert trouver("") is None
