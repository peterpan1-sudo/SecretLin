"""Interface graphique du gestionnaire de mots de passe."""

import datetime
import math
import threading
import time
import tkinter
import tkinter.font
from functools import lru_cache
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from gestionnaire import (
    acces_rapide, apparence, effets, fuites, guichet, import_externe, langue, porte, raccourci,
    sante, totp,
)
from gestionnaire.coffre import (
    AMBIGUS, SYMBOLES, Coffre, CoffreCorrompu, FichierCleRequis, MotDePasseIncorrect, attente_apres,
    evaluer_force,
    generer_mot_de_passe, verifier_force,
)
from gestionnaire.logo import dessiner as dessiner_logo
from gestionnaire.marques import style_pastille
from gestionnaire.langue import t, tn
from gestionnaire.effets import (
    adoucir, animer, definir, lineaire, melanger, rebond, survol, transition, valeur,
)
from gestionnaire.voile import Voile

DANGER = apparence.DANGER
SUCCES = apparence.SUCCES
BLEU = "#2f6fed"
LIBELLES_FORCE = ["", "Faible", "Moyen", "Fort", "Très fort"]  # traduits à l'affichage
FAVORI = "#f5b83d"  # étoile des favoris


def categories_proposees() -> list[str]:
    """Catégories proposées dans la fiche d'un compte, en plus de celles déjà utilisées."""
    return [t("Réseaux sociaux"), t("E-mail"), t("Banque"), t("Achats"), t("Jeux"),
            t("Divertissement"), t("Travail"), t("Études")]


def appliquer_apparence(reglages):
    """Met en place les couleurs (FOND, TEXTE, STYLES…), la taille du texte et les
    animations et la langue choisies. Les widgets créés ensuite les utilisent."""
    global ECHELLE_TEXTE, STYLE_POLICE, _famille
    globals().update(apparence.couleurs(reglages))
    ECHELLE_TEXTE = apparence.TAILLES[reglages["taille"]]
    STYLE_POLICE = reglages["police"]
    _famille = None  # recherchée de nouveau au prochain appel de police()
    effets.ANIMATIONS = reglages["animations"]
    langue.choisir(reglages["langue"])


appliquer_apparence(apparence.DEFAUT)

DELAI_SOURIS_IMMOBILE_S = 300  # souris sur la fenêtre mais sans bouger
DELAI_SOURIS_DEHORS_S = 120  # souris hors de la fenêtre
EFFACEMENT_PRESSE_PAPIER_S = 180


def mdp_copie() -> str:
    return t("Mot de passe copié — effacé dans {n} min", n=EFFACEMENT_PRESSE_PAPIER_S // 60)


def duree_lisible(secondes) -> str:
    """« 45 s », « 2 min 05 s » ou « 1 h 00 min »."""
    secondes = max(0, math.ceil(secondes))
    minutes, s = divmod(secondes, 60)
    heures, minutes = divmod(minutes, 60)
    if heures:
        return f"{heures} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {s:02d} s"
    return f"{s} s"


def police(taille=13, gras=False):
    global _famille
    if _famille is None:
        dispo = set(tkinter.font.families())
        _famille = next((f for f in (STYLE_POLICE,) + apparence.POLICES_SECOURS
                         if f in dispo), "TkDefaultFont")
    return ctk.CTkFont(family=_famille, size=round(taille * ECHELLE_TEXTE),
                       weight="bold" if gras else "normal")


def couleur_fond(widget) -> str:
    """Couleur de fond réellement visible derrière un widget."""
    w = widget
    while w is not None:
        try:
            c = w.cget("fg_color")
        except (ValueError, tkinter.TclError, AttributeError):
            c = None
        if isinstance(c, (list, tuple)):
            c = c[1]
        if c and c != "transparent":
            return c
        w = w.master
    return FOND


# --- Composants animés ------------------------------------------------------

@lru_cache(maxsize=2048)
def _image_bouton(largeur, hauteur, bouton_l, bouton_h, fond_parent, halo, fond, bord):
    """Halo arrondi et bouton arrondi (bordure 1 px), dessinés en 3× puis réduits :
    bords lisses et tailles au tiers de pixel près, pour un zoom fluide."""
    k = 3
    im = Image.new("RGB", (largeur * k, hauteur * k), fond_parent)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, largeur * k - 1, hauteur * k - 1), radius=12 * k, fill=halo)
    x0, y0 = (largeur * k - bouton_l) / 2, (hauteur * k - bouton_h) / 2
    x1, y1 = x0 + bouton_l - 1, y0 + bouton_h - 1
    d.rounded_rectangle((x0, y0, x1, y1), radius=9 * k, fill=bord)
    d.rounded_rectangle((x0 + k, y0 + k, x1 - k, y1 - k), radius=8 * k, fill=fond)
    return im.resize((largeur, hauteur), Image.LANCZOS)


@lru_cache(maxsize=16)
def _engrenage(taille, couleur):
    """Icône d'engrenage (8 dents, trou central), dessinée en 4× puis réduite."""
    k = 4
    s = taille * k
    c = s / 2
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r_dent, r_corps = s * 0.49, s * 0.36
    points = []
    for i in range(8):
        a = 2 * math.pi * i / 8
        for r, da in ((r_corps, -0.36), (r_dent, -0.2), (r_dent, 0.2), (r_corps, 0.36)):
            points.append((c + r * math.cos(a + da), c + r * math.sin(a + da)))
    d.polygon(points, fill=couleur)
    d.ellipse((c - r_corps, c - r_corps, c + r_corps, c + r_corps), fill=couleur)
    r_trou = s * 0.15
    d.ellipse((c - r_trou, c - r_trou, c + r_trou, c + r_trou), fill=(0, 0, 0, 0))
    return im.resize((taille, taille), Image.LANCZOS)


@lru_cache(maxsize=32)
def _pastille(taille, couleur, bord, anneau):
    """Rond de couleur entouré d'un anneau (ou sans, si anneau est None), dessiné en 4×
    puis réduit : bords lisses, sans pixels en escalier. Mesures sur une base de 38 px."""
    s = taille * 4
    u = s / 38
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if anneau:
        d.ellipse((2 * u, 2 * u, s - 2 * u, s - 2 * u), outline=anneau, width=round(2 * u))
    d.ellipse((7 * u, 7 * u, s - 7 * u, s - 7 * u), fill=couleur, outline=bord, width=round(u))
    return im.resize((taille, taille), Image.LANCZOS)


class BoutonAnime(tkinter.Canvas):
    """Bouton qui grossit au survol, s'entoure d'un halo et lance un éclat au clic.

    Tout est dessiné dans une seule image de taille fixe : rien n'est redimensionné
    pendant l'animation, donc ni bord noir fugace ni texte qui tremble."""

    MARGE = 7

    def __init__(self, parent, texte, commande, style="secondaire", width=120, height=38,
                 taille_police=13, icone=False):
        self.s = STYLES[style]
        self.fond_parent = couleur_fond(parent)
        fonte = police(taille_police, gras=style == "principal")
        # Avec un texte agrandi (réglage Apparence), le bouton s'élargit pour le contenir.
        width = max(width, fonte.measure(texte) + (taille_police + 10 if icone else 0) + 26)
        m = self.MARGE
        self.l, self.h = width + 2 * m, height + 2 * m
        super().__init__(parent, width=self.l, height=self.h, bg=self.fond_parent,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.commande = commande
        self.largeur, self.hauteur = width, height
        self.actif = True
        self.survole = False
        self._dernier_clic = 0.0
        self._image = None

        self._fond_dessin = self.create_image(0, 0, anchor="nw")
        self._texte = self.create_text(self.l / 2, self.h / 2, text=texte, fill=self.s["texte"],
                                       font=fonte)
        if icone:
            # Engrenage seul au centre, ou à gauche du texte avec l'ensemble centré.
            taille = taille_police + 3 if texte else 18
            self._icone = ImageTk.PhotoImage(_engrenage(taille, self.s["texte"]))
            debut = (self.l - (taille + (7 + fonte.measure(texte) if texte else 0))) / 2
            self.create_image(debut + taille / 2, self.h / 2, image=self._icone)
            self.coords(self._texte, debut + taille + 7, self.h / 2)
            self.itemconfigure(self._texte, anchor="w")
        definir(self, "fond", self.s["fond"])
        definir(self, "bord", self.s["bord"])
        definir(self, "halo", self.fond_parent)
        definir(self, "zoom", 0.0)
        self._dessiner()
        survol(self, self._entrer, self._sortir)
        self.bind("<ButtonPress-1>", self._appui)
        self.bind("<ButtonRelease-1>", self._relache)

    def _dessiner(self, _v=None):
        z = valeur(self, "zoom")
        image = _image_bouton(self.l, self.h, round((self.largeur + 8 * z) * 3),
                              round((self.hauteur + 6 * z) * 3), self.fond_parent,
                              valeur(self, "halo"), valeur(self, "fond"), valeur(self, "bord"))
        self._image = ImageTk.PhotoImage(image)
        self.itemconfigure(self._fond_dessin, image=self._image)

    def _vers(self, survole, duree=0.2):
        s = self.s
        transition(self, "fond", s["fond_survol"] if survole else s["fond"], duree, self._dessiner)
        transition(self, "bord", s["bord_survol"] if survole else s["bord"], duree, self._dessiner)
        transition(self, "halo", s["halo"] if survole else self.fond_parent, duree + 0.1,
                   self._dessiner)
        transition(self, "zoom", 1.0 if survole else 0.0, duree + 0.12, self._dessiner,
                   courbe=rebond if survole else adoucir)

    def _entrer(self):
        self.survole = True
        if self.actif:
            self._vers(True)

    def _sortir(self):
        self.survole = False
        self._vers(False)

    def _appui(self, _e=None):
        if self.actif:
            transition(self, "zoom", -0.6, 0.08, self._dessiner)

    def _relache(self, e):
        # Comme un vrai bouton : le clic compte si la souris est encore dessus au relâché.
        if 0 <= e.x < self.l and 0 <= e.y < self.h:
            self._clic()
        elif self.actif:
            self._vers(self.survole)

    def _clic(self):
        maintenant = time.monotonic()
        if not self.actif or maintenant - self._dernier_clic < 0.35:
            return
        self._dernier_clic = maintenant
        # Éclat : le bouton et son halo s'illuminent puis reviennent doucement.
        definir(self, "fond", self.s["eclat"])
        definir(self, "bord", ECLAT)
        definir(self, "halo", ECLAT)
        self._dessiner()
        self._vers(self.survole, duree=0.5)
        if self.commande:
            # Programmé sur la fenêtre principale, pas sur le bouton : la commande peut
            # détruire la page qui contient ce bouton (« ← Retour », changement de thème…).
            self._root().after(70, self.commande)

    def changer_texte(self, texte):
        self.itemconfigure(self._texte, text=texte)

    def activer(self, actif, texte=None):
        self.actif = actif
        self.configure(cursor="hand2" if actif else "")
        self.itemconfigure(self._texte, fill=self.s["texte"] if actif
                           else melanger(self.s["texte"], self.s["fond"], 0.55))
        if texte:
            self.changer_texte(texte)
        if not actif:
            self._vers(False)


def champ(parent, placeholder="", masque=False, **kw):
    """Champ de saisie dont la bordure s'illumine au survol et quand il est actif."""
    kw.setdefault("height", 42)
    e = ctk.CTkEntry(
        parent, placeholder_text=placeholder, show="•" if masque else "",
        fg_color=FOND, border_color=BORDURE, border_width=1, corner_radius=9,
        text_color=TEXTE, placeholder_text_color=TEXTE_DOUX, font=police(13), **kw,
    )
    definir(e, "bord", BORDURE)
    etat = {"focus": False, "survol": False}

    def maj():
        cible = BORDURE_ECLAT if etat["focus"] else CHAMP_SURVOL if etat["survol"] else BORDURE
        transition(e, "bord", cible, 0.22, lambda c: e.configure(border_color=c))

    def regler(cle, v):
        etat[cle] = v
        maj()

    e.bind("<FocusIn>", lambda _e: regler("focus", True))
    e.bind("<FocusOut>", lambda _e: regler("focus", False))
    survol(e, lambda: regler("survol", True), lambda: regler("survol", False))
    return e


def eclat_champ(e):
    definir(e, "bord", ECLAT)
    e.configure(border_color=ECLAT)
    transition(e, "bord", BORDURE_ECLAT, 0.6, lambda c: e.configure(border_color=c))


class LogoAnime(tkinter.Canvas):
    """Logo SecretLin avec des ondes bleues qui s'en échappent."""

    ETAPES_OUVERTURE = 8

    def __init__(self, parent, fond, taille=120, pulsation=True):
        super().__init__(parent, width=taille, height=taille, bg=fond, highlightthickness=0, bd=0)
        self.fond = fond
        self.taille = taille
        self._n = 0
        self.images = [ImageTk.PhotoImage(dessiner_logo(taille, fond=False))]
        self.dessin = self.create_image(taille / 2, taille / 2, image=self.images[0])
        if pulsation:
            self._root().after(300, self._onde)

    def _onde(self):
        if not self.winfo_exists():
            return
        self._n += 1
        anneau = self.create_oval(0, 0, 0, 0, outline=BLEU, width=2)
        self.tag_lower(anneau)
        c, k = self.taille / 2, self.taille / 100

        def etape(t):
            r = (30 + 19 * t) * k
            self.coords(anneau, c - r, c + 2 * k - r, c + r, c + 2 * k + r)
            self.itemconfigure(anneau, outline=melanger(BLEU, self.fond, t))

        animer(self, f"onde{self._n}", 2.0, etape, fin=lambda: self.delete(anneau))
        self._root().after(1400, self._onde)

    def ouvrir(self, fin):
        """L'anse du cadenas se soulève (déverrouillage)."""
        n = self.ETAPES_OUVERTURE
        while len(self.images) <= n:
            self.images.append(ImageTk.PhotoImage(
                dessiner_logo(self.taille, fond=False, ouverture=len(self.images) / n)))
        animer(self, "ouvrir", 0.35,
               lambda t: self.itemconfigure(self.dessin, image=self.images[round(t * n)]), fin=fin)


class JaugeForce(ctk.CTkFrame):
    """Barre animée indiquant la solidité d'un mot de passe."""

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self.barre = ctk.CTkProgressBar(self, height=6, corner_radius=3, fg_color=BORDURE,
                                        progress_color=BORDURE)
        self.barre.set(0)
        self.barre.pack(side="left", fill="x", expand=True)
        self.libelle = ctk.CTkLabel(self, text="", width=72, anchor="e", font=police(11, gras=True),
                                    text_color=TEXTE_DOUX)
        self.libelle.pack(side="right", padx=(10, 0))
        definir(self.barre, "niveau", 0.0)
        definir(self.barre, "couleur", BORDURE)

    def maj(self, mdp):
        n = evaluer_force(mdp)
        transition(self.barre, "niveau", n / 4, 0.4, self.barre.set)
        transition(self.barre, "couleur", COULEURS_FORCE[n], 0.4,
                   lambda c: self.barre.configure(progress_color=c))
        self.libelle.configure(text=t(LIBELLES_FORCE[n]) if n else "", text_color=COULEURS_FORCE[n] if n else TEXTE_DOUX)


# --- Application ------------------------------------------------------------

class Application(ctk.CTk):
    def __init__(self):
        super().__init__(className="SecretLin")
        self.coffre = Coffre()
        self.reglages = apparence.charger(apparence.chemin_reglages(self.coffre.chemin))
        appliquer_apparence(self.reglages)
        ctk.set_appearance_mode(MODE)
        self.title("SecretLin")
        self._icone = ImageTk.PhotoImage(dessiner_logo(128))
        self.iconphoto(True, self._icone)
        self.geometry("1040x720")
        self.minsize(800, 640)
        self.configure(fg_color=FOND)

        self.ecran = None
        self.derniere_activite = time.monotonic()
        self.dehors_depuis = None
        self._position_souris = None
        # Le compteur d'échecs est relu au lancement : fermer puis relancer SecretLin
        # ne remet pas l'attente à zéro.
        self.echecs, bloque = self.coffre.lire_echecs()
        self.bloque_jusqua = time.monotonic() + max(0.0, bloque - time.time())
        self._jeton_presse_papier = None
        # Vérification des fuites (Have I Been Pwned) : mot de passe → nombre de fuites,
        # gardé en mémoire jusqu'au verrouillage seulement.
        self.fuites = {}
        self.etat_fuites = ""
        # Accès rapide (code PIN) et porte locale pour le remplissage rapide et l'extension.
        self.acces = acces_rapide.Session()
        self.guichet = guichet.Guichet(self.coffre, self.acces, _InterfaceGuichet(self))
        self.porte = porte.Porte(self._requete_porte)
        try:
            self.porte.ouvrir()
        except OSError:
            pass  # sans porte, SecretLin marche normalement (pas de remplissage rapide)

        for evt in ("<Any-KeyPress>", "<Any-ButtonPress>"):
            self.bind_all(evt, self._activite, add="+")
        self.bind_all("<Control-l>", lambda _e: self._raccourci("verrouiller"))
        self.bind_all("<Control-n>", lambda _e: self._raccourci("ajouter"))
        self.bind_all("<Control-f>", lambda _e: self._raccourci("rechercher"))
        self.protocol("WM_DELETE_WINDOW", self._fermer)
        self.after(200, self._surveiller_inactivite)

        self.afficher_connexion()
        self.after(40, self._fondu_entree)

    def _fondu_entree(self):
        try:
            self.attributes("-alpha", 0.0)
            animer(self, "fondu", 0.45, lambda t: self.attributes("-alpha", t))
        except tkinter.TclError:
            pass

    def _raccourci(self, action):
        if not isinstance(self.ecran, EcranPrincipal) or self.grab_current() is not None:
            return
        if action == "verrouiller":
            self.verrouiller()
        elif action == "ajouter":
            FenetreEntree(self.ecran)
        else:
            self.ecran.afficher_liste()
            self.ecran.recherche.focus_set()

    # --- Navigation -------------------------------------------------------

    def _changer_ecran(self, ecran):
        # Le nouvel écran est en place avant la destruction de l'ancien : une erreur pendant
        # celle-ci ne laisse pas l'application pointer sur un écran à moitié détruit.
        ancien, self.ecran = self.ecran, ecran
        ecran.pack(fill="both", expand=True)
        if ancien is not None:
            ancien.destroy()

    def afficher_connexion(self):
        if self.coffre.existe():
            self._changer_ecran(EcranDeverrouillage(self))
        else:
            self._changer_ecran(EcranCreation(self))

    def afficher_principal(self):
        self._activite()
        self._changer_ecran(EcranPrincipal(self))

    def enregistrer_reglages(self, **choix):
        self.reglages.update(choix)
        try:
            apparence.enregistrer(apparence.chemin_reglages(self.coffre.chemin), self.reglages)
        except OSError:
            pass  # disque plein ou en lecture seule : le choix vaut au moins pour cette session

    def changer_apparence(self, page=None, **choix):
        """Applique et enregistre un réglage d'apparence ou de langue, puis redessine l'écran
        principal en revenant sur la page du réglage (Apparence par défaut)."""
        self.enregistrer_reglages(**choix)
        appliquer_apparence(self.reglages)
        ctk.set_appearance_mode(MODE)
        self.configure(fg_color=FOND)
        self.afficher_principal()
        self.ecran.ouvrir_page(PageReglages)
        self.ecran.ouvrir_page(page or PageApparence)

    def noter_echecs(self, delai):
        """Enregistre le compteur d'échecs et l'attente en cours (« delai » secondes)."""
        try:
            self.coffre.noter_echecs(self.echecs, time.time() + delai if delai else 0.0)
        except OSError:
            pass  # un disque plein ne doit pas bloquer l'écran de déverrouillage

    def deverrouille(self):
        """Le coffre vient d'être ouvert avec le mot de passe maître."""
        self.acces.demarrer()

    def acces_rapide_actif(self) -> bool:
        return bool(self.reglages.get("pin")) and self.coffre._cle is not None \
            and not self.acces.expiree()

    def verrouiller(self, partiel=False):
        """Verrouille l'écran. Complet : la clé du coffre est effacée. Partiel (verrouillage
        automatique, fenêtre fermée) avec un code PIN défini : l'écran demande le mot de
        passe maître, mais le coffre reste ouvert en mémoire pour l'accès rapide."""
        for fenetre in self.winfo_children():
            if isinstance(fenetre, ctk.CTkToplevel):
                fenetre.destroy()
        if not (partiel and self.acces_rapide_actif()):
            self.coffre.verrouiller()
            self.acces.arreter()
            self.fuites, self.etat_fuites = {}, ""
        self.vider_presse_papier()
        self.afficher_connexion()

    def montrer(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _requete_porte(self, requete):
        """Appelé par la porte (autre fil d'exécution) : la réponse est préparée dans le
        fil de l'interface, seul à toucher au coffre."""
        fini, reponse = threading.Event(), {}

        def traiter():
            try:
                reponse.update(self.guichet.traiter(requete))
            finally:
                fini.set()

        self.after(0, traiter)
        return reponse if fini.wait(20) else {"erreur": "occupe"}

    # --- Sécurité ---------------------------------------------------------

    def _activite(self, _evt=None):
        """Clic, touche ou mouvement de souris sur l'application : les compteurs repartent."""
        self.derniere_activite = time.monotonic()

    def _souris(self):
        """Position de la souris et si elle se trouve sur une fenêtre de SecretLin."""
        try:
            x, y = self.winfo_pointerxy()
            return (x, y), bool(str(self.tk.call("winfo", "containing", x, y)))
        except tkinter.TclError:
            return None, True

    def _surveiller_inactivite(self):
        maintenant = time.monotonic()
        position, dedans = self._souris()
        if dedans:
            self.dehors_depuis = None
            if position != self._position_souris:
                self._position_souris = position
                self._activite()
        elif self.dehors_depuis is None:
            self.dehors_depuis = maintenant

        if isinstance(self.ecran, EcranPrincipal):
            if self.dehors_depuis is not None:
                total, raison = DELAI_SOURIS_DEHORS_S, t("Souris hors de la fenêtre")
                depuis = max(self.dehors_depuis, self.derniere_activite)
            else:
                total, raison = DELAI_SOURIS_IMMOBILE_S, t("Souris immobile")
                depuis = self.derniere_activite
            restant = total - (maintenant - depuis)
            if restant <= 0:
                self.verrouiller(partiel=True)
            else:
                self.ecran.maj_minuterie(restant, total, raison)
        elif self.coffre._cle is not None and self.acces.expiree():
            self.verrouiller()  # accès rapide terminé : la clé est effacée
        self.after(200, self._surveiller_inactivite)

    def copier(self, texte):
        self.clipboard_clear()
        self.clipboard_append(texte)
        jeton = object()
        self._jeton_presse_papier = jeton
        self.after(EFFACEMENT_PRESSE_PAPIER_S * 1000, lambda: self._effacer_si(jeton))

    def _effacer_si(self, jeton):
        if self._jeton_presse_papier is jeton:
            self.vider_presse_papier()

    def vider_presse_papier(self):
        if self._jeton_presse_papier is not None:
            self.clipboard_clear()
            self.clipboard_append("")
            self._jeton_presse_papier = None

    def _fermer(self):
        """Croix de la fenêtre : avec l'accès rapide, SecretLin continue en arrière-plan
        (écran verrouillé) ; sinon il se ferme."""
        if self.acces_rapide_actif():
            self.verrouiller(partiel=True)
            self.withdraw()
        else:
            self.quitter()

    def quitter(self):
        self.vider_presse_papier()
        self.coffre.verrouiller()
        self.acces.arreter()
        self.porte.fermer()
        self.destroy()


class _InterfaceGuichet:
    """Ce dont le guichet a besoin de l'application (voir guichet.Guichet)."""

    def __init__(self, app):
        self.app = app

    def ecran_ouvert(self):
        return isinstance(self.app.ecran, EcranPrincipal) and self.app.state() != "withdrawn"

    def pin(self):
        return self.app.reglages.get("pin")

    def copier(self, texte, champ):
        self.app.copier(texte)
        if self.ecran_ouvert():
            self.app.ecran.notifier(t("Copié par le remplissage rapide"))

    def verrouiller(self):
        self.app.verrouiller()

    def montrer(self):
        self.app.montrer()


# --- Écrans de connexion ----------------------------------------------------

def case_fuites(parent):
    """Case « vérifier que le mot de passe maître n'a pas fuité », cochée par défaut."""
    case = ctk.CTkCheckBox(parent, text=t("Vérifier qu'il n'a pas fuité (Have I Been Pwned)"),
                           font=police(12), text_color=TEXTE_DOUX, fg_color=ACCENT,
                           hover_color=STYLES["principal"]["fond_survol"],
                           border_color=BORDURE_ECLAT, checkmark_color=ACCENT_TEXTE)
    case.select()
    return case


def probleme_fuite(mdp) -> str | None:
    """Message d'erreur si le mot de passe a fuité ou ne peut pas être vérifié, sinon None.
    Seul le début de son empreinte part sur Internet (voir fuites.py)."""
    try:
        n = fuites.verifier([mdp])[mdp]
    except OSError:
        return t("Vérification des fuites impossible (pas d'Internet ?). Décochez la case "
                 "pour continuer sans vérifier.")
    if n:
        return t("Ce mot de passe apparaît dans des fuites de données (vu {n} fois) : "
                 "choisissez-en un autre.", n=f"{n:,}".replace(",", " "))
    return None


class EcranCentre(ctk.CTkFrame):
    """Carte centrée utilisée pour la création et le déverrouillage."""

    def __init__(self, app, titre, sous_titre):
        super().__init__(app, fg_color=FOND)
        self.app = app
        self.carte = ctk.CTkFrame(self, fg_color=PANNEAU, corner_radius=22,
                                  border_width=1, border_color=BORDURE)
        self.carte.place(relx=0.5, rely=0.55, anchor="center")
        definir(self.carte, "bord", BORDURE)
        interieur = ctk.CTkFrame(self.carte, fg_color="transparent")
        interieur.pack(padx=46, pady=(30, 38))
        self.interieur = interieur

        self.logo = LogoAnime(interieur, PANNEAU)
        self.logo.pack()
        ctk.CTkLabel(interieur, text=titre, font=police(24, gras=True),
                     text_color=TEXTE).pack(pady=(4, 4))
        ctk.CTkLabel(interieur, text=sous_titre, font=police(13), text_color=TEXTE_DOUX,
                     wraplength=330, justify="center").pack(pady=(0, 24))

        self.message = ctk.CTkLabel(interieur, text="", font=police(12), text_color=DANGER,
                                    wraplength=330, justify="center")

        ctk.CTkLabel(self, text="SecretLin  ·  AES-256-GCM  ·  Argon2id  ·  "
                     + t("Données stockées uniquement sur cet ordinateur"),
                     font=police(11), text_color=TEXTE_ETEINT).place(relx=0.5, rely=0.97, anchor="s")

        # Entrée : la carte glisse doucement vers le haut.
        animer(self.carte, "entree", 0.6, lambda t: self.carte.place_configure(rely=0.55 - 0.05 * t))

    def afficher_message(self, texte, couleur=DANGER):
        self.message.configure(text=texte, text_color=couleur)

    def secouer(self):
        animer(self.carte, "secousse", 0.5,
               lambda t: self.carte.place_configure(x=round(16 * math.sin(t * math.pi * 6) * (1 - t))),
               courbe=lineaire)
        definir(self.carte, "bord", DANGER)
        self.carte.configure(border_color=DANGER)
        transition(self.carte, "bord", BORDURE, 1.2, lambda c: self.carte.configure(border_color=c))


class EcranCreation(EcranCentre):
    def __init__(self, app):
        super().__init__(app, t("Bienvenue sur SecretLin"),
                         t("Choisissez un mot de passe maître. C'est le seul que vous "
                           "aurez à retenir : sans lui, personne — pas même vous — "
                           "ne pourra ouvrir le coffre."))
        self.mdp = champ(self.interieur, t("Mot de passe maître"), masque=True, width=340)
        self.mdp.pack(pady=(0, 8))
        self.jauge = JaugeForce(self.interieur)
        self.jauge.pack(fill="x", pady=(0, 12))
        self.mdp.bind("<KeyRelease>", lambda _e: self.jauge.maj(self.mdp.get()))
        self.confirmation = champ(self.interieur, t("Confirmer le mot de passe"), masque=True,
                                  width=340)
        self.confirmation.pack(pady=(0, 4))
        self.case_fuites = case_fuites(self.interieur)
        self.case_fuites.pack(anchor="w", pady=(6, 0))
        self.message.pack(pady=(6, 6))
        self.bouton = BoutonAnime(self.interieur, t("Créer le coffre"), self._creer, style="principal",
                                  width=340, height=44)
        self.bouton.pack()
        self.confirmation.bind("<Return>", lambda _e: self._creer())
        self.mdp.focus_set()

    def _creer(self):
        mdp, conf = self.mdp.get(), self.confirmation.get()
        problemes = verifier_force(mdp)
        if problemes:
            self.afficher_message(t("Il manque : {liste}.", liste=", ".join(problemes)))
            self.secouer()
            return
        if mdp != conf:
            self.afficher_message(t("Les deux mots de passe ne correspondent pas."))
            self.secouer()
            return
        self.bouton.activer(False, t("Création…"))
        self.afficher_message("")
        verifier = bool(self.case_fuites.get())

        def travail():
            probleme = probleme_fuite(mdp) if verifier else None
            if probleme:
                self.app.after(0, lambda: self._refuse(probleme))
                return
            self.app.coffre.creer(mdp)
            self.app.after(0, self.app.deverrouille)
            self.app.after(0, lambda: self.logo.ouvrir(self.app.afficher_principal))

        threading.Thread(target=travail, daemon=True).start()

    def _refuse(self, probleme):
        self.bouton.activer(True, t("Créer le coffre"))
        self.afficher_message(probleme)
        self.secouer()


class EcranDeverrouillage(EcranCentre):
    def __init__(self, app):
        super().__init__(app, t("Coffre verrouillé"), t("Entrez votre mot de passe maître."))
        self.mdp = champ(self.interieur, t("Mot de passe maître"), masque=True, width=340)
        self.mdp.pack(pady=(0, 4))
        self.avec_fichier = app.coffre.besoin_fichier_cle()
        if self.avec_fichier:
            ligne = ctk.CTkFrame(self.interieur, fg_color="transparent")
            ligne.pack(fill="x", pady=(6, 0))
            self.nom_fichier = ctk.CTkLabel(ligne, text="", font=police(12), anchor="w",
                                            width=230, text_color=TEXTE_DOUX)
            self.nom_fichier.pack(side="left", fill="x", expand=True)
            BoutonAnime(ligne, t("Fichier-clé…"), self._choisir_fichier, width=106, height=34,
                        taille_police=12).pack(side="right")
            self._afficher_fichier()
        self.message.pack(pady=(6, 6))
        self.bouton = BoutonAnime(self.interieur, t("Déverrouiller"), self._ouvrir, style="principal",
                                  width=340, height=44)
        self.bouton.pack()
        self.mdp.bind("<Return>", lambda _e: self._ouvrir())
        self.mdp.focus_set()
        if app.acces_rapide_actif():
            ctk.CTkLabel(self.interieur, text=t("Le remplissage rapide reste disponible avec le "
                                                "code PIN."), font=police(11),
                         text_color=TEXTE_DOUX).pack(pady=(14, 0))
            BoutonAnime(self.interieur, t("Quitter SecretLin"), app.quitter, width=160,
                        height=32, taille_police=12).pack(pady=(6, 0))
        self._decompte()

    def _afficher_fichier(self):
        chemin = self.app.reglages["fichier_cle"]
        if chemin:
            self.nom_fichier.configure(text="🔑  " + Path(chemin).name, text_color=TEXTE)
        else:
            self.nom_fichier.configure(text=t("Aucun fichier-clé choisi"), text_color=TEXTE_DOUX)

    def _choisir_fichier(self):
        chemin = filedialog.askopenfilename(parent=self, title=t("Choisir le fichier-clé"))
        if chemin:
            self.app.enregistrer_reglages(fichier_cle=chemin)
            self._afficher_fichier()
            self.afficher_message("")

    def _decompte(self):
        """Pendant l'attente, le bouton reste grisé et le temps restant défile chaque seconde."""
        if not self.winfo_exists():
            return
        attente = self.app.bloque_jusqua - time.monotonic()
        if attente > 0:
            if self.bouton.actif:
                self.bouton.activer(False, t("Patientez…"))
            self.afficher_message(t("Trop d'essais. Réessayez dans {duree}.", duree=duree_lisible(attente)))
            self.after(1000, self._decompte)
        elif not self.bouton.actif:
            self.bouton.activer(True, t("Déverrouiller"))
            self.afficher_message("")

    def _ouvrir(self):
        if self.app.bloque_jusqua > time.monotonic():
            self.secouer()
            return
        mdp = self.mdp.get()
        if not mdp:
            self.secouer()
            return
        contenu_cle = None
        if self.avec_fichier:
            chemin = self.app.reglages["fichier_cle"]
            if not chemin:
                self.afficher_message(t("Ce coffre s'ouvre avec un fichier-clé : choisissez-le."))
                self.secouer()
                return
            try:
                contenu_cle = self.app.coffre.lire_fichier_cle(Path(chemin))
            except (OSError, ValueError):
                self.afficher_message(t("Fichier-clé introuvable ou illisible. Branchez la clé "
                                        "USB ou choisissez le fichier."))
                self.secouer()
                return
        self.bouton.activer(False, t("Vérification…"))
        self.afficher_message("")

        def travail():
            try:
                self.app.coffre.ouvrir(mdp, contenu_cle)
                resultat = None
            except (MotDePasseIncorrect, FichierCleRequis):
                resultat = "incorrect"
            except CoffreCorrompu:
                resultat = "corrompu"
            self.app.after(0, lambda: self._resultat(resultat))

        threading.Thread(target=travail, daemon=True).start()

    def _resultat(self, resultat):
        if resultat is None:
            self.app.echecs = 0
            self.app.noter_echecs(0)
            self.afficher_message(t("Déverrouillé"), SUCCES)
            # Sur la fenêtre principale : afficher_principal() détruit cet écran.
            self.app.deverrouille()
            self.logo.ouvrir(lambda: self.app.after(150, self.app.afficher_principal))
            return
        self.bouton.activer(True, t("Déverrouiller"))
        self.mdp.delete(0, "end")
        self.secouer()
        if resultat == "corrompu":
            self.afficher_message(t("Le fichier du coffre est illisible ou endommagé."))
            return
        self.app.echecs += 1
        # Attente croissante après plusieurs erreurs : 1, 3, 5, 10, 15, 30 min puis 1 h.
        delai = attente_apres(self.app.echecs)
        if delai:
            self.app.bloque_jusqua = time.monotonic() + delai
            self.app.noter_echecs(delai)
            self._decompte()
        else:
            self.app.noter_echecs(0)
            self.afficher_message(t("Mot de passe ou fichier-clé incorrect.") if self.avec_fichier
                                  else t("Mot de passe incorrect."))


# --- Écran principal --------------------------------------------------------

class IndexAlphabet(ctk.CTkFrame):
    """Colonne A–Z : un clic fait défiler la liste jusqu'à la lettre."""

    LETTRES = "★ABCDEFGHIJKLMNOPQRSTUVWXYZ#"

    def __init__(self, parent, aller_a):
        super().__init__(parent, fg_color=PANNEAU, corner_radius=14, border_width=1,
                         border_color=BORDURE, width=42)
        self.aller_a = aller_a
        self.presentes = set()
        self.lettres = {}
        ctk.CTkFrame(self, fg_color="transparent", width=1, height=6).pack()
        for lettre in self.LETTRES:
            f = police(11, gras=True)
            lab = ctk.CTkLabel(self, text=lettre, width=34, height=18, font=f,
                               text_color=TEXTE_ETEINT, cursor="hand2")
            lab.pack(expand=True, padx=4)
            definir(lab, "couleur", TEXTE_ETEINT)
            definir(lab, "taille", 11.0)
            survol(lab, lambda l=lettre: self._survol(l, True), lambda l=lettre: self._survol(l, False))
            lab.bind("<Button-1>", lambda _e, l=lettre: self._clic(l))
            self.lettres[lettre] = (lab, f)
        ctk.CTkFrame(self, fg_color="transparent", width=1, height=6).pack()

    def _couleur_repos(self, lettre):
        return TEXTE_DOUX if lettre in self.presentes else TEXTE_ETEINT

    def maj(self, presentes):
        anciennes, self.presentes = self.presentes, presentes
        for lettre, (lab, _f) in self.lettres.items():
            # Seules les lettres qui changent s'animent : la recherche appelle maj() souvent.
            if (lettre in anciennes) == (lettre in presentes):
                continue
            transition(lab, "couleur", self._couleur_repos(lettre), 0.3,
                       lambda c, lab=lab: lab.configure(text_color=c))

    def _survol(self, lettre, dedans):
        if lettre not in self.presentes:
            return
        lab, f = self.lettres[lettre]
        transition(lab, "couleur", ECLAT if dedans else self._couleur_repos(lettre), 0.18,
                   lambda c: lab.configure(text_color=c))
        transition(lab, "taille", 15.0 if dedans else 11.0, 0.22,
                   lambda v: f.configure(size=round(v * ECHELLE_TEXTE)),
                   courbe=rebond if dedans else adoucir)

    def _clic(self, lettre):
        if lettre in self.presentes:
            self.aller_a(lettre)


def _distance(c1: str, c2: str) -> int:
    """Écart entre deux couleurs « #rrggbb »."""
    return sum(abs(int(c1[i:i + 2], 16) - int(c2[i:i + 2], 16)) for i in (1, 3, 5))


class Pastille(ctk.CTkLabel):
    """Carré à gauche d'un identifiant : logo de la marque reconnue, sinon l'initiale."""

    def __init__(self, parent, site, taille=42):
        super().__init__(parent, text="", width=taille, height=taille, corner_radius=10,
                         font=police(16, gras=True))
        self.survole = False
        self.changer_site(site)

    def changer_site(self, site):
        self.style = style_pastille(site, CARTE_SURVOL, ACCENT, TEXTE, ACCENT_TEXTE,
                                    fond_clair=MODE == "light")
        st = self.style
        fond = st["fond_survol"] if self.survole else st["fond"]
        texte = st["texte_survol"] if self.survole else st["texte"]
        definir(self, "fond", fond)
        definir(self, "texte", texte)
        self._logo = st["image_survol"] if self.survole else st["image"]
        self.configure(fg_color=fond, text_color=texte, image=self._logo,
                       text="" if st["image"] else (site.strip()[:1].upper() or "?"))

    def survol(self, survole):
        self.survole = survole
        st = self.style
        cible, depart = (st["fond_survol"], st["fond"]) if survole else (st["fond"], st["fond_survol"])
        image = st["image_survol"] if survole else st["image"]

        def fond(c):
            self.configure(fg_color=c)
            # Le logo change de couleur quand le fond est à mi-chemin. Changé dès le début,
            # il aurait presque la couleur du fond et disparaîtrait un instant.
            if image is not None and image is not self._logo and \
                    _distance(c, cible) <= _distance(c, depart):
                self._logo = image
                self.configure(image=image)
        transition(self, "fond", cible, 0.25, fond)
        transition(self, "texte", st["texte_survol"] if survole else st["texte"], 0.25,
                   lambda c: self.configure(text_color=c))


class CarteIdentifiant(ctk.CTkFrame):
    """Une ligne de la liste : s'élargit et s'illumine au survol."""

    MARGE = 10

    def __init__(self, ecran, parent, e, marge_depart=None):
        super().__init__(parent, fg_color=CARTE, corner_radius=12, border_width=1, border_color=BORDURE)
        self.ecran = ecran
        depart = self.MARGE if marge_depart is None else marge_depart
        self.pack(fill="x", padx=depart, pady=4)
        definir(self, "marge", float(depart))
        definir(self, "bord", BORDURE)

        etoile = ctk.CTkLabel(self, text="★" if e.get("favori") else "☆", width=22,
                              font=police(17), cursor="hand2",
                              text_color=FAVORI if e.get("favori") else TEXTE_ETEINT)
        etoile.pack(side="left", padx=(12, 0))
        etoile.bind("<Button-1>", lambda _e: ecran.basculer_favori(e))
        if not e.get("favori"):
            survol(etoile, lambda: etoile.configure(text_color=TEXTE_DOUX),
                   lambda: etoile.configure(text_color=TEXTE_ETEINT))
        self.pastille = Pastille(self, e["site"])
        self.pastille.pack(side="left", padx=(8, 14), pady=12)

        textes = ctk.CTkFrame(self, fg_color="transparent")
        textes.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(textes, text=e["site"], font=police(15, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x")
        details = "  ·  ".join(v for v in (e["utilisateur"], e.get("email", ""),
                                           e.get("categorie", "")) if v) or "—"
        ctk.CTkLabel(textes, text=details, font=police(12), text_color=TEXTE_DOUX,
                     anchor="w").pack(fill="x")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(side="right", padx=8)
        BoutonAnime(actions, t("Modifier"), lambda: FenetreEntree(ecran, e),
                    width=88, height=32, taille_police=12).pack(side="right", padx=(10, 0))
        for texte, cle, largeur, message in (
            (t("Mot de passe"), "mot_de_passe", 112, mdp_copie()),
            (t("E-mail"), "email", 76, t("E-mail copié")),
            (t("Utilisateur"), "utilisateur", 98, t("Nom d'utilisateur copié")),
        ):
            b = BoutonAnime(actions, texte, lambda c=cle, m=message: ecran.copier(e[c], m),
                            width=largeur, height=32, taille_police=12)
            b.pack(side="right")
            if not e.get(cle):
                b.activer(False)
        self._jeton_2fa = None
        if totp.valide(e.get("totp", "")):
            self._bouton_2fa = BoutonAnime(actions, "", lambda: ecran.copier(
                totp.code(e["totp"]), t("Code de double authentification copié")),
                width=118, height=32, taille_police=12)
            self._bouton_2fa.pack(side="right")
            self._maj_2fa(e["totp"])
        ctk.CTkLabel(actions, text=t("Copier"), font=police(11), text_color=TEXTE_DOUX).pack(
            side="right", padx=(0, 4))

        survol(self, lambda: self._etat(True), lambda: self._etat(False))
        for w in (self, textes, self.pastille):
            tkinter.Misc.bind(w, "<Double-Button-1>", lambda _e: FenetreEntree(ecran, e), "+")

    def _maj_2fa(self, cle):
        """Code 2FA en cours et secondes restantes, mis à jour chaque seconde."""
        code = totp.code(cle)
        self._bouton_2fa.changer_texte(f"{code[:3]} {code[3:]} · {totp.restant(cle)}s")
        self._jeton_2fa = self.after(1000 - int(time.time() * 1000) % 1000,
                                     lambda: self._maj_2fa(cle))

    def destroy(self):
        # Un minuteur laissé en route après la destruction appellerait une commande Tcl
        # supprimée, dont le nom peut être repris par un autre gestionnaire d'événement.
        if self._jeton_2fa is not None:
            self.after_cancel(self._jeton_2fa)
            self._jeton_2fa = None
        super().destroy()

    def _marge(self, v):
        self.pack_configure(padx=round(v))

    def _etat(self, survole):
        transition(self, "marge", 3.0 if survole else float(self.MARGE), 0.25, self._marge,
                   courbe=rebond if survole else adoucir)
        transition(self, "bord", BORDURE_ECLAT if survole else BORDURE, 0.25,
                   lambda c: self.configure(border_color=c))
        self.pastille.survol(survole)

    def apparaitre(self):
        transition(self, "marge", float(self.MARGE), 0.45, self._marge)


class EcranPrincipal(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=FOND)
        self.app = app
        self.entetes = {}

        # En-tête
        entete = ctk.CTkFrame(self, fg_color=PANNEAU, corner_radius=0, height=80)
        entete.pack(fill="x")
        entete.pack_propagate(False)
        ctk.CTkLabel(entete, text="", image=ctk.CTkImage(dessiner_logo(96), size=(48, 48))).pack(
            side="left", padx=(22, 12))
        titres = ctk.CTkFrame(entete, fg_color="transparent")
        titres.pack(side="left")
        ctk.CTkLabel(titres, text="SecretLin", font=police(20, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(titres, text=t("Chiffré de bout en bout") + "  ·  AES-256", font=police(11),
                     text_color=TEXTE_DOUX, anchor="w").pack(fill="x")

        BoutonAnime(entete, "", self.afficher_reglages, width=38, icone=True).pack(
            side="right", padx=(0, 16))
        BoutonAnime(entete, t("Verrouiller"), app.verrouiller, width=112).pack(side="right")
        BoutonAnime(entete, "+  " + t("Ajouter"), lambda: FenetreEntree(self), style="principal",
                    width=124).pack(side="right")

        statut = ctk.CTkFrame(entete, fg_color="transparent")
        statut.pack(side="right", padx=18)
        ctk.CTkLabel(statut, text="●  " + t("Déverrouillé"), font=police(11, gras=True), text_color=SUCCES,
                     fg_color=SUCCES_FOND, corner_radius=11, height=24).pack(anchor="e", ipadx=8)
        self.minuterie = ctk.CTkLabel(statut, text="", font=police(10), text_color=TEXTE_DOUX,
                                      anchor="e", width=230)
        self.minuterie.pack(anchor="e", pady=(2, 1))
        self.barre_temps = ctk.CTkProgressBar(statut, width=230, height=4, corner_radius=2,
                                              fg_color=BORDURE, progress_color=SUCCES)
        self.barre_temps.pack(anchor="e")
        ctk.CTkFrame(self, fg_color=BORDURE, height=1, corner_radius=0).pack(fill="x")

        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(fill="both", expand=True, padx=(18, 18), pady=18)
        self.corps = corps
        # Pages ouvertes par-dessus la liste (Réglages, puis Sécurité…), la dernière visible.
        self.pages = []
        # Rubriques des réglages construites d'avance, cachées : au clic elles s'affichent
        # aussitôt, qu'elles soient légères (Sécurité) ou chargées (Apparence).
        self._pages_pretes = {}

        self.index = IndexAlphabet(corps, self.aller_a)
        self.index.pack(side="left", fill="y", padx=(0, 14))

        contenu = ctk.CTkFrame(corps, fg_color="transparent")
        contenu.pack(side="left", fill="both", expand=True)

        barre = ctk.CTkFrame(contenu, fg_color="transparent")
        barre.pack(fill="x", padx=10, pady=(0, 6))
        self.recherche = champ(barre, t("Rechercher un site ou un identifiant…") + "   (Ctrl+F)")
        self.recherche.pack(side="left", fill="x", expand=True)
        self.recherche.bind("<KeyRelease>", lambda _e: self._recherche_modifiee())
        self._jeton_recherche = None
        self.compteur = ctk.CTkLabel(barre, text="", font=police(12), text_color=TEXTE_DOUX)
        self.categorie = None  # catégorie affichée (None : toutes)
        self.filtre_categorie = ctk.CTkOptionMenu(
            barre, values=[t("Toutes les catégories")], width=170, height=40, corner_radius=9,
            fg_color=CARTE, button_color=CARTE, button_hover_color=CARTE_SURVOL,
            text_color=TEXTE, font=police(12), dropdown_font=police(12),
            dropdown_fg_color=PANNEAU, dropdown_hover_color=CARTE_SURVOL,
            dropdown_text_color=TEXTE, command=self._categorie_choisie)
        self.filtre_categorie.pack(side="left", padx=(8, 0))
        BoutonAnime(barre, t("Sauvegarde"), lambda: FenetreSauvegarde(self), width=112).pack(side="right")
        BoutonAnime(barre, t("Bilan de santé"), lambda: self.ouvrir_page(PageSante),
                    width=132).pack(side="right", padx=(0, 8))
        self.compteur.pack(side="right", padx=(14, 0))

        self.liste = ctk.CTkScrollableFrame(contenu, fg_color="transparent",
                                            scrollbar_button_color=BORDURE,
                                            scrollbar_button_hover_color=BORDURE_ECLAT)
        self.liste.pack(fill="both", expand=True)
        self.voile = Voile(self.liste)

        # Notification qui glisse depuis le bas
        self.toast = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=12)
        self.toast_texte = ctk.CTkLabel(self.toast, text="", text_color=ACCENT_TEXTE, font=police(12, gras=True))
        self.toast_texte.pack(padx=18, pady=9)
        definir(self.toast, "y", 1.12)
        self._jeton_toast = None

        self._texte_minuterie = None
        self.maj_minuterie(DELAI_SOURIS_IMMOBILE_S, DELAI_SOURIS_IMMOBILE_S, t("Souris immobile"))
        self.rafraichir(animer_entree=True)

    def maj_minuterie(self, restant, total, raison):
        """Compte à rebours en direct avant le verrouillage automatique."""
        part = max(0.0, min(1.0, restant / total))
        if part > 0.5:
            couleur = SUCCES
        elif restant > 5:
            couleur = "#f0883e"
        else:
            couleur = DANGER
        self.barre_temps.set(part)
        self.barre_temps.configure(progress_color=couleur)
        texte = t("{raison} · verrouillage {duree}", raison=raison, duree=duree_lisible(restant))
        if texte != self._texte_minuterie:
            self._texte_minuterie = texte
            self.minuterie.configure(text=texte, text_color=TEXTE_DOUX if part > 0.5 else couleur)

    def copier(self, texte, message):
        self.app.copier(texte)
        self.notifier(message)

    def basculer_favori(self, e):
        self.app.coffre.basculer_favori(e["id"])
        self.notifier(t("Ajouté aux favoris") if e["favori"] else t("Retiré des favoris"))
        self.rafraichir()

    def ouvrir_page(self, classe):
        """Affiche une page à la place de la liste (ou de la page précédente). L'en-tête
        reste visible : le verrouillage automatique continue de tourner."""
        page = self._pages_pretes.pop(classe, None) or classe(self)
        (self.pages[-1] if self.pages else self.corps).pack_forget()
        page.pack(fill="both", expand=True, padx=18, pady=18)
        self.pages.append(page)
        page.affichee()

    def preparer_pages(self, classes):
        """Construit ces pages en arrière-plan, une à la fois pour ne pas figer l'écran."""
        if not classes or not self.winfo_exists():
            return
        if classes[0] not in self._pages_pretes:
            self._pages_pretes[classes[0]] = classes[0](self)
        self.after(30, lambda: self.preparer_pages(classes[1:]))

    def page_precedente(self):
        self.pages.pop().destroy()
        if self.pages:
            self.pages[-1].pack(fill="both", expand=True, padx=18, pady=18)
            self.pages[-1].affichee()
        else:
            self.corps.pack(fill="both", expand=True, padx=(18, 18), pady=18)
            for page in self._pages_pretes.values():
                page.destroy()
            self._pages_pretes.clear()

    def afficher_liste(self):
        while self.pages:
            self.page_precedente()

    def afficher_reglages(self):
        if not (self.pages and isinstance(self.pages[-1], PageReglages)):
            self.afficher_liste()
            self.ouvrir_page(PageReglages)

    def notifier(self, texte):
        self.toast_texte.configure(text=f"✓   {texte}")
        self.toast.place(relx=0.5, rely=1.12, anchor="s")
        self.toast.lift()
        transition(self.toast, "y", 0.965, 0.45, lambda v: self.toast.place_configure(rely=v),
                   courbe=rebond)
        jeton = object()
        self._jeton_toast = jeton
        self.after(2300, lambda: self._cacher_toast(jeton))

    def _cacher_toast(self, jeton):
        if self._jeton_toast is jeton:
            transition(self.toast, "y", 1.12, 0.35, lambda v: self.toast.place_configure(rely=v))

    def aller_a(self, lettre):
        cible_widget = self.entetes.get(lettre)
        if cible_widget is None:
            return
        self.voile.terminer()
        self.liste.update_idletasks()
        canvas = self.liste._parent_canvas
        total = max(self.liste.winfo_height(), 1)
        cible = cible_widget.winfo_y() / total
        debut = canvas.yview()[0]
        animer(canvas, "defilement", 0.45, lambda t: canvas.yview_moveto(debut + (cible - debut) * t))
        # La lettre de section clignote pour montrer où l'on est arrivé.
        lab = cible_widget.lettre
        definir(lab, "couleur", ECLAT)
        lab.configure(text_color=ECLAT)
        transition(lab, "couleur", TEXTE_DOUX, 1.2, lambda c: lab.configure(text_color=c))

    def _categorie_choisie(self, choix):
        self.categorie = None if choix == t("Toutes les catégories") else choix
        self._afficher(self.recherche.get().strip().casefold(), anime=True)

    def _maj_filtre_categorie(self):
        categories = self.app.coffre.categories()
        if self.categorie not in categories:
            self.categorie = None
        self.filtre_categorie.configure(values=[t("Toutes les catégories")] + categories)
        self.filtre_categorie.set(self.categorie or t("Toutes les catégories"))
        if categories:
            self.filtre_categorie.pack(side="left", padx=(8, 0), after=self.recherche)
        else:
            self.filtre_categorie.pack_forget()

    def _recherche_modifiee(self):
        """Attend une courte pause dans la frappe avant de refiltrer la liste."""
        if self._jeton_recherche is not None:
            self.after_cancel(self._jeton_recherche)
        self._jeton_recherche = self.after(120, self._filtrer)

    def _filtrer(self):
        self._jeton_recherche = None
        if not self.winfo_exists():
            return
        # Une touche qui ne change pas le texte (retour arrière sur un champ vide, Maj,
        # flèches…) ne touche pas à la liste.
        filtre = self.recherche.get().strip().casefold()
        if filtre != self._filtre_affiche:
            self._afficher(filtre, anime=True)

    def rafraichir(self, animer_entree=False):
        """Recrée toutes les cartes, après un ajout, une modification ou un import."""
        self.voile.terminer()
        for enfant in self.liste.winfo_children():
            enfant.destroy()
        self._vide = None
        self._texte_vide = None
        self._sections = []  # [(lettre, case de l'en-tête, [(entrée, case de la carte), …]), …]
        cartes = []
        lettre_courante = None
        entrees = self.app.coffre.entrees
        # Favoris d'abord (section ★), puis les autres par ordre alphabétique.
        for e in [e for e in entrees if e.get("favori")] + [e for e in entrees if not e.get("favori")]:
            initiale = e["site"][:1].upper()
            if e.get("favori"):
                lettre = "★"
            else:
                lettre = initiale if initiale.isalpha() and initiale in IndexAlphabet.LETTRES else "#"
            if lettre != lettre_courante:
                lettre_courante = lettre
                self._sections.append((lettre, self._entete_section(lettre), []))
            anime = animer_entree and len(cartes) < 25
            case = self._case()
            carte = CarteIdentifiant(self, case, e, marge_depart=70 if anime else None)
            self._sections[-1][2].append((e, case))
            cartes.append(carte)
        self._maj_filtre_categorie()
        self._afficher(self.recherche.get().strip().casefold(), anime=False)

        for page in self.pages:
            page.coffre_modifie()

        if animer_entree:
            for i, carte in enumerate(cartes[:25]):
                self.after(30 * i, carte.apparaitre)

    def _afficher(self, filtre, anime):
        """Montre les cartes qui correspondent à la recherche. Les cartes existent déjà :
        on ne fait que ranger ou ressortir leur case, et le voile anime le changement."""
        self._filtre_affiche = filtre
        entetes = {}
        plan = []  # (case, visible) dans l'ordre de la liste
        nombre = 0
        for lettre, entete, cartes in self._sections:
            visibles = [any(filtre in e.get(k, "").casefold()
                            for k in ("site", "utilisateur", "email", "categorie"))
                        and (self.categorie is None or e.get("categorie") == self.categorie)
                        for e, _case in cartes]
            plan.append((entete, any(visibles)))
            plan.extend((case, visible) for (_e, case), visible in zip(cartes, visibles))
            if any(visibles):
                entetes[lettre] = entete
            nombre += sum(visibles)
        total = len(self.app.coffre.entrees)
        filtre_actif = filtre or self.categorie is not None
        texte_vide = None if nombre else (
            t("Aucun résultat.") if filtre_actif else
            t("Votre coffre est vide.\nCliquez sur « + Ajouter » pour enregistrer un premier compte."))

        def appliquer():
            self.entetes = entetes
            if texte_vide != self._texte_vide and self._vide is not None:
                self._vide.destroy()
                self._vide = None
            # Les cases déjà affichées gardent leur place ; celles qui reviennent sont
            # insérées entre leurs voisines.
            precedente = None
            for case, visible in plan:
                if visible and not case.winfo_manager():
                    if precedente is not None:
                        case.pack(fill="x", after=precedente)
                    else:
                        suivante = next((c for c, _v in plan if c.winfo_manager()), None)
                        case.pack(fill="x", before=suivante) if suivante else case.pack(fill="x")
                elif not visible and case.winfo_manager():
                    case.pack_forget()
                if case.winfo_manager():
                    precedente = case
            if texte_vide is not None and self._vide is None:
                self._vide = ctk.CTkFrame(self.liste, fg_color="transparent")
                self._vide.pack(pady=70)
                if not filtre_actif:
                    LogoAnime(self._vide, FOND).pack()
                ctk.CTkLabel(self._vide, text=texte_vide, font=police(14), text_color=TEXTE_DOUX,
                             justify="center").pack(pady=(12, 0))
            self._texte_vide = texte_vide
            self.compteur.configure(text=f"{nombre} / {total}" if filtre_actif else
                                    tn("{n} identifiant", "{n} identifiants", total))
            self.index.maj(set(entetes))

        change = texte_vide != self._texte_vide or any(
            visible != bool(case.winfo_manager()) for case, visible in plan)
        if not change:
            appliquer()  # rien ne bouge dans la liste : seuls le compteur et l'index changent
        elif anime and effets.ANIMATIONS:
            self.voile.changer(appliquer)
        else:
            self.voile.terminer()
            appliquer()

    def _case(self):
        """Emplacement d'un élément dans la liste : c'est lui qu'on range ou ressort."""
        return tkinter.Frame(self.liste, bg=FOND, bd=0, highlightthickness=0)

    def _entete_section(self, lettre):
        case = self._case()
        ligne = ctk.CTkFrame(case, fg_color="transparent")
        ligne.pack(fill="x", padx=14, pady=(16, 4))
        lab = ctk.CTkLabel(ligne, text="★  " + t("Favoris") if lettre == "★" else lettre,
                           font=police(14, gras=True), text_color=TEXTE_DOUX, width=20, anchor="w")
        lab.pack(side="left")
        definir(lab, "couleur", TEXTE_DOUX)
        ctk.CTkFrame(ligne, fg_color=BORDURE, height=1, corner_radius=0).pack(
            side="left", fill="x", expand=True, padx=(10, 0))
        case.lettre = lab
        return case


# --- Fenêtres ---------------------------------------------------------------

class Dialogue(ctk.CTkToplevel):
    """Fenêtre modale qui apparaît en fondu, centrée sur l'application."""

    def __init__(self, parent, titre):
        super().__init__(parent)
        self.title(titre)
        self.configure(fg_color=PANNEAU)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.bind("<Escape>", lambda _e: self.destroy())
        try:
            self.attributes("-alpha", 0.0)
        except tkinter.TclError:
            pass
        self.after(30, self._montrer)

    def _montrer(self):
        self.update_idletasks()
        maitre = self.master.winfo_toplevel()
        x = maitre.winfo_rootx() + (maitre.winfo_width() - self.winfo_width()) // 2
        y = maitre.winfo_rooty() + (maitre.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        try:
            animer(self, "fondu", 0.25, lambda t: self.attributes("-alpha", t))
        except tkinter.TclError:
            pass
        self.lift()
        self.focus_force()
        self.after(30, self.grab_set)


class FenetreEntree(Dialogue):
    """Fenêtre d'ajout ou de modification d'un identifiant."""

    def __init__(self, ecran: EcranPrincipal, entree: dict | None = None):
        super().__init__(ecran.app, t("Modifier") if entree else t("Ajouter un identifiant"))
        self.ecran = ecran
        self.entree = entree

        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)

        ctk.CTkLabel(corps, text=t("Modifier l'identifiant") if entree else t("Nouvel identifiant"),
                     font=police(20, gras=True), text_color=TEXTE, anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text=t("Les données sont chiffrées dès l'enregistrement."), font=police(12),
                     text_color=TEXTE_DOUX, anchor="w").pack(fill="x", pady=(2, 12))

        def etiquette(texte):
            ctk.CTkLabel(corps, text=texte.upper(), font=police(10, gras=True), text_color=TEXTE_DOUX,
                         anchor="w").pack(fill="x", pady=(10, 4))

        etiquette(t("Site ou application"))
        ligne_site = ctk.CTkFrame(corps, fg_color="transparent")
        ligne_site.pack(fill="x")
        self.apercu = Pastille(ligne_site, entree["site"] if entree else "")
        self.apercu.pack(side="left", padx=(0, 10))
        self.site = champ(ligne_site, t("ex. Discord, Netflix, Steam…"))
        self.site.pack(side="left", fill="x", expand=True)
        self.site.bind("<KeyRelease>", lambda _e: self.apercu.changer_site(self.site.get()))

        def ligne_avec_copie(placeholder, quoi):
            ligne = ctk.CTkFrame(corps, fg_color="transparent")
            ligne.pack(fill="x")
            entree_champ = champ(ligne, placeholder)
            entree_champ.pack(side="left", fill="x", expand=True)
            BoutonAnime(ligne, t("Copier"), lambda: self._copier(entree_champ.get(), quoi),
                        width=84, height=42, taille_police=12).pack(side="left")
            return entree_champ, ligne

        etiquette(t("Nom d'utilisateur"))
        self.utilisateur, _ = ligne_avec_copie(t("ex. jeandupont75"), t("Nom d'utilisateur copié"))

        etiquette(t("Adresse e-mail"))
        self.email, _ = ligne_avec_copie(t("ex. jean.dupont@mail.com"), t("E-mail copié"))

        etiquette(t("Mot de passe"))
        ligne = ctk.CTkFrame(corps, fg_color="transparent")
        ligne.pack(fill="x")
        self.mdp = champ(ligne, "", masque=True)
        self.mdp.pack(side="left", fill="x", expand=True)
        self.bouton_voir = BoutonAnime(ligne, t("Afficher"), self._basculer, width=84, height=42,
                                       taille_police=12)
        self.bouton_voir.pack(side="left")
        BoutonAnime(ligne, t("Générer"), self._generer, width=84, height=42,
                    taille_police=12).pack(side="left")
        BoutonAnime(ligne, t("Copier"), lambda: self._copier(self.mdp.get(), mdp_copie()),
                    width=84, height=42, taille_police=12).pack(side="left")
        self.jauge = JaugeForce(corps)
        self.jauge.pack(fill="x", pady=(4, 0))
        self.mdp.bind("<KeyRelease>", lambda _e: self.jauge.maj(self.mdp.get()))

        etiquette(t("Clé de double authentification (facultatif)"))
        self.totp = champ(corps, t("ex. JBSWY3DPEHPK3PXP ou otpauth://…"))
        self.totp.pack(fill="x")
        if entree and entree.get("totp"):
            self.totp.insert(0, entree["totp"])

        etiquette(t("Catégorie (facultatif)"))
        ligne = ctk.CTkFrame(corps, fg_color="transparent")
        ligne.pack(fill="x")
        utilisees = ecran.app.coffre.categories()
        self.categorie = ctk.CTkComboBox(
            ligne, values=utilisees + [c for c in categories_proposees() if c not in utilisees],
            height=42, corner_radius=9, fg_color=FOND, border_color=BORDURE, border_width=1,
            button_color=CARTE, button_hover_color=CARTE_SURVOL, text_color=TEXTE,
            font=police(13), dropdown_font=police(12), dropdown_fg_color=PANNEAU,
            dropdown_hover_color=CARTE_SURVOL, dropdown_text_color=TEXTE)
        self.categorie.set(entree.get("categorie", "") if entree else "")
        self.categorie.pack(side="left", fill="x", expand=True)
        self.favori = ctk.CTkCheckBox(ligne, text="★  " + t("Favori"), font=police(13),
                                      text_color=TEXTE, fg_color=ACCENT,
                                      hover_color=STYLES["principal"]["fond_survol"],
                                      border_color=BORDURE_ECLAT, checkmark_color=ACCENT_TEXTE)
        if entree and entree.get("favori"):
            self.favori.select()
        self.favori.pack(side="left", padx=(14, 0))

        etiquette(t("Notes (facultatif)"))
        self.notes = ctk.CTkTextbox(corps, width=520, height=60, fg_color=FOND, border_color=BORDURE,
                                    border_width=1, corner_radius=9, text_color=TEXTE, font=police(13))
        self.notes.pack()

        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=DANGER)
        self.message.pack(pady=(6, 0))

        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(fill="x", pady=(4, 0))
        BoutonAnime(boutons, t("Enregistrer"), self._enregistrer, style="principal",
                    width=130).pack(side="right")
        BoutonAnime(boutons, t("Annuler"), self.destroy, width=100).pack(side="right")
        if entree:
            BoutonAnime(boutons, t("Supprimer"), self._supprimer, style="danger",
                        width=104).pack(side="left")
            if entree.get("historique"):
                BoutonAnime(boutons, t("Historique"), lambda: DialogueHistorique(self, entree),
                            width=110).pack(side="left", padx=(8, 0))
            self.site.insert(0, entree["site"])
            self.utilisateur.insert(0, entree["utilisateur"])
            self.email.insert(0, entree.get("email", ""))
            self.mdp.insert(0, entree["mot_de_passe"])
            self.notes.insert("1.0", entree.get("notes", ""))
            self.jauge.maj(entree["mot_de_passe"])

        for w in (self.site, self.utilisateur, self.email, self.mdp):
            w.bind("<Return>", lambda _e: self._enregistrer())
        self.after(80, self.site.focus_set)

    def _copier(self, texte, message):
        if not texte:
            self.message.configure(text=t("Ce champ est vide."), text_color=DANGER)
            return
        self.ecran.app.copier(texte)
        self.message.configure(text=f"✓  {message}", text_color=SUCCES)

    def _basculer(self):
        visible = self.mdp.cget("show") == ""
        self.mdp.configure(show="•" if visible else "")
        self.bouton_voir.changer_texte(t("Afficher") if visible else t("Masquer"))

    def _generer(self):
        mdp = generer_mot_de_passe(**apparence.options_generateur(self.ecran.app.reglages))
        if self.mdp.cget("show") != "":
            self._basculer()

        # Effet « machine à écrire » puis éclat de la bordure.
        def etape(t):
            self.mdp.delete(0, "end")
            self.mdp.insert(0, mdp[:round(len(mdp) * t)])

        def fin():
            self.jauge.maj(mdp)
            eclat_champ(self.mdp)

        animer(self.mdp, "frappe", 0.55, etape, fin=fin, courbe=lineaire)

    def _enregistrer(self):
        site = self.site.get().strip()
        mdp = self.mdp.get()
        if not site:
            self.message.configure(text=t("Indiquez le nom du site ou de l'application."),
                                   text_color=DANGER)
            return
        if not mdp:
            self.message.configure(text=t("Indiquez un mot de passe (ou cliquez sur « Générer »)."),
                                   text_color=DANGER)
            return
        email = self.email.get().strip()
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            self.message.configure(text=t("L'adresse e-mail ne semble pas valide."),
                                   text_color=DANGER)
            return
        cle_2fa = self.totp.get().strip()
        if cle_2fa and not totp.valide(cle_2fa):
            self.message.configure(text=t("La clé de double authentification n'est pas valable."),
                                   text_color=DANGER)
            return
        champs = dict(site=site, utilisateur=self.utilisateur.get(), email=email, mot_de_passe=mdp,
                      notes=self.notes.get("1.0", "end"), categorie=self.categorie.get(),
                      favori=bool(self.favori.get()), totp=cle_2fa)
        coffre = self.ecran.app.coffre
        if self.entree:
            coffre.modifier(self.entree["id"], **champs)
            self.ecran.notifier(t("Identifiant modifié"))
        else:
            coffre.ajouter(**champs)
            self.ecran.notifier(t("Identifiant ajouté"))
        self.ecran.rafraichir()
        self.destroy()

    def _supprimer(self):
        ConfirmationSuppression(self, self.entree["site"], self._confirmer_suppression)

    def _confirmer_suppression(self):
        self.ecran.app.coffre.supprimer(self.entree["id"])
        self.ecran.notifier(t("Identifiant supprimé"))
        self.ecran.rafraichir()
        self.destroy()


class DialogueHistorique(Dialogue):
    """Anciens mots de passe d'un compte, du plus récent au plus ancien."""

    def __init__(self, parent, entree):
        super().__init__(parent, t("Historique"))
        app = parent.winfo_toplevel()
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)
        ctk.CTkLabel(corps, text=t("Anciens mots de passe de « {nom} »", nom=entree["site"]),
                     font=police(17, gras=True), text_color=TEXTE, anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text=t("Utile si le changement sur le site n'a pas abouti."),
                     font=police(12), text_color=TEXTE_DOUX, anchor="w").pack(fill="x",
                                                                            pady=(2, 12))
        familles = set(tkinter.font.families())
        mono = next((f for f in ("JetBrains Mono", "DejaVu Sans Mono") if f in familles),
                    "TkFixedFont")
        for ancien in entree["historique"]:
            ligne = ctk.CTkFrame(corps, fg_color=CARTE, corner_radius=10)
            ligne.pack(fill="x", pady=3)
            try:
                date = datetime.date.fromisoformat(ancien["remplace_le"]).strftime("%d/%m/%Y")
            except ValueError:
                date = ancien["remplace_le"]
            ctk.CTkLabel(ligne, text=t("Remplacé le {date}", date=date), font=police(11),
                         text_color=TEXTE_DOUX, width=130, anchor="w").pack(side="left",
                                                                           padx=(14, 6), pady=8)
            texte = ctk.CTkLabel(ligne, text="•" * 12, text_color=TEXTE, anchor="w", width=220,
                                 font=ctk.CTkFont(family=mono, size=round(13 * ECHELLE_TEXTE)))
            texte.pack(side="left", fill="x", expand=True)
            mdp = ancien["mot_de_passe"]
            BoutonAnime(ligne, t("Copier"), lambda m=mdp: self._copier(app, m), width=80, height=30,
                        taille_police=12).pack(side="right", padx=(0, 8))
            voir = BoutonAnime(ligne, t("Afficher"), None, width=84, height=30, taille_police=12)
            voir.commande = lambda w=texte, m=mdp, b=voir: self._basculer(w, m, b)
            voir.pack(side="right", padx=(0, 6))
        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=SUCCES)
        self.message.pack(pady=(6, 0))
        BoutonAnime(corps, t("Fermer"), self.destroy, width=100).pack(anchor="e", pady=(4, 0))

    def _basculer(self, libelle, mdp, bouton):
        visible = libelle.cget("text") == mdp
        libelle.configure(text="•" * 12 if visible else mdp)
        bouton.changer_texte(t("Afficher") if visible else t("Masquer"))

    def _copier(self, app, mdp):
        app.copier(mdp)
        self.message.configure(text="✓  " + mdp_copie())


class ConfirmationSuppression(Dialogue):
    def __init__(self, parent, nom, action):
        super().__init__(parent, t("Confirmer"))
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)
        ctk.CTkLabel(corps, text=t("Supprimer « {nom} » ?", nom=nom), font=police(17, gras=True),
                     text_color=TEXTE).pack(anchor="w")
        ctk.CTkLabel(corps, text=t("Cette action est définitive."), font=police(13),
                     text_color=TEXTE_DOUX).pack(anchor="w", pady=(4, 18))
        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(fill="x")

        def confirmer():
            self.destroy()
            action()

        BoutonAnime(boutons, t("Supprimer"), confirmer, style="danger", width=110).pack(side="right")
        BoutonAnime(boutons, t("Annuler"), self.destroy, width=100).pack(side="right")


class FenetreSauvegarde(Dialogue):
    """Export et import chiffrés, et restauration de la copie automatique du coffre."""

    EXTENSION = ".secretlin"

    def types(self):
        return [(t("Export SecretLin"), "*" + self.EXTENSION), (t("Tous les fichiers"), "*")]

    def __init__(self, ecran: EcranPrincipal):
        super().__init__(ecran.app, t("Sauvegarde"))
        self.ecran = ecran
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)
        ctk.CTkLabel(corps, text=t("Sauvegarde du coffre"), font=police(20, gras=True),
                     text_color=TEXTE, anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text=t("Les fichiers exportés restent chiffrés."), font=police(12),
                     text_color=TEXTE_DOUX, anchor="w").pack(fill="x", pady=(2, 10))

        def rangee(titre, texte, bouton, commande, actif=True):
            ligne = ctk.CTkFrame(corps, fg_color=CARTE, corner_radius=12)
            ligne.pack(fill="x", pady=5)
            textes = ctk.CTkFrame(ligne, fg_color="transparent")
            textes.pack(side="left", fill="x", expand=True, padx=(16, 8), pady=12)
            ctk.CTkLabel(textes, text=titre, font=police(14, gras=True), text_color=TEXTE,
                         anchor="w").pack(fill="x")
            ctk.CTkLabel(textes, text=texte, font=police(12), text_color=TEXTE_DOUX, anchor="w",
                         justify="left", wraplength=330).pack(fill="x")
            b = BoutonAnime(ligne, bouton, commande, width=110)
            b.pack(side="right", padx=(0, 8))
            b.activer(actif)

        rangee(t("Exporter"), t("Enregistre tous vos identifiants dans un fichier chiffré "
                                "avec un mot de passe d'export."), t("Exporter…"), self._exporter)
        rangee(t("Importer"), t("Ajoute les identifiants d'un fichier exporté. "
                                "Les doublons sont ignorés."), t("Importer…"), self._importer)
        rangee(t("Depuis un autre gestionnaire"),
               t("Firefox, Chrome, Bitwarden, KeePass, 1Password ou LastPass : importez leur "
                 "fichier d'export CSV."), t("Choisir…"), self._importer_externe)
        rangee(t("Restaurer"), t("Revient à une copie automatique : celle d'avant le dernier "
                                 "enregistrement, ou celle faite à l'un des derniers "
                                 "déverrouillages."),
               t("Restaurer…"), self._restaurer, actif=ecran.app.coffre.a_une_sauvegarde())

        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=DANGER,
                                    wraplength=480)
        self.message.pack(pady=(6, 0))
        BoutonAnime(corps, t("Fermer"), self.destroy, width=100).pack(anchor="e", pady=(4, 0))

    def _exporter(self):
        nom = f"secretlin-{datetime.date.today().isoformat()}{self.EXTENSION}"
        chemin = filedialog.asksaveasfilename(parent=self, title=t("Exporter le coffre"),
                                              initialfile=nom, defaultextension=self.EXTENSION,
                                              filetypes=self.types())
        if not chemin:
            return
        DialogueMotDePasse(
            self, t("Mot de passe d'export"),
            t("Choisissez un mot de passe pour ce fichier. Il sera demandé à l'import."),
            nouveau=True, libelle=t("Exporter"),
            travail=lambda mdp: self.ecran.app.coffre.exporter(Path(chemin), mdp),
            succes=lambda _r: self._fin(t("Coffre exporté")))

    def _importer(self):
        chemin = filedialog.askopenfilename(parent=self, title=t("Importer un export"),
                                            filetypes=self.types())
        if not chemin:
            return
        DialogueMotDePasse(
            self, t("Importer"), t("Entrez le mot de passe choisi lors de l'export."),
            libelle=t("Importer"),
            travail=lambda mdp: self.ecran.app.coffre.importer(Path(chemin), mdp),
            succes=lambda n: self._fin(
                tn("{n} identifiant importé", "{n} identifiants importés", n) if n
                else t("Rien à importer : tout est déjà dans le coffre")))

    def _importer_externe(self):
        chemin = filedialog.askopenfilename(
            parent=self, title=t("Importer depuis un autre gestionnaire"),
            filetypes=[(t("Fichier CSV"), "*.csv"), (t("Tous les fichiers"), "*")])
        if not chemin:
            return
        try:
            source, entrees = import_externe.lire(Path(chemin))
        except (OSError, ValueError) as e:
            self.message.configure(text=str(e) if isinstance(e, import_externe.FormatInconnu)
                                   else t("Fichier illisible."))
            return
        self.message.configure(text="")
        DialogueImportExterne(self, Path(chemin), source, entrees)

    def _restaurer(self):
        coffre = self.ecran.app.coffre
        choix = []
        if coffre.chemin_sauvegarde.exists():
            choix.append((t("Avant le dernier enregistrement"), coffre.chemin_sauvegarde))
        for copie in coffre.copies_ouverture():
            date = coffre.date_copie(copie)
            if date:
                choix.append((t("Déverrouillage du {date} à {heure}", date=f"{date:%d/%m/%Y}",
                                heure=f"{date:%H:%M:%S}"), copie))
        DialogueMotDePasse(
            self, t("Restaurer"),
            t("Choisissez la copie à remettre en place, puis entrez le mot de passe maître "
              "qui l'ouvre. Le coffre actuel reste récupérable avec « Avant le dernier "
              "enregistrement »."),
            libelle=t("Restaurer"), style="danger", choix=choix,
            travail=lambda mdp, copie: coffre.restaurer_sauvegarde(mdp, copie),
            succes=lambda _r: self._fin(t("Copie restaurée")))

    def _fin(self, message):
        self.ecran.rafraichir()
        self.ecran.notifier(message)
        self.destroy()


class DialogueImportExterne(Dialogue):
    """Confirmation avant d'importer un CSV d'un autre gestionnaire, avec l'option de
    supprimer ce fichier, qui contient les mots de passe en clair."""

    def __init__(self, fenetre: FenetreSauvegarde, chemin: Path, source: str, entrees: list):
        super().__init__(fenetre, t("Importer"))
        self.fenetre, self.chemin, self.entrees = fenetre, chemin, entrees
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)
        titre = (t("Fichier CSV") if source == "CSV"
                 else t("Export {source}", source=source))
        ctk.CTkLabel(corps, text=titre, font=police(17, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text=tn("{n} identifiant trouvé dans ce fichier.",
                                    "{n} identifiants trouvés dans ce fichier.", len(entrees)),
                     font=police(13), text_color=TEXTE, anchor="w").pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(corps, text=t("Les comptes déjà présents dans le coffre ne seront pas "
                                   "ajoutés deux fois."),
                     font=police(12), text_color=TEXTE_DOUX, anchor="w", justify="left",
                     wraplength=360).pack(fill="x")
        ctk.CTkLabel(corps, text=t("⚠  Ce fichier contient vos mots de passe en clair : "
                                   "supprimez-le après l'import."),
                     font=police(12), text_color="#f0883e", anchor="w", justify="left",
                     wraplength=360).pack(fill="x", pady=(12, 6))
        self.supprimer = ctk.CTkCheckBox(corps, text=t("Supprimer le fichier CSV après l'import"),
                                         font=police(12), text_color=TEXTE, fg_color=ACCENT,
                                         hover_color=STYLES["principal"]["fond_survol"],
                                         border_color=BORDURE_ECLAT, checkmark_color=ACCENT_TEXTE)
        self.supprimer.pack(anchor="w", pady=(0, 14))
        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(fill="x")
        bouton = BoutonAnime(boutons, t("Importer"), self._importer, style="principal", width=120)
        bouton.pack(side="right")
        bouton.activer(bool(entrees))
        BoutonAnime(boutons, t("Annuler"), self.destroy, width=100).pack(side="right")

    def _importer(self):
        ajoutees, ignorees = self.fenetre.ecran.app.coffre.ajouter_externes(self.entrees)
        message = tn("{n} identifiant importé", "{n} identifiants importés", ajoutees)
        if ignorees:
            message += "  ·  " + tn("{n} déjà présent", "{n} déjà présents", ignorees)
        if self.supprimer.get():
            try:
                self.chemin.unlink()
            except OSError:
                message += "  ·  " + t("le fichier CSV n'a pas pu être supprimé")
        self.destroy()
        self.fenetre._fin(message)


class DialogueMotDePasse(Dialogue):
    """Demande un mot de passe, puis lance « travail(mdp) » en arrière-plan
    (Argon2id prend du temps) et appelle « succes(resultat) » s'il réussit."""

    def __init__(self, parent, titre, texte, travail, succes, libelle=None,
                 nouveau=False, style="principal", choix=None):
        super().__init__(parent, titre)
        self.app = parent.winfo_toplevel()
        self.travail, self.succes, self.nouveau = travail, succes, nouveau
        # « choix » : liste de (libellé, valeur) ; la valeur choisie est passée à « travail ».
        self.choix = dict(choix) if choix else None
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)
        ctk.CTkLabel(corps, text=titre, font=police(17, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text=texte, font=police(12), text_color=TEXTE_DOUX, anchor="w",
                     justify="left", wraplength=340).pack(fill="x", pady=(4, 14))
        if self.choix:
            self.liste = ctk.CTkOptionMenu(
                corps, values=list(self.choix), width=340, height=38, corner_radius=9,
                fg_color=FOND, button_color=CARTE, button_hover_color=CARTE_SURVOL,
                text_color=TEXTE, font=police(13), dropdown_font=police(13),
                dropdown_fg_color=PANNEAU, dropdown_hover_color=CARTE_SURVOL,
                dropdown_text_color=TEXTE)
            self.liste.pack(pady=(0, 10))
        self.mdp = champ(corps, t("Mot de passe"), masque=True, width=340)
        self.mdp.pack()
        if nouveau:
            self.jauge = JaugeForce(corps)
            self.jauge.pack(fill="x", pady=(4, 8))
            self.mdp.bind("<KeyRelease>", lambda _e: self.jauge.maj(self.mdp.get()))
            self.confirmation = champ(corps, t("Confirmer le mot de passe"), masque=True, width=340)
            self.confirmation.pack()
            self.confirmation.bind("<Return>", lambda _e: self._valider())
        else:
            self.mdp.bind("<Return>", lambda _e: self._valider())
        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=DANGER,
                                    wraplength=340)
        self.message.pack(pady=(6, 0))
        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(fill="x", pady=(4, 0))
        self.libelle = libelle = libelle or t("Valider")
        self.bouton = BoutonAnime(boutons, libelle, self._valider, style=style, width=120)
        self.bouton.pack(side="right")
        BoutonAnime(boutons, t("Annuler"), self.destroy, width=100).pack(side="right")
        self.after(80, self.mdp.focus_set)

    def _valider(self):
        mdp = self.mdp.get()
        if not mdp:
            self.message.configure(text=t("Entrez un mot de passe."))
            return
        if self.nouveau:
            problemes = verifier_force(mdp)
            if problemes:
                self.message.configure(text=t("Il manque : {liste}.", liste=", ".join(problemes)))
                return
            if mdp != self.confirmation.get():
                self.message.configure(text=t("Les deux mots de passe ne correspondent pas."))
                return
        valeur = self.liste.get() if self.choix else None
        self.bouton.activer(False, t("Patientez…"))
        self.message.configure(text="")

        def fond():
            try:
                if self.choix:
                    resultat, erreur = self.travail(mdp, self.choix[valeur]), None
                else:
                    resultat, erreur = self.travail(mdp), None
            except MotDePasseIncorrect:
                resultat, erreur = None, t("Mot de passe incorrect.")
            except CoffreCorrompu:
                resultat, erreur = None, t("Ce fichier est illisible ou n'est pas un export SecretLin.")
            except (OSError, RuntimeError, ValueError) as e:
                resultat, erreur = None, t("Opération impossible : {erreur}", erreur=e)
            self.app.after(0, lambda: self._resultat(resultat, erreur))

        threading.Thread(target=fond, daemon=True).start()

    def _resultat(self, resultat, erreur):
        # Le coffre a pu être verrouillé pendant l'opération : on ne le laisse pas ouvert.
        if not isinstance(self.app.ecran, EcranPrincipal):
            self.app.coffre.verrouiller()
            return
        if not self.winfo_exists():
            return
        if erreur:
            self.bouton.activer(True, self.libelle)
            self.mdp.delete(0, "end")
            self.message.configure(text=erreur)
            return
        self.destroy()
        self.succes(resultat)


# --- Réglages ---------------------------------------------------------------

def sur_clic(widgets, action):
    """Appelle action() quand on clique sur l'un des widgets. Un widget CTk se dessine
    dans un canevas intérieur : c'est son propre bind() qui y relaie le clic."""
    for w in widgets:
        w.bind("<Button-1>", lambda _e: action(), add="+")


class Page(ctk.CTkFrame):
    """Page affichée à la place de la liste : bouton de retour, titre et sous-titre."""

    def __init__(self, ecran: EcranPrincipal, titre, sous_titre, retour=None):
        super().__init__(ecran, fg_color="transparent")
        self.ecran = ecran
        haut = ctk.CTkFrame(self, fg_color="transparent")
        haut.pack(fill="x")
        BoutonAnime(haut, "←  " + (retour or t("Retour")), ecran.page_precedente, width=112).pack(side="left")
        ctk.CTkLabel(haut, text=titre, font=police(22, gras=True), text_color=TEXTE).pack(
            side="left", padx=(12, 0))
        ctk.CTkLabel(self, text=sous_titre, font=police(12), text_color=TEXTE_DOUX,
                     anchor="w").pack(fill="x", padx=(8, 0), pady=(6, 16))

    def affichee(self):
        """Appelée chaque fois que la page devient visible."""

    def coffre_modifie(self):
        """Appelée après un ajout, une modification ou une suppression d'identifiant."""

    def _section(self, parent, titre, texte):
        carte = ctk.CTkFrame(parent, fg_color=CARTE, corner_radius=12, border_width=1,
                             border_color=BORDURE)
        carte.pack(fill="x", pady=4)
        ctk.CTkLabel(carte, text=titre, font=police(15, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(carte, text=texte, font=police(12), text_color=TEXTE_DOUX,
                     anchor="w").pack(fill="x", padx=20, pady=(2, 10))
        contenu = ctk.CTkFrame(carte, fg_color="transparent")
        contenu.pack(fill="x", padx=20, pady=(0, 16))
        return contenu


class CarteMenu(ctk.CTkFrame):
    """Rubrique cliquable des réglages : titre, description facultative et flèche."""

    def __init__(self, parent, titre, description, action):
        super().__init__(parent, fg_color=CARTE, corner_radius=12, border_width=1,
                         border_color=BORDURE, cursor="hand2")
        definir(self, "bord", BORDURE)
        textes = ctk.CTkFrame(self, fg_color="transparent")
        textes.pack(side="left", fill="x", expand=True, padx=18, pady=14)
        widgets = [self, textes]
        lignes = [(titre, 15, True, TEXTE)]
        if description:
            lignes.append((description, 12, False, TEXTE_DOUX))
        for texte, taille, gras, couleur in lignes:
            l = ctk.CTkLabel(textes, text=texte, font=police(taille, gras=gras),
                             text_color=couleur, anchor="w")
            l.pack(fill="x")
            widgets.append(l)
        fleche = ctk.CTkLabel(self, text="›", font=police(24), text_color=TEXTE_DOUX)
        fleche.pack(side="right", padx=18)
        widgets.append(fleche)
        sur_clic(widgets, action)
        survol(self, lambda: self._etat(True), lambda: self._etat(False))

    def _etat(self, survole):
        transition(self, "bord", BORDURE_ECLAT if survole else BORDURE, 0.25,
                   lambda c: self.configure(border_color=c))


class PageReglages(Page):
    """Liste des rubriques de réglages. Pour en ajouter une : une ligne dans « rubriques »."""

    def __init__(self, ecran: EcranPrincipal):
        super().__init__(ecran, t("Réglages"), t("Choisissez une rubrique."))
        self.rubriques = [
            (t("Sécurité"), "", PageSecurite),
            (t("Générateur"), "", PageGenerateur),
            (t("Apparence"), "", PageApparence),
            (t("Langue"), "", PageLangue),
        ]
        for titre, description, classe in self.rubriques:
            CarteMenu(self, titre, description,
                      lambda c=classe: ecran.ouvrir_page(c)).pack(fill="x", pady=4)
        CarteMenu(self, t("Quitter SecretLin"),
                  t("Ferme complètement l'application, même en arrière-plan."),
                  lambda: ecran.app.after(50, ecran.app.quitter)).pack(fill="x", pady=(16, 4))

    def affichee(self):
        # Une fois la page à l'écran : la rubrique quittée est reconstruite pour la prochaine fois.
        self.after(150, lambda: self.ecran.preparer_pages([c for _, _, c in self.rubriques]))


class PageSecurite(Page):
    def __init__(self, ecran: EcranPrincipal):
        super().__init__(ecran, t("Sécurité"), t("Tout ce qui protège l'accès à votre coffre."),
                         retour=t("Réglages"))
        defilement = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                            scrollbar_button_color=BORDURE,
                                            scrollbar_button_hover_color=BORDURE_ECLAT)
        defilement.pack(fill="both", expand=True)
        self.section = SectionMotDePasse(defilement, ecran)
        self.section.pack(fill="x", pady=4)
        SectionAccesRapide(defilement, ecran).pack(fill="x", pady=4)
        SectionFichierCle(defilement, ecran).pack(fill="x", pady=4)

    def affichee(self):
        self.after(80, self.section.actuel.focus_set)


class PageGenerateur(Page):
    """Options du bouton « Générer » : longueur et types de caractères, avec un aperçu."""

    def __init__(self, ecran: EcranPrincipal):
        super().__init__(ecran, t("Générateur"), t("Ce que produit le bouton « Générer » quand "
                                                   "vous ajoutez ou modifiez un identifiant."),
                         retour=t("Réglages"))
        self.app = ecran.app
        r = self.app.reglages
        self._jeton = None
        defilement = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                            scrollbar_button_color=BORDURE,
                                            scrollbar_button_hover_color=BORDURE_ECLAT)
        defilement.pack(fill="both", expand=True)
        apercu = self._section(defilement, t("Aperçu"), t("Un exemple avec les réglages ci-dessous."))
        ligne = ctk.CTkFrame(apercu, fg_color="transparent")
        ligne.pack(fill="x")
        familles = set(tkinter.font.families())
        mono = next((f for f in ("JetBrains Mono", "DejaVu Sans Mono", "Consolas", "Courier New")
                     if f in familles), "TkFixedFont")
        self.exemple = ctk.CTkLabel(ligne, text="", font=ctk.CTkFont(
            family=mono, size=round(15 * ECHELLE_TEXTE)), text_color=TEXTE, anchor="w")
        self.exemple.pack(side="left", fill="x", expand=True)
        BoutonAnime(ligne, t("Régénérer"), self._apercu, width=110).pack(side="right")
        self.jauge = JaugeForce(apercu)
        self.jauge.pack(fill="x", pady=(6, 0))

        longueur = self._section(defilement, t("Longueur"), t("Plus c'est long, plus c'est solide."))
        self.valeur = ctk.CTkLabel(longueur, text="", font=police(13, gras=True),
                                   text_color=TEXTE, width=120, anchor="w")
        self.valeur.pack(side="left")
        mini, maxi = apparence.LONGUEUR_MIN, apparence.LONGUEUR_MAX
        self.curseur = ctk.CTkSlider(longueur, from_=mini, to=maxi, number_of_steps=maxi - mini,
                                     command=lambda _v: self._modifie(), fg_color=BORDURE,
                                     progress_color=ACCENT, button_color=ACCENT,
                                     button_hover_color=STYLES["principal"]["fond_survol"])
        self.curseur.set(r["longueur"])
        self.curseur.pack(side="left", fill="x", expand=True, padx=(8, 0))

        caracteres = self._section(defilement, t("Caractères"),
                                   t("Les minuscules (a–z) sont toujours incluses."))
        self.interrupteurs = {}
        for cle, texte in (("majuscules", t("Majuscules (A–Z)")), ("chiffres", t("Chiffres (0–9)")),
                           ("symboles", t("Symboles") + " (" + SYMBOLES + ")"),
                           ("sans_ambigus", t("Éviter les caractères qui se ressemblent")
                            + " (" + " ".join(AMBIGUS) + ")")):
            inter = ctk.CTkSwitch(caracteres, text=texte, font=police(13), text_color=TEXTE,
                                  command=self._modifie, fg_color=BORDURE, progress_color=ACCENT,
                                  button_color=TEXTE_DOUX, button_hover_color=TEXTE)
            if r[cle]:
                inter.select()
            inter.pack(anchor="w", pady=4)
            self.interrupteurs[cle] = inter
        self._modifie(enregistrer=False)

    def _reglages_choisis(self):
        options = {cle: bool(i.get()) for cle, i in self.interrupteurs.items()}
        return dict(options, longueur=round(self.curseur.get()))

    def _apercu(self):
        mdp = generer_mot_de_passe(**self._reglages_choisis())
        self.exemple.configure(text=mdp)
        self.jauge.maj(mdp)

    def _modifie(self, enregistrer=True):
        options = self._reglages_choisis()
        self.valeur.configure(text=t("{n} caractères", n=options["longueur"]))
        self._apercu()
        if enregistrer:
            # Le curseur appelle ceci à chaque cran : on n'écrit le fichier qu'une fois arrêté.
            # Sur la fenêtre principale : l'enregistrement a lieu même si l'on quitte la page.
            if self._jeton:
                self.app.after_cancel(self._jeton)
            options = self._reglages_choisis()
            self._jeton = self.app.after(400, lambda: self.app.enregistrer_reglages(**options))


class PageApparence(Page):
    """Thème, couleur d'accent, police, taille du texte et animations : chaque choix s'applique
    tout de suite et reste enregistré."""

    def __init__(self, ecran: EcranPrincipal):
        super().__init__(ecran, t("Apparence"), t("Chaque choix s'applique tout de suite et reste "
                                                  "enregistré."), retour=t("Réglages"))
        self.app = ecran.app
        r = self.app.reglages
        defilement = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                            scrollbar_button_color=BORDURE,
                                            scrollbar_button_hover_color=BORDURE_ECLAT)
        defilement.pack(fill="both", expand=True)

        themes = self._section(defilement, t("Thème"), t("L'ambiance de toute l'application."))
        for nom, theme in apparence.THEMES.items():
            self._apercu_theme(themes, nom, theme, nom == r["theme"]).pack(side="left", padx=(0, 10))

        accents = self._section(defilement, t("Couleur d'accent"),
                                t("Les boutons principaux, comme « Ajouter », et les notifications."))
        for nom, couleur in apparence.ACCENTS.items():
            couleur = couleur or apparence.THEMES[r["theme"]]["neutre"]
            self._pastille_accent(accents, nom, couleur, nom == r["accent"]).pack(
                side="left", padx=(0, 14))

        polices = self._section(defilement, t("Police"), t("Le style des lettres dans toute "
                                                            "l'application."))
        installees = set(tkinter.font.families())
        for i, nom in enumerate(apparence.POLICES):
            self._apercu_police(polices, nom, nom == r["police"], nom in installees).grid(
                row=i // 5, column=i % 5, padx=(0, 10), pady=(0, 10))

        tailles = self._section(defilement, t("Taille du texte"), t("Pour tout le texte de l'application."))
        self._choix(tailles, list(apparence.TAILLES), r["taille"],
                    lambda v: self._changer(taille=v))

        anim = self._section(defilement, t("Animations"),
                             t("Zoom et halo des boutons, fumée de la recherche, transitions."))
        self._choix(anim, ["Activées", "Désactivées"],
                    "Activées" if r["animations"] else "Désactivées",
                    lambda v: self._changer(animations=v == "Activées"))

        BoutonAnime(defilement, t("Revenir à l'apparence d'origine"),
                    lambda: self._changer(**{c: apparence.DEFAUT[c] for c in apparence.CLES_APPARENCE}),
                    width=240).pack(anchor="w", pady=(6, 4))

    def _changer(self, **choix):
        # Après la fin du clic : l'écran entier (et ce bouton) va être recréé.
        self.app.after(80, lambda: self.app.changer_apparence(**choix))

    def _choix(self, parent, options, actuel, action):
        """Rangée de boutons dont un seul est choisi (mis en avant)."""
        for option in options:
            BoutonAnime(parent, t(option), lambda o=option: action(o),
                        style="principal" if option == actuel else "secondaire",
                        width=110).pack(side="left")

    def _apercu_theme(self, parent, nom, t, choisi):
        """Vignette qui montre le thème en miniature : fond, carte, texte et accent."""
        cadre = ctk.CTkFrame(parent, fg_color=t["fond"], corner_radius=10, width=132, height=86,
                             border_width=2, border_color=ACCENT if choisi else t["bordure"],
                             cursor="hand2")
        cadre.pack_propagate(False)
        carte = ctk.CTkFrame(cadre, fg_color=t["carte"], corner_radius=6, height=30,
                             border_width=1, border_color=t["bordure"])
        carte.pack(fill="x", padx=10, pady=(10, 6))
        carte.pack_propagate(False)
        ligne = ctk.CTkFrame(carte, fg_color=t["texte_doux"], corner_radius=2, width=46, height=4)
        ligne.place(x=8, rely=0.5, anchor="w")
        bouton = ctk.CTkFrame(carte, fg_color=t["neutre"], corner_radius=4, width=22, height=12)
        bouton.place(relx=1.0, x=-8, rely=0.5, anchor="e")
        libelle = ctk.CTkLabel(cadre, text=("✓  " if choisi else "") + langue.t(nom),
                               font=police(12, gras=True), text_color=t["texte"],
                               fg_color="transparent")
        libelle.pack(anchor="w", padx=10)
        sur_clic((cadre, carte, ligne, bouton, libelle), lambda: self._changer(theme=nom))
        if not choisi:
            survol(cadre, lambda: cadre.configure(border_color=BORDURE_ECLAT),
                   lambda: cadre.configure(border_color=t["bordure"]))
        return cadre

    def _apercu_police(self, parent, nom, choisie, installee):
        """Vignette écrite dans la police elle-même ; grisée si elle n'est pas installée."""
        cadre = ctk.CTkFrame(parent, fg_color=PANNEAU, corner_radius=10, width=132, height=86,
                             border_width=2, border_color=ACCENT if choisie else BORDURE,
                             cursor="hand2" if installee else "")
        cadre.pack_propagate(False)
        famille = nom if installee else "TkDefaultFont"
        exemple = ctk.CTkLabel(cadre, text="Aa 123" if installee else nom, text_color=TEXTE if installee else TEXTE_ETEINT,
                               font=ctk.CTkFont(family=famille,
                                                size=round((22 if installee else 14) * ECHELLE_TEXTE)))
        exemple.pack(anchor="w", padx=10, pady=(8, 0))
        libelle = ctk.CTkLabel(cadre, text=("✓  " if choisie else "") + nom
                               if installee else t("Non installée"),
                               text_color=TEXTE_DOUX if installee else TEXTE_ETEINT,
                               font=ctk.CTkFont(family=famille, size=round(12 * ECHELLE_TEXTE),
                                                weight="bold" if choisie else "normal"))
        libelle.pack(anchor="w", padx=10)
        if installee:
            sur_clic((cadre, exemple, libelle), lambda: self._changer(police=nom))
            if not choisie:
                survol(cadre, lambda: cadre.configure(border_color=BORDURE_ECLAT),
                       lambda: cadre.configure(border_color=BORDURE))
        return cadre

    def _pastille_accent(self, parent, nom, couleur, choisie):
        """Rond de couleur cliquable, entouré quand c'est l'accent choisi."""
        bloc = ctk.CTkFrame(parent, fg_color="transparent", cursor="hand2")

        def image(anneau):
            return ctk.CTkImage(_pastille(76, couleur, BORDURE, anneau), size=(38, 38))

        rond = ctk.CTkLabel(bloc, text="", image=image(TEXTE if choisie else None), cursor="hand2")
        rond.pack()
        libelle = ctk.CTkLabel(bloc, text=t(nom), font=police(11, gras=choisie),
                               text_color=TEXTE if choisie else TEXTE_DOUX)
        libelle.pack(pady=(2, 0))
        sur_clic((bloc, rond, libelle), lambda: self._changer(accent=nom))
        if not choisie:
            normal, survole = image(None), image(BORDURE_ECLAT)
            survol(bloc, lambda: rond.configure(image=survole),
                   lambda: rond.configure(image=normal))
        return bloc

class PageLangue(Page):
    """Langue de l'interface : automatique (celle du système) ou l'une des langues proposées."""

    def __init__(self, ecran: EcranPrincipal):
        super().__init__(ecran, t("Langue"), t("La langue de toute l'application."),
                         retour=t("Réglages"))
        self.app = ecran.app
        choisie = self.app.reglages["langue"]
        auto = self._section(self, t("Automatique"),
                             t("Suit la langue de l'ordinateur ({langue}).",
                               langue=langue.LANGUES[langue.langue_systeme()]))
        self._bouton(auto, t("Automatique"), langue.AUTO, choisie).pack(anchor="w")
        liste = self._section(self, t("Langues"), t("Chaque langue est écrite dans sa propre langue."))
        for i, (code, nom) in enumerate(langue.LANGUES.items()):
            self._bouton(liste, nom, code, choisie).grid(row=i // 5, column=i % 5, padx=(0, 10),
                                                         pady=(0, 10), sticky="w")

    def _bouton(self, parent, texte, code, choisie):
        return BoutonAnime(parent, ("✓  " if code == choisie else "") + texte,
                           lambda: self.app.after(80, lambda: self.app.changer_apparence(
                               page=PageLangue, langue=code)),
                           style="principal" if code == choisie else "secondaire", width=140)


def duree_depuis(jours: int) -> str:
    """« 14 mois », « 2 ans »…"""
    if jours >= 730:
        return t("{n} ans", n=jours // 365)
    return t("{n} mois", n=jours // 30)


class PageSante(Page):
    """Bilan de santé : les mots de passe faibles, réutilisés, trop anciens ou piratés,
    chacun avec un bouton pour le changer."""

    def __init__(self, ecran: EcranPrincipal):
        super().__init__(ecran, t("Bilan de santé"), t("Les mots de passe à changer en priorité."))
        self.app = ecran.app
        self.defilement = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                                 scrollbar_button_color=BORDURE,
                                                 scrollbar_button_hover_color=BORDURE_ECLAT)
        self.defilement.pack(fill="both", expand=True)
        self._remplir()
        self._verifier_fuites()

    def coffre_modifie(self):
        self._redessiner()
        self._verifier_fuites()

    def _redessiner(self):
        if not self.winfo_exists():
            return
        for enfant in self.defilement.winfo_children():
            enfant.destroy()
        self._remplir()

    def _verifier_fuites(self, tout=False):
        """Vérifie en ligne les mots de passe pas encore vérifiés (tous si « tout »), si
        l'option est activée."""
        app = self.app
        if not app.reglages["verifier_fuites"]:
            return
        a_verifier = {e["mot_de_passe"] for e in app.coffre.entrees}
        if not tout:
            a_verifier -= set(app.fuites)
        if not a_verifier:
            return
        app.etat_fuites = t("Vérification en cours…")
        self._redessiner()

        def fond():
            try:
                resultats, etat = fuites.verifier(a_verifier), ""
            except OSError:
                resultats, etat = {}, t("Vérification impossible : pas de connexion Internet ?")
            app.after(0, lambda: fin(resultats, etat))

        def fin(resultats, etat):
            if not isinstance(app.ecran, EcranPrincipal):
                return  # verrouillé entre-temps : on ne garde rien
            app.fuites.update(resultats)
            app.etat_fuites = etat
            self._redessiner()

        threading.Thread(target=fond, daemon=True).start()

    def _changer_option_fuites(self, active):
        self.app.enregistrer_reglages(verifier_fuites=active)
        if not active:
            self.app.fuites, self.app.etat_fuites = {}, ""
            self._redessiner()
        else:
            self._verifier_fuites(tout=True)

    def _remplir(self):
        entrees = self.app.coffre.entrees
        verifie = self.app.reglages["verifier_fuites"]
        b = sante.bilan(entrees, fuites=self.app.fuites if verifie else None)
        self._resume(b, len(entrees), verifie)
        self._section_fuites(verifie)
        categories = (
            ("pirates", t("Mots de passe piratés"),
             t("Ils apparaissent dans des fuites de données publiques : changez-les en premier."),
             lambda e: t("Vu {n} fois dans des fuites",
                         n=f"{self.app.fuites[e['mot_de_passe']]:,}".replace(",", " "))),
            ("faibles", t("Mots de passe faibles"),
             t("Trop courts ou trop simples : faciles à deviner pour un programme."),
             lambda e: t("Force : {niveau}",
                         niveau=t(LIBELLES_FORCE[evaluer_force(e["mot_de_passe"])]))),
            ("reutilises", t("Mots de passe réutilisés"),
             t("Si l'un de ces sites se fait pirater, les autres comptes sont exposés aussi."),
             lambda e: t("Utilisé sur {n} comptes", n=b["usages"][e["mot_de_passe"]])),
            ("anciens", t("Mots de passe anciens"),
             t("Pas changés depuis plus d'un an."),
             lambda e: t("Pas changé depuis {duree}", duree=duree_depuis(sante.age_jours(e)))),
        )
        for cle, titre, texte, raison in categories:
            if b[cle]:
                section = self._section(self.defilement, f"{titre}  ({len(b[cle])})", texte)
                for e in b[cle]:
                    self._ligne(section, e, raison(e))

    def _section_fuites(self, verifie):
        section = self._section(self.defilement, t("Fuites de données"),
                                t("Vérifie si vos mots de passe apparaissent dans des fuites "
                                  "connues, avec le service Have I Been Pwned."))
        interrupteur = ctk.CTkSwitch(
            section, text=t("Vérifier en ligne (Internet)"), font=police(13), text_color=TEXTE,
            command=lambda: self._changer_option_fuites(bool(interrupteur.get())),
            fg_color=BORDURE, progress_color=ACCENT, button_color=TEXTE_DOUX,
            button_hover_color=TEXTE)
        if verifie:
            interrupteur.select()
        interrupteur.pack(anchor="w")
        ctk.CTkLabel(section, text=t("Vos mots de passe ne sont jamais envoyés : seuls les 5 "
                                     "premiers caractères de leur empreinte partent sur "
                                     "Internet, et la comparaison se fait sur l'ordinateur."),
                     font=police(11), text_color=TEXTE_DOUX, anchor="w", justify="left",
                     wraplength=640).pack(fill="x", pady=(6, 0))
        if verifie and self.app.etat_fuites:
            ctk.CTkLabel(section, text=self.app.etat_fuites, font=police(12),
                         text_color=TEXTE if "…" in self.app.etat_fuites else DANGER,
                         anchor="w").pack(fill="x", pady=(6, 0))
        if verifie and not self.app.etat_fuites.endswith("…"):
            BoutonAnime(section, t("Vérifier à nouveau"),
                        lambda: self.app.after(50, lambda: self._verifier_fuites(tout=True)),
                        width=160, height=32, taille_police=12).pack(anchor="w", pady=(8, 0))

    def _resume(self, b, total, verifie=False):
        carte = ctk.CTkFrame(self.defilement, fg_color=CARTE, corner_radius=12, border_width=1,
                             border_color=BORDURE)
        carte.pack(fill="x", pady=4)
        note = b["note"]
        couleur = SUCCES if note == 100 else "#f0883e" if note >= 60 else DANGER
        ctk.CTkLabel(carte, text=f"{note} %", font=police(40, gras=True),
                     text_color=couleur).pack(side="left", padx=(24, 18), pady=18)
        textes = ctk.CTkFrame(carte, fg_color="transparent")
        textes.pack(side="left", fill="x", expand=True)
        if not total:
            titre, detail = t("Aucun identifiant"), t("Ajoutez un compte pour voir son bilan.")
        elif not b["a_probleme"]:
            titre = t("Tout est en ordre")
            detail = t("Aucun mot de passe faible, réutilisé ou ancien.")
        else:
            titre = tn("{n} compte sur {total} à améliorer", "{n} comptes sur {total} à améliorer",
                       b["a_probleme"], total=total)
            detail = t("Cliquez sur « Changer », puis sur « Générer » pour un mot de passe solide.")
        ctk.CTkLabel(textes, text=titre, font=police(16, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(textes, text=detail, font=police(12), text_color=TEXTE_DOUX,
                     anchor="w").pack(fill="x", pady=(2, 0))
        compteurs = ctk.CTkFrame(carte, fg_color="transparent")
        compteurs.pack(side="right", padx=20)
        compteurs_affiches = [("faibles", t("Faibles")), ("reutilises", t("Réutilisés")),
                              ("anciens", t("Anciens"))]
        if verifie:
            compteurs_affiches.insert(0, ("pirates", t("Piratés")))
        for cle, nom in compteurs_affiches:
            bloc = ctk.CTkFrame(compteurs, fg_color="transparent")
            bloc.pack(side="left", padx=10)
            n = len(b[cle])
            ctk.CTkLabel(bloc, text=str(n), font=police(22, gras=True),
                         text_color=DANGER if n else TEXTE_DOUX).pack()
            ctk.CTkLabel(bloc, text=nom, font=police(11), text_color=TEXTE_DOUX).pack()

    def _ligne(self, parent, e, raison):
        ligne = ctk.CTkFrame(parent, fg_color="transparent")
        ligne.pack(fill="x", pady=3)
        Pastille(ligne, e["site"]).pack(side="left", padx=(0, 12))
        textes = ctk.CTkFrame(ligne, fg_color="transparent")
        textes.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(textes, text=e["site"], font=police(14, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x")
        details = "  ·  ".join(v for v in (e["utilisateur"], raison) if v)
        ctk.CTkLabel(textes, text=details, font=police(12), text_color=TEXTE_DOUX,
                     anchor="w").pack(fill="x")
        BoutonAnime(ligne, t("Changer"), lambda: FenetreEntree(self.ecran, e), width=96, height=32,
                    taille_police=12).pack(side="right")


class SectionMotDePasse(ctk.CTkFrame):
    """Changer le mot de passe maître : l'actuel est redemandé, pour qu'une personne
    devant l'ordinateur resté ouvert ne puisse pas le remplacer."""

    def __init__(self, parent, ecran: EcranPrincipal):
        super().__init__(parent, fg_color=CARTE, corner_radius=12, border_width=1,
                         border_color=BORDURE)
        self.ecran = ecran
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(anchor="w", padx=20, pady=18)
        ctk.CTkLabel(corps, text=t("Mot de passe maître"), font=police(15, gras=True),
                     text_color=TEXTE, anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text=t("Le coffre et ses copies automatiques seront rechiffrés : "
                                   "l'ancien mot de passe n'ouvrira plus rien. Les fichiers "
                                   "exportés gardent leur propre mot de passe d'export."),
                     font=police(12), text_color=TEXTE_DOUX, anchor="w", justify="left",
                     wraplength=340).pack(fill="x", pady=(4, 14))
        self.actuel = champ(corps, t("Mot de passe actuel"), masque=True, width=340)
        self.actuel.pack(pady=(0, 12))
        self.nouveau = champ(corps, t("Nouveau mot de passe"), masque=True, width=340)
        self.nouveau.pack()
        self.jauge = JaugeForce(corps)
        self.jauge.pack(fill="x", pady=(4, 8))
        self.nouveau.bind("<KeyRelease>", lambda _e: self.jauge.maj(self.nouveau.get()))
        self.confirmation = champ(corps, t("Confirmer le nouveau mot de passe"), masque=True,
                                  width=340)
        self.confirmation.pack()
        self.case_fuites = case_fuites(corps)
        self.case_fuites.pack(anchor="w", pady=(8, 0))
        self.confirmation.bind("<Return>", lambda _e: self._valider())
        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=DANGER,
                                    wraplength=340)
        self.message.pack(pady=(6, 0))
        self.bouton = BoutonAnime(corps, t("Changer le mot de passe"), self._valider,
                                  style="principal", width=200)
        self.bouton.pack(anchor="e", pady=(4, 0))

    def _valider(self):
        actuel, nouveau = self.actuel.get(), self.nouveau.get()
        if not actuel:
            self.message.configure(text=t("Entrez votre mot de passe actuel."))
            return
        problemes = verifier_force(nouveau)
        if problemes:
            self.message.configure(text=t("Il manque : {liste}.", liste=", ".join(problemes)))
            return
        if nouveau != self.confirmation.get():
            self.message.configure(text=t("Les deux nouveaux mots de passe ne correspondent pas."))
            return
        if nouveau == actuel:
            self.message.configure(text=t("Le nouveau mot de passe doit être différent de l'actuel."))
            return
        self.bouton.activer(False, t("Patientez…"))
        self.message.configure(text="")
        app = self.ecran.app
        verifier = bool(self.case_fuites.get())

        def fond():
            try:
                erreur = probleme_fuite(nouveau) if verifier else None
                if erreur is None:
                    app.coffre.changer_mot_de_passe(nouveau, actuel=actuel)
            except MotDePasseIncorrect:
                erreur = t("Mot de passe actuel incorrect.")
            except (OSError, RuntimeError) as e:
                erreur = t("Changement impossible : {erreur}", erreur=e)
            app.after(0, lambda: self._resultat(erreur))

        threading.Thread(target=fond, daemon=True).start()

    def _resultat(self, erreur):
        app = self.ecran.app
        # Le coffre a pu être verrouillé pendant l'opération : on ne le laisse pas ouvert.
        if app.ecran is not self.ecran:
            app.coffre.verrouiller()
            return
        if not self.winfo_exists():
            return
        self.bouton.activer(True, t("Changer le mot de passe"))
        self.actuel.delete(0, "end")
        if erreur:
            self.message.configure(text=erreur)
            self.actuel.focus_set()
            return
        self.nouveau.delete(0, "end")
        self.confirmation.delete(0, "end")
        self.jauge.maj("")
        self.ecran.notifier(t("Mot de passe maître changé"))

class SectionAccesRapide(ctk.CTkFrame):
    """Code PIN à 4 chiffres pour le remplissage rapide et l'extension de navigateur."""

    def __init__(self, parent, ecran: EcranPrincipal):
        super().__init__(parent, fg_color=CARTE, corner_radius=12, border_width=1,
                         border_color=BORDURE)
        self.ecran = ecran
        app = ecran.app
        self.defini = bool(app.reglages.get("pin"))
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(anchor="w", padx=20, pady=18)
        ctk.CTkLabel(corps, text=t("Accès rapide (code PIN)"), font=police(15, gras=True),
                     text_color=TEXTE, anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text=t("Un code à 4 chiffres pour copier un identifiant avec le "
                                   "remplissage rapide ou l'extension de navigateur, sans "
                                   "redonner le mot de passe maître."),
                     font=police(12), text_color=TEXTE_DOUX, anchor="w", justify="left",
                     wraplength=440).pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(corps, text=t("Il ne marche que si SecretLin a été déverrouillé avec le mot "
                                   "de passe maître depuis moins de 8 heures et n'a pas été "
                                   "quitté. Après 3 codes faux, le mot de passe maître est "
                                   "redemandé. Avec un code, la croix de la fenêtre laisse "
                                   "SecretLin ouvert en arrière-plan."),
                     font=police(11), text_color=TEXTE_DOUX, anchor="w", justify="left",
                     wraplength=440).pack(fill="x", pady=(0, 10))
        if self.defini:
            ctk.CTkLabel(corps, text="✓  " + t("Code PIN défini."), font=police(12, gras=True),
                         text_color=SUCCES, anchor="w").pack(fill="x", pady=(0, 8))
        ligne = ctk.CTkFrame(corps, fg_color="transparent")
        ligne.pack(anchor="w")
        self.pin = champ(ligne, t("Nouveau code (4 chiffres)"), masque=True, width=166)
        self.pin.pack(side="left", padx=(0, 8))
        self.confirmation = champ(ligne, t("Confirmer le code"), masque=True, width=166)
        self.confirmation.pack(side="left")
        self.maitre = champ(corps, t("Mot de passe maître actuel"), masque=True, width=340)
        self.maitre.pack(anchor="w", pady=(10, 0))
        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=DANGER,
                                    wraplength=440)
        self.message.pack(pady=(6, 0))
        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(anchor="w", pady=(4, 0))
        self.boutons = [BoutonAnime(boutons, t("Changer le code") if self.defini
                                    else t("Définir le code"), self._definir,
                                    style="principal", width=160)]
        if self.defini:
            self.boutons.append(BoutonAnime(boutons, t("Retirer le code"), self._retirer,
                                            style="danger", width=150))
        for b in self.boutons:
            b.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(corps, text=t("Raccourci clavier du remplissage rapide : Ctrl+Alt+P"),
                     font=police(13, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x", pady=(18, 2))
        ctk.CTkLabel(corps, text=t("Sur un autre bureau, créez un raccourci qui lance : {cmd}",
                                   cmd=raccourci.commande()),
                     font=police(11), text_color=TEXTE_DOUX, anchor="w", justify="left",
                     wraplength=440).pack(fill="x")
        self.message_raccourci = ctk.CTkLabel(corps, text="", font=police(12),
                                              text_color=SUCCES, wraplength=440)
        BoutonAnime(corps, t("Installer le raccourci"), self._raccourci,
                    width=180).pack(anchor="w", pady=(8, 0))
        self.message_raccourci.pack(anchor="w", pady=(6, 0))

    def _raccourci(self):
        if raccourci.installer():
            self.message_raccourci.configure(text="✓  " + t("Raccourci installé : Ctrl+Alt+P."),
                                             text_color=SUCCES)
        else:
            self.message_raccourci.configure(
                text=t("Bureau non reconnu : créez le raccourci vous-même dans les réglages "
                       "du clavier."), text_color=DANGER)

    def _definir(self):
        code, confirmation = self.pin.get(), self.confirmation.get()
        if not acces_rapide.pin_valide(code):
            self.message.configure(text=t("Le code doit faire exactement 4 chiffres."))
            return
        if code != confirmation:
            self.message.configure(text=t("Les deux codes ne correspondent pas."))
            return
        self._lancer(acces_rapide.nouveau_pin(code))

    def _retirer(self):
        self._lancer(None)

    def _lancer(self, nouveau):
        maitre = self.maitre.get()
        if not maitre:
            self.message.configure(text=t("Entrez votre mot de passe actuel."))
            return
        app = self.ecran.app
        for b in self.boutons:
            b.activer(False)
        self.message.configure(text=t("Patientez…"), text_color=TEXTE_DOUX)

        def fond():
            juste = app.coffre.verifier_mot_de_passe(maitre)
            app.after(0, lambda: self._resultat(juste, nouveau))

        threading.Thread(target=fond, daemon=True).start()

    def _resultat(self, juste, nouveau):
        app = self.ecran.app
        if app.ecran is not self.ecran or not self.winfo_exists():
            return
        if not juste:
            for b in self.boutons:
                b.activer(True)
            self.maitre.delete(0, "end")
            self.message.configure(text=t("Mot de passe actuel incorrect."), text_color=DANGER)
            return
        app.enregistrer_reglages(pin=nouveau)
        app.acces.demarrer()
        ancienne = self.ecran._pages_pretes.pop(PageSecurite, None)
        if ancienne is not None:
            ancienne.destroy()
        self.ecran.notifier(t("Code PIN enregistré") if nouveau else t("Code PIN retiré"))
        self.ecran.page_precedente()
        self.ecran.ouvrir_page(PageSecurite)


class SectionFichierCle(ctk.CTkFrame):
    """Fichier-clé : un deuxième facteur pour ouvrir le coffre, en plus du mot de passe."""

    def __init__(self, parent, ecran: EcranPrincipal):
        super().__init__(parent, fg_color=CARTE, corner_radius=12, border_width=1,
                         border_color=BORDURE)
        self.ecran = ecran
        app = ecran.app
        self.actif = app.coffre.besoin_fichier_cle()
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(anchor="w", padx=20, pady=18)
        ctk.CTkLabel(corps, text=t("Fichier-clé (deuxième facteur)"), font=police(15, gras=True),
                     text_color=TEXTE, anchor="w").pack(fill="x")
        if self.actif:
            nom = Path(app.reglages["fichier_cle"]).name or "?"
            texte = t("Activé : le coffre s'ouvre avec le mot de passe maître et le fichier "
                      "« {nom} ».", nom=nom)
        else:
            texte = t("En plus du mot de passe maître, le coffre ne s'ouvrira qu'avec ce fichier, "
                      "par exemple rangé sur une clé USB.")
        ctk.CTkLabel(corps, text=texte, font=police(12), text_color=TEXTE_DOUX, anchor="w",
                     justify="left", wraplength=420).pack(fill="x", pady=(4, 4))
        ctk.CTkLabel(corps, text=t("⚠  Si vous perdez ce fichier, le coffre ne pourra plus jamais "
                                   "être ouvert : gardez-en une copie en lieu sûr."),
                     font=police(12), text_color="#f0883e", anchor="w", justify="left",
                     wraplength=420).pack(fill="x", pady=(0, 12))
        self.actuel = champ(corps, t("Mot de passe maître actuel"), masque=True, width=340)
        self.actuel.pack(anchor="w")
        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=DANGER,
                                    wraplength=420)
        self.message.pack(pady=(6, 0))
        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(anchor="w", pady=(4, 0))
        self.boutons = []
        if self.actif:
            self.boutons.append(BoutonAnime(boutons, t("Retirer le fichier-clé"), self._retirer,
                                            style="danger", width=180))
        else:
            self.boutons.append(BoutonAnime(boutons, t("Créer un fichier-clé…"), self._creer,
                                            style="principal", width=180))
            self.boutons.append(BoutonAnime(boutons, t("Utiliser un fichier existant…"),
                                            self._existant, width=200))
        for b in self.boutons:
            b.pack(side="left", padx=(0, 8))

    def _mot_de_passe(self):
        actuel = self.actuel.get()
        if not actuel:
            self.message.configure(text=t("Entrez votre mot de passe actuel."))
        return actuel

    def _creer(self):
        if not (actuel := self._mot_de_passe()):
            return
        chemin = filedialog.asksaveasfilename(parent=self, title=t("Enregistrer le fichier-clé"),
                                              initialfile="secretlin.cle")
        if chemin:
            self._lancer(actuel, chemin, nouveau=True)

    def _existant(self):
        if not (actuel := self._mot_de_passe()):
            return
        chemin = filedialog.askopenfilename(parent=self, title=t("Choisir le fichier-clé"))
        if chemin:
            self._lancer(actuel, chemin, nouveau=False)

    def _retirer(self):
        if actuel := self._mot_de_passe():
            self._lancer(actuel, "", nouveau=False)

    def _lancer(self, actuel, chemin, nouveau):
        """Vérifie le mot de passe puis active (chemin donné) ou retire le fichier-clé, en
        arrière-plan : Argon2id prend du temps."""
        app = self.ecran.app
        for b in self.boutons:
            b.activer(False)
        self.message.configure(text=t("Patientez…"), text_color=TEXTE_DOUX)

        def fond():
            try:
                if not app.coffre.verifier_mot_de_passe(actuel):
                    raise MotDePasseIncorrect()
                if not chemin:
                    app.coffre.retirer_fichier_cle(actuel)
                else:
                    contenu = (app.coffre.creer_fichier_cle(Path(chemin)) if nouveau
                               else app.coffre.lire_fichier_cle(Path(chemin)))
                    app.coffre.activer_fichier_cle(contenu, actuel)
                erreur = None
            except MotDePasseIncorrect:
                erreur = t("Mot de passe actuel incorrect.")
            except (OSError, RuntimeError, ValueError) as e:
                erreur = t("Opération impossible : {erreur}", erreur=e)
            app.after(0, lambda: self._resultat(erreur, chemin))

        threading.Thread(target=fond, daemon=True).start()

    def _resultat(self, erreur, chemin):
        app = self.ecran.app
        if app.ecran is not self.ecran:
            app.coffre.verrouiller()
            return
        if not self.winfo_exists():
            return
        if erreur:
            for b in self.boutons:
                b.activer(True)
            self.actuel.delete(0, "end")
            self.message.configure(text=erreur, text_color=DANGER)
            return
        app.enregistrer_reglages(fichier_cle=chemin)
        # La page préparée d'avance montrerait l'ancien état.
        ancienne = self.ecran._pages_pretes.pop(PageSecurite, None)
        if ancienne is not None:
            ancienne.destroy()
        self.ecran.notifier(t("Fichier-clé activé") if chemin else t("Fichier-clé retiré"))
        # La page est redessinée pour montrer le nouvel état.
        self.ecran.page_precedente()
        self.ecran.ouvrir_page(PageSecurite)


def main():
    import sys
    if "--remplissage" in sys.argv[1:]:
        from gestionnaire import remplissage
        remplissage.main()
        return
    # Déjà ouvert (peut-être caché en arrière-plan) : on montre la fenêtre existante.
    if porte.demander({"action": "montrer"}, delai=2) is not None:
        return
    Application().mainloop()


if __name__ == "__main__":
    main()
