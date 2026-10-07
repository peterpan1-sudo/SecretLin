"""Logo SecretLin dessiné par le code : cadenas argenté enlacé par une lame bleue
en forme de queue de dragon (clin d'œil au style Kali Linux)."""

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

BLEU_CLAIR = (120, 170, 255)
BLEU = (47, 111, 237)
BLEU_FONCE = (22, 52, 140)
ARGENT_CLAIR = (246, 246, 250)
ARGENT_FONCE = (150, 150, 162)
NOIR = (11, 11, 13)


def _degrade(taille, haut, bas, horizontal=False):
    l, h = taille
    masque = Image.linear_gradient("L").resize((l, h))
    if horizontal:
        masque = masque.rotate(90, expand=False)
    return Image.composite(Image.new("RGBA", taille, bas + (255,)),
                           Image.new("RGBA", taille, haut + (255,)), masque)


def _remplir(image, forme, haut, bas, horizontal=False):
    """Peint le masque `forme` avec un dégradé."""
    image.paste(_degrade(image.size, haut, bas, horizontal), (0, 0), forme)


def _bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d
                 for a, b, c, d in zip(p0, p1, p2, p3))


def _lame(s, points, largeur, pointe=0.85):
    """Polygone effilé qui suit une courbe de Bézier : épais au milieu, pointu aux bouts."""
    n = 80
    centre = [_bezier(*points, i / n) for i in range(n + 1)]
    gauche, droite = [], []
    for i, (x, y) in enumerate(centre):
        a = centre[max(i - 1, 0)]
        b = centre[min(i + 1, n)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        norme = math.hypot(dx, dy) or 1
        nx, ny = -dy / norme, dx / norme
        t = i / n
        w = largeur * s * (math.sin(math.pi * t) ** pointe) / 2
        gauche.append((x * s + nx * w, y * s + ny * w))
        droite.append((x * s - nx * w, y * s - ny * w))
    return gauche + droite[::-1]


def _pics(dessin, s, points, largeur):
    """Pics dorsaux de dragon, inclinés vers la queue, sur le bord extérieur de la lame."""
    for t, hauteur in ((0.30, 4.0), (0.40, 5.0), (0.50, 5.5), (0.60, 5.0), (0.70, 4.0)):
        x, y = _bezier(*points, t)
        x2, y2 = _bezier(*points, t + 0.01)
        tx, ty = x2 - x, y2 - y
        norme = math.hypot(tx, ty)
        tx, ty = tx / norme, ty / norme
        nx, ny = ty, -tx  # côté extérieur de la courbe
        bord = largeur * (math.sin(math.pi * t) ** 0.85) / 2 - 0.5
        bx, by = x + nx * bord, y + ny * bord
        base = 2.6
        dessin.polygon([
            ((bx - tx * base) * s, (by - ty * base) * s),
            ((bx + tx * base) * s, (by + ty * base) * s),
            ((bx + nx * hauteur - tx * hauteur * 0.8) * s, (by + ny * hauteur - ty * hauteur * 0.8) * s),
        ], fill=255)


def _arrondi(dessin, boite, rayon, **kw):
    dessin.rounded_rectangle(boite, radius=rayon, **kw)


@lru_cache(maxsize=32)
def dessiner(taille=256, fond=True, ouverture=0.0) -> Image.Image:
    """Logo en RGBA. `ouverture` (0 à 1) soulève l'anse du cadenas."""
    ss = 4  # sur-échantillonnage pour des bords lisses
    S = taille * ss
    s = S / 100  # le dessin est pensé sur une grille de 100 × 100
    image = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    if fond:
        masque = Image.new("L", (S, S), 0)
        _arrondi(ImageDraw.Draw(masque), (2 * s, 2 * s, 98 * s, 98 * s), 22 * s, fill=255)
        _remplir(image, masque, (30, 32, 40), NOIR)
        # Lueur bleue diffuse derrière le cadenas
        lueur = Image.new("L", (S, S), 0)
        ImageDraw.Draw(lueur).ellipse((22 * s, 28 * s, 78 * s, 84 * s), fill=90)
        lueur = lueur.filter(ImageFilter.GaussianBlur(14 * s))
        couche = Image.new("RGBA", (S, S), BLEU + (0,))
        couche.putalpha(Image.composite(lueur, Image.new("L", (S, S), 0), masque))
        image.alpha_composite(couche)
        bord = Image.new("L", (S, S), 0)
        _arrondi(ImageDraw.Draw(bord), (2 * s, 2 * s, 98 * s, 98 * s), 22 * s, outline=255,
                 width=max(1, round(0.8 * s)))
        image.paste((70, 72, 84, 255), (0, 0), bord)

    # Queue de dragon : deux lames bleues qui s'enroulent autour du cadenas
    for points, largeur, haut, bas in (
        (((14, 86), (4, 50), (40, 8), (86, 14)), 9.0, BLEU_CLAIR, BLEU_FONCE),
        (((22, 92), (30, 70), (70, 76), (90, 40)), 5.5, BLEU, BLEU_FONCE),
    ):
        forme = Image.new("L", (S, S), 0)
        dessin = ImageDraw.Draw(forme)
        dessin.polygon(_lame(s, points, largeur), fill=255)
        if largeur > 8:
            _pics(dessin, s, points, largeur)
        _remplir(image, forme, haut, bas)

    # Anse du cadenas
    dy = -9 * ouverture * s
    anse = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(anse)
    ep = 6.5 * s
    d.arc((37 * s, 24 * s + dy, 63 * s, 50 * s + dy), 180, 360, fill=255, width=round(ep))
    d.rectangle((37 * s, 37 * s + dy, 37 * s + ep, 50 * s + dy), fill=255)
    d.rectangle((63 * s - ep, 37 * s + dy, 63 * s, 50 * s + dy), fill=255)
    _remplir(image, anse, ARGENT_CLAIR, ARGENT_FONCE, horizontal=True)

    # Ombre puis corps du cadenas
    ombre = Image.new("L", (S, S), 0)
    _arrondi(ImageDraw.Draw(ombre), (31 * s, 49 * s, 69 * s, 79 * s), 7 * s, fill=150)
    ombre = ombre.filter(ImageFilter.GaussianBlur(2.5 * s))
    couche = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    couche.putalpha(ombre)
    image.alpha_composite(couche, (0, round(1.5 * s)))

    corps = Image.new("L", (S, S), 0)
    _arrondi(ImageDraw.Draw(corps), (30 * s, 47 * s, 70 * s, 77 * s), 7 * s, fill=255)
    _remplir(image, corps, ARGENT_CLAIR, ARGENT_FONCE)

    # Serrure en forme de flèche (pointe vers le bas, comme une goutte effilée)
    d = ImageDraw.Draw(image)
    d.ellipse((45.5 * s, 54 * s, 54.5 * s, 63 * s), fill=NOIR)
    d.polygon([(46.8 * s, 60 * s), (53.2 * s, 60 * s), (50 * s, 71 * s)], fill=NOIR)
    d.ellipse((48.2 * s, 56.6 * s, 51.8 * s, 60.2 * s), fill=BLEU)

    return image.resize((taille, taille), Image.LANCZOS)


if __name__ == "__main__":
    import sys
    dessiner(int(sys.argv[2]) if len(sys.argv) > 2 else 256).save(sys.argv[1])
