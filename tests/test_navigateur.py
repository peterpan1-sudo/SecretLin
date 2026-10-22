import base64
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from gestionnaire import hote_navigateur, navigateurs

EXTENSION = Path(__file__).resolve().parent.parent / "extension"


def test_messages_aller_retour():
    flux = io.BytesIO()
    hote_navigateur.ecrire_message(flux, {"action": "etat"})
    flux.seek(0)
    assert hote_navigateur.lire_message(flux) == {"action": "etat"}
    assert hote_navigateur.lire_message(flux) is None


def test_seules_les_actions_utiles_passent():
    recues = []

    def demander(m):
        recues.append(m)
        return {"ok": True}

    assert hote_navigateur.repondre({"action": "copier", "id": "x"}, demander) == \
        {"erreur": "action refusée"}
    assert hote_navigateur.repondre("pas un dict", demander) == {"erreur": "action refusée"}
    hote_navigateur.repondre({"action": "chercher", "adresse": "https://a.fr", "autre": 1}, demander)
    assert recues == [{"action": "chercher", "adresse": "https://a.fr"}]
    assert hote_navigateur.repondre({"action": "etat"}, lambda m: None) == {"erreur": "absent"}


def test_identifiant_chrome_fixe_par_la_cle():
    manifeste = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    empreinte = hashlib.sha256(base64.b64decode(manifeste["key"])).hexdigest()[:32]
    assert "".join("abcdefghijklmnop"[int(c, 16)] for c in empreinte) == navigateurs.ID_CHROME
    assert manifeste["browser_specific_settings"]["gecko"]["id"] == navigateurs.ID_FIREFOX
    assert "nativeMessaging" in manifeste["permissions"]


def test_traductions_de_l_extension_completes():
    dossier = EXTENSION / "_locales"
    reference = set(json.loads((dossier / "fr" / "messages.json").read_text(encoding="utf-8")))
    utilisees = set()
    for js in EXTENSION.glob("*.js"):
        texte = js.read_text(encoding="utf-8")
        utilisees |= set(re.findall(r'\bt\("(\w+)"', texte))
    assert utilisees and utilisees <= reference
    for langue in dossier.iterdir():
        assert set(json.loads((langue / "messages.json").read_text(encoding="utf-8"))) == \
            reference, langue.name


def test_installation_dans_les_navigateurs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "donnees"))
    (tmp_path / ".mozilla").mkdir()
    (tmp_path / ".config/chromium").mkdir(parents=True)
    assert sorted(navigateurs.installer(tmp_path)) == ["Chromium", "Firefox"]
    ff = json.loads((tmp_path / ".mozilla/native-messaging-hosts/fr.secretlin.navigateur.json")
                    .read_text())
    ch = json.loads((tmp_path / ".config/chromium/NativeMessagingHosts/"
                                "fr.secretlin.navigateur.json").read_text())
    assert ff["allowed_extensions"] == [navigateurs.ID_FIREFOX] and "allowed_origins" not in ff
    assert ch["allowed_origins"] == [f"chrome-extension://{navigateurs.ID_CHROME}/"]
    assert Path(ch["path"]).is_file() and ch["type"] == "stdio"


def test_paquet_firefox(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with zipfile.ZipFile(navigateurs.paquet_firefox()) as archive:
        noms = archive.namelist()
    assert "manifest.json" in noms and "_locales/ja/messages.json" in noms
