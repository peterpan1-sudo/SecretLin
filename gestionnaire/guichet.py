"""Réponses aux demandes qui arrivent par la porte locale (remplissage rapide, extension
de navigateur). Aucun secret ne sort sans autorisation : coffre ouvert à l'écran, ou
code PIN juste depuis moins de deux minutes."""

import re
import unicodedata
from urllib.parse import urlsplit

from gestionnaire import acces_rapide, totp

RESULTATS_MAX = 30
# Avant-derniers morceaux d'adresse qui ne sont pas le nom du site (« amazon.co.uk »).
SUFFIXES_DOUBLES = {"co", "com", "org", "net", "gov", "gouv", "ac", "edu", "ne", "or"}


def _simplifier(texte: str) -> str:
    """« Proton Mail » → « protonmail » : minuscules, sans accents ni séparateurs."""
    texte = unicodedata.normalize("NFKD", texte.casefold())
    return re.sub(r"[^a-z0-9]", "", texte.encode("ascii", "ignore").decode())


def hote(adresse: str) -> str:
    adresse = adresse.strip()
    nom = urlsplit(adresse if "://" in adresse else "https://" + adresse).hostname or ""
    return nom.removeprefix("www.")


def nom_du_site(nom_hote: str) -> str:
    """« accounts.google.com » → « google » ; « amazon.co.uk » → « amazon »."""
    morceaux = [m for m in nom_hote.split(".") if m]
    if len(morceaux) >= 3 and morceaux[-2] in SUFFIXES_DOUBLES:
        return morceaux[-3]
    return morceaux[-2] if len(morceaux) >= 2 else (morceaux[0] if morceaux else "")


def _hotes_notes(notes: str) -> set[str]:
    """Adresses de sites notées dans les notes (les imports y rangent l'adresse du site)."""
    return {hote(m) for m in re.findall(r"[\w.-]+\.[a-z]{2,}(?:/\S*)?", notes.casefold())}


def correspond(entree: dict, adresse: str) -> bool:
    """Le compte va-t-il avec la page « adresse » ? La règle est stricte, pour ne rien
    proposer sur un site d'hameçonnage au nom ressemblant (« amaz.com », « netflix-x.com ») :
    - une adresse notée dans les notes, le même site ou l'un de ses sous-domaines ;
    - ou le nom du compte (ou son premier mot) égal au nom du site : « Discord » pour
      discord.com, « Proton Mail » pour proton.me, « netflix.com » pour netflix.com."""
    nom_hote = hote(adresse)
    if not nom_hote:
        return False
    for h in _hotes_notes(entree.get("notes", "")):
        if h and (nom_hote == h or nom_hote.endswith("." + h)):
            return True
    nom = _simplifier(nom_du_site(nom_hote))
    if not nom:
        return False
    mots = re.findall(r"\w+", entree["site"].casefold())
    return nom in (_simplifier(entree["site"]), _simplifier(mots[0]) if mots else "") \
        or hote(entree["site"]) == nom_hote


def _resume(e: dict) -> dict:
    return {"id": e["id"], "site": e["site"], "utilisateur": e["utilisateur"],
            "email": e.get("email", ""), "totp": totp.valide(e.get("totp", ""))}


class Guichet:
    """« interface » fournit : ecran_ouvert() (coffre déverrouillé à l'écran), pin()
    (code enregistré ou None), copier(texte, message), verrouiller(), montrer()."""

    def __init__(self, coffre, session: acces_rapide.Session, interface):
        self.coffre, self.session, self.interface = coffre, session, interface

    def etat(self) -> str:
        """« ouvert », « pin » (code demandé) ou « ferme » (mot de passe maître demandé)."""
        if self.coffre._cle is None:
            return "ferme"
        if self.interface.ecran_ouvert():
            return "ouvert"
        if self.interface.pin() and not self.session.expiree():
            return "pin"
        return "ferme"

    def traiter(self, requete: dict) -> dict:
        action = requete.get("action")
        if action == "montrer":
            self.interface.montrer()
            return {"ok": True}
        etat = self.etat()
        if action == "etat":
            return {"etat": etat, "pin": bool(self.interface.pin())}
        if etat == "ferme":
            return {"erreur": "ferme"}
        if action == "chercher":
            return {"comptes": self._chercher(requete)}
        if action == "pin":
            return self._essayer_pin(requete, etat)
        if action in ("copier", "identifiants"):
            if etat != "ouvert" and not self.session.jeton_valide(requete.get("jeton")):
                return {"erreur": "pin"}
            e = next((e for e in self.coffre.entrees if e["id"] == requete.get("id")), None)
            if e is None:
                return {"erreur": "introuvable"}
            return self._copier(e, requete.get("champ")) if action == "copier" \
                else self._identifiants(e)
        return {"erreur": "action inconnue"}

    def _chercher(self, requete) -> list[dict]:
        entrees = self.coffre.entrees
        if isinstance(requete.get("adresse"), str):
            trouvees = [e for e in entrees if correspond(e, requete["adresse"])]
        else:
            texte = str(requete.get("texte", "")).strip().casefold()
            trouvees = [e for e in entrees if any(texte in e.get(k, "").casefold()
                                                  for k in ("site", "utilisateur", "email",
                                                            "categorie"))]
        trouvees.sort(key=lambda e: (not e.get("favori"), e["site"].casefold()))
        return [_resume(e) for e in trouvees[:RESULTATS_MAX]]

    def _essayer_pin(self, requete, etat) -> dict:
        if etat == "ouvert":
            return {"ok": True, "jeton": None}
        jeton, restants = self.session.essayer(str(requete.get("pin", "")), self.interface.pin())
        if jeton:
            return {"ok": True, "jeton": jeton}
        if restants == 0:
            self.interface.verrouiller()
            return {"ok": False, "restants": 0, "verrouille": True}
        return {"ok": False, "restants": restants}

    def _copier(self, e, champ) -> dict:
        if champ == "totp":
            if not totp.valide(e.get("totp", "")):
                return {"erreur": "vide"}
            valeur = totp.code(e["totp"])
        elif champ in ("utilisateur", "email", "mot_de_passe"):
            valeur = e.get(champ, "")
        else:
            return {"erreur": "champ inconnu"}
        if not valeur:
            return {"erreur": "vide"}
        self.interface.copier(valeur, champ)
        return {"ok": True}

    def _identifiants(self, e) -> dict:
        return {"ok": True, "utilisateur": e["utilisateur"], "email": e.get("email", ""),
                "mot_de_passe": e["mot_de_passe"],
                "totp": totp.code(e["totp"]) if totp.valide(e.get("totp", "")) else ""}
