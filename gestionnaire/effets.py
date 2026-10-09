"""Animations de l'interface : transitions de couleur et de taille, survol, éclats."""

import time
import tkinter
import weakref

IMAGE_MS = 16


def _rgb(couleur: str) -> tuple[int, int, int]:
    c = couleur.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def melanger(c1: str, c2: str, t: float) -> str:
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x + (y - x) * t))) for x, y in zip(a, b))


def adoucir(t: float) -> float:
    return 1 - (1 - t) ** 3


def rebond(t: float) -> float:
    """Dépasse légèrement la cible puis revient : effet « pop »."""
    c1 = 1.9
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def lineaire(t: float) -> float:
    return t


def _dans(chemin: str, nom: str) -> bool:
    return chemin == nom or chemin.startswith(nom + ".")


def pointeur_dans(widget) -> bool:
    try:
        x, y = widget.winfo_pointerxy()
        chemin = str(widget.tk.call("winfo", "containing", x, y))
    except tkinter.TclError:
        return False
    return _dans(chemin, str(widget))


_figes = set()  # conteneurs figés pendant qu'un calque les recouvre
_survoles = weakref.WeakSet()  # widgets qui réagissent au survol


def _fige(widget) -> bool:
    nom = str(widget)
    return any(_dans(nom, conteneur) for conteneur in _figes)


def figer(conteneur):
    """Met en pause les animations et le survol des widgets de « conteneur », pendant
    qu'un calque le recouvre : rien n'y change d'apparence. (La souris survole alors le
    calque : pour les widgets dessous, ce n'est pas une vraie sortie.)"""
    _figes.add(str(conteneur))


def animer(widget, cle, duree, etape, fin=None, courbe=adoucir):
    """Appelle etape(t) à chaque image pendant `duree` secondes.

    Une nouvelle animation sur la même clé remplace la précédente.
    """
    racine = widget._root()
    taches = widget.__dict__.setdefault("_animations", {})
    ancienne = taches.pop(cle, None)
    if ancienne:
        try:
            racine.after_cancel(ancienne)
        except tkinter.TclError:
            pass
    horloge = {"debut": time.perf_counter(), "vu": time.perf_counter()}

    def tick():
        taches.pop(cle, None)
        try:
            if not widget.winfo_exists():
                return
            maintenant = time.perf_counter()
            if _fige(widget):
                # En pause : le temps passé figé ne compte pas.
                horloge["debut"] += maintenant - horloge["vu"]
                horloge["vu"] = maintenant
                taches[cle] = racine.after(IMAGE_MS, tick)
                return
            horloge["vu"] = maintenant
            t = 1.0 if duree <= 0 else min(1.0, (maintenant - horloge["debut"]) / duree)
            etape(courbe(t))
            if t < 1:
                taches[cle] = racine.after(IMAGE_MS, tick)
            elif fin:
                fin()
        except tkinter.TclError:
            pass  # widget détruit pendant l'animation

    tick()


def definir(widget, nom, valeur):
    """Fixe la valeur courante d'une propriété animée (sans animation)."""
    widget.__dict__.setdefault("_etats_anim", {})[nom] = valeur


def valeur(widget, nom, defaut=None):
    return widget.__dict__.get("_etats_anim", {}).get(nom, defaut)


def transition(widget, nom, cible, duree, applique, courbe=adoucir):
    """Fait glisser une propriété (couleur ou nombre) de sa valeur actuelle vers `cible`."""
    etats = widget.__dict__.setdefault("_etats_anim", {})
    depart = etats.get(nom, cible)
    if isinstance(cible, str):
        def interp(t):
            return melanger(depart, cible, t)
    else:
        def interp(t):
            return depart + (cible - depart) * t

    def etape(t):
        v = interp(t)
        etats[nom] = v
        applique(v)

    animer(widget, nom, duree, etape, courbe=courbe)


def liberer(conteneur):
    """Fin de figer() : les animations reprennent où elles en étaient, et chaque widget
    de « conteneur » prend l'état de survol qui correspond à la souris."""
    _figes.discard(str(conteneur))
    try:
        x, y = conteneur.winfo_pointerxy()
        chemin = str(conteneur.tk.call("winfo", "containing", x, y))
    except tkinter.TclError:
        return
    nom = str(conteneur)
    for widget in list(_survoles):
        if _dans(str(widget), nom):
            for recalculer in widget.__dict__.get("_survols", ()):
                recalculer(chemin)


def survol(widget, entrer, sortir):
    """Appelle entrer()/sortir() quand la souris entre ou quitte le widget et tout son contenu."""
    etat = {"dedans": False}

    def changer(dedans):
        if dedans != etat["dedans"]:
            etat["dedans"] = dedans
            (entrer if dedans else sortir)()

    def sur_entree(_e):
        if not _fige(widget):
            changer(True)

    def verifier():
        try:
            if etat["dedans"] and not _fige(widget) and not pointeur_dans(widget):
                changer(False)
        except tkinter.TclError:
            pass

    def sur_sortie(_e):
        try:
            widget._root().after(30, verifier)
        except tkinter.TclError:
            pass

    def recalculer(chemin):
        try:
            if widget.winfo_exists():
                changer(_dans(chemin, str(widget)))
        except tkinter.TclError:
            pass

    tkinter.Misc.bind(widget, "<Enter>", sur_entree, "+")
    tkinter.Misc.bind(widget, "<Leave>", sur_sortie, "+")
    # Rangé sur le widget lui-même : il disparaît avec lui.
    widget.__dict__.setdefault("_survols", []).append(recalculer)
    _survoles.add(widget)
