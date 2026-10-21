import os
import tkinter

import pytest

from gestionnaire.capture import garder_contenu, photographier

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="pas d'écran X")


@pytest.fixture
def fenetre():
    racine = tkinter.Tk()
    yield racine
    racine.destroy()


def afficher(racine):
    for _ in range(20):
        racine.update()


def test_photo_du_contenu_de_la_fenetre(fenetre):
    fenetre.geometry("300x200+40+40")
    toile = tkinter.Canvas(fenetre, bg="#336699", highlightthickness=0)
    toile.pack(fill="both", expand=True)
    cadre = tkinter.Frame(toile, bg="#cc4422", width=60, height=40)
    toile.create_window(100, 100, window=cadre, anchor="nw")
    afficher(fenetre)
    image = photographier(toile)
    assert image.size == (toile.winfo_width(), toile.winfo_height())
    assert image.getpixel((10, 10)) == (0x33, 0x66, 0x99)
    assert image.getpixel((120, 120)) == (0xCC, 0x44, 0x22)  # les widgets enfants aussi


def test_refus_du_serveur_sans_planter(fenetre):
    # En partie hors de l'écran, Xorg refuse la photo : on doit juste obtenir None.
    fenetre.geometry("300x200+-150+40")
    toile = tkinter.Canvas(fenetre, bg="#336699", highlightthickness=0)
    toile.pack(fill="both", expand=True)
    afficher(fenetre)
    photographier(toile)
    bouton = tkinter.Button(fenetre, text="ok")
    toile.destroy()
    bouton.pack()
    afficher(fenetre)
    assert bouton.winfo_ismapped()


def test_photo_d_une_zone(fenetre):
    fenetre.geometry("300x200+40+40")
    toile = tkinter.Canvas(fenetre, bg="#336699", highlightthickness=0)
    toile.pack(fill="both", expand=True)
    toile.create_rectangle(100, 50, 160, 90, fill="#cc4422", width=0)
    afficher(fenetre)
    image = photographier(toile, (90, 40, 80, 60))
    assert image.size == (80, 60)
    assert image.getpixel((0, 0)) == (0x33, 0x66, 0x99)
    assert image.getpixel((20, 20)) == (0xCC, 0x44, 0x22)


def test_contenu_garde_sous_une_autre_fenetre(fenetre):
    # Recouverte, une fenêtre dont le contenu est gardé se photographie quand même.
    fenetre.geometry("300x200+40+40")
    dessous = tkinter.Canvas(fenetre, bg="#336699", highlightthickness=0)
    dessous.place(x=0, y=0, relwidth=1, relheight=1)
    dessus = tkinter.Canvas(fenetre, bg="#cc4422", highlightthickness=0)
    dessus.place(x=0, y=0, relwidth=1, relheight=1)
    afficher(fenetre)
    assert garder_contenu(dessous)
    tkinter.Misc.lower(dessus, dessous)
    afficher(fenetre)
    tkinter.Misc.tkraise(dessus, dessous)
    dessous.create_rectangle(0, 0, 300, 200, fill="#11aa55", width=0)
    afficher(fenetre)
    assert photographier(dessous).getpixel((150, 100)) == (0x11, 0xAA, 0x55)
