"""Connexion entre les navigateurs et SecretLin : déclaration du programme intermédiaire
(« native messaging host ») auprès de chaque navigateur installé, et préparation de
l'extension. Seule l'extension SecretLin (identifiant fixe) a le droit de le lancer."""

import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

from gestionnaire.hote_navigateur import NOM

ID_CHROME = "lmjcifimdkpbfbmdohapjgljfbcbacjd"  # fixé par la clé publique du manifeste
ID_FIREFOX = "secretlin@peterpan1-sudo.github.io"
RACINE = Path(__file__).resolve().parent.parent
INSTALLE = Path("/usr/share/secretlin")

# Navigateur → dossier (dans le dossier personnel) où il cherche les déclarations.
DOSSIERS_CHROMIUM = {
    "Google Chrome": ".config/google-chrome",
    "Chromium": ".config/chromium",
    "Brave": ".config/BraveSoftware/Brave-Browser",
    "Microsoft Edge": ".config/microsoft-edge",
    "Vivaldi": ".config/vivaldi",
    "Opera": ".config/opera",
}
DOSSIERS_FIREFOX = {
    "Firefox": ".mozilla",
    "LibreWolf": ".librewolf",
}


def dossier_donnees() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return Path(base) / "secretlin"


def dossier_extension() -> Path:
    installe = INSTALLE / "extension"
    return installe if installe.is_dir() else RACINE / "extension"


def programme_intermediaire() -> Path:
    """Programme lancé par les navigateurs : celui du paquet, sinon un petit script créé
    pour le code source."""
    installe = INSTALLE / "secretlin-navigateur"
    if installe.is_file():
        return installe
    script = dossier_donnees() / "secretlin-navigateur"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{RACINE / "navigateur.py"}" "$@"\n',
                      encoding="utf-8")
    script.chmod(0o700)
    return script


def declaration(chemin: Path, famille: str) -> dict:
    d = {"name": NOM, "description": "SecretLin", "path": str(chemin), "type": "stdio"}
    if famille == "firefox":
        d["allowed_extensions"] = [ID_FIREFOX]
    else:
        d["allowed_origins"] = [f"chrome-extension://{ID_CHROME}/"]
    return d


def installer(maison: Path | None = None) -> list[str]:
    """Déclare SecretLin auprès des navigateurs présents. Renvoie leurs noms."""
    maison = maison or Path.home()
    chemin = programme_intermediaire()
    installes = []
    for familles, sous_dossier in ((DOSSIERS_CHROMIUM, "NativeMessagingHosts"),
                                   (DOSSIERS_FIREFOX, "native-messaging-hosts")):
        famille = "firefox" if familles is DOSSIERS_FIREFOX else "chromium"
        for nom, dossier in familles.items():
            base = maison / dossier
            if not base.is_dir():
                continue
            cible = base / sous_dossier
            cible.mkdir(parents=True, exist_ok=True)
            (cible / f"{NOM}.json").write_text(
                json.dumps(declaration(chemin, famille), indent=2) + "\n", encoding="utf-8")
            installes.append(nom)
    return installes


def paquet_firefox() -> Path:
    """Fichier .xpi de l'extension (une archive zip), pour l'installer dans Firefox."""
    sortie = dossier_donnees() / "secretlin-firefox.xpi"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    source = dossier_extension()
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as archive:
        for fichier in sorted(source.rglob("*")):
            if fichier.is_file():
                archive.write(fichier, fichier.relative_to(source).as_posix())
    return sortie


def navigateurs_presents() -> list[str]:
    commandes = {"Firefox": ("firefox", "firefox-esr"), "Chromium": ("chromium",),
                 "Google Chrome": ("google-chrome", "google-chrome-stable"),
                 "Brave": ("brave-browser", "brave"), "Microsoft Edge": ("microsoft-edge",),
                 "Vivaldi": ("vivaldi",), "Opera": ("opera",)}
    return [nom for nom, cmds in commandes.items() if any(shutil.which(c) for c in cmds)]
