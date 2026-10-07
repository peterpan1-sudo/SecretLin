"""Coffre chiffré : stockage des identifiants protégé par un mot de passe maître.

Chiffrement : AES-256-GCM (confidentialité + détection de toute modification).
Dérivation de clé : Argon2id (résistant aux attaques par force brute sur GPU).
"""

import base64
import json
import math
import os
import secrets
import string
import sys
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

VERSION = 1
# Paramètres Argon2id : 256 Mio de mémoire par essai, ce qui rend la force brute très coûteuse.
ARGON2_MEMOIRE_KIO = 256 * 1024
ARGON2_ITERATIONS = 4
ARGON2_VOIES = 4
LONGUEUR_MIN_MAITRE = 12


class MotDePasseIncorrect(Exception):
    pass


class CoffreCorrompu(Exception):
    pass


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


def chemin_coffre() -> Path:
    return dossier_donnees() / "coffre.vault"


def _b64(donnees: bytes) -> str:
    return base64.b64encode(donnees).decode("ascii")


def _deb64(texte: str) -> bytes:
    return base64.b64decode(texte.encode("ascii"))


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
        problemes.append(f"au moins {LONGUEUR_MIN_MAITRE} caractères")
    if not any(c.islower() for c in mot_de_passe):
        problemes.append("une minuscule")
    if not any(c.isupper() for c in mot_de_passe):
        problemes.append("une majuscule")
    if not any(c.isdigit() for c in mot_de_passe):
        problemes.append("un chiffre")
    if not any(not c.isalnum() for c in mot_de_passe):
        problemes.append("un caractère spécial")
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


def generer_mot_de_passe(longueur: int = 20) -> str:
    """Mot de passe aléatoire cryptographiquement sûr, avec chaque type de caractère."""
    speciaux = "!@#$%&*-_=+?"
    alphabet = string.ascii_letters + string.digits + speciaux
    while True:
        mdp = "".join(secrets.choice(alphabet) for _ in range(longueur))
        if (any(c.islower() for c in mdp) and any(c.isupper() for c in mdp)
                and any(c.isdigit() for c in mdp) and any(c in speciaux for c in mdp)):
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
        sel = secrets.token_bytes(16)
        self._entete = {
            "version": VERSION,
            "kdf": "argon2id",
            "sel": _b64(sel),
            "memoire": ARGON2_MEMOIRE_KIO,
            "iterations": ARGON2_ITERATIONS,
            "voies": ARGON2_VOIES,
        }
        self._cle = _deriver_cle(mot_de_passe, sel, ARGON2_MEMOIRE_KIO, ARGON2_ITERATIONS, ARGON2_VOIES)

    def creer(self, mot_de_passe: str) -> None:
        self._nouveau_chiffrement(mot_de_passe)
        self.entrees = []
        self.sauvegarder()

    def ouvrir(self, mot_de_passe: str) -> None:
        try:
            contenu = json.loads(self.chemin.read_text(encoding="utf-8"))
            entete = contenu["entete"]
            nonce = _deb64(contenu["nonce"])
            chiffre = _deb64(contenu["donnees"])
        except (OSError, ValueError, KeyError) as e:
            raise CoffreCorrompu(str(e)) from e

        cle = _deriver_cle(
            mot_de_passe, _deb64(entete["sel"]),
            entete["memoire"], entete["iterations"], entete["voies"],
        )
        aad = json.dumps(entete, sort_keys=True).encode("utf-8")
        try:
            clair = AESGCM(cle).decrypt(nonce, chiffre, aad)
        except InvalidTag:
            raise MotDePasseIncorrect() from None

        self._cle = cle
        self._entete = entete
        self.entrees = json.loads(clair.decode("utf-8"))
        for e in self.entrees:
            _separer_email(e)
        self._trier()

    def verrouiller(self) -> None:
        self._cle = None
        self.entrees = []

    def sauvegarder(self) -> None:
        if self._cle is None or self._entete is None:
            raise RuntimeError("Coffre verrouillé")
        self._trier()
        nonce = secrets.token_bytes(12)
        aad = json.dumps(self._entete, sort_keys=True).encode("utf-8")
        clair = json.dumps(self.entrees, ensure_ascii=False).encode("utf-8")
        chiffre = AESGCM(self._cle).encrypt(nonce, clair, aad)
        contenu = json.dumps({
            "entete": self._entete,
            "nonce": _b64(nonce),
            "donnees": _b64(chiffre),
        })
        # Écriture atomique : le coffre n'est jamais à moitié écrit en cas de coupure.
        fd, tmp = tempfile.mkstemp(dir=self.chemin.parent, prefix=".coffre-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(contenu)
                f.flush()
                os.fsync(f.fileno())
            if sys.platform != "win32":
                os.chmod(tmp, 0o600)
            os.replace(tmp, self.chemin)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def changer_mot_de_passe(self, nouveau: str) -> None:
        # Les entrées restent intactes : on régénère la clé puis on sauvegarde
        # une seule fois (jamais de coffre vide écrit entre-temps).
        self._nouveau_chiffrement(nouveau)
        self.sauvegarder()

    def _trier(self) -> None:
        self.entrees.sort(key=lambda e: (e["site"].casefold(), e["utilisateur"].casefold()))

    def ajouter(self, site: str, utilisateur: str, mot_de_passe: str, notes: str = "",
                email: str = "") -> None:
        self.entrees.append({
            "id": secrets.token_hex(8),
            "site": site.strip(),
            "utilisateur": utilisateur.strip(),
            "email": email.strip(),
            "mot_de_passe": mot_de_passe,
            "notes": notes.strip(),
        })
        self.sauvegarder()

    def modifier(self, id_entree: str, **champs) -> None:
        for e in self.entrees:
            if e["id"] == id_entree:
                e.update({k: v.strip() if k != "mot_de_passe" else v for k, v in champs.items()})
                break
        self.sauvegarder()

    def supprimer(self, id_entree: str) -> None:
        self.entrees = [e for e in self.entrees if e["id"] != id_entree]
        self.sauvegarder()
