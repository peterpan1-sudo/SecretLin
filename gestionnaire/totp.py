"""Codes de double authentification (TOTP, RFC 6238), comme Google Authenticator.

La clé est celle que donne un site en activant la double authentification : un texte en
base32 (« JBSWY3DPEHPK3PXP ») ou une adresse « otpauth://totp/…?secret=… » (le contenu
du QR code)."""

import base64
import hashlib
import hmac
import struct
import time
from urllib.parse import parse_qs, urlsplit

ALGORITHMES = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


def lire(cle: str) -> dict:
    """Secret et réglages d'une clé ; ValueError si elle n'est pas valable."""
    cle = cle.strip()
    reglages = {"chiffres": 6, "periode": 30, "algorithme": "SHA1"}
    if cle.lower().startswith("otpauth://"):
        adresse = urlsplit(cle)
        if adresse.netloc.lower() != "totp":
            raise ValueError("seuls les codes basés sur l'heure (totp) sont pris en charge")
        params = {k.lower(): v[0] for k, v in parse_qs(adresse.query).items()}
        cle = params.get("secret", "")
        try:
            reglages["chiffres"] = int(params.get("digits", 6))
            reglages["periode"] = int(params.get("period", 30))
        except ValueError:
            raise ValueError("réglages invalides") from None
        reglages["algorithme"] = params.get("algorithm", "SHA1").upper()
    if reglages["algorithme"] not in ALGORITHMES or not 6 <= reglages["chiffres"] <= 8 \
            or not 1 <= reglages["periode"] <= 300:
        raise ValueError("réglages invalides")
    texte = "".join(cle.split()).replace("-", "").upper()
    try:
        secret = base64.b32decode(texte + "=" * (-len(texte) % 8))
    except ValueError:
        raise ValueError("clé invalide") from None
    if not secret:
        raise ValueError("clé vide")
    return dict(reglages, secret=secret)


def code(cle: str, instant: float | None = None) -> str:
    r = lire(cle)
    compteur = int((time.time() if instant is None else instant) // r["periode"])
    empreinte = hmac.new(r["secret"], struct.pack(">Q", compteur),
                         ALGORITHMES[r["algorithme"]]).digest()
    decalage = empreinte[-1] & 0x0F
    nombre = struct.unpack(">I", empreinte[decalage:decalage + 4])[0] & 0x7FFFFFFF
    return str(nombre % 10 ** r["chiffres"]).zfill(r["chiffres"])


def restant(cle: str, instant: float | None = None) -> int:
    """Secondes avant le prochain code."""
    periode = lire(cle)["periode"]
    return periode - int(time.time() if instant is None else instant) % periode


def valide(cle: str) -> bool:
    try:
        lire(cle)
        return True
    except ValueError:
        return False
