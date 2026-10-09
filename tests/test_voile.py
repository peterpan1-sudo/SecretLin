import os
import time

import pytest
from PIL import Image, ImageDraw

from gestionnaire.voile import DERIVE, MARGE, base_fumee, fumee

FOND = (11, 11, 13)


def carte():
    image = Image.new("RGB", (400, 60), FOND)
    ImageDraw.Draw(image).rounded_rectangle((10, 4, 390, 56), 12, fill=(26, 26, 30))
    return image


def test_fumee_deborde_puis_disparait():
    bases = base_fumee(carte(), FOND)
    image, dx, dy = fumee(bases, FOND, 0.5)
    assert dx < 10 and dy < 4  # le flou déborde de la carte
    assert image.width > 380 and image.height > 52
    assert fumee(bases, FOND, 1.0) is None  # complètement dissipée


def test_fumee_presque_nette_au_debut():
    image, dx, dy = fumee(base_fumee(carte(), FOND), FOND, 1 / 16)
    assert abs(dx - 10) <= 3 and abs(dy - 4) <= 3


ecran = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="pas d'écran X")


@pytest.fixture
def liste():
    import customtkinter as ctk
    racine = ctk.CTk()
    racine.geometry("500x400+40+40")
    racine.configure(fg_color="#0b0b0d")
    cadre = ctk.CTkScrollableFrame(racine, fg_color="transparent")
    cadre.pack(fill="both", expand=True)
    yield racine, cadre
    racine.destroy()


def pomper(racine, secondes):
    fin = time.perf_counter() + secondes
    while time.perf_counter() < fin:
        racine.update()
        time.sleep(0.005)


def cases(cadre, couleurs):
    import tkinter
    resultat = []
    for couleur in couleurs:
        case = tkinter.Frame(cadre, bg="#0b0b0d", height=60)
        tkinter.Frame(case, bg=couleur, height=50).pack(fill="x", padx=10, pady=5)
        case.pack(fill="x")
        resultat.append(case)
    return resultat


@ecran
def test_le_calque_montre_la_liste_puis_s_efface(liste):
    from gestionnaire.capture import photographier
    from gestionnaire.voile import Voile
    racine, cadre = liste
    a, b, c = cases(cadre, ["#aa3333", "#33aa33", "#3333aa"])
    voile = Voile(cadre)
    pomper(racine, 0.3)
    avant = photographier(voile.vue)

    voile.changer(lambda: a.pack_forget())
    assert voile.actif
    voile.toile.update_idletasks()
    # Levé, le calque montre exactement la liste d'avant.
    assert photographier(voile.toile).tobytes() == avant.tobytes()

    pomper(racine, 1.5)
    assert not voile.actif and not voile.blocs
    assert cadre.pack_slaves() == [b, c]


@ecran
def test_changement_pendant_l_animation(liste):
    from gestionnaire.voile import Voile
    racine, cadre = liste
    a, b, c = cases(cadre, ["#aa3333", "#33aa33", "#3333aa"])
    voile = Voile(cadre)
    pomper(racine, 0.3)
    voile.changer(lambda: (a.pack_forget(), b.pack_forget()))
    pomper(racine, 0.15)
    # La deuxième carte revient pendant que la fumée se forme : elle remonte à sa place.
    voile.changer(lambda: b.pack(fill="x", before=c))
    bloc_b = next(bl for bl in voile.blocs if b in [e.widget for e in bl.elements])
    assert not bloc_b.part()
    pomper(racine, 1.5)
    assert not voile.actif
    assert cadre.pack_slaves() == [b, c]


@ecran
def test_terminer_baisse_le_calque(liste):
    from gestionnaire.voile import Voile
    racine, cadre = liste
    a, b = cases(cadre, ["#aa3333", "#33aa33"])
    voile = Voile(cadre)
    pomper(racine, 0.3)
    voile.changer(lambda: a.pack_forget())
    voile.terminer()
    assert not voile.actif and not voile.blocs and voile._tache is None
    pomper(racine, 0.1)
    assert DERIVE > 0 and MARGE % 2 == 0
