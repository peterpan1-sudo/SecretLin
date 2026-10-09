"""Animation de la liste quand la recherche la filtre.

Un calque (une toile) recouvre la liste le temps de l'animation. Il montre d'abord la
liste telle qu'elle est ; la vraie liste change ensuite dessous, d'un coup, sans qu'on
la voie. Sur le calque, chaque élément est une image qui va de son ancienne place à la
nouvelle : ceux qu'on écarte glissent vers le bas en se dissipant en fumée, les autres
remontent occuper la place, ceux qui reviennent se condensent. À la fin, le calque
repasse sous la liste, qui a exactement la même apparence : rien ne bouge à ce moment-là.

Pourquoi un calque : sous Wayland (XWayland), une fenêtre qu'on affiche, cache ou
redimensionne apparaît un instant vide, le temps que Tk la redessine. Ici, rien de tout
cela n'est visible : on ne fait que déplacer des images sur une seule toile. Le serveur
garde le contenu de la liste et du calque quand ils sont recouverts (garder_contenu) :
passer de l'un à l'autre se fait sans image vide entre les deux.
"""

import concurrent.futures
import math
import time
import tkinter

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageTk

from gestionnaire.capture import garder_contenu, photographier
from gestionnaire.effets import figer, liberer

IMAGE_S = 1 / 60
DUREE_FUMEE = 0.5     # un élément écarté se dissipe
DUREE_PLACE = 0.45    # les éléments qui restent rejoignent leur nouvelle place
DUREE_RETOUR = 0.4    # un élément qui revient se condense
DELAI_PLACE = 0.08    # les éléments qui restent partent juste après la fumée
DELAI_RETOUR = 0.15   # un élément qui revient attend que sa place commence à s'ouvrir
DERIVE = 34           # glissement vers le bas d'un élément qui se dissipe (pixels)
DERIVE_RETOUR = 16    # un élément qui revient monte de cette hauteur en se condensant
NIVEAUX = 16          # étapes de fumée, calculées à l'avance
FLOU = 12.0           # rayon du flou quand l'élément a disparu (pixels)
ECLAT = 0.35          # la fumée s'éclaircit un peu en se formant
GONFLE = 24           # elle gonfle de ce nombre de pixels en largeur et en hauteur
MARGE = 24            # elle déborde de l'élément de cette largeur (nombre pair)
ESSAIS_PHOTO = 12     # photos de la nouvelle liste avant de renoncer à une photo stable

_PAS_PRET = object()
_SEUIL = [0] * 3 + [255] * 253
_ouvriers = None


def _executeur():
    global _ouvriers
    if _ouvriers is None:
        # Le flou se calcule sans bloquer Python : plusieurs niveaux à la fois.
        _ouvriers = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="fumee")
    return _ouvriers


def base_fumee(bande, fond):
    """La bande entourée d'une marge (la fumée déborde), en taille réelle et réduite de
    moitié : très floue, la fumée se calcule sur une image quatre fois plus petite."""
    toile = Image.new("RGB", (bande.width + 2 * MARGE, bande.height + 2 * MARGE), fond)
    toile.paste(bande, (MARGE, MARGE))
    return toile, toile.reduce(2)


def fumee(bases, fond, s):
    """La bande dissipée au niveau s (0 : nette, 1 : disparue), recadrée sur ce qui en
    reste visible : (image, décalage x, décalage y) par rapport au coin de la bande, ou
    None s'il ne reste rien. « bases » vient de base_fumee()."""
    pleine, demie = bases
    rayon = FLOU * s ** 1.5
    if rayon < 1.6:
        image, echelle = pleine.filter(ImageFilter.GaussianBlur(rayon)), 1
    else:
        image, echelle = demie.filter(ImageFilter.GaussianBlur(rayon / 2)), 2
    image = ImageEnhance.Color(image).enhance(1 - s)  # une fumée est grise
    # Elle s'éclaircit un peu en se formant, puis se dissipe dans le fond.
    uni = Image.new("RGB", image.size, fond)
    image = Image.blend(uni, image, (1 + ECLAT * math.sin(math.pi * s)) * (1 - s * s * (3 - 2 * s)))
    # Le gris décale très légèrement la couleur du fond : un écart de 1 ou 2 n'est pas
    # de la fumée.
    boite = ImageChops.difference(image, uni).convert("L").point(_SEUIL).getbbox()
    if not boite:
        return None
    gauche, haut, droite, bas = boite
    # Et elle gonfle.
    largeur = round((droite - gauche) * echelle + GONFLE * s)
    hauteur = round((bas - haut) * echelle + GONFLE * s)
    image = image.crop(boite)
    if image.size != (largeur, hauteur):
        image = image.resize((largeur, hauteur), Image.BILINEAR)
    x = (gauche + droite) * echelle / 2 - MARGE - largeur / 2
    y = (haut + bas) * echelle / 2 - MARGE - hauteur / 2
    return image, round(x), round(y)


class _Element:
    """Un élément de la liste (en-tête de section, carte…) et son apparence."""

    def __init__(self, widget, hauteur):
        self.widget = widget
        self.hauteur = hauteur
        self.image = None      # apparence, prise sur une photo de la liste
        self.lignes = (0, 0)   # lignes de self.image qui viennent d'une photo
        self.apres = None      # haut de l'élément dans la nouvelle liste (None : écarté)
        self.bloc = None

    def complet(self):
        return self.lignes == (0, self.hauteur)

    def relever(self, photo, haut_photo, haut, fond):
        """Prend sur « photo » (qui commence à la ligne haut_photo de la liste) les
        lignes visibles de l'élément, placé à la ligne « haut »."""
        a = max(0, haut_photo - haut)
        b = min(self.hauteur, haut_photo + photo.height - haut)
        if b <= a:
            return
        # Une nouvelle image : l'ancienne sert peut-être en ce moment au calcul de la fumée.
        if self.image is None or self.image.width != photo.width:
            image, self.lignes = Image.new("RGB", (photo.width, self.hauteur), fond), (a, b)
        else:
            image = self.image.copy()
            self.lignes = (min(a, self.lignes[0]), max(b, self.lignes[1]))
        image.paste(photo.crop((0, haut + a - haut_photo, photo.width, haut + b - haut_photo)), (0, a))
        self.image = image


class _Bloc:
    """Une image du calque : un élément, ou plusieurs éléments voisins qui se dissipent
    ensemble (une seule fumée, sans raccord entre eux)."""

    def __init__(self, voile, elements, y):
        self.voile = voile
        self.elements = elements
        for e in elements:
            e.bloc = self
        self.hauteur = sum(e.hauteur for e in elements)
        self.y, self.v = float(y), 0.0   # haut du bloc et vitesse (pixels/s)
        self.f = 0.0                     # 0 : net ; 1 : dissipé
        self.mouvement = None            # (début, durée, départ, pente, arrivée)
        self.fondu = None                # (début, durée, départ, arrivée)
        self.item = voile.toile.create_image(0, 0, anchor="nw", state="hidden")
        self.montre = None
        self._oublier()

    def _oublier(self):
        """L'apparence a changé : les images déjà préparées ne servent plus."""
        for futur in getattr(self, "_niveaux", {}).values():
            futur.cancel()
        for item in getattr(self, "_chauffe", {}).values():
            self.voile.toile.delete(item)
        self._chauffe = {}  # niveau -> élément caché qui garde son image prête pour l'écran
        self._bande = None
        self._base = None
        self._nette = None
        self._niveaux = {}  # niveau -> calcul en cours ou fini
        self._photos = {}   # niveau -> (PhotoImage, dx, dy), ou None si plus rien de visible

    def copie(self, elements, decalage):
        """Nouveau bloc pour une partie des éléments, dans le même état que celui-ci."""
        b = _Bloc(self.voile, elements, self.y + decalage)
        b.v, b.f, b.fondu = self.v, self.f, self.fondu
        if self.mouvement:
            debut, duree, depart, pente, arrivee = self.mouvement
            b.mouvement = (debut, duree, depart + decalage, pente, arrivee + decalage)
        return b

    # --- Trajectoire ---------------------------------------------------------

    def avancer(self, t):
        if self.mouvement:
            debut, duree, depart, pente, arrivee = self.mouvement
            u = (t - debut) / duree
            if u >= 1:
                self.y, self.v, self.mouvement = arrivee, 0.0, None
            elif u > 0:
                # Courbe d'Hermite : part à la vitesse actuelle, arrive à vitesse nulle.
                u2, u3 = u * u, u * u * u
                self.y = ((2 * u3 - 3 * u2 + 1) * depart + (u3 - 2 * u2 + u) * pente
                          + (3 * u2 - 2 * u3) * arrivee)
                self.v = ((6 * u2 - 6 * u) * (depart - arrivee) + (3 * u2 - 4 * u + 1) * pente) / duree
        if self.fondu:
            debut, duree, depart, arrivee = self.fondu
            u = (t - debut) / duree if duree > 0 else 1.0
            if u >= 1:
                self.f, self.fondu = arrivee, None
            elif u > 0:
                self.f = depart + (arrivee - depart) * u

    def aller(self, t, arrivee, duree, delai=0.0):
        if self.mouvement and self.mouvement[4] == arrivee:
            return  # même destination : le mouvement continue tel quel
        if not self.mouvement and abs(self.y - arrivee) < 0.5:
            self.y = arrivee
            return
        if self.v:
            delai = 0.0  # déjà en route : il repart d'où il est, sans s'arrêter
        self.mouvement = (t + delai, duree, self.y, self.v * duree, arrivee)

    def estomper(self, t, arrivee, duree, delai=0.0):
        """Va vers le niveau de fumée « arrivee » ; « duree » est celle d'un trajet complet."""
        if self.fondu and self.fondu[3] == arrivee or not self.fondu and self.f == arrivee:
            return
        self.fondu = (t + delai, duree * abs(arrivee - self.f), self.f, arrivee)
        self.preparer()

    def destination(self):
        return self.mouvement[4] if self.mouvement else self.y

    def part(self):
        return (self.fondu[3] if self.fondu else self.f) == 1.0

    def au_repos(self):
        return self.mouvement is None and self.fondu is None

    def rang(self):
        """Ordre d'empilement : la fumée sous les éléments qui reviennent, eux-mêmes
        sous ceux qui restent (les cartes passent par-dessus la fumée)."""
        if self.part():
            return 0
        return 1 if self.f > 0 or self.fondu else 2

    # --- Images --------------------------------------------------------------

    def bande(self):
        """Apparence du bloc (image PIL), ou None tant qu'un élément n'a pas été vu."""
        if self._bande is None:
            if any(e.image is None for e in self.elements):
                return None
            if len(self.elements) == 1:
                self._bande = self.elements[0].image
            else:
                self._bande = Image.new("RGB", (self.elements[0].image.width, self.hauteur),
                                        self.voile.fond)
                haut = 0
                for e in self.elements:
                    self._bande.paste(e.image, (0, haut))
                    haut += e.hauteur
        return self._bande

    def _image_nette(self):
        if self._nette is None:
            bande = self.bande()
            if bande is None:
                return None
            # Seul ce qui n'est pas du fond est posé sur le calque : le reste ne cache rien.
            boite = ImageChops.difference(bande, Image.new("RGB", bande.size, self.voile.fond)).getbbox()
            self._nette = ((ImageTk.PhotoImage(bande.crop(boite), master=self.voile.toile),
                            boite[0], boite[1]) if boite else None,)
        return self._nette[0]

    def preparer(self):
        """Lance le calcul des niveaux de fumée, dans l'ordre où ils vont servir."""
        bande = self.bande()
        if bande is None:
            return
        if self._base is None:
            self._base = base_fumee(bande, self.voile.fond)
        n = round(self.f * NIVEAUX)
        cible = self.fondu[3] if self.fondu else self.f
        ordre = range(max(n, 1), NIVEAUX) if cible > self.f else range(min(n, NIVEAUX - 1), 0, -1)
        for k in ordre:
            if k not in self._niveaux:
                self._niveaux[k] = _executeur().submit(fumee, self._base, self.voile.fond, k / NIVEAUX)

    def _image_fumee(self, n, attendre=False):
        if n in self._photos:
            return self._photos[n]
        if n not in self._niveaux:
            self.preparer()
            if n not in self._niveaux:
                return None
        futur = self._niveaux[n]
        if not futur.done() and not attendre:
            return _PAS_PRET
        resultat = futur.result()
        self._photos[n] = resultat and (
            ImageTk.PhotoImage(resultat[0], master=self.voile.toile), resultat[1], resultat[2])
        return self._photos[n]

    def anticiper(self):
        """Prépare les images des prochains niveaux, pour que l'image suivante n'ait plus
        qu'à les poser."""
        if not self.fondu:
            return
        n = round(self.f * NIVEAUX)
        pas = 1 if self.fondu[3] > self.f else -1
        prochains = (n + pas, n + 2 * pas)
        for k in prochains:
            if k == 0:
                rendu = self._image_nette()
            elif 0 < k < NIVEAUX and (k in self._photos or k in self._niveaux and self._niveaux[k].done()):
                rendu = self._image_fumee(k)
            else:
                continue
            if rendu and k not in self._chauffe:
                # Tk convertit une image pour l'écran la première fois qu'elle est posée
                # sur la toile : un élément caché le lui fait faire dès maintenant.
                self._chauffe[k] = self.voile.toile.create_image(0, 0, image=rendu[0], state="hidden")
        for k in [k for k in self._chauffe if k not in prochains]:
            self.voile.toile.delete(self._chauffe.pop(k))

    def dessiner(self):
        n = round(self.f * NIVEAUX)
        if n >= NIVEAUX:
            rendu = None
        elif n == 0:
            rendu = self._image_nette()
        else:
            rendu = self._image_fumee(n)
        if rendu is _PAS_PRET:
            # Niveau pas encore calculé : on garde le précédent, ou on l'attend s'il n'y
            # en a pas (le bloc vient d'être créé et ne doit pas manquer à l'écran).
            rendu = self.montre if self.montre is not None else self._image_fumee(n, attendre=True)
        toile = self.voile.toile
        if rendu is None:
            toile.itemconfigure(self.item, state="hidden")
        else:
            photo, dx, dy = rendu
            if rendu is not self.montre:
                toile.itemconfigure(self.item, image=photo, state="normal")
            toile.coords(self.item, dx, round(self.y) + dy)
        self.montre = rendu

    def effacer(self):
        self._oublier()
        self.voile.toile.delete(self.item)


class Voile:
    """Calque d'animation d'une liste (CTkScrollableFrame) dont les éléments sont
    empilés avec pack() : changer() anime le passage d'un contenu à l'autre."""

    def __init__(self, liste):
        self.liste = liste
        self.vue = liste._parent_canvas
        self.toile = tkinter.Canvas(self.vue.master, bg=self.vue.cget("bg"), bd=0,
                                    highlightthickness=0)
        self.toile.place(in_=self.vue, x=0, y=0, relwidth=1, relheight=1)
        tkinter.Misc.lower(self.toile, self.vue)
        self.fond = tuple(v >> 8 for v in self.vue.winfo_rgb(self.vue.cget("bg")))
        self.garde = False
        self.actif = False
        self.blocs = []
        self._tache = None
        self._debut_image = 0.0
        self._taille = None
        self._attente = []
        self.vue.bind("<Configure>", self._redimensionnee, "+")

    # --- Interface -----------------------------------------------------------

    def changer(self, appliquer):
        """Appelle appliquer(), qui change le contenu de la liste, et anime le passage
        de l'ancien contenu au nouveau. Peut être appelé pendant une animation."""
        maintenant = time.perf_counter()
        if not self.actif and not self._lever():
            appliquer()
            return
        for b in self.blocs:
            b.avancer(maintenant)
        try:
            appliquer()
            self._repartir(maintenant)
        except BaseException:
            self.terminer()
            raise
        self._planifier()

    def terminer(self):
        """Arrête l'animation : la liste s'affiche aussitôt dans son état final."""
        if self._tache is not None:
            self.toile.after_cancel(self._tache)
            self._tache = None
        if self.actif:
            self._baisser()

    # --- Début et fin --------------------------------------------------------

    def _lever(self):
        """Pose sur la liste un calque qui en montre l'apparence actuelle."""
        if not self.vue.winfo_viewable():
            return False
        if not self.garde:
            # Sans cela, découvrir la liste ou le calque montrerait un instant une zone
            # vide. Demandé une fois les fenêtres affichées : le serveur doit les connaître.
            self.garde = garder_contenu(self.vue) and garder_contenu(self.toile)
            if not self.garde:
                return False  # Windows, macOS… : pas d'animation, la liste change d'un coup
        largeur, hauteur = self.vue.winfo_width(), self.vue.winfo_height()
        visibles = [(w, y, h) for w, y, h in self._disposition() if y < hauteur and y + h > 0]
        haut = max(0, min((y for _w, y, _h in visibles), default=0))
        bas = min(hauteur, max((y + h for _w, y, h in visibles), default=0))
        photo = None
        if bas > haut:
            photo = photographier(self.vue, (0, haut, largeur, bas - haut))
            if photo is None:
                return False
        self._taille = (largeur, hauteur)
        for w, y, h in visibles:
            e = _Element(w, h)
            e.relever(photo, haut, y, self.fond)
            self.blocs.append(_Bloc(self, [e], y))
        for b in self.blocs:
            b.dessiner()
        # Le calque est dessiné pendant qu'il est caché : levé, il montre déjà la liste.
        self.toile.update_idletasks()
        tkinter.Misc.tkraise(self.toile, self.vue)
        figer(self.vue)
        self.actif = True
        return True

    def _baisser(self):
        self.vue.update_idletasks()
        tkinter.Misc.lower(self.toile, self.vue)
        for b in self.blocs:
            b.effacer()
        self.blocs = []
        self._attente = []
        self.actif = False
        liberer(self.vue)

    def _redimensionnee(self, evenement):
        if self.actif and (evenement.width, evenement.height) != self._taille:
            self.terminer()

    # --- Animation -----------------------------------------------------------

    def _disposition(self):
        """[(widget, haut, hauteur)] des éléments de la liste, en pixels depuis le haut de
        la zone visible."""
        self.liste.update_idletasks()
        self.vue.configure(scrollregion=self.vue.bbox("all"))
        defilement = round(self.vue.canvasy(0))
        return [(w, w.winfo_y() - defilement, w.winfo_height()) for w in self.liste.pack_slaves()]

    def _repartir(self, t):
        """Donne à chaque bloc sa destination dans la nouvelle liste."""
        largeur, hauteur = self._taille
        disposition = self._disposition()
        nouveau = {w: (y, h) for w, y, h in disposition}
        for b in self.blocs:
            for e in b.elements:
                y, h = nouveau.get(e.widget, (None, None))
                e.apres = y if h == e.hauteur else None
        anciens, self.blocs = self.blocs, []
        for b in anciens:
            self.blocs.extend(self._decouper(b))
        self.blocs = self._regrouper(self.blocs)

        # Ceux qui commencent à partir laissent un court instant d'avance à la fumée.
        depart = any(b.elements[0].apres is None and not b.part() for b in self.blocs)
        for b in self.blocs:
            arrivee = b.elements[0].apres
            if arrivee is None:
                if not b.part():
                    b.aller(t, b.y + DERIVE, DUREE_FUMEE)
                    b.estomper(t, 1.0, DUREE_FUMEE)
            else:
                b.aller(t, arrivee, DUREE_PLACE, DELAI_PLACE if depart else 0.0)
                b.estomper(t, 0.0, DUREE_RETOUR)

        # Les éléments qui apparaissent dans la zone visible ; voisins, ils forment un bloc.
        connus = {e.widget for b in self.blocs for e in b.elements}
        groupes = []
        for w, y, h in disposition:
            if w in connus or y >= hauteur or y + h <= 0:
                continue
            e = _Element(w, h)
            e.apres = y
            if groupes and groupes[-1][-1].apres + groupes[-1][-1].hauteur == y:
                groupes[-1].append(e)
            else:
                groupes.append([e])
        for groupe in groupes:
            b = _Bloc(self, groupe, groupe[0].apres + DERIVE_RETOUR)
            b.f = 1.0
            b.aller(t, groupe[0].apres, DUREE_RETOUR, DELAI_RETOUR)
            b.estomper(t, 0.0, DUREE_RETOUR, DELAI_RETOUR)
            self.blocs.append(b)

        for b in sorted(self.blocs, key=_Bloc.rang):
            self.toile.tag_raise(b.item)
            b.dessiner()  # les blocs remplacés sont déjà effacés : rien ne doit manquer

        # Ce qu'on n'a pas encore vu en entier sera pris sur une photo de la nouvelle liste.
        self._attente = [e for b in self.blocs for e in b.elements if e.apres is not None
                         and e.apres < hauteur and e.apres + e.hauteur > 0 and not e.complet()]
        self._essais = 0
        self._derniere = None
        self._images_depuis = 0

    def _decouper(self, bloc):
        """Sépare un bloc dont les éléments n'ont plus le même sort."""
        morceaux, debut = [], 0
        elements = bloc.elements
        for i in range(1, len(elements) + 1):
            if i < len(elements):
                a, b = elements[i - 1], elements[i]
                ensemble = (a.apres is None and b.apres is None) or (
                    a.apres is not None and b.apres == a.apres + a.hauteur)
                if ensemble:
                    continue
            morceaux.append(elements[debut:i])
            debut = i
        if len(morceaux) == 1:
            return [bloc]
        resultat, decalage = [], 0
        for groupe in morceaux:
            resultat.append(bloc.copie(groupe, decalage))
            decalage += sum(e.hauteur for e in groupe)
        bloc.effacer()
        return resultat

    def _regrouper(self, blocs):
        """Réunit les éléments voisins qui commencent à partir ensemble : une seule fumée,
        sans raccord entre eux."""
        def commence_a_partir(b):
            return b.elements[0].apres is None and not b.part() and b.au_repos() and b.f == 0

        resultat = []
        for b in sorted(blocs, key=lambda b: b.y):
            p = resultat[-1] if resultat else None
            if p and commence_a_partir(p) and commence_a_partir(b) and p.y + p.hauteur == b.y:
                resultat[-1] = _Bloc(self, p.elements + b.elements, p.y)
                p.effacer()
                b.effacer()
            else:
                resultat.append(b)
        return resultat

    def _planifier(self):
        """Prochaine image un soixantième de seconde après le début de celle-ci : des
        images régulières, sans en rattraper deux d'affilée après un retard."""
        if self._tache is None:
            maintenant = time.perf_counter()
            delai = max(4, int((self._debut_image + IMAGE_S - maintenant) * 1000))
            self._tache = self.toile.after(delai, self._image)

    def _image(self):
        self._tache = None
        self._debut_image = time.perf_counter()
        try:
            if not self.toile.winfo_exists():
                return
            t = time.perf_counter()
            for b in self.blocs:
                b.avancer(t)
            restants = []
            for b in self.blocs:
                if b.part() and b.au_repos():
                    b.effacer()  # complètement dissipé
                else:
                    restants.append(b)
            self.blocs = restants
            for b in self.blocs:
                b.dessiner()
            if not self._attente and all(b.au_repos() for b in self.blocs):
                self._baisser()
            else:
                self._planifier()
                # Le reste du travail attend que cette image soit dessinée et envoyée à
                # l'écran (tâche d'attente, puis minuterie) : elle ne prend pas de retard.
                self.toile.after_idle(lambda: self.toile.after(0, self._entre_images))
        except tkinter.TclError:
            pass  # écran détruit pendant l'animation (verrouillage…)

    def _entre_images(self):
        try:
            if self.actif:
                self._photographier_nouvelle_liste()
                for b in self.blocs:
                    b.anticiper()
        except tkinter.TclError:
            pass

    def _photographier_nouvelle_liste(self):
        """Prend l'apparence des éléments qui arrivent sur la vraie liste, cachée sous le
        calque, une fois que Tk a fini de la dessiner (deux photos identiques)."""
        if not self._attente:
            return
        self._images_depuis += 1
        if self._images_depuis < 2:
            return
        largeur, hauteur = self._taille
        haut = max(0, min(e.apres for e in self._attente))
        bas = min(hauteur, max(e.apres + e.hauteur for e in self._attente))
        photo = photographier(self.vue, (0, haut, largeur, bas - haut))
        self._essais += 1
        octets = photo.tobytes() if photo is not None else None
        if (octets is None or octets != self._derniere) and self._essais < ESSAIS_PHOTO:
            self._derniere = octets
            return
        if photo is not None:
            for e in self._attente:
                e.relever(photo, haut, e.apres, self.fond)
            for b in {e.bloc for e in self._attente}:
                b._oublier()
                b.preparer()
        self._attente = []
