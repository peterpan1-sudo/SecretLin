"""Mots de passe apparus dans des fuites de données, via le service gratuit
Have I Been Pwned (« Pwned Passwords »).

Le mot de passe n'est jamais envoyé : seuls les 5 premiers caractères de son empreinte
SHA-1 partent sur Internet (méthode « k-anonymat »). Le service renvoie toutes les
empreintes connues qui commencent ainsi (plusieurs centaines, complétées par des
fausses grâce à « Add-Padding »), et la comparaison se fait ici, sur l'ordinateur."""

import hashlib
import urllib.request

ADRESSE = "https://api.pwnedpasswords.com/range/"
DELAI_S = 10


def empreinte(mot_de_passe: str) -> str:
    return hashlib.sha1(mot_de_passe.encode("utf-8")).hexdigest().upper()


def _telecharger(prefixe: str) -> str:
    requete = urllib.request.Request(ADRESSE + prefixe,
                                     headers={"User-Agent": "SecretLin", "Add-Padding": "true"})
    with urllib.request.urlopen(requete, timeout=DELAI_S) as reponse:
        return reponse.read().decode("utf-8")


def verifier(mots_de_passe, telecharger=_telecharger) -> dict[str, int]:
    """Nombre de fuites où apparaît chaque mot de passe (0 : aucune). Une seule requête par
    début d'empreinte. OSError si le service ne répond pas."""
    empreintes = {mdp: empreinte(mdp) for mdp in set(mots_de_passe) if mdp}
    connues = {}
    for prefixe in {e[:5] for e in empreintes.values()}:
        for ligne in telecharger(prefixe).splitlines():
            suite, _, nombre = ligne.strip().partition(":")
            if nombre.isdigit() and int(nombre) > 0:
                connues[prefixe + suite.upper()] = int(nombre)
    return {mdp: connues.get(e, 0) for mdp, e in empreintes.items()}
