import pytest

from gestionnaire import acces_rapide, guichet, porte
from gestionnaire.coffre import Coffre


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Interface:
    def __init__(self, pin="1234"):
        self.ouvert = False
        self.code = acces_rapide.nouveau_pin(pin) if pin else None
        self.copies, self.verrouillages, self.montre = [], 0, False

    def ecran_ouvert(self):
        return self.ouvert

    def pin(self):
        return self.code

    def copier(self, texte, champ):
        self.copies.append((texte, champ))

    def verrouiller(self):
        self.verrouillages += 1

    def montrer(self):
        self.montre = True


@pytest.fixture
def coffre(tmp_path):
    c = Coffre(tmp_path / "coffre.vault")
    c.creer("Maitre-Tres-Solide-42!")
    c.ajouter("Discord", "alexm", "mdp-discord", totp="JBSWY3DPEHPK3PXP")
    c.ajouter("Netflix", "", "mdp-netflix", email="alex@mail.fr")
    return c


def test_pin_enregistre_sans_le_code_en_clair():
    enregistre = acces_rapide.nouveau_pin("0042")
    assert "0042" not in str(enregistre)
    assert acces_rapide.verifier_pin("0042", enregistre)
    assert not acces_rapide.verifier_pin("0043", enregistre)
    assert not acces_rapide.verifier_pin("0042", None)
    for mauvais in ("123", "12345", "abcd", "١٢٣٤"):
        assert not acces_rapide.pin_valide(mauvais)
        with pytest.raises(ValueError):
            acces_rapide.nouveau_pin(mauvais)


def test_session_jetons_et_duree():
    h = Horloge()
    s = acces_rapide.Session(h)
    assert s.expiree()
    s.demarrer()
    jeton, _ = s.essayer("1234", acces_rapide.nouveau_pin("1234"))
    assert s.jeton_valide(jeton) and not s.jeton_valide("autre") and not s.jeton_valide(None)
    h.t += acces_rapide.DUREE_JETON_S + 1
    assert not s.jeton_valide(jeton)
    h.t += acces_rapide.DUREE_MAX_S
    assert s.expiree()


def test_guichet_ferme_ne_donne_rien(coffre):
    i = Interface()
    g = guichet.Guichet(coffre, acces_rapide.Session(), i)  # session jamais démarrée
    assert g.traiter({"action": "etat"}) == {"etat": "ferme", "pin": True}
    assert g.traiter({"action": "chercher", "texte": ""}) == {"erreur": "ferme"}
    coffre.verrouiller()
    i.ouvert = True
    assert g.traiter({"action": "etat"})["etat"] == "ferme"


def test_guichet_avec_pin(coffre):
    i, h = Interface(), Horloge()
    s = acces_rapide.Session(h)
    s.demarrer()
    g = guichet.Guichet(coffre, s, i)
    assert g.traiter({"action": "etat"})["etat"] == "pin"
    comptes = g.traiter({"action": "chercher", "adresse": "https://discord.com/login"})["comptes"]
    assert [c["site"] for c in comptes] == ["Discord"] and comptes[0]["totp"] is True
    assert "mot_de_passe" not in comptes[0]
    ident = comptes[0]["id"]
    # Sans code juste : rien ne sort.
    assert g.traiter({"action": "identifiants", "id": ident}) == {"erreur": "pin"}
    assert g.traiter({"action": "copier", "id": ident, "champ": "mot_de_passe",
                      "jeton": "invente"}) == {"erreur": "pin"}
    assert g.traiter({"action": "pin", "pin": "0000"}) == {"ok": False, "restants": 2}
    jeton = g.traiter({"action": "pin", "pin": "1234"})["jeton"]
    assert g.traiter({"action": "copier", "id": ident, "champ": "mot_de_passe",
                      "jeton": jeton}) == {"ok": True}
    assert i.copies == [("mdp-discord", "mot_de_passe")]
    r = g.traiter({"action": "identifiants", "id": ident, "jeton": jeton})
    assert (r["utilisateur"], r["mot_de_passe"], len(r["totp"])) == ("alexm", "mdp-discord", 6)
    h.t += acces_rapide.DUREE_JETON_S + 1
    assert g.traiter({"action": "identifiants", "id": ident, "jeton": jeton}) == {"erreur": "pin"}


def test_trois_erreurs_verrouillent(coffre):
    i = Interface()
    s = acces_rapide.Session()
    s.demarrer()
    g = guichet.Guichet(coffre, s, i)
    g.traiter({"action": "pin", "pin": "0000"})
    g.traiter({"action": "pin", "pin": "0001"})
    assert g.traiter({"action": "pin", "pin": "0002"}) == {"ok": False, "restants": 0,
                                                           "verrouille": True}
    assert i.verrouillages == 1


def test_ecran_ouvert_pas_de_pin(coffre):
    i = Interface(pin=None)
    i.ouvert = True
    g = guichet.Guichet(coffre, acces_rapide.Session(), i)
    netflix = g.traiter({"action": "chercher", "texte": "netf"})["comptes"][0]
    assert g.traiter({"action": "copier", "id": netflix["id"], "champ": "email"}) == {"ok": True}
    assert g.traiter({"action": "copier", "id": netflix["id"], "champ": "utilisateur"}) == \
        {"erreur": "vide"}
    assert g.traiter({"action": "montrer"}) == {"ok": True} and i.montre


def test_porte_aller_retour(tmp_path, monkeypatch):
    if not porte.disponible():
        pytest.skip("Linux seulement")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    p = porte.Porte(lambda r: {"recu": r})
    assert p.ouvrir()
    try:
        assert (tmp_path / "secretlin").stat().st_mode & 0o777 == 0o700
        assert porte.chemin_socket().stat().st_mode & 0o777 == 0o600
        assert porte.demander({"action": "etat"}) == {"recu": {"action": "etat"}}
        assert not porte.Porte(lambda r: {}).ouvrir()  # une seule instance
    finally:
        p.fermer()
    assert porte.demander({"action": "etat"}) is None
