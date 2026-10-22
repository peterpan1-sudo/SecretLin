from gestionnaire import raccourci


def test_gnome(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    appels = []

    def executer(args):
        appels.append(args)
        return "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/']" \
            if args[1] == "get" else ""

    assert raccourci.installer(executer)
    liste = appels[1][-1]
    assert "custom0" in liste and raccourci.CHEMIN_GNOME in liste
    assert any(a[-2:] == ["binding", "'<Control><Alt>p'"] for a in appels)
    assert raccourci._gvariant("a 'b' \\c") == "'a \\'b\\' \\\\c'"
    assert any(a[-2] == "command" and "--remplissage" in a[-1] for a in appels)


def test_gnome_liste_vide(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    appels = []
    assert raccourci.installer(lambda a: appels.append(a) or ("@as []" if a[1] == "get" else ""))
    assert appels[1][-1] == str([raccourci.CHEMIN_GNOME])


def test_bureau_inconnu_ou_outil_absent(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert not raccourci.installer(lambda a: "")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "XFCE")

    def absent(_a):
        raise FileNotFoundError("xfconf-query")

    assert not raccourci.installer(absent)
