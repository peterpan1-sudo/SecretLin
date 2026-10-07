"""Reconnaît le site ou l'application d'après son nom et fournit son logo.

Les logos viennent de Simple Icons (CC0) et sont intégrés à l'application :
rien n'est téléchargé, donc aucun service extérieur ne voit la liste de vos comptes.
"""

import io
import json
import re
import unicodedata
import zipfile
from functools import lru_cache
from pathlib import Path

import customtkinter as ctk
from PIL import Image

ARCHIVE = Path(__file__).parent / "logos.zip"

# Noms courants qui ne correspondent pas directement à un logo.
ALIAS = {
    "twitter": "x", "insta": "instagram", "fb": "facebook", "yt": "youtube",
    "psn": "playstation", "playstationnetwork": "playstation", "lol": "leagueoflegends",
    "battlenet": "battledotnet", "blizzard": "battledotnet", "epic": "epicgames",
    "protonmail": "protonmail", "whatsappweb": "whatsapp", "appleid": "apple",
    "icloud": "icloud", "messengerfacebook": "messenger", "primevideo": "primevideo",
    "disney": "disneyplus", "disney+": "disneyplus", "hbo": "hbomax", "max": "hbomax",
    "banquepostale": "labanquepostale", "postale": "labanquepostale",
    "hotmail": "outlook", "live": "outlook", "msn": "outlook",
    "ubisoftconnect": "ubisoft", "eaapp": "ea", "origin": "ea", "googlemail": "gmail",
}

# Marques sans logo disponible : la pastille prend au moins leur couleur.
COULEURS_SANS_LOGO = {
    "amazon": "FF9900", "microsoft": "00A4EF", "outlook": "0078D4", "linkedin": "0A66C2",
    "yahoo": "6001D2", "leboncoin": "FF6E14", "doctolib": "107ACA", "ameli": "0C419A",
    "impots": "000091", "impotsgouv": "000091", "caf": "0D6EAF", "franceconnect": "000091",
    "boursorama": "D0003F", "boursobank": "D0003F", "creditagricole": "00A88F",
    "societegenerale": "E9041E", "bnpparibas": "00915A", "bnp": "00915A",
    "creditmutuel": "0060AE", "cic": "0F7AC0", "lcl": "1D2D87", "caissedepargne": "E2001A",
    "labanquepostale": "003DA5", "laposte": "FFC90E", "free": "CD1E25", "sfr": "E2001A",
    "bouygues": "009FE3", "bouyguestelecom": "009FE3", "orange": "FF7900",
    "chatgpt": "10A37F", "openai": "10A37F", "canva": "00C4CC", "xbox": "107C10",
    "nintendo": "E60012", "vinted": "09B1BA", "ebay": "E53238", "adobe": "FF0000",
    "dropbox": "0061FF", "skype": "00AFF0", "teams": "6264A7", "onedrive": "0078D4",
    "office": "D83B01", "office365": "D83B01", "cdiscount": "1A3E8C", "fnac": "E1A925",
    "sncf": "A1006B", "sncfconnect": "0C131F", "uber": "000000", "ubereats": "06C167",
    "deliveroo": "00CCBC", "pole emploi": "2A3E8C", "franceTravail": "2A3E8C",
}


def normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9+]", "", texte)


COULEURS_SANS_LOGO = {normaliser(k): v for k, v in COULEURS_SANS_LOGO.items()}


def _nom_de_domaine(texte: str) -> str:
    """« https://www.discord.com/app » → « discord »."""
    t = texte.strip().casefold()
    t = re.sub(r"^[a-z]+://", "", t).split("/")[0]
    if "." in t and " " not in t:
        morceaux = [m for m in t.split(".") if m not in ("www", "app", "login", "account", "accounts")]
        if len(morceaux) >= 2:
            return morceaux[-2]
        if morceaux:
            return morceaux[0]
    return texte


@lru_cache(maxsize=1)
def _catalogue():
    with zipfile.ZipFile(ARCHIVE) as z:
        index = json.loads(z.read("index.json"))
    noms = {}
    for slug, info in index.items():
        for nom in [slug, info["titre"], *info["alias"]]:
            noms.setdefault(normaliser(nom), slug)
    return index, noms


def _chercher(cle: str):
    index, noms = _catalogue()
    cle = ALIAS.get(cle, cle)
    if cle in noms:
        slug = noms[cle]
        return slug, index[slug]["couleur"]
    if cle in COULEURS_SANS_LOGO:
        return None, COULEURS_SANS_LOGO[cle]
    return None


@lru_cache(maxsize=2048)
def trouver(site: str):
    """Renvoie (slug du logo ou None, couleur hexadécimale) ou None si inconnu."""
    if not ARCHIVE.exists() or not site.strip():
        return None
    entier = normaliser(_nom_de_domaine(site))
    if trouve := _chercher(entier):
        return trouve
    # « Compte Discord perso » → on essaie chaque mot, puis les paires de mots.
    mots = [normaliser(m) for m in re.split(r"[\s\-_./:]+", site) if m]
    candidats = [a + b for a, b in zip(mots, mots[1:])] + [m for m in mots if len(m) >= 4]
    for c in sorted(candidats, key=len, reverse=True):
        if trouve := _chercher(c):
            return trouve
    return None


def _luminance(hexa: str) -> float:
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _saturation(hexa: str) -> float:
    composantes = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return max(composantes) - min(composantes)


def _eclaircir(hexa: str, t: float) -> str:
    return "".join(f"{round(int(hexa[i:i + 2], 16) + (255 - int(hexa[i:i + 2], 16)) * t):02X}"
                   for i in (0, 2, 4))


@lru_cache(maxsize=512)
def image_logo(slug: str, couleur: str, taille: int) -> ctk.CTkImage:
    with zipfile.ZipFile(ARCHIVE) as z:
        masque = Image.open(io.BytesIO(z.read(f"{slug}.png"))).convert("L")
    image = Image.new("RGBA", masque.size, "#" + couleur)
    image.putalpha(masque)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(taille, taille))


def style_pastille(site: str, fond_neutre: str, fond_survol_neutre: str, texte_neutre: str,
                   texte_survol_neutre: str, taille_logo: int = 24) -> dict:
    """Couleurs et images d'une pastille au repos et au survol, selon la marque reconnue."""
    trouve = trouver(site)
    if not trouve:
        return dict(fond=fond_neutre, fond_survol=fond_survol_neutre, texte=texte_neutre,
                    texte_survol=texte_survol_neutre, image=None, image_survol=None)
    slug, couleur = trouve
    lum = _luminance(couleur)
    gris = _saturation(couleur) < 0.15
    # Au repos : logo à sa couleur sur fond sombre (éclaircie si trop foncée pour être lisible).
    if gris and lum < 0.5:
        couleur_repos = "ECECEF"
    elif lum < 0.3:
        couleur_repos = _eclaircir(couleur, 0.45)
    else:
        couleur_repos = couleur
    # Au survol : le fond prend la couleur de la marque (gris clair pour les marques noires).
    fond_survol = "ECECEF" if gris and lum < 0.3 else couleur
    contraste = "0B0B0D" if _luminance(fond_survol) > 0.6 else "FFFFFF"
    fond_survol = "#" + fond_survol
    return dict(
        fond=fond_neutre, fond_survol=fond_survol,
        texte="#" + couleur_repos, texte_survol="#" + contraste,
        image=image_logo(slug, couleur_repos, taille_logo) if slug else None,
        image_survol=image_logo(slug, contraste, taille_logo) if slug else None,
    )
