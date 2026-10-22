"""Raccourci clavier global du remplissage rapide (Ctrl+Alt+P), ajouté aux raccourcis
personnalisés du bureau : GNOME ou Xfce. Sous Wayland, une application ne peut pas
écouter le clavier quand elle n'a pas la main : c'est le bureau qui lance la commande."""

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

NOM = "SecretLin"
TOUCHES_GNOME = "<Control><Alt>p"
TOUCHES_XFCE = "<Primary><Alt>p"
SCHEMA_GNOME = "org.gnome.settings-daemon.plugins.media-keys"
CHEMIN_GNOME = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/secretlin/"


def commande() -> str:
    """Commande lancée par le raccourci : celle de la version de SecretLin qui l'installe
    (le programme installé, ou le code source lancé depuis son dossier). Une autre version,
    plus ancienne, ne connaîtrait peut-être pas le remplissage rapide."""
    racine = Path(__file__).resolve().parent.parent
    if racine == Path("/usr/share/secretlin") and shutil.which("secretlin"):
        return "secretlin --remplissage"
    return f'"{sys.executable}" "{racine / "lancer.py"}" --remplissage'


def bureau() -> str:
    nom = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "GNOME" in nom or "UNITY" in nom or "BUDGIE" in nom:
        return "gnome"
    if "XFCE" in nom:
        return "xfce"
    return ""


def _gvariant(texte: str) -> str:
    """Texte écrit comme gsettings l'attend (sinon des guillemets dans la commande, utiles
    pour un dossier avec des espaces, sont refusés)."""
    return "'" + texte.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _executer(arguments) -> str:
    return subprocess.run(arguments, check=True, capture_output=True, text=True,
                          timeout=10).stdout.strip()


def installer(executer=_executer) -> bool:
    """Ajoute le raccourci. Faux si le bureau n'est pas pris en charge ou si l'outil de
    réglage manque (l'utilisateur crée alors le raccourci lui-même)."""
    try:
        if bureau() == "gnome":
            liste = executer(["gsettings", "get", SCHEMA_GNOME, "custom-keybindings"])
            chemins = ast.literal_eval(liste.removeprefix("@as ").strip() or "[]")
            if CHEMIN_GNOME not in chemins:
                chemins.append(CHEMIN_GNOME)
                executer(["gsettings", "set", SCHEMA_GNOME, "custom-keybindings", str(chemins)])
            schema = f"{SCHEMA_GNOME}.custom-keybinding:{CHEMIN_GNOME}"
            for cle, valeur in (("name", NOM), ("command", commande()),
                                ("binding", TOUCHES_GNOME)):
                executer(["gsettings", "set", schema, cle, _gvariant(valeur)])
            return True
        if bureau() == "xfce":
            executer(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p",
                      f"/commands/custom/{TOUCHES_XFCE}", "-n", "-t", "string", "-s", commande()])
            return True
    except (OSError, subprocess.SubprocessError, ValueError, SyntaxError):
        return False
    return False
