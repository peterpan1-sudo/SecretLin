"""Intermédiaire entre l'extension de navigateur et SecretLin (« native messaging »).

Le navigateur lance ce programme et lui écrit des messages (longueur sur 4 octets puis
JSON) ; chacun est transmis à SecretLin par la porte locale, et la réponse renvoyée de la
même façon. Seules les demandes utiles à l'extension passent."""

import json
import struct
import sys

from gestionnaire import porte

NOM = "fr.secretlin.navigateur"
ACTIONS = {"etat", "chercher", "pin", "identifiants", "montrer"}
TAILLE_MAX = 64 * 1024


def lire_message(flux):
    entete = flux.read(4)
    if len(entete) < 4:
        return None
    taille = struct.unpack("<I", entete)[0]
    if taille > TAILLE_MAX:
        raise ValueError("message trop long")
    return json.loads(flux.read(taille).decode("utf-8"))


def ecrire_message(flux, message):
    donnees = json.dumps(message).encode("utf-8")
    flux.write(struct.pack("<I", len(donnees)) + donnees)
    flux.flush()


def repondre(message, demander=porte.demander) -> dict:
    if not isinstance(message, dict) or message.get("action") not in ACTIONS:
        return {"erreur": "action refusée"}
    if message["action"] == "chercher":
        # L'extension cherche par adresse de page, ou par texte depuis son menu.
        message = {k: v for k, v in message.items() if k in ("action", "adresse", "texte")}
    reponse = demander(message)
    return reponse if reponse is not None else {"erreur": "absent"}


def main():
    entree, sortie = sys.stdin.buffer, sys.stdout.buffer
    while True:
        try:
            message = lire_message(entree)
        except (ValueError, UnicodeDecodeError):
            return
        if message is None:
            return
        ecrire_message(sortie, repondre(message))


if __name__ == "__main__":
    main()
