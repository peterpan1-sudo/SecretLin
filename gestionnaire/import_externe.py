"""Lecture des fichiers CSV exportés par d'autres gestionnaires de mots de passe et par
les navigateurs. La source est reconnue d'après les noms de colonnes."""

import csv
from pathlib import Path
from urllib.parse import urlsplit

from gestionnaire.langue import t

# (nom de la source, colonnes qui la reconnaissent, colonnes de chaque champ : la première
# présente est utilisée). Les noms de colonnes sont comparés en minuscules.
FORMATS = [
    ("Bitwarden", {"login_uri", "login_password"},
     dict(site=("name",), url=("login_uri",), utilisateur=("login_username",),
          mot_de_passe=("login_password",), notes=("notes",), categorie=("folder",),
          favori=("favorite",))),
    ("KeePass", {"title", "group", "password"},
     dict(site=("title",), url=("url",), utilisateur=("username",), mot_de_passe=("password",),
          notes=("notes",), categorie=("group",))),
    ("KeePass", {"account", "login name"},
     dict(site=("account",), url=("web site",), utilisateur=("login name",),
          mot_de_passe=("password",), notes=("comments",))),
    ("1Password", {"title", "otpauth"},
     dict(site=("title",), url=("url",), utilisateur=("username",), mot_de_passe=("password",),
          notes=("notes",), categorie=("tags",), favori=("favorite",))),
    ("LastPass", {"grouping", "extra"},
     dict(site=("name",), url=("url",), utilisateur=("username",), mot_de_passe=("password",),
          notes=("extra",), categorie=("grouping",), favori=("fav",))),
    ("Firefox", {"httprealm", "formactionorigin"},
     dict(site=(), url=("url",), utilisateur=("username",), mot_de_passe=("password",), notes=())),
    ("Chrome", {"name", "url", "username", "password"},
     dict(site=("name",), url=("url",), utilisateur=("username",), mot_de_passe=("password",),
          notes=("note",))),
    # Tout autre CSV avec une colonne « password » (ou « mot de passe »).
    ("CSV", {"password"},
     dict(site=("name", "title", "site"), url=("url", "website", "uri"),
          utilisateur=("username", "login", "user"), mot_de_passe=("password",),
          notes=("notes", "note", "comments"))),
    ("CSV", {"mot de passe"},
     dict(site=("nom", "site", "titre"), url=("url", "adresse"),
          utilisateur=("utilisateur", "identifiant", "nom d'utilisateur"),
          mot_de_passe=("mot de passe",), notes=("notes", "note"))),
]


# Groupe racine de KeePass : ce n'est pas une vraie catégorie.
GROUPES_RACINE = {"root", "racine", "passwords", "database"}
VRAI = {"1", "true", "yes", "oui"}


class FormatInconnu(ValueError):
    pass


def nom_depuis_url(url: str) -> str:
    """« https://www.netflix.com/login » → « netflix.com »."""
    hote = urlsplit(url if "://" in url else "https://" + url).hostname or ""
    return hote.removeprefix("www.")


def lire(chemin: Path) -> tuple[str, list[dict]]:
    """Nom de la source et identifiants trouvés (site, utilisateur, email, mot_de_passe,
    notes). Les lignes sans mot de passe sont ignorées."""
    try:
        texte = Path(chemin).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        texte = Path(chemin).read_text(encoding="latin-1")
    lignes = list(csv.reader(texte.splitlines()))
    if not lignes:
        raise FormatInconnu(t("Ce fichier est vide."))
    colonnes = [c.strip().casefold() for c in lignes[0]]
    for source, reperes, champs in FORMATS:
        if reperes <= set(colonnes):
            break
    else:
        raise FormatInconnu(t("Ce fichier n'est pas un export CSV reconnu."))

    def valeur(ligne, noms):
        for nom in noms:
            if nom in colonnes:
                i = colonnes.index(nom)
                if i < len(ligne) and ligne[i].strip():
                    return ligne[i].strip()
        return ""

    entrees = []
    type_bitwarden = "type" in colonnes and source == "Bitwarden"
    for ligne in lignes[1:]:
        if type_bitwarden and valeur(ligne, ("type",)) not in ("", "login"):
            continue
        mdp = next((ligne[colonnes.index(n)] for n in champs["mot_de_passe"]
                    if n in colonnes and colonnes.index(n) < len(ligne)), "")
        if not mdp:
            continue
        url = valeur(ligne, champs["url"])
        site = valeur(ligne, champs["site"]) or nom_depuis_url(url) or t("Sans nom")
        utilisateur = valeur(ligne, champs["utilisateur"])
        email = ""
        if "@" in utilisateur and " " not in utilisateur:
            email, utilisateur = utilisateur, ""
        notes = valeur(ligne, champs["notes"])
        if url and url not in notes and nom_depuis_url(url) != site:
            notes = (url + "\n" + notes).strip()
        categorie = valeur(ligne, champs.get("categorie", ())).split("/")[-1].strip()
        if categorie.casefold() in GROUPES_RACINE:
            categorie = ""
        favori = valeur(ligne, champs.get("favori", ())).casefold() in VRAI
        entrees.append(dict(site=site, utilisateur=utilisateur, email=email, mot_de_passe=mdp,
                            notes=notes, categorie=categorie, favori=favori))
    return source, entrees
