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


def cases_cliquables(cadre, couleurs):
    """Comme cases(), avec la liste des clics reçus par chaque carte."""
    resultat = []
    for case in cases(cadre, couleurs):
        clics = []
        carte = case.winfo_children()[0]
        carte.bind("<ButtonPress-1>", lambda _e, c=clics: c.append("appui"))
        carte.bind("<ButtonRelease-1>", lambda _e, c=clics: c.append("relache"))
        resultat.append((case, clics))
    return resultat


def cliquer(voile, widget, bouton=1):
    """Clic réel au milieu de « widget », qui arrive sur le calque s'il est levé."""
    x = widget.winfo_rootx() + widget.winfo_width() // 2
    y = widget.winfo_rooty() + widget.winfo_height() // 2
    options = dict(x=x - voile.toile.winfo_rootx(), y=y - voile.toile.winfo_rooty(),
                   rootx=x, rooty=y)
    voile.toile.event_generate("<ButtonPress-%d>" % bouton, **options)
    if bouton in (1, 2, 3):
        voile.toile.event_generate("<ButtonRelease-%d>" % bouton, **options)


@ecran
def test_clic_sur_un_element_a_sa_place(liste):
    from gestionnaire.voile import Voile
    racine, cadre = liste
    (a, clics_a), (b, clics_b), (c, _) = cases_cliquables(cadre, ["#aa3333", "#33aa33", "#3333aa"])
    voile = Voile(cadre)
    pomper(racine, 0.3)
    voile.changer(lambda: c.pack_forget())  # a et b ne bougent pas
    assert voile.actif
    cliquer(voile, b)
    # L'animation s'arrête et le clic arrive à la carte visée, tout de suite.
    assert not voile.actif
    assert clics_b == ["appui", "relache"] and clics_a == []


@ecran
def test_clic_sur_un_element_en_mouvement(liste):
    from gestionnaire.voile import Voile
    racine, cadre = liste
    (a, clics_a), (b, clics_b), (c, clics_c) = cases_cliquables(cadre, ["#aa3333", "#33aa33", "#3333aa"])
    voile = Voile(cadre)
    pomper(racine, 0.3)
    position = b.winfo_rooty()
    voile.changer(lambda: a.pack_forget())  # b et c remontent
    pomper(racine, 0.12)
    # On vise b là où il est dessiné ; dessous, la vraie liste a déjà c à cet endroit.
    bloc_b = next(bl for bl in voile.blocs if b in [e.widget for e in bl.elements])
    assert not bloc_b.a_sa_place()
    x = b.winfo_rootx() + 50
    y = voile.toile.winfo_rooty() + round(bloc_b.y) + 30
    voile.toile.event_generate("<ButtonPress-1>", x=50, y=y - voile.toile.winfo_rooty(), rootx=x, rooty=y)
    voile.toile.event_generate("<ButtonRelease-1>", x=50, y=y - voile.toile.winfo_rooty(), rootx=x, rooty=y)
    # L'animation s'arrête, mais le clic ne part pas sur une autre carte que celle vue.
    assert not voile.actif
    assert clics_a == clics_b == clics_c == []
    assert b.winfo_rooty() < position


@ecran
def test_molette_pendant_l_animation(liste):
    from gestionnaire.voile import Voile
    racine, cadre = liste
    elements = cases(cadre, ["#aa3333", "#33aa33", "#3333aa"] * 4)
    voile = Voile(cadre)
    pomper(racine, 0.3)
    voile.changer(lambda: elements[0].pack_forget())
    cliquer(voile, elements[1], bouton=5)
    assert not voile.actif
    pomper(racine, 0.05)
    assert voile.vue.canvasy(0) > 0  # la liste a défilé


@ecran
def test_defilement_sous_le_calque(liste):
    from gestionnaire.voile import Voile
    racine, cadre = liste
    elements = cases(cadre, ["#aa3333", "#33aa33", "#3333aa"] * 4)
    voile = Voile(cadre)
    pomper(racine, 0.3)
    voile.changer(lambda: elements[0].pack_forget())
    voile.vue.yview_moveto(0.3)  # barre de défilement, qui n'est pas sous le calque
    pomper(racine, 0.05)
    assert not voile.actif  # le calque ne montre plus une liste qui n'est plus là


@ecran
def test_defilement_anime_arrete_par_le_voile(liste):
    from gestionnaire.effets import animer
    from gestionnaire.voile import Voile
    racine, cadre = liste
    elements = cases(cadre, ["#aa3333", "#33aa33", "#3333aa"] * 4)
    voile = Voile(cadre)
    pomper(racine, 0.3)
    vue = voile.vue
    animer(vue, "defilement", 0.4, lambda t: vue.yview_moveto(0.5 * t))
    pomper(racine, 0.1)
    voile.changer(lambda: elements[-1].pack_forget())
    position = vue.canvasy(0)
    pomper(racine, 1.5)
    assert not voile.actif
    assert vue.canvasy(0) == position  # le défilement ne reprend pas après le voile


@ecran
def test_ecran_detruit_pendant_l_animation(liste):
    import customtkinter as ctk

    from gestionnaire import effets
    from gestionnaire.voile import Voile
    racine, _cadre = liste
    erreurs = []
    racine.report_callback_exception = lambda *e: erreurs.append(e)
    ecran_ = ctk.CTkFrame(racine)
    ecran_.pack(fill="both", expand=True)
    cadre = ctk.CTkScrollableFrame(ecran_)
    cadre.pack(fill="both", expand=True)
    a, b = cases(cadre, ["#aa3333", "#33aa33"])
    voile = Voile(cadre)
    pomper(racine, 0.3)
    vue = str(voile.vue)
    voile.changer(lambda: a.pack_forget())
    pomper(racine, 0.05)
    ecran_.destroy()  # verrouillage pendant l'animation
    pomper(racine, 0.3)
    assert not voile.actif and not voile.blocs and voile._tache is None
    assert vue not in effets._figes
    assert erreurs == []


@ecran
def test_le_fil_principal_n_attend_jamais_un_ouvrier(liste, monkeypatch):
    import concurrent.futures
    import threading

    from gestionnaire import voile as module
    from gestionnaire.voile import Voile
    racine, cadre = liste
    a, b = cases(cadre, ["#aa3333", "#33aa33"])
    bloque = threading.Event()
    ouvrier = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    ouvrier.submit(bloque.wait)  # les calculs de fumée ne commenceront jamais
    monkeypatch.setattr(module, "_executeur", lambda: ouvrier)
    try:
        voile = Voile(cadre)
        pomper(racine, 0.3)
        voile.changer(lambda: a.pack_forget())
        bloc = voile.blocs[0]
        debut = time.perf_counter()
        rendu = bloc._image_fumee(5, attendre=True)
        assert time.perf_counter() - debut < 1
        assert rendu is not None and rendu is not module._PAS_PRET
        voile.terminer()
        assert bloc.montre is None  # plus d'image Tk gardée par un bloc effacé
    finally:
        bloque.set()
        ouvrier.shutdown()
