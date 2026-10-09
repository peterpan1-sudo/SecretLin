"""Deux services demandés directement au serveur X, pour l'animation de la recherche.

- photographier() : le contenu d'une fenêtre de l'application. On lit notre propre
  fenêtre et non l'écran : sous Wayland (XWayland), l'écran entier n'est pas lisible
  mais les fenêtres de l'application le sont. Rien n'est écrit sur le disque.
- garder_contenu() : le serveur conserve ce qu'affiche une fenêtre même quand une autre
  la recouvre (« backing store »). Sans cela, une fenêtre découverte reste vide le temps
  que Tk la redessine, et ce vide s'affiche un instant sous Wayland.
"""

import ctypes
import ctypes.util

from PIL import Image

ZPIXMAP = 2
TOUS_LES_PLANS = ctypes.c_ulong(-1).value
CW_BACKING_STORE = 1 << 6
TOUJOURS = 2


class _XImage(ctypes.Structure):
    # Début de la structure XImage de Xlib : les champs suivants ne servent pas ici.
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
                ("format", ctypes.c_int), ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
                ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int),
                ("bitmap_pad", ctypes.c_int), ("depth", ctypes.c_int),
                ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int),
                ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong),
                ("blue_mask", ctypes.c_ulong)]


class _AttributsFenetre(ctypes.Structure):
    # XSetWindowAttributes ; seul backing_store est lu (masque CW_BACKING_STORE).
    _fields_ = [("background_pixmap", ctypes.c_ulong), ("background_pixel", ctypes.c_ulong),
                ("border_pixmap", ctypes.c_ulong), ("border_pixel", ctypes.c_ulong),
                ("bit_gravity", ctypes.c_int), ("win_gravity", ctypes.c_int),
                ("backing_store", ctypes.c_int), ("backing_planes", ctypes.c_ulong),
                ("backing_pixel", ctypes.c_ulong), ("save_under", ctypes.c_int),
                ("event_mask", ctypes.c_long), ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int), ("colormap", ctypes.c_ulong),
                ("cursor", ctypes.c_ulong)]


_GestionErreur = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_erreurs = []
# Gardé dans une variable du module : Xlib l'appelle, il ne doit pas être libéré.
_noter_erreur = _GestionErreur(lambda _affichage, _evenement: _erreurs.append(1) or 0)

_xlib = None        # bibliothèque X11, chargée au premier appel (False : indisponible)
_affichages = {}    # connexion au serveur X, par nom d'écran


def _charger():
    global _xlib
    if _xlib is None:
        _xlib = False
        nom = ctypes.util.find_library("X11")
        if nom:
            try:
                x = ctypes.CDLL(nom)
            except OSError:
                return False
            x.XOpenDisplay.restype = ctypes.c_void_p
            x.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x.XGetImage.restype = ctypes.POINTER(_XImage)
            x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
            x.XDestroyImage.argtypes = [ctypes.POINTER(_XImage)]
            x.XChangeWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                                  ctypes.POINTER(_AttributsFenetre)]
            x.XSetErrorHandler.restype = ctypes.c_void_p
            x.XSetErrorHandler.argtypes = [ctypes.c_void_p]
            x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
            _xlib = x
    return _xlib


def _connexion(widget):
    """(Xlib, connexion au serveur X du widget), ou (None, None) hors de X11."""
    if widget.tk.call("tk", "windowingsystem") != "x11":
        return None, None
    x = _charger()
    if not x:
        return None, None
    ecran = widget.winfo_screen()
    if ecran not in _affichages:
        _affichages[ecran] = x.XOpenDisplay(ecran.encode())
    return (x, _affichages[ecran]) if _affichages[ecran] else (None, None)


def _demander(x, affichage, requete):
    """Envoie une requête et attend la réponse du serveur ; False s'il l'a refusée.

    Sans gestionnaire d'erreur, Xlib fermerait l'application sur un refus du serveur.
    Celui de Tk est remis aussitôt : Tk ne lit pas sa connexion pendant ce temps."""
    _erreurs.clear()
    ancien = x.XSetErrorHandler(ctypes.cast(_noter_erreur, ctypes.c_void_p))
    try:
        resultat = requete()
        x.XSync(affichage, 0)
    finally:
        x.XSetErrorHandler(ancien)
    return resultat, not _erreurs


def photographier(widget, zone=None):
    """Image RGB de « widget » tel qu'il est affiché (enfants compris), ou None si le
    système ne le permet pas (Windows, macOS, fenêtre en partie hors de l'écran…).

    « zone » (x, y, largeur, hauteur) limite la photo à une partie du widget : une photo
    plus petite se prend plus vite. Une fenêtre recouverte dont le contenu est gardé
    (garder_contenu) est lue telle qu'elle serait affichée, sans ce qui la recouvre."""
    x, affichage = _connexion(widget)
    if zone is None:
        zone = (0, 0, widget.winfo_width(), widget.winfo_height())
        if zone[2] <= 1 or zone[3] <= 1:
            return None  # pas encore affiché
    gauche, haut, largeur, hauteur = zone
    if not x or largeur < 1 or hauteur < 1:
        return None
    image, accepte = _demander(x, affichage, lambda: x.XGetImage(
        affichage, widget.winfo_id(), gauche, haut, largeur, hauteur, TOUS_LES_PLANS, ZPIXMAP))
    if not image:
        return None
    try:
        i = image.contents
        if not accepte or i.bits_per_pixel != 32 or (i.red_mask, i.green_mask, i.blue_mask) != (
                0xFF0000, 0xFF00, 0xFF):
            return None
        donnees = ctypes.string_at(i.data, i.bytes_per_line * i.height)
        brut = "BGRX" if i.byte_order == 0 else "XRGB"
        return Image.frombuffer("RGB", (i.width, i.height), donnees, "raw", brut,
                                i.bytes_per_line, 1).copy()
    finally:
        x.XDestroyImage(image)


def garder_contenu(widget):
    """Demande au serveur X de conserver le contenu de « widget » (et de ses enfants)
    quand il est recouvert. Renvoie False si ce n'est pas possible."""
    x, affichage = _connexion(widget)
    if not x:
        return False
    attributs = _AttributsFenetre(backing_store=TOUJOURS)
    _resultat, accepte = _demander(x, affichage, lambda: x.XChangeWindowAttributes(
        affichage, widget.winfo_id(), CW_BACKING_STORE, ctypes.byref(attributs)))
    return accepte
