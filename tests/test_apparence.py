import re

from gestionnaire import apparence


def test_reglages_absents_ou_illisibles(tmp_path):
    assert apparence.charger(tmp_path / "absent.json") == apparence.DEFAUT
    chemin = tmp_path / "reglages.json"
    chemin.write_text("pas du json", encoding="utf-8")
    assert apparence.charger(chemin) == apparence.DEFAUT
    chemin.write_text("[1, 2]", encoding="utf-8")
    assert apparence.charger(chemin) == apparence.DEFAUT


def test_valeurs_inconnues_remplacees(tmp_path):
    chemin = tmp_path / "reglages.json"
    chemin.write_text('{"theme": "Arc-en-ciel", "accent": "Bleu", "taille": 3, '
                      '"animations": "oui"}', encoding="utf-8")
    assert apparence.charger(chemin) == dict(apparence.DEFAUT, accent="Bleu")


def test_enregistrer_puis_relire(tmp_path):
    chemin = apparence.chemin_reglages(tmp_path / "coffre.vault")
    choix = {"theme": "Clair", "accent": "Rose", "taille": "Grande", "animations": False}
    apparence.enregistrer(chemin, choix)
    assert chemin.name == "reglages.json"
    assert apparence.charger(chemin) == choix


def test_graphite_garde_ses_couleurs_d_origine():
    c = apparence.couleurs(apparence.DEFAUT)
    assert (c["FOND"], c["ACCENT"], c["ACCENT_TEXTE"]) == ("#0b0b0d", "#e4e4e7", "#0b0b0d")
    assert c["STYLES"]["principal"]["fond_survol"] == "#ffffff"
    assert c["STYLES"]["secondaire"]["fond"] == "#202025"
    assert c["STYLES"]["danger"]["bord"] == "#5a2a2d"


def test_toutes_les_combinaisons_donnent_des_couleurs_valides():
    hexa = re.compile(r"^#[0-9a-f]{6}$")
    for theme in apparence.THEMES:
        for accent in apparence.ACCENTS:
            c = apparence.couleurs(dict(apparence.DEFAUT, theme=theme, accent=accent))
            valeurs = [v for k, v in c.items() if k not in ("MODE", "STYLES", "COULEURS_FORCE")]
            valeurs += [v for style in c["STYLES"].values() for v in style.values()]
            assert all(hexa.match(v) for v in valeurs), (theme, accent)


def test_texte_lisible_sur_l_accent():
    clair = apparence.couleurs(dict(apparence.DEFAUT, theme="Clair"))
    assert clair["ACCENT_TEXTE"] == "#ffffff"  # accent neutre presque noir
    bleu = apparence.couleurs(dict(apparence.DEFAUT, accent="Bleu"))
    assert bleu["ACCENT_TEXTE"] == "#ffffff"
