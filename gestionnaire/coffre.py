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


SUFFIXE_SAUVEGARDE = ".bak"


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
        memoire, iterations, voies = entete["memoire"], entete["iterations"], entete["voies"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise CoffreCorrompu(str(e)) from e

    cle = _deriver_cle(mot_de_passe, sel, memoire, iterations, voies)
    aad = json.dumps(entete, sort_keys=True).encode("utf-8")
    try:
        clair = AESGCM(cle).decrypt(nonce, chiffre, aad)
    except InvalidTag:
        raise MotDePasseIncorrect() from None

    entrees = json.loads(clair.decode("utf-8"))
    for e in entrees:
        _separer_email(e)
    return cle, entete, entrees


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

    def ouvrir(self, mot_de_passe: str) -> None:
        self._cle, self._entete, self.entrees = _dechiffrer(self.chemin, mot_de_passe)
        self._trier()

    def verrouiller(self) -> None:
        self._cle = None
        self.entrees = []

    def sauvegarder(self) -> None:
        if self._cle is None or self._entete is None:
            raise RuntimeError("Coffre verrouillé")
        self._trier()
        contenu = _chiffrer(self._cle, self._entete, self.entrees)
        # Avant d'écraser le coffre, on garde sa version précédente (toujours chiffrée) :
        # si l'écriture ou les données posent problème, rien n'est perdu.
        if self.chemin.exists():
            _ecrire_atomique(self.chemin_sauvegarde, self.chemin.read_text(encoding="utf-8"))
        _ecrire_atomique(self.chemin, contenu)

    def a_une_sauvegarde(self) -> bool:
        return self.chemin_sauvegarde.exists()

    def restaurer_sauvegarde(self, mot_de_passe: str) -> None:
        """Remet en place la copie de sauvegarde, après avoir vérifié que « mot_de_passe »
        l'ouvre bien. Le coffre actuel devient à son tour la copie : une restauration
        faite par erreur s'annule en restaurant une seconde fois."""
        cle, entete, entrees = _dechiffrer(self.chemin_sauvegarde, mot_de_passe)
        ancienne = self.chemin_sauvegarde.read_text(encoding="utf-8")
        if self.chemin.exists():
            _ecrire_atomique(self.chemin_sauvegarde, self.chemin.read_text(encoding="utf-8"))
        _ecrire_atomique(self.chemin, ancienne)
        self._cle, self._entete, self.entrees = cle, entete, entrees
        self._trier()

    def exporter(self, destination: Path, mot_de_passe_export: str) -> None:
        """Écrit toutes les entrées dans « destination », chiffrées avec un mot de passe
        propre à l'export (sel et clé neufs, indépendants du mot de passe maître)."""
        if self._cle is None:
            raise RuntimeError("Coffre verrouillé")
        problemes = verifier_force(mot_de_passe_export)
        if problemes:
            raise ValueError("Mot de passe d'export trop faible : il manque " + ", ".join(problemes))
        entete, sel = _nouvel_entete()
        cle = _deriver_cle(mot_de_passe_export, sel, entete["memoire"], entete["iterations"],
                           entete["voies"])
        _ecrire_atomique(Path(destination), _chiffrer(cle, entete, self.entrees))

    def importer(self, source: Path, mot_de_passe_export: str) -> int:
        """Ajoute au coffre les entrées d'un fichier exporté (ou de tout fichier au
        format coffre). Les entrées déjà présentes à l'identique sont ignorées.
        Renvoie le nombre d'entrées ajoutées."""
        if self._cle is None:
            raise RuntimeError("Coffre verrouillé")
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
