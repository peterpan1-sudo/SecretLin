import base64

import pytest

from gestionnaire import totp

# Exemples officiels de la RFC 6238 (annexe B), codes à 8 chiffres.
SECRET_SHA1 = base64.b32encode(b"12345678901234567890").decode()
SECRET_SHA256 = base64.b32encode(b"12345678901234567890123456789012").decode()


@pytest.mark.parametrize("instant, attendu", [(59, "94287082"), (1111111109, "07081804"),
                                              (1234567890, "89005924"), (2000000000, "69279037")])
def test_exemples_rfc_6238(instant, attendu):
    cle = f"otpauth://totp/Exemple?secret={SECRET_SHA1}&digits=8"
    assert totp.code(cle, instant) == attendu


def test_sha256():
    cle = f"otpauth://totp/Exemple?secret={SECRET_SHA256}&digits=8&algorithm=SHA256"
    assert totp.code(cle, 59) == "46119246"


def test_cle_simple_six_chiffres():
    cle = SECRET_SHA1.lower()[:16] + " " + SECRET_SHA1.lower()[16:]  # espaces et minuscules
    assert totp.code(cle, 59) == "287082"
    assert totp.code(SECRET_SHA1, 59) == "287082"
    assert totp.restant(SECRET_SHA1, 59) == 1
    assert totp.restant(SECRET_SHA1, 60) == 30


@pytest.mark.parametrize("cle", ["", "pas une clé !", "otpauth://hotp/x?secret=GEZDGNBV",
                                 "otpauth://totp/x?secret=GEZDGNBV&digits=12",
                                 "otpauth://totp/x?secret=GEZDGNBV&algorithm=MD5"])
def test_cles_invalides(cle):
    assert not totp.valide(cle)
    with pytest.raises(ValueError):
        totp.code(cle)
