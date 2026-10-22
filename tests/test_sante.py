import datetime

from gestionnaire import sante
from gestionnaire.coffre import Coffre

FORT = "k8#Vq2!xR9$mT4&wZ"


def compte(id_, mdp, change_le=None):
    e = {"id": id_, "site": id_, "utilisateur": "", "mot_de_passe": mdp}
    if change_le:
        e["change_le"] = change_le
    return e


def test_coffre_sain():
    b = sante.bilan([compte("a", FORT), compte("b", FORT + "x")])
    assert (b["faibles"], b["reutilises"], b["anciens"], b["note"]) == ([], [], [], 100)
    assert sante.bilan([])["note"] == 100


def test_faibles_reutilises_et_anciens():
    jour = datetime.date(2026, 10, 22)
    entrees = [compte("faible", "azerty"), compte("r1", FORT), compte("r2", FORT),
               compte("vieux", FORT + "v", "2025-01-01"), compte("recent", FORT + "w", "2026-10-01"),
               compte("sans_date", FORT + "z")]
    b = sante.bilan(entrees, jour)
    assert [e["id"] for e in b["faibles"]] == ["faible"]
    assert [e["id"] for e in b["reutilises"]] == ["r1", "r2"]
    assert [e["id"] for e in b["anciens"]] == ["vieux"]
    assert b["a_probleme"] == 4 and b["note"] == 33


def test_un_compte_a_plusieurs_problemes_compte_une_fois():
    b = sante.bilan([compte("a", "1234", "2020-01-01"), compte("b", "1234")],
                    datetime.date(2026, 10, 22))
    assert b["a_probleme"] == 2 and b["note"] == 0


def test_date_de_changement(tmp_path):
    c = Coffre(tmp_path / "coffre.vault")
    c.creer("Maitre-Tres-Solide-42!")
    c.ajouter("site", "moi", "ancien")
    e = c.entrees[0]
    assert e["change_le"] == datetime.date.today().isoformat()
    e["change_le"] = "2020-01-01"
    c.modifier(e["id"], site="site", mot_de_passe="ancien", notes="note")
    assert e["change_le"] == "2020-01-01"  # mot de passe identique : date gardée
    c.modifier(e["id"], mot_de_passe="nouveau")
    assert e["change_le"] == datetime.date.today().isoformat()
    c.verrouiller()
    c.ouvrir("Maitre-Tres-Solide-42!")
    assert c.entrees[0]["change_le"] == datetime.date.today().isoformat()
