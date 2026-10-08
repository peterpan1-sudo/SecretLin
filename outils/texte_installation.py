"""Réécrit la section « Installation » des notes d'une version GitHub.

La commande de mise à jour télécharge elle-même le paquet : elle marche quel que
soit le dossier où l'on se trouve, sans téléchargement préalable dans le navigateur.

Usage : python3 outils/texte_installation.py <tag, ex. v1.1.2> <fichier de notes>
Le fichier est modifié sur place ; la CI le renvoie ensuite à GitHub.
"""

import sys
from pathlib import Path

DEPOT = "peterpan1-sudo/SecretLin"
TITRE = "### Installation"


def section(tag: str) -> str:
    version = tag.removeprefix("v")
    paquet = f"secretlin_{version}_all.deb"
    url = f"https://github.com/{DEPOT}/releases/download/{tag}/{paquet}"
    return f"""{TITRE}
Mise à jour depuis une version précédente : copier cette commande dans un terminal. Elle télécharge le paquet puis l'installe, quel que soit le dossier où l'on se trouve.

```
cd /tmp && wget -N {url} && sudo apt install ./{paquet}
```

Première installation : télécharger les 3 fichiers `.deb` ci-dessous, ouvrir un terminal dans le dossier où ils sont (souvent `cd ~/Téléchargements`), puis :

```
sudo apt install ./python3-darkdetect_0.8.0-1_all.deb ./python3-customtkinter_6.0.0-1_all.deb ./{paquet}
```

Le coffre existant (`~/.local/share/GestionnaireMDP/coffre.vault`) est conservé.
"""


def reecrire(notes: str, tag: str) -> str:
    """Remplace tout ce qui suit « ### Installation » (ou l'ajoute à la fin)."""
    notes = notes.replace("\r\n", "\n")
    debut = notes.find(TITRE)
    avant = notes[:debut] if debut >= 0 else notes
    avant = avant.rstrip() + "\n\n" if avant.strip() else ""
    return avant + section(tag)


if __name__ == "__main__":
    tag, chemin = sys.argv[1], Path(sys.argv[2])
    chemin.write_text(reecrire(chemin.read_text(encoding="utf-8"), tag), encoding="utf-8")
