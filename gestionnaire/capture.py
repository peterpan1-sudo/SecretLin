"""Photo d'une fenêtre de l'application, demandée directement au serveur X.

Sert à l'effet de fumée de la recherche. On lit le contenu de notre propre fenêtre et
non celui de l'écran : sous Wayland (XWayland), l'écran entier n'est pas lisible mais
les fenêtres de l'application le sont. Rien n'est écrit sur le disque.
"""

import ctypes
import ctypes.util

from PIL import Image

ZPIXMAP = 2
TOUS_LES_PLANS = ctypes.c_ulong(-1).value


class _XImage(ctypes.Structure):
    # Début de la structure XImage de Xlib : les champs suivants ne servent pas ici.
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
                ("format", ctypes.c_int), ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
                ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int),
                ("bitmap_pad", ctypes.c_int), ("depth", ctypes.c_int),
                ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int),
                ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong),
                ("blue_mask", ctypes.c_ulong)]


_GestionErreur = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_erreurs = []
# Gardé dans une variable du module : Xlib l'appelle, il ne doit pas être libéré.
_noter_erreur = _GestionErreur(lambda _affichage, _evenement: _erreurs.append(1) or 0)

_xlib = None        # bibliothèque X11, chargée à la première photo (False : indisponible)
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
            x.XSetErrorHandler.restype = ctypes.c_void_p
            x.XSetErrorHandler.argtypes = [ctypes.c_void_p]
            x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
            _xlib = x
    return _xlib


def photographier(widget):
    """Image RGB de « widget » tel qu'il est affiché (enfants compris), ou None si le
    système ne le permet pas (Windows, macOS, fenêtre en partie hors de l'écran…)."""
    if widget.tk.call("tk", "windowingsystem") != "x11":
        return None
    x = _charger()
    if not x:
        return None
    ecran = widget.winfo_screen()
    if ecran not in _affichages:
        _affichages[ecran] = x.XOpenDisplay(ecran.encode())
    affichage = _affichages[ecran]
    largeur, hauteur = widget.winfo_width(), widget.winfo_height()
    if not affichage or largeur <= 1 or hauteur <= 1:
        return None
    # Sans gestionnaire d'erreur, Xlib fermerait l'application sur un refus du serveur.
    # Celui de Tk est remis aussitôt : Tk ne lit pas sa connexion pendant ce temps.
    _erreurs.clear()
    ancien = x.XSetErrorHandler(ctypes.cast(_noter_erreur, ctypes.c_void_p))
    try:
        image = x.XGetImage(affichage, widget.winfo_id(), 0, 0, largeur, hauteur,
                            TOUS_LES_PLANS, ZPIXMAP)
        x.XSync(affichage, 0)
    finally:
        x.XSetErrorHandler(ancien)
    if not image:
        return None
    try:
        i = image.contents
        if _erreurs or i.bits_per_pixel != 32 or (i.red_mask, i.green_mask, i.blue_mask) != (
                0xFF0000, 0xFF00, 0xFF):
            return None
        donnees = ctypes.string_at(i.data, i.bytes_per_line * i.height)
        brut = "BGRX" if i.byte_order == 0 else "XRGB"
        return Image.frombuffer("RGB", (i.width, i.height), donnees, "raw", brut,
                                i.bytes_per_line, 1).copy()
    finally:
        x.XDestroyImage(image)
