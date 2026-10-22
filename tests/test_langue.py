import re

import pytest

from gestionnaire import apparence, langue
from gestionnaire.langue import t, tn
from tests.cles_traduction import cles

AUTRES = [code for code in langue.LANGUES if code != "fr"]


@pytest.fixture(autouse=True)
def francais():
    yield
    langue.choisir("fr")


def test_chaque_texte_est_traduit_dans_toutes_les_langues():
    for texte in cles():
        traductions = langue._TRADUCTIONS.get(texte)
        assert traductions, f"pas de traduction : {texte!r}"
        manquantes = [c for c in AUTRES if not traductions.get(c)]
        assert not manquantes, (texte, manquantes)


def test_memes_valeurs_a_remplacer():
    variables = re.compile(r"\{(\w+)\}")
    for texte, traductions in langue._TRADUCTIONS.items():
        attendues = set(variables.findall(texte))
        for code, traduit in traductions.items():
            assert set(variables.findall(traduit)) == attendues, (texte, code)


def test_pas_de_traduction_inutile():
    assert set(langue._TRADUCTIONS) <= set(cles())


def test_traduction_et_valeurs():
    langue.choisir("en")
    assert t("Annuler") == "Cancel"
    assert t("{n} caractères", n=20) == "20 characters"
    assert t("Texte absent des traductions") == "Texte absent des traductions"
    langue.choisir("fr")
    assert t("Annuler") == "Annuler"


def test_pluriel():
    assert tn("{n} identifiant", "{n} identifiants", 0) == "0 identifiant"
    assert tn("{n} identifiant", "{n} identifiants", 2) == "2 identifiants"
    langue.choisir("en")
    assert tn("{n} identifiant", "{n} identifiants", 0) == "0 logins"
    assert tn("{n} identifiant", "{n} identifiants", 1) == "1 login"


def test_langue_automatique(monkeypatch):
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    langue.choisir(langue.AUTO)
    assert langue.actuelle() == "de"
    monkeypatch.setenv("LANG", "xx_XX.UTF-8")
    monkeypatch.setattr(langue.locale, "getlocale", lambda: (None, None))
    assert langue.langue_systeme() == "en"


def test_reglage_de_langue(tmp_path):
    chemin = tmp_path / "reglages.json"
    assert apparence.charger(chemin)["langue"] == langue.AUTO
    chemin.write_text('{"langue": "ja"}', encoding="utf-8")
    assert apparence.charger(chemin)["langue"] == "ja"
    chemin.write_text('{"langue": "klingon"}', encoding="utf-8")
    assert apparence.charger(chemin)["langue"] == langue.AUTO
