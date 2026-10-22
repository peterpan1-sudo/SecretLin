"""Coffre chiffré : stockage des identifiants protégé par un mot de passe maître.

Chiffrement : AES-256-GCM (confidentialité + détection de toute modification).
Dérivation de clé : Argon2id (résistant aux attaques par force brute sur GPU).
"""

import base64
import datetime
import hmac
import json
import math
import os
import secrets
import string
import sys
import tempfile
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from gestionnaire.langue import t

VERSION = 1
# Paramètres Argon2id : 256 Mio de mémoire par essai, ce qui rend la force brute très coûteuse.
ARGON2_MEMOIRE_KIO = 256 * 1024
ARGON2_ITERATIONS = 4
ARGON2_VOIES = 4
LONGUEUR_MIN_MAITRE = 12
HISTORIQUE_MAX = 10  # anciens mots de passe gardés par compte
# Limites des paramètres Argon2id acceptés à la lecture d'un fichier : un fichier piégé
# ne doit pas pouvoir réclamer des Gio de mémoire ou des heures de calcul.
ARGON2_MEMOIRE_MAX_KIO = 1024 * 1024
ARGON2_ITERATIONS_MAX = 16
ARGON2_VOIES_MAX = 16


class MotDePasseIncorrect(Exception):
    pass


class CoffreCorrompu(Exception):
    pass


SUFFIXE_SAUVEGARDE = ".bak"
# Copies faites à chaque déverrouillage : on garde les plus récentes.
NB_COPIES_OUVERTURE = 5
FORMAT_COPIE = "coffre-%Y%m%d-%H%M%S-%f.vault"
# Attente imposée après des mots de passe maîtres incorrects (secondes) : 1 min au
# 3e échec, puis 3, 5, 10, 15, 30 min, et 1 h pour chaque échec suivant.
PALIERS_ATTENTE = (60, 180, 300, 600, 900, 1800, 3600)
ATTENTE_MAX = PALIERS_ATTENTE[-1]
ECHECS_AVANT_ATTENTE = 3


def dossier_donnees() -> Path:
    """Dossier privé de l'utilisateur où est rangé le coffre."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    dossier = base / "GestionnaireMDP"
    dossier.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(dossier, 0o700)
    return dossier


def attente_apres(echecs: int) -> int:
    """Secondes d'attente imposées après « echecs » mots de passe incorrects d'affilée."""
    if echecs < ECHECS_AVANT_ATTENTE:
        return 0
    return PALIERS_ATTENTE[min(echecs - ECHECS_AVANT_ATTENTE, len(PALIERS_ATTENTE) - 1)]


def chemin_coffre() -> Path:
    return dossier_donnees() / "coffre.vault"


def _b64(donnees: bytes) -> str:
    return base64.b64encode(donnees).decode("ascii")


def _deb64(texte: str) -> bytes:
    return base64.b64decode(texte.encode("ascii"))


def _ecrire_atomique(chemin: Path, contenu: str) -> None:
    """Écrit « contenu » dans « chemin » sans jamais laisser un fichier à moitié écrit,
    même en cas de coupure (fichier temporaire puis renommage)."""
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".coffre-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenu)
            f.flush()
            os.fsync(f.fileno())
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _verifier_parametres(entete: dict) -> None:
    """Refuse un en-tête dont les paramètres Argon2id sont absurdes ou dangereux."""
    if entete.get("kdf") != "argon2id":
        raise ValueError("méthode de dérivation inconnue")
    limites = {"memoire": (8, ARGON2_MEMOIRE_MAX_KIO), "iterations": (1, ARGON2_ITERATIONS_MAX),
               "voies": (1, ARGON2_VOIES_MAX)}
    for nom, (mini, maxi) in limites.items():
        valeur = entete[nom]
        if type(valeur) is not int or not mini <= valeur <= maxi:
            raise ValueError(f"paramètre {nom} hors limites")
    if entete["memoire"] < 8 * entete["voies"]:
        raise ValueError("paramètre memoire trop petit")


def _deriver_cle(mot_de_passe: str, sel: bytes, memoire: int, iterations: int, voies: int) -> bytes:
    kdf = Argon2id(
        salt=sel,
        length=32,
        iterations=iterations,
        lanes=voies,
        memory_cost=memoire,
    )
    return kdf.derive(mot_de_passe.encode("utf-8"))


def verifier_force(mot_de_passe: str) -> list[str]:
    """Renvoie la liste des problèmes du mot de passe maître (vide si correct)."""
    problemes = []
    if len(mot_de_passe) < LONGUEUR_MIN_MAITRE:
        problemes.append(t("au moins {n} caractères", n=LONGUEUR_MIN_MAITRE))
    if not any(c.islower() for c in mot_de_passe):
        problemes.append(t("une minuscule"))
    if not any(c.isupper() for c in mot_de_passe):
        problemes.append(t("une majuscule"))
    if not any(c.isdigit() for c in mot_de_passe):
        problemes.append(t("un chiffre"))
    if not any(not c.isalnum() for c in mot_de_passe):
        problemes.append(t("un caractère spécial"))
    return problemes


def evaluer_force(mot_de_passe: str) -> int:
    """Note de 0 (vide) à 4 (très fort), d'après l'entropie estimée."""
    if not mot_de_passe:
        return 0
    taille_alphabet = (
        26 * any(c.islower() for c in mot_de_passe)
        + 26 * any(c.isupper() for c in mot_de_passe)
        + 10 * any(c.isdigit() for c in mot_de_passe)
        + 32 * any(not c.isalnum() for c in mot_de_passe)
    )
    # Les caractères répétés n'apportent presque rien.
    entropie = len(set(mot_de_passe)) * math.log2(max(taille_alphabet, 2))
    if entropie < 40:
        return 1
    if entropie < 65:
        return 2
    if entropie < 90:
        return 3
    return 4


SYMBOLES = "!@#$%&*-_=+?"
AMBIGUS = "Il1O0o"  # se confondent à l'œil


def generer_mot_de_passe(longueur: int = 20, majuscules: bool = True, chiffres: bool = True,
                         symboles: bool = True, sans_ambigus: bool = False) -> str:
    """Mot de passe aléatoire cryptographiquement sûr : des minuscules, plus chaque type
    de caractère demandé, présent au moins une fois."""
    familles = [string.ascii_lowercase]
    if majuscules:
        familles.append(string.ascii_uppercase)
    if chiffres:
        familles.append(string.digits)
    if symboles:
        familles.append(SYMBOLES)
    if sans_ambigus:
        familles = ["".join(c for c in f if c not in AMBIGUS) for f in familles]
    longueur = max(longueur, len(familles))
    alphabet = "".join(familles)
    while True:
        mdp = "".join(secrets.choice(alphabet) for _ in range(longueur))
        if all(any(c in f for c in mdp) for f in familles):
            return mdp


def _separer_email(entree: dict) -> None:
    """Anciennes versions : un seul champ « utilisateur ou e-mail ». Une adresse e-mail
    qui s'y trouve est déplacée dans le nouveau champ « email »."""
    if "email" in entree:
        return
    if "@" in entree["utilisateur"]:
        entree["email"], entree["utilisateur"] = entree["utilisateur"], ""
    else:
        entree["email"] = ""


def _nouvel_entete() -> tuple[dict, bytes]:
    """En-tête neuf (sel aléatoire, paramètres Argon2id actuels) et sel brut."""
    sel = secrets.token_bytes(16)
    entete = {
        "version": VERSION,
        "kdf": "argon2id",
        "sel": _b64(sel),
        "memoire": ARGON2_MEMOIRE_KIO,
        "iterations": ARGON2_ITERATIONS,
        "voies": ARGON2_VOIES,
    }
    return entete, sel


def _chiffrer(cle: bytes, entete: dict, entrees: list[dict]) -> str:
    nonce = secrets.token_bytes(12)
    aad = json.dumps(entete, sort_keys=True).encode("utf-8")
    clair = json.dumps(entrees, ensure_ascii=False).encode("utf-8")
    chiffre = AESGCM(cle).encrypt(nonce, clair, aad)
    return json.dumps({
        "entete": entete,
        "nonce": _b64(nonce),
        "donnees": _b64(chiffre),
    })


def _dechiffrer(chemin: Path, mot_de_passe: str) -> tuple[bytes, dict, list[dict]]:
    """Lit et déchiffre un fichier au format coffre. Renvoie (clé, en-tête, entrées)."""
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        entete = contenu["entete"]
        nonce = _deb64(contenu["nonce"])
        chiffre = _deb64(contenu["donnees"])
        sel = _deb64(entete["sel"])
        _verifier_parametres(entete)
        memoire, iterations, voies = entete["memoire"], entete["iterations"], entete["voies"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise CoffreCorrompu(str(e)) from e

    cle = _deriver_cle(mot_de_passe, sel, memoire, iterations, voies)
    aad = json.dumps(entete, sort_keys=True).encode("utf-8")
    try:
        clair = AESGCM(cle).decrypt(nonce, chiffre, aad)
    except InvalidTag:
        raise MotDePasseIncorrect() from None

    try:
        entrees = _verifier_entrees(json.loads(clair.decode("utf-8")))
    except (ValueError, TypeError) as e:
        raise CoffreCorrompu(str(e)) from e
    return cle, entete, entrees


def _verifier_entrees(entrees) -> list[dict]:
    """Contrôle les entrées déchiffrées : une liste de fiches dont chaque champ est un
    texte. Les champs facultatifs manquants sont complétés."""
    if not isinstance(entrees, list):
        raise ValueError("la liste des comptes est absente")
    for e in entrees:
        if not isinstance(e, dict):
            raise ValueError("compte illisible")
        for cle in ("site", "utilisateur", "mot_de_passe"):
            if not isinstance(e.get(cle), str):
                raise ValueError(f"champ {cle} manquant ou invalide")
        e.setdefault("notes", "")
        _separer_email(e)
        if not isinstance(e["email"], str) or not isinstance(e["notes"], str):
            raise ValueError("champ email ou notes invalide")
        if not isinstance(e.get("id"), str) or not e["id"]:
            e["id"] = secrets.token_hex(8)
        if not isinstance(e.get("change_le"), str):
            e.pop("change_le", None)  # date inconnue (compte créé avant le bilan de santé)
        if not isinstance(e.get("favori"), bool):
            e["favori"] = False
        if not isinstance(e.get("categorie"), str):
            e["categorie"] = ""
        if not isinstance(e.get("totp"), str):
            e["totp"] = ""
        historique = e.get("historique")
        if not isinstance(historique, list):
            historique = []
        e["historique"] = [h for h in historique if isinstance(h, dict)
                           and isinstance(h.get("mot_de_passe"), str)
                           and isinstance(h.get("remplace_le"), str)]
    return entrees


def _empreinte(entree: dict) -> tuple:
    """Contenu d'une entrée, sans son identifiant : sert à repérer les doublons."""
    return tuple(entree.get(k, "") for k in ("site", "utilisateur", "email", "mot_de_passe", "notes"))


class Coffre:
    def __init__(self, chemin: Path | None = None):
        self.chemin = chemin or chemin_coffre()
        self.entrees: list[dict] = []
        self._cle: bytes | None = None
        self._entete: dict | None = None

    def existe(self) -> bool:
        return self.chemin.exists()

    def _nouveau_chiffrement(self, mot_de_passe: str) -> None:
        """Régénère sel, en-tête et clé pour « mot_de_passe ». Ne touche ni aux
        entrées ni au fichier : l'appelant sauvegarde une seule fois ensuite."""
        self._entete, sel = _nouvel_entete()
        self._cle = _deriver_cle(mot_de_passe, sel, ARGON2_MEMOIRE_KIO, ARGON2_ITERATIONS, ARGON2_VOIES)

    def creer(self, mot_de_passe: str) -> None:
        self._nouveau_chiffrement(mot_de_passe)
        self.entrees = []
        self.sauvegarder()

    @property
    def chemin_sauvegarde(self) -> Path:
        """Copie de la version précédente du coffre, refaite avant chaque écriture."""
        return self.chemin.with_name(self.chemin.name + SUFFIXE_SAUVEGARDE)

    @property
    def dossier_copies(self) -> Path:
        """Dossier des copies faites à chaque déverrouillage."""
        return self.chemin.parent / "sauvegardes"

    @property
    def chemin_echecs(self) -> Path:
        """Compteur des déverrouillages ratés, gardé d'un lancement à l'autre."""
        return self.chemin.with_name(self.chemin.stem + "-echecs.json")

    def lire_echecs(self) -> tuple[int, float]:
        """Nombre d'échecs de déverrouillage et heure (time.time) jusqu'à laquelle les
        essais sont refusés. Un fichier absent ou illisible compte pour aucun échec."""
        try:
            donnees = json.loads(self.chemin_echecs.read_text(encoding="utf-8"))
            echecs = max(0, int(donnees["echecs"]))
            bloque_jusqua = float(donnees["bloque_jusqua"])
        except (OSError, ValueError, KeyError, TypeError):
            return 0, 0.0
        # Si l'horloge a été reculée, l'attente ne dépasse quand même pas le maximum.
        return echecs, min(bloque_jusqua, time.time() + ATTENTE_MAX)

    def noter_echecs(self, echecs: int, bloque_jusqua: float = 0.0) -> None:
        """Enregistre le compteur ; à zéro, le fichier est supprimé."""
        if echecs <= 0:
            self.chemin_echecs.unlink(missing_ok=True)
            return
        _ecrire_atomique(self.chemin_echecs, json.dumps({"echecs": echecs, "bloque_jusqua": bloque_jusqua}))

    def ouvrir(self, mot_de_passe: str) -> None:
        self._cle, self._entete, self.entrees = _dechiffrer(self.chemin, mot_de_passe)
        self._trier()
        try:
            self._copie_ouverture()
        except OSError:
            pass  # une copie impossible (disque plein…) ne doit pas empêcher d'ouvrir le coffre

    def _copie_ouverture(self) -> None:
        """Copie le coffre tel qu'il est au déverrouillage, sauf s'il n'a pas changé depuis
        la dernière copie, puis ne garde que les NB_COPIES_OUVERTURE plus récentes."""
        contenu = self.chemin.read_text(encoding="utf-8")
        copies = self.copies_ouverture()
        if copies and copies[0].read_text(encoding="utf-8") == contenu:
            return
        self.dossier_copies.mkdir(exist_ok=True)
        if sys.platform != "win32":
            os.chmod(self.dossier_copies, 0o700)
        nom = datetime.datetime.now().strftime(FORMAT_COPIE)
        _ecrire_atomique(self.dossier_copies / nom, contenu)
        for ancienne in self.copies_ouverture()[NB_COPIES_OUVERTURE:]:
            ancienne.unlink()

    def copies_ouverture(self) -> list[Path]:
        """Copies faites au déverrouillage, de la plus récente à la plus ancienne."""
        if not self.dossier_copies.is_dir():
            return []
        return sorted(self.dossier_copies.glob("coffre-*.vault"), reverse=True)

    @staticmethod
    def date_copie(copie: Path) -> datetime.datetime | None:
        try:
            return datetime.datetime.strptime(copie.name, FORMAT_COPIE)
        except ValueError:
            return None

    def verrouiller(self) -> None:
        self._cle = None
        self.entrees = []

    def sauvegarder(self) -> None:
        if self._cle is None or self._entete is None:
            raise RuntimeError(t("Coffre verrouillé"))
        self._trier()
        contenu = _chiffrer(self._cle, self._entete, self.entrees)
        # Avant d'écraser le coffre, on garde sa version précédente (toujours chiffrée) :
        # si l'écriture ou les données posent problème, rien n'est perdu.
        if self.chemin.exists():
            _ecrire_atomique(self.chemin_sauvegarde, self.chemin.read_text(encoding="utf-8"))
        _ecrire_atomique(self.chemin, contenu)

    def a_une_sauvegarde(self) -> bool:
        return self.chemin_sauvegarde.exists() or bool(self.copies_ouverture())

    def restaurer_sauvegarde(self, mot_de_passe: str, source: Path | None = None) -> None:
        """Remet en place une copie du coffre : celle d'avant le dernier enregistrement
        par défaut, ou « source » (par exemple une copie faite au déverrouillage).
        « mot_de_passe » doit ouvrir cette copie. Le coffre actuel devient la copie
        d'avant le dernier enregistrement : une restauration faite par erreur s'annule
        en restaurant cette copie."""
        source = Path(source) if source else self.chemin_sauvegarde
        cle, entete, entrees = _dechiffrer(source, mot_de_passe)
        contenu = source.read_text(encoding="utf-8")
        if self.chemin.exists():
            _ecrire_atomique(self.chemin_sauvegarde, self.chemin.read_text(encoding="utf-8"))
        _ecrire_atomique(self.chemin, contenu)
        self._cle, self._entete, self.entrees = cle, entete, entrees
        self._trier()

    def exporter(self, destination: Path, mot_de_passe_export: str) -> None:
        """Écrit toutes les entrées dans « destination », chiffrées avec un mot de passe
        propre à l'export (sel et clé neufs, indépendants du mot de passe maître)."""
        if self._cle is None:
            raise RuntimeError(t("Coffre verrouillé"))
        problemes = verifier_force(mot_de_passe_export)
        if problemes:
            raise ValueError(t("Mot de passe d'export trop faible : il manque {liste}",
                               liste=", ".join(problemes)))
        entete, sel = _nouvel_entete()
        cle = _deriver_cle(mot_de_passe_export, sel, entete["memoire"], entete["iterations"],
                           entete["voies"])
        _ecrire_atomique(Path(destination), _chiffrer(cle, entete, self.entrees))

    def importer(self, source: Path, mot_de_passe_export: str) -> int:
        """Ajoute au coffre les entrées d'un fichier exporté (ou de tout fichier au
        format coffre). Les entrées déjà présentes à l'identique sont ignorées.
        Renvoie le nombre d'entrées ajoutées."""
        if self._cle is None:
            raise RuntimeError(t("Coffre verrouillé"))
        _, _, importees = _dechiffrer(Path(source), mot_de_passe_export)
        connues = {_empreinte(e) for e in self.entrees}
        ids = {e["id"] for e in self.entrees}
        ajoutees = 0
        for e in importees:
            if _empreinte(e) in connues:
                continue
            e = {**e}
            if e.get("id") in ids or not e.get("id"):
                e["id"] = secrets.token_hex(8)
            self.entrees.append(e)
            connues.add(_empreinte(e))
            ids.add(e["id"])
            ajoutees += 1
        if ajoutees:
            self.sauvegarder()
        return ajoutees

    def ajouter_externes(self, entrees: list[dict]) -> tuple[int, int]:
        """Ajoute des identifiants venus d'un autre gestionnaire (voir import_externe).
        Un compte déjà présent (même site, utilisateur, e-mail et mot de passe) est ignoré.
        Renvoie (ajoutés, ignorés)."""
        if self._cle is None:
            raise RuntimeError(t("Coffre verrouillé"))

        def cle(e):
            return (e["site"].strip().casefold(), e["utilisateur"].strip(),
                    e.get("email", "").strip().casefold(), e["mot_de_passe"])

        connues = {cle(e) for e in self.entrees}
        aujourdhui = datetime.date.today().isoformat()
        ajoutees = 0
        for e in entrees:
            if cle(e) in connues:
                continue
            connues.add(cle(e))
            self.entrees.append({
                "id": secrets.token_hex(8),
                "site": e["site"].strip(),
                "utilisateur": e["utilisateur"].strip(),
                "email": e.get("email", "").strip(),
                "mot_de_passe": e["mot_de_passe"],
                "notes": e.get("notes", "").strip(),
                "change_le": aujourdhui,
                "categorie": e.get("categorie", "").strip(),
                "favori": bool(e.get("favori", False)),
                "historique": [],
                "totp": e.get("totp", "").strip(),
            })
            ajoutees += 1
        if ajoutees:
            self.sauvegarder()
        return ajoutees, len(entrees) - ajoutees

    def verifier_mot_de_passe(self, mot_de_passe: str) -> bool:
        """Vrai si « mot_de_passe » est le mot de passe maître du coffre ouvert."""
        if self._cle is None:
            raise RuntimeError(t("Coffre verrouillé"))
        e = self._entete
        cle = _deriver_cle(mot_de_passe, _deb64(e["sel"]), e["memoire"], e["iterations"], e["voies"])
        return hmac.compare_digest(cle, self._cle)

    def changer_mot_de_passe(self, nouveau: str, actuel: str | None = None) -> None:
        """Rechiffre le coffre avec « nouveau ». Si « actuel » est donné, il doit être
        le mot de passe maître en place, sinon MotDePasseIncorrect est levée."""
        if self._cle is None:
            raise RuntimeError(t("Coffre verrouillé"))
        if actuel is not None and not self.verifier_mot_de_passe(actuel):
            raise MotDePasseIncorrect()
        # Les entrées restent intactes : on régénère la clé puis on sauvegarde
        # une seule fois (jamais de coffre vide écrit entre-temps).
        ancienne_cle, ancien_entete = self._cle, self._entete
        self._nouveau_chiffrement(nouveau)
        self.sauvegarder()
        self._rechiffrer_copies(ancienne_cle, ancien_entete)

    def _rechiffrer_copies(self, ancienne_cle: bytes, ancien_entete: dict) -> None:
        """Après un changement de mot de passe, aucune copie (.bak, sauvegardes/) ne doit
        encore s'ouvrir avec l'ancien : celles chiffrées avec l'ancienne clé sont
        rechiffrées avec la nouvelle, les autres (clé inconnue, illisibles) sont supprimées."""
        aad = json.dumps(ancien_entete, sort_keys=True).encode("utf-8")
        for copie in [self.chemin_sauvegarde, *self.copies_ouverture()]:
            if not copie.exists():
                continue
            try:
                contenu = json.loads(copie.read_text(encoding="utf-8"))
                if contenu["entete"] != ancien_entete:
                    raise ValueError("copie chiffrée avec une autre clé")
                clair = AESGCM(ancienne_cle).decrypt(
                    _deb64(contenu["nonce"]), _deb64(contenu["donnees"]), aad)
                _ecrire_atomique(copie, _chiffrer(self._cle, self._entete,
                                                  json.loads(clair.decode("utf-8"))))
            except (OSError, ValueError, KeyError, TypeError, InvalidTag):
                copie.unlink(missing_ok=True)

    def _trier(self) -> None:
        self.entrees.sort(key=lambda e: (e["site"].casefold(), e["utilisateur"].casefold()))

    def ajouter(self, site: str, utilisateur: str, mot_de_passe: str, notes: str = "",
                email: str = "", categorie: str = "", favori: bool = False,
                totp: str = "") -> None:
        self.entrees.append({
            "id": secrets.token_hex(8),
            "site": site.strip(),
            "utilisateur": utilisateur.strip(),
            "email": email.strip(),
            "mot_de_passe": mot_de_passe,
            "notes": notes.strip(),
            "change_le": datetime.date.today().isoformat(),
            "categorie": categorie.strip(),
            "favori": favori,
            "historique": [],
            "totp": totp.strip(),
        })
        self.sauvegarder()

    def modifier(self, id_entree: str, **champs) -> None:
        for e in self.entrees:
            if e["id"] == id_entree:
                if "mot_de_passe" in champs and champs["mot_de_passe"] != e["mot_de_passe"]:
                    # L'ancien mot de passe est gardé : utile si le changement sur le site
                    # n'a pas abouti.
                    ancien = {"mot_de_passe": e["mot_de_passe"],
                              "remplace_le": datetime.date.today().isoformat()}
                    e["historique"] = ([ancien] + e.get("historique", []))[:HISTORIQUE_MAX]
                    e["change_le"] = datetime.date.today().isoformat()
                e.update({k: v.strip() if isinstance(v, str) and k != "mot_de_passe" else v
                          for k, v in champs.items()})
                break
        self.sauvegarder()

    def basculer_favori(self, id_entree: str) -> None:
        for e in self.entrees:
            if e["id"] == id_entree:
                e["favori"] = not e.get("favori", False)
        self.sauvegarder()

    def categories(self) -> list[str]:
        """Catégories utilisées, sans doublon, par ordre alphabétique."""
        return sorted({e["categorie"] for e in self.entrees if e.get("categorie")},
                      key=str.casefold)

    def supprimer(self, id_entree: str) -> None:
        self.entrees = [e for e in self.entrees if e["id"] != id_entree]
        self.sauvegarder()
