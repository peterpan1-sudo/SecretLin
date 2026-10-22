"""Remplissage rapide : petite fenêtre ouverte par un raccourci clavier global
(« secretlin --remplissage »). On cherche un compte, on donne le code PIN, puis on copie
l'identifiant et le mot de passe. Tout passe par la porte locale : c'est SecretLin, ouvert
en arrière-plan, qui garde le coffre et remplit le presse-papier."""

import subprocess
import sys
from pathlib import Path

import customtkinter as ctk

from gestionnaire import apparence, app as ui, porte
from gestionnaire.coffre import chemin_coffre
from gestionnaire.langue import t


class Remplissage(ctk.CTk):
    def __init__(self):
        super().__init__(className="SecretLin")
        self.title(t("SecretLin — remplissage rapide"))
        self.configure(fg_color=ui.PANNEAU)
        self.geometry("480x470")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.jeton = None
        self.etat = None
        self.corps = None
        self.after(30, self._debut)

    # --- Écrans -----------------------------------------------------------

    def _vider(self):
        if self.corps is not None:
            self.corps.destroy()
        self.corps = ctk.CTkFrame(self, fg_color="transparent")
        self.corps.pack(fill="both", expand=True, padx=24, pady=20)
        return self.corps

    def _titre(self, corps, texte, detail=""):
        ctk.CTkLabel(corps, text=texte, font=ui.police(18, gras=True), text_color=ui.TEXTE,
                     anchor="w").pack(fill="x")
        if detail:
            ctk.CTkLabel(corps, text=detail, font=ui.police(12), text_color=ui.TEXTE_DOUX,
                         anchor="w", justify="left", wraplength=420).pack(fill="x", pady=(2, 0))

    def _debut(self):
        reponse = porte.demander({"action": "etat"})
        self.etat = reponse.get("etat") if reponse else None
        if self.etat in ("ouvert", "pin"):
            self._recherche()
            return
        corps = self._vider()
        if self.etat is None:
            self._titre(corps, t("SecretLin n'est pas ouvert"),
                        t("Ouvrez SecretLin et déverrouillez-le avec votre mot de passe maître, "
                          "puis relancez le remplissage rapide."))
        else:
            self._titre(corps, t("SecretLin est verrouillé"),
                        t("Déverrouillez-le avec votre mot de passe maître : le code PIN ne "
                          "sert que tant que SecretLin reste ouvert."))
        ui.BoutonAnime(corps, t("Ouvrir SecretLin"), self._ouvrir_secretlin, style="principal",
                       width=180).pack(anchor="w", pady=(18, 0))

    def _ouvrir_secretlin(self):
        if porte.demander({"action": "montrer"}) is None:
            lanceur = Path(__file__).resolve().parent.parent / "lancer.py"
            subprocess.Popen([sys.executable, str(lanceur)], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        self.destroy()

    def _recherche(self):
        corps = self._vider()
        self._titre(corps, t("Remplissage rapide"),
                    t("Tapez le nom du site, puis Entrée."))
        self.champ = ui.champ(corps, t("Rechercher un site ou un identifiant…"))
        self.champ.pack(fill="x", pady=(12, 8))
        self.champ.bind("<KeyRelease>", self._touche)
        self.liste = ctk.CTkScrollableFrame(corps, fg_color="transparent",
                                            scrollbar_button_color=ui.BORDURE)
        self.liste.pack(fill="both", expand=True)
        self.comptes, self.choisi = [], 0
        self._chercher()
        self.after(50, self.champ.focus_force)

    def _touche(self, evt):
        if evt.keysym == "Return":
            if self.comptes:
                self._choisir(self.comptes[self.choisi])
        elif evt.keysym in ("Down", "Up"):
            if self.comptes:
                self.choisi = (self.choisi + (1 if evt.keysym == "Down" else -1)) % len(self.comptes)
                self._afficher()
        else:
            self._chercher()

    def _chercher(self):
        reponse = porte.demander({"action": "chercher", "texte": self.champ.get()})
        if not reponse or "comptes" not in reponse:
            self._debut()
            return
        self.comptes, self.choisi = reponse["comptes"][:8], 0
        self._afficher()

    def _afficher(self):
        for enfant in self.liste.winfo_children():
            enfant.destroy()
        if not self.comptes:
            ctk.CTkLabel(self.liste, text=t("Aucun résultat."), font=ui.police(13),
                         text_color=ui.TEXTE_DOUX).pack(pady=20)
        for i, c in enumerate(self.comptes):
            ligne = ctk.CTkFrame(self.liste, fg_color=ui.CARTE_SURVOL if i == self.choisi
                                 else ui.CARTE, corner_radius=10, cursor="hand2")
            ligne.pack(fill="x", pady=3)
            pastille = ui.Pastille(ligne, c["site"], taille=34)
            pastille.pack(side="left", padx=(10, 10), pady=8)
            textes = ctk.CTkFrame(ligne, fg_color="transparent")
            textes.pack(side="left", fill="x", expand=True)
            nom = ctk.CTkLabel(textes, text=c["site"],
                               font=ui.police(14, gras=True), text_color=ui.TEXTE, anchor="w")
            nom.pack(fill="x")
            detail = ctk.CTkLabel(textes, text=c["utilisateur"] or c["email"] or "—",
                                  font=ui.police(11), text_color=ui.TEXTE_DOUX, anchor="w")
            detail.pack(fill="x")
            ui.sur_clic((ligne, pastille, textes, nom, detail), lambda c=c: self._choisir(c))

    def _choisir(self, compte):
        self.compte = compte
        if self.etat == "pin" and not self.jeton:
            self._code()
        else:
            self._copies()

    def _code(self):
        corps = self._vider()
        self._titre(corps, t("Code PIN"), t("Entrez votre code à 4 chiffres pour « {site} ».",
                                             site=self.compte["site"]))
        self.pin = ui.champ(corps, "••••", masque=True, width=160)
        self.pin.configure(font=ui.police(22, gras=True), justify="center")
        self.pin.pack(pady=(18, 6))
        self.pin.bind("<Return>", lambda _e: self._valider_code())
        self.pin.bind("<KeyRelease>", lambda _e: len(self.pin.get()) == 4 and self._valider_code())
        self.message = ctk.CTkLabel(corps, text="", font=ui.police(12), text_color=ui.DANGER)
        self.message.pack()
        self.after(50, self.pin.focus_force)

    def _valider_code(self):
        code = self.pin.get()
        self.pin.delete(0, "end")
        reponse = porte.demander({"action": "pin", "pin": code}) or {}
        if reponse.get("ok"):
            self.jeton = reponse.get("jeton")
            self._copies()
        elif reponse.get("verrouille"):
            self.message.configure(text=t("Trop d'erreurs : SecretLin s'est verrouillé."))
            self.after(2500, self.destroy)
        elif "restants" in reponse:
            self.message.configure(text=tn_restants(reponse["restants"]))
        else:
            self._debut()

    def _copies(self):
        c = self.compte
        corps = self._vider()
        self._titre(corps, c["site"], t("Entrée copie l'identifiant, puis le mot de passe."))
        self.message = ctk.CTkLabel(corps, text="", font=ui.police(12), text_color=ui.SUCCES)
        boutons = []
        if c["utilisateur"]:
            boutons.append((t("Copier le nom d'utilisateur"), "utilisateur", c["utilisateur"]))
        if c["email"]:
            boutons.append((t("Copier l'e-mail"), "email", c["email"]))
        boutons.append((t("Copier le mot de passe"), "mot_de_passe", "••••••••"))
        if c["totp"]:
            boutons.append((t("Copier le code 2FA"), "totp", ""))
        self.ordre = [champ for _, champ, _ in boutons]
        self.etape = 0
        for libelle, champ, valeur in boutons:
            ligne = ctk.CTkFrame(corps, fg_color=ui.CARTE, corner_radius=10)
            ligne.pack(fill="x", pady=(10, 0))
            ctk.CTkLabel(ligne, text=valeur, font=ui.police(12), text_color=ui.TEXTE_DOUX,
                         anchor="w").pack(side="left", fill="x", expand=True, padx=12)
            ui.BoutonAnime(ligne, libelle, lambda ch=champ: self._copier(ch),
                           style="principal" if champ == "mot_de_passe" else "secondaire",
                           width=210, height=36).pack(side="right", padx=6, pady=6)
        self.message.pack(pady=(14, 0))
        self.bind("<Return>", lambda _e: self._suivant())
        self.focus_force()

    def _suivant(self):
        if self.etape < len(self.ordre):
            self._copier(self.ordre[self.etape])

    def _copier(self, champ):
        reponse = porte.demander({"action": "copier", "id": self.compte["id"], "champ": champ,
                                  "jeton": self.jeton}) or {}
        if not reponse.get("ok"):
            self.jeton = None
            self._debut()
            return
        noms = {"utilisateur": t("Nom d'utilisateur copié"), "email": t("E-mail copié"),
                "mot_de_passe": ui.mdp_copie(),
                "totp": t("Code de double authentification copié")}
        self.message.configure(text="✓  " + noms[champ])
        if champ in self.ordre:
            self.etape = self.ordre.index(champ) + 1
        if champ == "mot_de_passe":
            self.after(1500, self.destroy)  # le mot de passe est le dernier à coller


def tn_restants(n):
    return ui.tn("Code faux : encore {n} essai.", "Code faux : encore {n} essais.", n)


def main():
    reglages = apparence.charger(apparence.chemin_reglages(chemin_coffre()))
    ui.appliquer_apparence(reglages)
    ctk.set_appearance_mode(ui.MODE)
    Remplissage().mainloop()
