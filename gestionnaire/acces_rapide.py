"""Accès rapide : un code PIN à 4 chiffres pour copier ou remplir un identifiant sans
redéverrouiller tout SecretLin (remplissage rapide, extension de navigateur).

Un code de 4 chiffres ne peut pas protéger un fichier (10 000 essais suffisent) : il ne
déchiffre donc rien. Il ne sert que tant que SecretLin a été déverrouillé avec le mot de
passe maître et tourne encore, la clé du coffre étant en mémoire. Trois erreurs, la
durée maximale dépassée, « Verrouiller » ou « Quitter » : la clé est effacée et le mot de
passe maître redevient nécessaire."""

import base64
import hashlib
import hmac
import secrets
import time

ESSAIS_MAX = 3
DUREE_MAX_S = 8 * 3600  # depuis le dernier déverrouillage par le mot de passe maître
DUREE_JETON_S = 120  # après un code juste, le temps de copier identifiant et mot de passe


def _empreinte(pin: str, sel: bytes) -> bytes:
    return hashlib.scrypt(pin.encode("utf-8"), salt=sel, n=2 ** 14, r=8, p=1, dklen=32)


def pin_valide(pin: str) -> bool:
    return len(pin) == 4 and pin.isascii() and pin.isdigit()


def nouveau_pin(pin: str) -> dict:
    """Ce qui est enregistré dans les réglages : un sel et l'empreinte du code."""
    if not pin_valide(pin):
        raise ValueError("le code doit faire 4 chiffres")
    sel = secrets.token_bytes(16)
    return {"sel": base64.b64encode(sel).decode(),
            "empreinte": base64.b64encode(_empreinte(pin, sel)).decode()}


def verifier_pin(pin: str, enregistre: dict | None) -> bool:
    try:
        sel = base64.b64decode(enregistre["sel"])
        attendue = base64.b64decode(enregistre["empreinte"])
    except (KeyError, TypeError, ValueError):
        return False
    return pin_valide(pin) and hmac.compare_digest(_empreinte(pin, sel), attendue)


class Session:
    """État de l'accès rapide pendant que le coffre est ouvert en mémoire."""

    def __init__(self, horloge=time.monotonic):
        self._horloge = horloge
        self.ouvert_depuis = None  # déverrouillage par le mot de passe maître
        self.erreurs = 0
        self._jetons = {}  # jeton → date de fin

    def demarrer(self):
        self.ouvert_depuis = self._horloge()
        self.erreurs = 0
        self._jetons.clear()

    def arreter(self):
        self.ouvert_depuis = None
        self._jetons.clear()

    def expiree(self) -> bool:
        return (self.ouvert_depuis is None
                or self._horloge() - self.ouvert_depuis > DUREE_MAX_S)

    def essayer(self, pin: str, enregistre: dict | None) -> tuple[str | None, int]:
        """(jeton, essais restants). Jeton None : code faux ; à 0 essai restant,
        l'appelant doit verrouiller complètement le coffre."""
        if verifier_pin(pin, enregistre):
            self.erreurs = 0
            jeton = secrets.token_urlsafe(24)
            self._jetons[jeton] = self._horloge() + DUREE_JETON_S
            return jeton, ESSAIS_MAX
        self.erreurs += 1
        return None, max(0, ESSAIS_MAX - self.erreurs)

    def jeton_valide(self, jeton) -> bool:
        fin = self._jetons.get(jeton) if isinstance(jeton, str) else None
        return fin is not None and self._horloge() <= fin
