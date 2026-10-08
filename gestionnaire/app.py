"""Interface graphique du gestionnaire de mots de passe."""

import datetime
import math
import threading
import time
import tkinter
import tkinter.font
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import ImageTk

from gestionnaire.coffre import (
    ATTENTE_MAX, Coffre, CoffreCorrompu, MotDePasseIncorrect, evaluer_force,
    generer_mot_de_passe, verifier_force,
)
from gestionnaire.logo import dessiner as dessiner_logo
from gestionnaire.marques import style_pastille
from gestionnaire.effets import adoucir, animer, definir, lineaire, melanger, rebond, survol, transition

# Palette sobre gris / noir
FOND = "#0b0b0d"
PANNEAU = "#141417"
CARTE = "#1a1a1e"
CARTE_SURVOL = "#26262b"
BORDURE = "#2a2a30"
BORDURE_ECLAT = "#70707a"
TEXTE = "#ececef"
TEXTE_DOUX = "#8e8e98"
TEXTE_ETEINT = "#3a3a42"
ACCENT = "#e4e4e7"
BLANC = "#ffffff"
DANGER = "#e5484d"
SUCCES = "#46a758"
BLEU = "#2f6fed"
COULEURS_FORCE = [BORDURE, "#e5484d", "#f0883e", "#d4c34a", "#46a758"]
LIBELLES_FORCE = ["", "Faible", "Moyen", "Fort", "Très fort"]

STYLES = {
    "principal": dict(fond=ACCENT, fond_survol=BLANC, texte=FOND, bord=ACCENT,
                      bord_survol=BLANC, halo="#4a4a53", eclat=BLANC),
    "secondaire": dict(fond="#202025", fond_survol="#2c2c32", texte=TEXTE, bord=BORDURE,
                       bord_survol="#5c5c66", halo="#303037", eclat="#55555f"),
    "danger": dict(fond="#1d1315", fond_survol="#3a1a1d", texte=DANGER, bord="#5a2a2d",
                   bord_survol=DANGER, halo="#3a1c1f", eclat="#7a2a2e"),
}

DELAI_SOURIS_IMMOBILE_S = 30  # souris sur la fenêtre mais sans bouger
DELAI_SOURIS_DEHORS_S = 15  # souris hors de la fenêtre
EFFACEMENT_PRESSE_PAPIER_S = 20

_famille = None


def police(taille=13, gras=False):
    global _famille
    if _famille is None:
        dispo = set(tkinter.font.families())
        _famille = next((f for f in ("Inter", "Segoe UI", "Roboto", "Cantarell", "DejaVu Sans")
                         if f in dispo), "TkDefaultFont")
    return ctk.CTkFont(family=_famille, size=taille, weight="bold" if gras else "normal")


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

class BoutonAnime(ctk.CTkFrame):
    """Bouton qui grossit au survol, s'entoure d'un halo et lance un éclat au clic."""

    MARGE = 7

    def __init__(self, parent, texte, commande, style="secondaire", width=120, height=38,
                 taille_police=13):
        self.s = STYLES[style]
        self.fond_parent = couleur_fond(parent)
        m = self.MARGE
        super().__init__(parent, width=width + 2 * m, height=height + 2 * m,
                         corner_radius=12, fg_color=self.fond_parent)
        self.commande = commande
        self.largeur, self.hauteur = width, height
        self.actif = True
        self.survole = False
        self._dernier_clic = 0.0

        self.btn = ctk.CTkButton(
            self, text=texte, command=self._clic, width=width, height=height, corner_radius=9,
            hover=False, border_width=1, fg_color=self.s["fond"], border_color=self.s["bord"],
            text_color=self.s["texte"], font=police(taille_police, gras=style == "principal"),
        )
        self.btn.place(relx=0.5, rely=0.5, anchor="center")
        definir(self.btn, "fond", self.s["fond"])
        definir(self.btn, "bord", self.s["bord"])
        definir(self.btn, "zoom", 0.0)
        definir(self, "halo", self.fond_parent)
        survol(self.btn, self._entrer, self._sortir)
        self.btn.bind("<ButtonPress-1>", self._appui)

    def _zoom(self, v):
        self.btn.configure(width=round(self.largeur + 8 * v), height=round(self.hauteur + 6 * v))

    def _vers(self, survole, duree=0.2):
        s = self.s
        transition(self.btn, "fond", s["fond_survol"] if survole else s["fond"], duree,
                   lambda c: self.btn.configure(fg_color=c))
        transition(self.btn, "bord", s["bord_survol"] if survole else s["bord"], duree,
                   lambda c: self.btn.configure(border_color=c))
        transition(self, "halo", s["halo"] if survole else self.fond_parent, duree + 0.1,
                   lambda c: self.configure(fg_color=c))
        transition(self.btn, "zoom", 1.0 if survole else 0.0, duree + 0.12, self._zoom,
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
            transition(self.btn, "zoom", -0.6, 0.08, self._zoom)

    def _clic(self):
        maintenant = time.monotonic()
        if not self.actif or maintenant - self._dernier_clic < 0.35:
            return
        self._dernier_clic = maintenant
        # Éclat : le bouton et son halo s'illuminent puis reviennent doucement.
        definir(self.btn, "fond", self.s["eclat"])
        definir(self.btn, "bord", BLANC)
        definir(self, "halo", BLANC)
        self.btn.configure(fg_color=self.s["eclat"], border_color=BLANC)
        self.configure(fg_color=BLANC)
        self._vers(self.survole, duree=0.5)
        if self.commande:
            self.after(70, self.commande)

    def activer(self, actif, texte=None):
        self.actif = actif
        self.btn.configure(state="normal" if actif else "disabled")
        if texte:
            self.btn.configure(text=texte)
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
        cible = BORDURE_ECLAT if etat["focus"] else "#44444d" if etat["survol"] else BORDURE
        transition(e, "bord", cible, 0.22, lambda c: e.configure(border_color=c))

    def regler(cle, v):
        etat[cle] = v
        maj()

    e.bind("<FocusIn>", lambda _e: regler("focus", True))
    e.bind("<FocusOut>", lambda _e: regler("focus", False))
    survol(e, lambda: regler("survol", True), lambda: regler("survol", False))
    return e


def eclat_champ(e):
    definir(e, "bord", BLANC)
    e.configure(border_color=BLANC)
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
        self.libelle.configure(text=LIBELLES_FORCE[n], text_color=COULEURS_FORCE[n] if n else TEXTE_DOUX)


# --- Application ------------------------------------------------------------

class Application(ctk.CTk):
    def __init__(self):
        super().__init__(className="SecretLin")
        ctk.set_appearance_mode("dark")
        self.title("SecretLin")
        self._icone = ImageTk.PhotoImage(dessiner_logo(128))
        self.iconphoto(True, self._icone)
        self.geometry("1040x720")
        self.minsize(800, 640)
        self.configure(fg_color=FOND)

        self.coffre = Coffre()
        self.ecran = None
        self.derniere_activite = time.monotonic()
        self.dehors_depuis = None
        self._position_souris = None
        # Le compteur d'échecs est relu au lancement : fermer puis relancer SecretLin
        # ne remet pas l'attente à zéro.
        self.echecs, bloque = self.coffre.lire_echecs()
        self.bloque_jusqua = time.monotonic() + max(0.0, bloque - time.time())
        self._jeton_presse_papier = None

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
            self.ecran.recherche.focus_set()

    # --- Navigation -------------------------------------------------------

    def _changer_ecran(self, ecran):
        if self.ecran is not None:
            self.ecran.destroy()
        self.ecran = ecran
        ecran.pack(fill="both", expand=True)

    def afficher_connexion(self):
        if self.coffre.existe():
            self._changer_ecran(EcranDeverrouillage(self))
        else:
            self._changer_ecran(EcranCreation(self))

    def afficher_principal(self):
        self._activite()
        self._changer_ecran(EcranPrincipal(self))

    def noter_echecs(self, delai):
        """Enregistre le compteur d'échecs et l'attente en cours (« delai » secondes)."""
        try:
            self.coffre.noter_echecs(self.echecs, time.time() + delai if delai else 0.0)
        except OSError:
            pass  # un disque plein ne doit pas bloquer l'écran de déverrouillage

    def verrouiller(self):
        for fenetre in self.winfo_children():
            if isinstance(fenetre, ctk.CTkToplevel):
                fenetre.destroy()
        self.coffre.verrouiller()
        self.vider_presse_papier()
        self.afficher_connexion()

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
                total, raison = DELAI_SOURIS_DEHORS_S, "Souris hors de la fenêtre"
                depuis = max(self.dehors_depuis, self.derniere_activite)
            else:
                total, raison = DELAI_SOURIS_IMMOBILE_S, "Souris immobile"
                depuis = self.derniere_activite
            restant = total - (maintenant - depuis)
            if restant <= 0:
                self.verrouiller()
            else:
                self.ecran.maj_minuterie(restant, total, raison)
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
        self.vider_presse_papier()
        self.coffre.verrouiller()
        self.destroy()


# --- Écrans de connexion ----------------------------------------------------

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

        ctk.CTkLabel(self, text="SecretLin  ·  AES-256-GCM  ·  Argon2id  ·  Données stockées uniquement sur cet ordinateur",
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
        super().__init__(app, "Bienvenue sur SecretLin",
                         "Choisissez un mot de passe maître. C'est le seul que vous "
                         "aurez à retenir : sans lui, personne — pas même vous — "
                         "ne pourra ouvrir le coffre.")
        self.mdp = champ(self.interieur, "Mot de passe maître", masque=True, width=340)
        self.mdp.pack(pady=(0, 8))
        self.jauge = JaugeForce(self.interieur)
        self.jauge.pack(fill="x", pady=(0, 12))
        self.mdp.bind("<KeyRelease>", lambda _e: self.jauge.maj(self.mdp.get()))
        self.confirmation = champ(self.interieur, "Confirmer le mot de passe", masque=True, width=340)
        self.confirmation.pack(pady=(0, 4))
        self.message.pack(pady=(6, 6))
        self.bouton = BoutonAnime(self.interieur, "Créer le coffre", self._creer, style="principal",
                                  width=340, height=44)
        self.bouton.pack()
        self.confirmation.bind("<Return>", lambda _e: self._creer())
        self.mdp.focus_set()

    def _creer(self):
        mdp, conf = self.mdp.get(), self.confirmation.get()
        problemes = verifier_force(mdp)
        if problemes:
            self.afficher_message("Il manque : " + ", ".join(problemes) + ".")
            self.secouer()
            return
        if mdp != conf:
            self.afficher_message("Les deux mots de passe ne correspondent pas.")
            self.secouer()
            return
        self.bouton.activer(False, "Création…")
        self.afficher_message("")

        def travail():
            self.app.coffre.creer(mdp)
            self.app.after(0, lambda: self.logo.ouvrir(self.app.afficher_principal))

        threading.Thread(target=travail, daemon=True).start()


class EcranDeverrouillage(EcranCentre):
    def __init__(self, app):
        super().__init__(app, "Coffre verrouillé", "Entrez votre mot de passe maître.")
        self.mdp = champ(self.interieur, "Mot de passe maître", masque=True, width=340)
        self.mdp.pack(pady=(0, 4))
        self.message.pack(pady=(6, 6))
        self.bouton = BoutonAnime(self.interieur, "Déverrouiller", self._ouvrir, style="principal",
                                  width=340, height=44)
        self.bouton.pack()
        self.mdp.bind("<Return>", lambda _e: self._ouvrir())
        self.mdp.focus_set()

    def _ouvrir(self):
        attente = self.app.bloque_jusqua - time.monotonic()
        if attente > 0:
            self.afficher_message(f"Trop d'essais. Réessayez dans {int(attente) + 1} s.")
            self.secouer()
            return
        mdp = self.mdp.get()
        if not mdp:
            self.secouer()
            return
        self.bouton.activer(False, "Vérification…")
        self.afficher_message("")

        def travail():
            try:
                self.app.coffre.ouvrir(mdp)
                resultat = None
            except MotDePasseIncorrect:
                resultat = "incorrect"
            except CoffreCorrompu:
                resultat = "corrompu"
            self.app.after(0, lambda: self._resultat(resultat))

        threading.Thread(target=travail, daemon=True).start()

    def _resultat(self, resultat):
        if resultat is None:
            self.app.echecs = 0
            self.app.noter_echecs(0)
            self.afficher_message("Déverrouillé", SUCCES)
            self.logo.ouvrir(lambda: self.after(150, self.app.afficher_principal))
            return
        self.bouton.activer(True, "Déverrouiller")
        self.mdp.delete(0, "end")
        self.secouer()
        if resultat == "corrompu":
            self.afficher_message("Le fichier du coffre est illisible ou endommagé.")
            return
        self.app.echecs += 1
        # Délai croissant après plusieurs erreurs : 2, 4, 8… jusqu'à 5 minutes.
        if self.app.echecs >= 3:
            delai = min(2 ** (self.app.echecs - 2), ATTENTE_MAX)
            self.app.bloque_jusqua = time.monotonic() + delai
            self.app.noter_echecs(delai)
            self.afficher_message(f"Mot de passe incorrect. Patientez {delai} s.")
        else:
            self.app.noter_echecs(0)
            self.afficher_message("Mot de passe incorrect.")


# --- Écran principal --------------------------------------------------------

class IndexAlphabet(ctk.CTkFrame):
    """Colonne A–Z : un clic fait défiler la liste jusqu'à la lettre."""

    LETTRES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ#"

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
        self.presentes = presentes
        for lettre, (lab, _f) in self.lettres.items():
            transition(lab, "couleur", self._couleur_repos(lettre), 0.3,
                       lambda c, lab=lab: lab.configure(text_color=c))

    def _survol(self, lettre, dedans):
        if lettre not in self.presentes:
            return
        lab, f = self.lettres[lettre]
        transition(lab, "couleur", BLANC if dedans else self._couleur_repos(lettre), 0.18,
                   lambda c: lab.configure(text_color=c))
        transition(lab, "taille", 15.0 if dedans else 11.0, 0.22,
                   lambda v: f.configure(size=round(v)), courbe=rebond if dedans else adoucir)

    def _clic(self, lettre):
        if lettre in self.presentes:
            self.aller_a(lettre)


class Pastille(ctk.CTkLabel):
    """Carré à gauche d'un identifiant : logo de la marque reconnue, sinon l'initiale."""

    def __init__(self, parent, site, taille=42):
        super().__init__(parent, text="", width=taille, height=taille, corner_radius=10,
                         font=police(16, gras=True))
        self.survole = False
        self.changer_site(site)

    def changer_site(self, site):
        self.style = style_pastille(site, CARTE_SURVOL, ACCENT, TEXTE, FOND)
        st = self.style
        fond = st["fond_survol"] if self.survole else st["fond"]
        texte = st["texte_survol"] if self.survole else st["texte"]
        definir(self, "fond", fond)
        definir(self, "texte", texte)
        self.configure(fg_color=fond, text_color=texte,
                       image=st["image_survol"] if self.survole else st["image"],
                       text="" if st["image"] else (site.strip()[:1].upper() or "?"))

    def survol(self, survole):
        self.survole = survole
        st = self.style
        transition(self, "fond", st["fond_survol"] if survole else st["fond"], 0.25,
                   lambda c: self.configure(fg_color=c))
        transition(self, "texte", st["texte_survol"] if survole else st["texte"], 0.25,
                   lambda c: self.configure(text_color=c))
        if st["image"]:
            self.configure(image=st["image_survol"] if survole else st["image"])


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

        self.pastille = Pastille(self, e["site"])
        self.pastille.pack(side="left", padx=(14, 14), pady=12)

        textes = ctk.CTkFrame(self, fg_color="transparent")
        textes.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(textes, text=e["site"], font=police(15, gras=True), text_color=TEXTE,
                     anchor="w").pack(fill="x")
        details = "  ·  ".join(v for v in (e["utilisateur"], e.get("email", "")) if v) or "—"
        ctk.CTkLabel(textes, text=details, font=police(12), text_color=TEXTE_DOUX,
                     anchor="w").pack(fill="x")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(side="right", padx=8)
        BoutonAnime(actions, "Modifier", lambda: FenetreEntree(ecran, e),
                    width=88, height=32, taille_police=12).pack(side="right", padx=(10, 0))
        for texte, cle, largeur, message in (
            ("Mot de passe", "mot_de_passe", 112, "Mot de passe copié — effacé dans 20 s"),
            ("E-mail", "email", 76, "E-mail copié"),
            ("Utilisateur", "utilisateur", 98, "Nom d'utilisateur copié"),
        ):
            b = BoutonAnime(actions, texte, lambda c=cle, m=message: ecran.copier(e[c], m),
                            width=largeur, height=32, taille_police=12)
            b.pack(side="right")
            if not e.get(cle):
                b.activer(False)
        ctk.CTkLabel(actions, text="Copier", font=police(11), text_color=TEXTE_DOUX).pack(
            side="right", padx=(0, 4))

        survol(self, lambda: self._etat(True), lambda: self._etat(False))
        for w in (self, textes, self.pastille):
            tkinter.Misc.bind(w, "<Double-Button-1>", lambda _e: FenetreEntree(ecran, e), "+")

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
        ctk.CTkLabel(titres, text="Chiffré de bout en bout  ·  AES-256", font=police(11),
                     text_color=TEXTE_DOUX, anchor="w").pack(fill="x")

        BoutonAnime(entete, "Verrouiller", app.verrouiller, width=112).pack(side="right", padx=(0, 16))
        BoutonAnime(entete, "+  Ajouter", lambda: FenetreEntree(self), style="principal",
                    width=124).pack(side="right")

        statut = ctk.CTkFrame(entete, fg_color="transparent")
        statut.pack(side="right", padx=18)
        ctk.CTkLabel(statut, text="●  Déverrouillé", font=police(11, gras=True), text_color=SUCCES,
                     fg_color="#122016", corner_radius=11, height=24).pack(anchor="e", ipadx=8)
        self.minuterie = ctk.CTkLabel(statut, text="", font=police(10), text_color=TEXTE_DOUX,
                                      anchor="e", width=230)
        self.minuterie.pack(anchor="e", pady=(2, 1))
        self.barre_temps = ctk.CTkProgressBar(statut, width=230, height=4, corner_radius=2,
                                              fg_color=BORDURE, progress_color=SUCCES)
        self.barre_temps.pack(anchor="e")
        ctk.CTkFrame(self, fg_color=BORDURE, height=1, corner_radius=0).pack(fill="x")

        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(fill="both", expand=True, padx=(18, 18), pady=18)

        self.index = IndexAlphabet(corps, self.aller_a)
        self.index.pack(side="left", fill="y", padx=(0, 14))

        contenu = ctk.CTkFrame(corps, fg_color="transparent")
        contenu.pack(side="left", fill="both", expand=True)

        barre = ctk.CTkFrame(contenu, fg_color="transparent")
        barre.pack(fill="x", padx=10, pady=(0, 6))
        self.recherche = champ(barre, "Rechercher un site ou un identifiant…   (Ctrl+F)")
        self.recherche.pack(side="left", fill="x", expand=True)
        self.recherche.bind("<KeyRelease>", lambda _e: self.rafraichir(animer_entree=False))
        self.compteur = ctk.CTkLabel(barre, text="", font=police(12), text_color=TEXTE_DOUX)
        BoutonAnime(barre, "Sauvegarde", lambda: FenetreSauvegarde(self), width=112).pack(side="right")
        self.compteur.pack(side="right", padx=(14, 0))

        self.liste = ctk.CTkScrollableFrame(contenu, fg_color="transparent",
                                            scrollbar_button_color=BORDURE,
                                            scrollbar_button_hover_color=BORDURE_ECLAT)
        self.liste.pack(fill="both", expand=True)

        # Notification qui glisse depuis le bas
        self.toast = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=12)
        self.toast_texte = ctk.CTkLabel(self.toast, text="", text_color=FOND, font=police(12, gras=True))
        self.toast_texte.pack(padx=18, pady=9)
        definir(self.toast, "y", 1.12)
        self._jeton_toast = None

        self._texte_minuterie = None
        self.maj_minuterie(DELAI_SOURIS_IMMOBILE_S, DELAI_SOURIS_IMMOBILE_S, "Souris immobile")
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
        texte = f"{raison} · verrouillage {math.ceil(restant)} s"
        if texte != self._texte_minuterie:
            self._texte_minuterie = texte
            self.minuterie.configure(text=texte, text_color=TEXTE_DOUX if part > 0.5 else couleur)

    def copier(self, texte, message):
        self.app.copier(texte)
        self.notifier(message)

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
        self.liste.update_idletasks()
        canvas = self.liste._parent_canvas
        total = max(self.liste.winfo_height(), 1)
        cible = cible_widget.winfo_y() / total
        debut = canvas.yview()[0]
        animer(canvas, "defilement", 0.45, lambda t: canvas.yview_moveto(debut + (cible - debut) * t))
        # La lettre de section clignote pour montrer où l'on est arrivé.
        lab = cible_widget.lettre
        definir(lab, "couleur", BLANC)
        lab.configure(text_color=BLANC)
        transition(lab, "couleur", TEXTE_DOUX, 1.2, lambda c: lab.configure(text_color=c))

    def rafraichir(self, animer_entree=False):
        for enfant in self.liste.winfo_children():
            enfant.destroy()
        self.entetes = {}
        filtre = self.recherche.get().strip().casefold()
        entrees = [e for e in self.app.coffre.entrees
                   if any(filtre in e.get(k, "").casefold() for k in ("site", "utilisateur", "email"))]
        total = len(self.app.coffre.entrees)
        self.compteur.configure(text=f"{len(entrees)} / {total}" if filtre else
                                f"{total} identifiant{'s' if total > 1 else ''}")

        if not entrees:
            vide = ctk.CTkFrame(self.liste, fg_color="transparent")
            vide.pack(pady=70)
            if not filtre:
                LogoAnime(vide, FOND).pack()
            texte = ("Aucun résultat." if filtre else
                     "Votre coffre est vide.\nCliquez sur « + Ajouter » pour enregistrer un premier compte.")
            ctk.CTkLabel(vide, text=texte, font=police(14), text_color=TEXTE_DOUX,
                         justify="center").pack(pady=(12, 0))
            self.index.maj(set())
            return

        cartes = []
        lettre_courante = None
        for e in entrees:
            initiale = e["site"][:1].upper()
            lettre = initiale if initiale.isalpha() and initiale in IndexAlphabet.LETTRES else "#"
            if lettre != lettre_courante:
                lettre_courante = lettre
                self.entetes[lettre] = self._entete_section(lettre)
            anime = animer_entree and len(cartes) < 25
            cartes.append(CarteIdentifiant(self, self.liste, e, marge_depart=70 if anime else None))
        self.index.maj(set(self.entetes))

        if animer_entree:
            for i, carte in enumerate(cartes[:25]):
                self.after(30 * i, carte.apparaitre)

    def _entete_section(self, lettre):
        ligne = ctk.CTkFrame(self.liste, fg_color="transparent")
        ligne.pack(fill="x", padx=14, pady=(16, 4))
        lab = ctk.CTkLabel(ligne, text=lettre, font=police(14, gras=True), text_color=TEXTE_DOUX,
                           width=20, anchor="w")
        lab.pack(side="left")
        definir(lab, "couleur", TEXTE_DOUX)
        ctk.CTkFrame(ligne, fg_color=BORDURE, height=1, corner_radius=0).pack(
            side="left", fill="x", expand=True, padx=(10, 0))
        ligne.lettre = lab
        return ligne


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
        super().__init__(ecran.app, "Modifier" if entree else "Ajouter un identifiant")
        self.ecran = ecran
        self.entree = entree

        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)

        ctk.CTkLabel(corps, text="Modifier l'identifiant" if entree else "Nouvel identifiant",
                     font=police(20, gras=True), text_color=TEXTE, anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text="Les données sont chiffrées dès l'enregistrement.", font=police(12),
                     text_color=TEXTE_DOUX, anchor="w").pack(fill="x", pady=(2, 12))

        def etiquette(texte):
            ctk.CTkLabel(corps, text=texte.upper(), font=police(10, gras=True), text_color=TEXTE_DOUX,
                         anchor="w").pack(fill="x", pady=(10, 4))

        etiquette("Site ou application")
        ligne_site = ctk.CTkFrame(corps, fg_color="transparent")
        ligne_site.pack(fill="x")
        self.apercu = Pastille(ligne_site, entree["site"] if entree else "")
        self.apercu.pack(side="left", padx=(0, 10))
        self.site = champ(ligne_site, "ex. Discord, Netflix, Steam…")
        self.site.pack(side="left", fill="x", expand=True)
        self.site.bind("<KeyRelease>", lambda _e: self.apercu.changer_site(self.site.get()))

        def ligne_avec_copie(placeholder, quoi):
            ligne = ctk.CTkFrame(corps, fg_color="transparent")
            ligne.pack(fill="x")
            entree_champ = champ(ligne, placeholder)
            entree_champ.pack(side="left", fill="x", expand=True)
            BoutonAnime(ligne, "Copier", lambda: self._copier(entree_champ.get(), quoi),
                        width=84, height=42, taille_police=12).pack(side="left")
            return entree_champ, ligne

        etiquette("Nom d'utilisateur")
        self.utilisateur, _ = ligne_avec_copie("ex. jeandupont75", "Nom d'utilisateur copié")

        etiquette("Adresse e-mail")
        self.email, _ = ligne_avec_copie("ex. jean.dupont@mail.com", "E-mail copié")

        etiquette("Mot de passe")
        ligne = ctk.CTkFrame(corps, fg_color="transparent")
        ligne.pack(fill="x")
        self.mdp = champ(ligne, "", masque=True)
        self.mdp.pack(side="left", fill="x", expand=True)
        self.bouton_voir = BoutonAnime(ligne, "Afficher", self._basculer, width=84, height=42,
                                       taille_police=12)
        self.bouton_voir.pack(side="left")
        BoutonAnime(ligne, "Générer", self._generer, width=84, height=42,
                    taille_police=12).pack(side="left")
        BoutonAnime(ligne, "Copier", lambda: self._copier(self.mdp.get(), "Mot de passe copié — effacé dans 20 s"),
                    width=84, height=42, taille_police=12).pack(side="left")
        self.jauge = JaugeForce(corps)
        self.jauge.pack(fill="x", pady=(4, 0))
        self.mdp.bind("<KeyRelease>", lambda _e: self.jauge.maj(self.mdp.get()))

        etiquette("Notes (facultatif)")
        self.notes = ctk.CTkTextbox(corps, width=520, height=60, fg_color=FOND, border_color=BORDURE,
                                    border_width=1, corner_radius=9, text_color=TEXTE, font=police(13))
        self.notes.pack()

        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=DANGER)
        self.message.pack(pady=(6, 0))

        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(fill="x", pady=(4, 0))
        BoutonAnime(boutons, "Enregistrer", self._enregistrer, style="principal",
                    width=130).pack(side="right")
        BoutonAnime(boutons, "Annuler", self.destroy, width=100).pack(side="right")
        if entree:
            BoutonAnime(boutons, "Supprimer", self._supprimer, style="danger",
                        width=104).pack(side="left")
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
            self.message.configure(text="Ce champ est vide.", text_color=DANGER)
            return
        self.ecran.app.copier(texte)
        self.message.configure(text=f"✓  {message}", text_color=SUCCES)

    def _basculer(self):
        visible = self.mdp.cget("show") == ""
        self.mdp.configure(show="•" if visible else "")
        self.bouton_voir.btn.configure(text="Afficher" if visible else "Masquer")

    def _generer(self):
        mdp = generer_mot_de_passe()
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
            self.message.configure(text="Indiquez le nom du site ou de l'application.",
                                   text_color=DANGER)
            return
        if not mdp:
            self.message.configure(text="Indiquez un mot de passe (ou cliquez sur « Générer »).",
                                   text_color=DANGER)
            return
        email = self.email.get().strip()
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            self.message.configure(text="L'adresse e-mail ne semble pas valide.", text_color=DANGER)
            return
        champs = dict(site=site, utilisateur=self.utilisateur.get(), email=email, mot_de_passe=mdp,
                      notes=self.notes.get("1.0", "end"))
        coffre = self.ecran.app.coffre
        if self.entree:
            coffre.modifier(self.entree["id"], **champs)
            self.ecran.notifier("Identifiant modifié")
        else:
            coffre.ajouter(**champs)
            self.ecran.notifier("Identifiant ajouté")
        self.ecran.rafraichir()
        self.destroy()

    def _supprimer(self):
        ConfirmationSuppression(self, self.entree["site"], self._confirmer_suppression)

    def _confirmer_suppression(self):
        self.ecran.app.coffre.supprimer(self.entree["id"])
        self.ecran.notifier("Identifiant supprimé")
        self.ecran.rafraichir()
        self.destroy()


class ConfirmationSuppression(Dialogue):
    def __init__(self, parent, nom, action):
        super().__init__(parent, "Confirmer")
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)
        ctk.CTkLabel(corps, text=f"Supprimer « {nom} » ?", font=police(17, gras=True),
                     text_color=TEXTE).pack(anchor="w")
        ctk.CTkLabel(corps, text="Cette action est définitive.", font=police(13),
                     text_color=TEXTE_DOUX).pack(anchor="w", pady=(4, 18))
        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(fill="x")

        def confirmer():
            self.destroy()
            action()

        BoutonAnime(boutons, "Supprimer", confirmer, style="danger", width=110).pack(side="right")
        BoutonAnime(boutons, "Annuler", self.destroy, width=100).pack(side="right")


class FenetreSauvegarde(Dialogue):
    """Export et import chiffrés, et restauration de la copie automatique du coffre."""

    EXTENSION = ".secretlin"
    TYPES = [("Export SecretLin", "*" + EXTENSION), ("Tous les fichiers", "*")]

    def __init__(self, ecran: EcranPrincipal):
        super().__init__(ecran.app, "Sauvegarde")
        self.ecran = ecran
        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(padx=30, pady=26)
        ctk.CTkLabel(corps, text="Sauvegarde du coffre", font=police(20, gras=True),
                     text_color=TEXTE, anchor="w").pack(fill="x")
        ctk.CTkLabel(corps, text="Les fichiers exportés restent chiffrés.", font=police(12),
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

        rangee("Exporter", "Enregistre tous vos identifiants dans un fichier chiffré "
               "avec un mot de passe d'export.", "Exporter…", self._exporter)
        rangee("Importer", "Ajoute les identifiants d'un fichier exporté. "
               "Les doublons sont ignorés.", "Importer…", self._importer)
        rangee("Restaurer", "Revient à une copie automatique : celle d'avant le dernier "
               "enregistrement, ou celle faite à l'un des derniers déverrouillages.",
               "Restaurer…", self._restaurer, actif=ecran.app.coffre.a_une_sauvegarde())

        BoutonAnime(corps, "Fermer", self.destroy, width=100).pack(anchor="e", pady=(10, 0))

    def _exporter(self):
        nom = f"secretlin-{datetime.date.today().isoformat()}{self.EXTENSION}"
        chemin = filedialog.asksaveasfilename(parent=self, title="Exporter le coffre",
                                              initialfile=nom, defaultextension=self.EXTENSION,
                                              filetypes=self.TYPES)
        if not chemin:
            return
        DialogueMotDePasse(
            self, "Mot de passe d'export",
            "Choisissez un mot de passe pour ce fichier. Il sera demandé à l'import.",
            nouveau=True, libelle="Exporter",
            travail=lambda mdp: self.ecran.app.coffre.exporter(Path(chemin), mdp),
            succes=lambda _r: self._fin("Coffre exporté"))

    def _importer(self):
        chemin = filedialog.askopenfilename(parent=self, title="Importer un export",
                                            filetypes=self.TYPES)
        if not chemin:
            return
        DialogueMotDePasse(
            self, "Importer", "Entrez le mot de passe choisi lors de l'export.",
            libelle="Importer",
            travail=lambda mdp: self.ecran.app.coffre.importer(Path(chemin), mdp),
            succes=lambda n: self._fin(f"{n} identifiant{'s' if n > 1 else ''} importé{'s' if n > 1 else ''}"))

    def _restaurer(self):
        coffre = self.ecran.app.coffre
        choix = []
        if coffre.chemin_sauvegarde.exists():
            choix.append(("Avant le dernier enregistrement", coffre.chemin_sauvegarde))
        for copie in coffre.copies_ouverture():
            date = coffre.date_copie(copie)
            if date:
                choix.append((f"Déverrouillage du {date:%d/%m/%Y à %H:%M:%S}", copie))
        DialogueMotDePasse(
            self, "Restaurer",
            "Choisissez la copie à remettre en place, puis entrez le mot de passe maître "
            "qui l'ouvre. Le coffre actuel reste récupérable avec « Avant le dernier "
            "enregistrement ».",
            libelle="Restaurer", style="danger", choix=choix,
            travail=lambda mdp, copie: coffre.restaurer_sauvegarde(mdp, copie),
            succes=lambda _r: self._fin("Copie restaurée"))

    def _fin(self, message):
        self.ecran.rafraichir()
        self.ecran.notifier(message)
        self.destroy()


class DialogueMotDePasse(Dialogue):
    """Demande un mot de passe, puis lance « travail(mdp) » en arrière-plan
    (Argon2id prend du temps) et appelle « succes(resultat) » s'il réussit."""

    def __init__(self, parent, titre, texte, travail, succes, libelle="Valider",
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
        self.mdp = champ(corps, "Mot de passe", masque=True, width=340)
        self.mdp.pack()
        if nouveau:
            self.jauge = JaugeForce(corps)
            self.jauge.pack(fill="x", pady=(4, 8))
            self.mdp.bind("<KeyRelease>", lambda _e: self.jauge.maj(self.mdp.get()))
            self.confirmation = champ(corps, "Confirmer le mot de passe", masque=True, width=340)
            self.confirmation.pack()
            self.confirmation.bind("<Return>", lambda _e: self._valider())
        else:
            self.mdp.bind("<Return>", lambda _e: self._valider())
        self.message = ctk.CTkLabel(corps, text="", font=police(12), text_color=DANGER,
                                    wraplength=340)
        self.message.pack(pady=(6, 0))
        boutons = ctk.CTkFrame(corps, fg_color="transparent")
        boutons.pack(fill="x", pady=(4, 0))
        self.libelle = libelle
        self.bouton = BoutonAnime(boutons, libelle, self._valider, style=style, width=120)
        self.bouton.pack(side="right")
        BoutonAnime(boutons, "Annuler", self.destroy, width=100).pack(side="right")
        self.after(80, self.mdp.focus_set)

    def _valider(self):
        mdp = self.mdp.get()
        if not mdp:
            self.message.configure(text="Entrez un mot de passe.")
            return
        if self.nouveau:
            problemes = verifier_force(mdp)
            if problemes:
                self.message.configure(text="Il manque : " + ", ".join(problemes) + ".")
                return
            if mdp != self.confirmation.get():
                self.message.configure(text="Les deux mots de passe ne correspondent pas.")
                return
        valeur = self.liste.get() if self.choix else None
        self.bouton.activer(False, "Patientez…")
        self.message.configure(text="")

        def fond():
            try:
                if self.choix:
                    resultat, erreur = self.travail(mdp, self.choix[valeur]), None
                else:
                    resultat, erreur = self.travail(mdp), None
            except MotDePasseIncorrect:
                resultat, erreur = None, "Mot de passe incorrect."
            except CoffreCorrompu:
                resultat, erreur = None, "Ce fichier est illisible ou n'est pas un export SecretLin."
            except (OSError, RuntimeError, ValueError) as e:
                resultat, erreur = None, f"Opération impossible : {e}"
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


def main():
    Application().mainloop()


if __name__ == "__main__":
    main()
