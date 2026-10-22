from gestionnaire import langue, tuto_video


def test_le_tutoriel_se_dessine_dans_chaque_langue():
    try:
        for code in langue.LANGUES:
            langue.choisir(code)
            film = tuto_video.images()
            assert len(film) > 100 and all(d > 0 for _, d in film)
            assert film[0][0].size == (tuto_video.L, tuto_video.H)
    finally:
        langue.choisir("fr")
