"""Réglages de SecretLin : apparence (thème de couleurs, couleur d'accent, police, taille
du texte, animations) et options du générateur de mots de passe. Les choix sont rangés
dans « reglages.json » à côté du coffre : rien de secret dedans, il n'est donc pas
chiffré."""

import json
import os
import sys
from pathlib import Path

from gestionnaire.effets import melanger

DANGER = "#e5484d"
SUCCES = "#46a758"

# Couleurs de base de chaque thème ; les autres (boutons, survols…) en sont déduites.
# « exact » fixe des couleurs déduites à la main (Graphite garde ainsi son rendu d'origine).
THEMES = {
    "Graphite": dict(
        mode="dark", fond="#0b0b0d", panneau="#141417", carte="#1a1a1e", carte_survol="#26262b",
        bordure="#2a2a30", bordure_eclat="#70707a", texte="#ececef", texte_doux="#8e8e98",
        texte_eteint="#3a3a42", neutre="#e4e4e7",
        exact=dict(
            CHAMP_SURVOL="#44444d", SUCCES_FOND="#122016", HALO_NEUTRE="#4a4a53",
            SURVOL_NEUTRE="#ffffff",
            SECONDAIRE=dict(fond="#202025", fond_survol="#2c2c32", bord_survol="#5c5c66",
                            halo="#303037", eclat="#55555f"),
            DANGER_BOUTON=dict(fond="#1d1315", fond_survol="#3a1a1d", bord="#5a2a2d",
                               halo="#3a1c1f", eclat="#7a2a2e"),
        )),
    "Noir pur": dict(
        mode="dark", fond="#000000", panneau="#0a0a0a", carte="#111111", carte_survol="#1c1c1c",
        bordure="#232323", bordure_eclat="#6a6a6a", texte="#f5f5f5", texte_doux="#8c8c8c",
        texte_eteint="#333333", neutre="#ededed"),
    "Nuit bleue": dict(
        mode="dark", fond="#0a0e17", panneau="#0f1522", carte="#141c2c", carte_survol="#1c2639",
        bordure="#243049", bordure_eclat="#5f7299", texte="#e8edf7", texte_doux="#8a96ad",
        texte_eteint="#2f3a52", neutre="#dfe6f3"),
    "Prune": dict(
        mode="dark", fond="#100b12", panneau="#17111a", carte="#1e1622", carte_survol="#2a1f30",
        bordure="#33263a", bordure_eclat="#7d6a88", texte="#f0eaf3", texte_doux="#9c8fa5",
        texte_eteint="#3e3245", neutre="#ebe2ef"),
    "Clair": dict(
        mode="light", fond="#f3f3f6", panneau="#ffffff", carte="#ffffff", carte_survol="#f0f0f4",
        bordure="#dcdce3", bordure_eclat="#8f8f9c", texte="#16161a", texte_doux="#5f5f6b",
        texte_eteint="#c2c2cb", neutre="#1c1c21"),
}

# None : couleur neutre du thème (presque blanc sur fond sombre, presque noir sur fond clair).
ACCENTS = {
    "Neutre": None,
    "Bleu": "#2f6fed",
    "Vert": "#2f9e57",
    "Violet": "#8e4ec6",
    "Orange": "#e8772e",
    "Rose": "#e93d82",
}

TAILLES = {"Petite": 0.9, "Normale": 1.0, "Grande": 1.15}

# Polices parmi les plus utilisées (classement Google Fonts et choix des designers d'interface).
# Sous Debian/Kali, chacune vient d'un paquet « fonts-… » (voir debian/control).
POLICES = ("Inter", "Roboto", "Open Sans", "Lato", "Montserrat", "Nunito", "Manrope",
           "Source Sans 3", "IBM Plex Sans", "JetBrains Mono")
# Police utilisée si celle choisie n'est pas installée : la première présente.
POLICES_SECOURS = ("Inter", "Segoe UI", "Roboto", "Cantarell", "DejaVu Sans")

LONGUEUR_MIN, LONGUEUR_MAX = 8, 64
OPTIONS_GENERATEUR = ("majuscules", "chiffres", "symboles", "sans_ambigus")

DEFAUT = {"theme": "Graphite", "accent": "Neutre", "police": "Inter", "taille": "Normale",
          "animations": True,
          "longueur": 20, "majuscules": True, "chiffres": True, "symboles": True,
          "sans_ambigus": False}


def _luminance(couleur: str) -> float:
    r, g, b = (int(couleur[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def couleurs(reglages: dict) -> dict:
    """Toutes les couleurs de l'interface pour ces réglages, sous les noms utilisés par
    l'interface (FOND, TEXTE, STYLES…)."""
    t = THEMES[reglages["theme"]]
    sombre = t["mode"] == "dark"
    extreme = "#ffffff" if sombre else "#000000"
    neutre = reglages["accent"] == "Neutre"
    exact = t.get("exact", {}) if neutre else {k: v for k, v in t.get("exact", {}).items()
                                                if k not in ("HALO_NEUTRE", "SURVOL_NEUTRE")}
    accent = ACCENTS[reglages["accent"]] or t["neutre"]
    accent_survol = exact.get("SURVOL_NEUTRE", melanger(accent, extreme, 0.25 if sombre else 0.2))
    accent_texte = "#0b0b0d" if _luminance(accent) > 0.55 else "#ffffff"

    def secondaire():
        d = dict(fond=melanger(t["carte"], t["texte"], 0.04),
                 fond_survol=melanger(t["carte"], t["texte"], 0.1),
                 bord_survol=melanger(t["bordure"], t["texte"], 0.35),
                 halo=melanger(t["panneau"], t["texte"], 0.12),
                 eclat=melanger(t["carte"], t["texte"], 0.25))
        d.update(exact.get("SECONDAIRE", {}))
        return dict(d, texte=t["texte"], bord=t["bordure"])

    def danger():
        d = dict(fond=melanger(t["carte"], DANGER, 0.06),
                 fond_survol=melanger(t["carte"], DANGER, 0.18),
                 bord=melanger(t["carte"], DANGER, 0.35),
                 halo=melanger(t["panneau"], DANGER, 0.15),
                 eclat=melanger(t["carte"], DANGER, 0.45))
        d.update(exact.get("DANGER_BOUTON", {}))
        return dict(d, texte=DANGER, bord_survol=DANGER)

    halo = exact.get("HALO_NEUTRE", melanger(t["panneau"], accent, 0.3))
    principal = dict(fond=accent, fond_survol=accent_survol, texte=accent_texte, bord=accent,
                     bord_survol=accent_survol, halo=halo,
                     eclat=extreme if neutre else melanger(accent, "#ffffff", 0.5))
    bordure = t["bordure"]
    return {
        "MODE": t["mode"],
        "FOND": t["fond"], "PANNEAU": t["panneau"], "CARTE": t["carte"],
        "CARTE_SURVOL": t["carte_survol"], "BORDURE": bordure,
        "BORDURE_ECLAT": t["bordure_eclat"], "TEXTE": t["texte"],
        "TEXTE_DOUX": t["texte_doux"], "TEXTE_ETEINT": t["texte_eteint"],
        "ACCENT": accent, "ACCENT_TEXTE": accent_texte, "ECLAT": extreme,
        "CHAMP_SURVOL": exact.get("CHAMP_SURVOL", melanger(bordure, t["texte"], 0.15)),
        "SUCCES_FOND": exact.get("SUCCES_FOND", melanger(t["panneau"], SUCCES, 0.12)),
        "COULEURS_FORCE": [bordure, DANGER, "#f0883e", "#d4c34a", SUCCES],
        "STYLES": {"principal": principal, "secondaire": secondaire(), "danger": danger()},
    }


def chemin_reglages(chemin_coffre: Path) -> Path:
    return Path(chemin_coffre).with_name("reglages.json")


def charger(chemin: Path) -> dict:
    """Réglages enregistrés ; toute valeur absente ou inconnue reprend sa valeur par défaut."""
    reglages = dict(DEFAUT)
    try:
        lus = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return reglages
    if not isinstance(lus, dict):
        return reglages
    for cle, permis in (("theme", THEMES), ("accent", ACCENTS), ("police", POLICES),
                         ("taille", TAILLES)):
        if lus.get(cle) in permis:
            reglages[cle] = lus[cle]
    for cle in ("animations",) + OPTIONS_GENERATEUR:
        if isinstance(lus.get(cle), bool):
            reglages[cle] = lus[cle]
    longueur = lus.get("longueur")
    if type(longueur) is int and LONGUEUR_MIN <= longueur <= LONGUEUR_MAX:
        reglages["longueur"] = longueur
    return reglages


def options_generateur(reglages: dict) -> dict:
    """Arguments de generer_mot_de_passe() pour ces réglages."""
    return {cle: reglages[cle] for cle in ("longueur",) + OPTIONS_GENERATEUR}


def enregistrer(chemin: Path, reglages: dict) -> None:
    chemin = Path(chemin)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(reglages, ensure_ascii=False, indent=2), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, chemin)
