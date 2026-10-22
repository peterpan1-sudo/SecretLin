import datetime

import pytest

from gestionnaire import fuites, sante


def test_seul_le_debut_de_l_empreinte_est_envoye():
    envoyes = []
    # SHA-1 de « password » : 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
    reponse = "1E4C9B93F3F0682250B6CF8331B7EE68FD8:3912816\r\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:0\r\n"

    def telecharger(prefixe):
        envoyes.append(prefixe)
        return reponse if prefixe == "5BAA6" else ""

    resultat = fuites.verifier(["password", "password", "Un-Mot-De-Passe-Unique-42!", ""],
                               telecharger)
    assert resultat == {"password": 3912816, "Un-Mot-De-Passe-Unique-42!": 0}
    assert sorted(envoyes) == sorted({"5BAA6", fuites.empreinte("Un-Mot-De-Passe-Unique-42!")[:5]})
    assert all(len(p) == 5 for p in envoyes)


def test_erreur_reseau():
    def telecharger(_prefixe):
        raise OSError("pas de réseau")

    with pytest.raises(OSError):
        fuites.verifier(["x"], telecharger)


def test_bilan_avec_fuites():
    entrees = [{"id": "a", "site": "a", "utilisateur": "", "mot_de_passe": "k8#Vq2!xR9$mT4&wZ"},
               {"id": "b", "site": "b", "utilisateur": "", "mot_de_passe": "k8#Vq2!xR9$mT4&wZ-2"}]
    b = sante.bilan(entrees, datetime.date(2026, 10, 22), {"k8#Vq2!xR9$mT4&wZ": 12})
    assert [e["id"] for e in b["pirates"]] == ["a"] and b["note"] == 50
    assert sante.bilan(entrees)["pirates"] == []
