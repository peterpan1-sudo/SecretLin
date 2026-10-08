import importlib.util
from pathlib import Path

_chemin = Path(__file__).resolve().parent.parent / "outils" / "texte_installation.py"
_spec = importlib.util.spec_from_file_location("texte_installation", _chemin)
texte_installation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(texte_installation)


def test_remplace_l_ancienne_section():
    notes = ("La recherche ne clignote plus.\r\n\r\n### Corrections\r\n- Recherche.\r\n\r\n"
             "### Installation\r\nsudo apt install ./secretlin_1.1.2_all.deb\r\n")
    resultat = texte_installation.reecrire(notes, "v1.1.2")
    assert resultat.startswith("La recherche ne clignote plus.\n\n### Corrections\n- Recherche.\n\n### Installation\n")
    assert resultat.count("### Installation") == 1
    assert ("cd /tmp && wget -N https://github.com/peterpan1-sudo/SecretLin/releases/download/v1.1.2/"
            "secretlin_1.1.2_all.deb && sudo apt install ./secretlin_1.1.2_all.deb") in resultat
    assert "\r" not in resultat


def test_ajoute_la_section_si_absente():
    resultat = texte_installation.reecrire("Corrections diverses.", "v2.0.0")
    assert resultat.startswith("Corrections diverses.\n\n### Installation\n")
    assert "./secretlin_2.0.0_all.deb" in resultat


def test_notes_vides():
    assert texte_installation.reecrire("", "v1.0.0").startswith("### Installation\n")
