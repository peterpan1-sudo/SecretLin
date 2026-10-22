"""Langue de l'interface. Les textes sont écrits en français dans le code ; t() renvoie
leur traduction dans la langue choisie, lue dans « traductions.json » (un texte français
→ ses traductions). Un texte sans traduction reste en français."""

import json
import locale
import os
from pathlib import Path

# Code → nom de la langue écrit dans cette langue.
LANGUES = {
    "fr": "Français",
    "en": "English",
    "es": "Español",
    "de": "Deutsch",
    "pt": "Português",
    "it": "Italiano",
    "ru": "Русский",
    "zh": "中文",
    "ja": "日本語",
    "ko": "한국어",
}
AUTO = "auto"  # suit la langue du système

_TRADUCTIONS = json.loads(Path(__file__).with_name("traductions.json").read_text(encoding="utf-8"))
_code = "fr"


def langue_systeme() -> str:
    """Langue du système si elle est proposée, sinon l'anglais."""
    candidats = [os.environ.get(v, "") for v in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")]
    try:
        candidats.append(locale.getlocale()[0] or "")
    except ValueError:
        pass
    for valeur in candidats:
        code = valeur[:2].lower()
        if code in LANGUES:
            return code
    return "en"


def choisir(code: str) -> None:
    global _code
    _code = code if code in LANGUES else langue_systeme()


def actuelle() -> str:
    return _code


def t(texte: str, **valeurs) -> str:
    """Traduction de « texte » ; les {nom} sont remplacés par les valeurs données."""
    if _code != "fr":
        texte = _TRADUCTIONS.get(texte, {}).get(_code, texte)
    return texte.format(**valeurs) if valeurs else texte


def tn(singulier: str, pluriel: str, n: int, **valeurs) -> str:
    """Comme t(), avec la forme au pluriel quand n l'exige (0 et 1 au singulier en français,
    seul 1 au singulier dans les autres langues)."""
    un = n <= 1 if _code == "fr" else n == 1
    return t(singulier if un else pluriel, n=n, **valeurs)
