"""Convertit les icônes Simple Icons (CC0) en masques PNG utilisés par l'application.

Usage : python outils/preparer_logos.py <dossier « package » de simple-icons>
Source : https://registry.npmjs.org/simple-icons/-/simple-icons-<version>.tgz
"""

import io
import json
import sys
import zipfile
from pathlib import Path

import cairosvg
from PIL import Image

TAILLE = 96


def main(source: Path):
    destination = Path(__file__).resolve().parent.parent / "gestionnaire" / "logos.zip"
    donnees = json.loads((source / "data" / "simple-icons.json").read_text(encoding="utf-8"))
    index = {}
    archive = zipfile.ZipFile(destination, "w", zipfile.ZIP_STORED)
    for icone in donnees:
        slug = icone["slug"]
        svg = source / "icons" / f"{slug}.svg"
        if not svg.exists():
            continue
        png = cairosvg.svg2png(url=str(svg), output_width=TAILLE, output_height=TAILLE)
        # On ne garde que la forme (canal alpha) : la couleur est appliquée à l'affichage.
        sortie = io.BytesIO()
        Image.open(io.BytesIO(png)).getchannel("A").save(sortie, "PNG", optimize=True)
        archive.writestr(f"{slug}.png", sortie.getvalue())
        index[slug] = {
            "titre": icone["title"],
            "couleur": icone["hex"],
            "alias": icone.get("aliases", {}).get("aka", []),
        }
    archive.writestr("index.json", json.dumps(index, ensure_ascii=False))
    archive.close()
    print(f"{len(index)} logos générés dans {destination}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
