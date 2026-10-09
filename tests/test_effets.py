import os
import tkinter

import pytest

from gestionnaire.effets import animer, figer, liberer, survol

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="pas d'écran X")


@pytest.fixture
def fenetre():
    racine = tkinter.Tk()
    racine.geometry("200x200+40+40")
    yield racine
    racine.destroy()


def attendre(racine, secondes):
    racine.after(int(secondes * 1000), racine.quit)
    racine.mainloop()


def test_animation_en_pause_dans_un_conteneur_fige(fenetre):
    cadre = tkinter.Frame(fenetre)
    cadre.pack()
    valeurs = []
    figer(cadre)
    animer(cadre, "essai", 0.2, valeurs.append)
    attendre(fenetre, 0.3)
    assert valeurs == []  # rien ne bouge tant que le conteneur est figé
    liberer(cadre)
    attendre(fenetre, 0.05)
    assert valeurs and valeurs[-1] < 1  # reprend au début, pas à la fin
    attendre(fenetre, 0.3)
    assert valeurs[-1] == 1


def test_survol_ignore_pendant_que_c_est_fige(fenetre):
    cadre = tkinter.Frame(fenetre, width=100, height=100)
    cadre.pack()
    etats = []
    survol(cadre, lambda: etats.append("entre"), lambda: etats.append("sort"))
    figer(fenetre)
    cadre.event_generate("<Enter>")
    attendre(fenetre, 0.05)
    assert etats == []
    liberer(fenetre)  # la souris n'est pas sur le cadre : il reste au repos
    assert etats == []
