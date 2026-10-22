"""Tutoriel vidéo : désactiver les suggestions de Firefox, qui passent par-dessus le menu
de SecretLin. Les images sont dessinées ici (Firefox simulé, curseur, légendes dans la
langue choisie) : la vidéo se joue dans l'application et sert aussi à faire le GIF du README.

images() renvoie une liste de (image, durée en millisecondes)."""

import math
import re
import subprocess
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from gestionnaire import langue
from gestionnaire.langue import t
from gestionnaire.logo import dessiner as dessiner_logo

L, H = 880, 540
HAUT_PAGE, BAS_PAGE = 82, 470
FOND = "#1c1b22"
BARRE = "#2b2a33"
CHAMP = "#42414d"
TEXTE = "#fbfbfe"
DOUX = "#bfbfc9"
BLEU = "#00ddff"
VIOLET = "#8e4ec6"
SITE = "https://monsite.fr/connexion"


@lru_cache(maxsize=32)
def _police(taille, gras=False, code="en"):
    """Police du système qui a les caractères de la langue « code », sinon celle de Pillow."""
    try:
        motif = f"sans:lang={code}" + (":bold" if gras else "")
        chemin = subprocess.run(["fc-match", "-f", "%{file}", motif], capture_output=True,
                                text=True, timeout=5).stdout.strip()
        return ImageFont.truetype(chemin, taille)
    except (OSError, subprocess.SubprocessError, ValueError):
        return ImageFont.load_default(size=taille)


def _asiatique(c: str) -> bool:
    return ord(c) >= 0x2E80  # idéogrammes, kana, hangeul, ponctuation pleine largeur


def _morceaux(texte, taille, gras):
    """Le texte découpé selon la police à utiliser : latine (et cyrillique), ou celle du
    chinois, du japonais ou du coréen, qui n'a pas toujours les lettres latines."""
    code = langue.actuelle() if langue.actuelle() in ("zh", "ja", "ko") else "en"
    for bloc in re.findall(r"[\u2e80-\U0010ffff]+|[^\u2e80-\U0010ffff]+", texte):
        yield bloc, _police(taille, gras, code if _asiatique(bloc[0]) else "en")


def _ecrire(d, xy, texte, taille, gras=False, fill=None, anchor="lm"):
    """Comme ImageDraw.text, avec une police par morceau de texte (ancres « lm » et « mm »)."""
    morceaux = list(_morceaux(texte, taille, gras))
    largeur = sum(police.getlength(bloc) for bloc, police in morceaux)
    x, y = xy
    if anchor[0] == "m":
        x -= largeur / 2
    for bloc, police in morceaux:
        d.text((x, y), bloc, anchor="l" + anchor[1], font=police, fill=fill)
        x += police.getlength(bloc)


@lru_cache(maxsize=1)
def _petit_logo():
    return dessiner_logo(36).resize((18, 18), Image.LANCZOS)


class Film:
    """Suite d'images construite pas à pas : on change l'état, puis on filme."""

    def __init__(self):
        self.images = []
        self.etat = dict(scene="connexion", adresse=SITE, frappe_adresse=False, email="",
                         mdp="", focus=None, menu_firefox=False, menu_secretlin=False,
                         recherche="", prefs={"signon.rememberSignons": True,
                                              "browser.formfill.enable": True},
                         etape=1, legende="", curseur=(700, 300), clic=None)

    def filmer(self, duree):
        self.images.append((dessiner(self.etat), duree))

    def tenir(self, duree, **changements):
        self.etat.update(changements)
        self.filmer(duree)

    def deplacer(self, vers, pas=12):
        x0, y0 = self.etat["curseur"]
        for i in range(1, pas + 1):
            k = (1 - math.cos(math.pi * i / pas)) / 2  # départ et arrivée en douceur
            self.etat["curseur"] = (round(x0 + (vers[0] - x0) * k), round(y0 + (vers[1] - y0) * k))
            self.filmer(30)

    def cliquer(self, double=False):
        for _ in range(2 if double else 1):
            for rayon in (6, 12, 18):
                self.etat["clic"] = rayon
                self.filmer(40)
        self.etat["clic"] = None

    def taper(self, cle, texte):
        depart = self.etat[cle]
        for i in range(1, len(texte) + 1):
            self.etat[cle] = depart + texte[:i]
            self.filmer(55)


# --- Dessin ---------------------------------------------------------------------------

def _champ(d, boite, texte, focus=False, masque=False, attente=""):
    x0, y0, x1, y1 = boite
    d.rounded_rectangle(boite, radius=6, fill="#ffffff", outline=BLEU if focus else "#c9c9d1",
                        width=2 if focus else 1)
    contenu = "•" * len(texte) if masque else texte
    _ecrire(d, (x0 + 10, (y0 + y1) / 2), contenu or attente, 14,
            fill="#15141a" if contenu else "#8f8f9d")


def _navigateur(d, adresse, frappe):
    d.rectangle((0, 0, L, 36), fill="#0f0e14")
    d.rounded_rectangle((8, 6, 250, 36), radius=6, fill=BARRE)
    titre = adresse.split("//")[-1].split("/")[0] or "about:config"
    _ecrire(d, (22, 21), titre, 13, fill=TEXTE)
    d.rectangle((0, 36, L, HAUT_PAGE), fill=BARRE)
    for i, x in enumerate((24, 54, 84)):  # précédent, suivant, actualiser
        d.ellipse((x - 9, 50, x + 9, 68), outline=DOUX, width=2)
    d.rounded_rectangle((110, 44, L - 20, 74), radius=6, fill=CHAMP,
                        outline=BLEU if frappe else CHAMP, width=2)
    _ecrire(d, (126, 59), adresse, 14, fill=TEXTE)


def _page_connexion(d, e):
    d.rectangle((0, HAUT_PAGE, L, BAS_PAGE), fill="#eef0f7")
    carte = (260, 110, 620, 440)
    d.rounded_rectangle(carte, radius=14, fill="#ffffff", outline="#dcdfe8")
    _ecrire(d, (440, 145), t("Connexion"), 22, gras=True, fill="#15141a", anchor="mm")
    _ecrire(d, (290, 185), t("Adresse e-mail"), 13, gras=True, fill="#3b3b45")
    _champ(d, (290, 198, 590, 236), e["email"], e["focus"] == "email")
    _ecrire(d, (290, 262), t("Mot de passe"), 13, gras=True, fill="#3b3b45")
    _champ(d, (290, 275, 590, 313), e["mdp"], e["focus"] == "mdp", masque=True)
    d.rounded_rectangle((290, 345, 590, 385), radius=8, fill="#5865f2")
    _ecrire(d, (440, 365), t("Se connecter"), 14, gras=True, fill="#ffffff", anchor="mm")


def _menu_secretlin(image, d, x, y):
    d.rounded_rectangle((x, y, x + 280, y + 82), radius=10, fill="#141417", outline="#2a2a30")
    image.paste(_petit_logo(), (x + 12, y + 9), _petit_logo())
    _ecrire(d, (x + 36, y + 18), "SecretLin", 12, gras=True, fill="#8e8e98")
    d.rounded_rectangle((x + 6, y + 32, x + 274, y + 76), radius=8, fill="#26262b")
    _ecrire(d, (x + 16, y + 44), "Monsite", 14, gras=True, fill="#ececef")
    _ecrire(d, (x + 16, y + 63), "alex.martin@mail.fr", 12, fill="#8e8e98")


def _menu_firefox(d, x, y):
    d.rounded_rectangle((x, y, x + 250, y + 74), radius=6, fill="#2b2a33", outline="#52525e")
    _ecrire(d, (x + 14, y + 20), "alex.martin75", 14, fill=TEXTE)
    d.line((x, y + 38, x + 250, y + 38), fill="#52525e")
    _ecrire(d, (x + 14, y + 56), t("Gérer les mots de passe"), 13, fill=TEXTE)


def _page_alerte(d):
    d.rectangle((0, HAUT_PAGE, L, BAS_PAGE), fill=FOND)
    _ecrire(d, (140, 170), "⚠", 46, fill="#ffa436")
    _ecrire(d, (210, 165), t("Faites preuve de prudence"), 24, gras=True, fill=TEXTE)
    _ecrire(d, (210, 210), t("Modifier les préférences avancées peut affecter Firefox."), 14,
            fill=DOUX)
    d.rounded_rectangle((210, 250, 520, 290), radius=6, fill="#00ddff")
    _ecrire(d, (365, 270), t("Accepter le risque et poursuivre"), 14, gras=True,
            fill="#15141a", anchor="mm")


def _page_config(d, e):
    d.rectangle((0, HAUT_PAGE, L, BAS_PAGE), fill=FOND)
    focus = e["focus"] == "recherche"
    d.rounded_rectangle((40, 104, L - 40, 140), radius=6, fill=CHAMP,
                        outline=BLEU if focus else CHAMP, width=2)
    _ecrire(d, (56, 122), e["recherche"] or t("Rechercher un nom de préférence"), 14,
            fill=TEXTE if e["recherche"] else DOUX)
    nom = next((n for n in e["prefs"] if e["recherche"] and n.startswith(e["recherche"])), None)
    if nom is None:
        return
    valeur = e["prefs"][nom]
    d.rounded_rectangle((40, 160, L - 40, 200), radius=4, fill="#2b2a33")
    gras = not valeur  # Firefox écrit en gras les préférences modifiées
    _ecrire(d, (56, 180), nom, 14, gras=gras, fill=TEXTE)
    _ecrire(d, (500, 180), t("Booléen"), 14, fill=DOUX)
    _ecrire(d, (620, 180), "true" if valeur else "false", 14, gras=gras,
            fill=TEXTE if valeur else "#54ffbd")


def _legende(d, e):
    d.rectangle((0, BAS_PAGE, L, H), fill="#0b0b0d")
    d.ellipse((20, BAS_PAGE + 18, 54, BAS_PAGE + 52), fill=VIOLET)
    _ecrire(d, (37, BAS_PAGE + 35), str(e["etape"]), 16, gras=True, fill="#ffffff", anchor="mm")
    _ecrire(d, (70, BAS_PAGE + 35), e["legende"], 16, gras=True, fill=TEXTE)


def _curseur(d, e):
    x, y = e["curseur"]
    if e["clic"]:
        r = e["clic"]
        d.ellipse((x - r, y - r, x + r, y + r), outline="#ffd60a", width=3)
    pointe = [(x, y), (x, y + 22), (x + 6, y + 17), (x + 10, y + 26), (x + 14, y + 24),
              (x + 10, y + 15), (x + 17, y + 15)]
    d.polygon(pointe, fill="#ffffff", outline="#000000")


def dessiner(e) -> Image.Image:
    image = Image.new("RGB", (L, H), FOND)
    d = ImageDraw.Draw(image)
    _navigateur(d, e["adresse"], e["frappe_adresse"])
    if e["scene"] == "connexion":
        _page_connexion(d, e)
        if e["menu_secretlin"]:
            _menu_secretlin(image, d, 290, 240)
        if e["menu_firefox"]:
            _menu_firefox(d, 290, 238)  # le menu de Firefox passe par-dessus
    elif e["scene"] == "alerte":
        _page_alerte(d)
    else:
        _page_config(d, e)
    _legende(d, e)
    _curseur(d, e)
    return image


# --- Scénario -------------------------------------------------------------------------

def images() -> list[tuple[Image.Image, int]]:
    f = Film()
    # 1. Le problème
    f.tenir(1800, etape=1, legende=t("Le problème : les suggestions de Firefox cachent "
                                      "celles de SecretLin."))
    f.deplacer((440, 217))
    f.cliquer()
    f.tenir(400, focus="email", menu_secretlin=True)
    f.tenir(2600, menu_firefox=True)
    # 2. about:config
    f.tenir(700, etape=2, legende=t("Tapez about:config dans la barre d'adresse."),
            menu_firefox=False, menu_secretlin=False, focus=None)
    f.deplacer((400, 59))
    f.cliquer()
    f.tenir(300, adresse="", frappe_adresse=True)
    f.taper("adresse", "about:config")
    f.tenir(900)
    f.tenir(1600, scene="alerte", frappe_adresse=False,
            legende=t("Acceptez l'avertissement."))
    f.deplacer((365, 270))
    f.cliquer()
    f.tenir(500, scene="config")
    # 3. Mots de passe de Firefox
    for etape, nom, legende in (
            (3, "signon.rememberSignons", t("Cherchez signon.rememberSignons et double-cliquez "
                                            "dessus : il passe à false.")),
            (4, "browser.formfill.enable", t("Puis browser.formfill.enable : double-clic, "
                                             "il passe à false."))):
        f.tenir(900, etape=etape, legende=legende, recherche="")
        f.deplacer((300, 122))
        f.cliquer()
        f.tenir(200, focus="recherche")
        f.taper("recherche", nom)
        f.tenir(700)
        f.deplacer((640, 180))
        f.cliquer(double=True)
        f.etat["prefs"] = dict(f.etat["prefs"], **{nom: False})
        f.tenir(2000, focus=None)
    # 5. Résultat
    f.tenir(600, etape=5, scene="connexion", adresse=SITE, recherche="",
            legende=t("Rechargez la page de connexion : seul SecretLin s'affiche."))
    f.deplacer((440, 217))
    f.cliquer()
    f.tenir(1800, focus="email", menu_secretlin=True)
    f.deplacer((420, 300))
    f.cliquer()
    f.tenir(2800, menu_secretlin=False, focus="mdp", email="alex.martin@mail.fr",
            mdp="Mot-De-Passe-2026!", legende=t("Un clic sur votre compte, et c'est rempli !"))
    return f.images


def enregistrer_gif(chemin) -> None:
    """GIF animé du tutoriel (pour le README)."""
    film = images()
    palette = film[0][0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    cadres = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image, _ in film]
    cadres[0].save(chemin, save_all=True, append_images=cadres[1:], loop=0, optimize=True,
                   duration=[duree for _, duree in film], disposal=1)
