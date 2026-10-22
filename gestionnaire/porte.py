"""Porte locale de SecretLin : le remplissage rapide et l'extension de navigateur
demandent un identifiant à l'application ouverte par un socket Unix.

Le socket est rangé dans un dossier privé (droits 700, dans $XDG_RUNTIME_DIR) et chaque
connexion est contrôlée : seuls les programmes de l'utilisateur lui-même sont acceptés.
Une requête et une réponse par connexion, en JSON sur une ligne."""

import json
import os
import socket
import struct
import sys
import tempfile
import threading
from pathlib import Path

TAILLE_MAX = 64 * 1024


def disponible() -> bool:
    return sys.platform.startswith("linux") and hasattr(socket, "AF_UNIX")


def dossier() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base and Path(base).is_dir():
        return Path(base) / "secretlin"
    return Path(tempfile.gettempdir()) / f"secretlin-{os.getuid()}"


def chemin_socket() -> Path:
    return dossier() / "porte"


def _lire_ligne(conn) -> bytes:
    donnees = b""
    while not donnees.endswith(b"\n"):
        morceau = conn.recv(4096)
        if not morceau:
            break
        donnees += morceau
        if len(donnees) > TAILLE_MAX:
            raise ValueError("requête trop longue")
    return donnees


def demander(requete: dict, delai: float = 10.0) -> dict | None:
    """Envoie une requête à SecretLin. None si l'application n'est pas ouverte."""
    if not disponible():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(delai)
            s.connect(str(chemin_socket()))
            s.sendall(json.dumps(requete).encode("utf-8") + b"\n")
            reponse = json.loads(_lire_ligne(s).decode("utf-8"))
            return reponse if isinstance(reponse, dict) else None
    except (OSError, ValueError):
        return None


def _meme_utilisateur(conn) -> bool:
    """Vrai si le programme à l'autre bout tourne sous le même utilisateur (SO_PEERCRED)."""
    try:
        donnees = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", donnees)
    except (OSError, AttributeError):
        return False
    return uid == os.getuid()


class Porte:
    """Serveur : « traiter(requete) → reponse » est appelé dans un fil d'exécution à part."""

    def __init__(self, traiter):
        self.traiter = traiter
        self._socket = None

    def ouvrir(self) -> bool:
        """Ouvre la porte. Faux si une autre instance de SecretLin l'a déjà ouverte."""
        if not disponible():
            return False
        d = dossier()
        d.mkdir(mode=0o700, exist_ok=True)
        info = d.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            os.chmod(d, 0o700)
            if d.stat().st_uid != os.getuid():
                return False
        chemin = chemin_socket()
        if chemin.exists():
            if demander({"action": "etat"}, delai=2) is not None:
                return False
            chemin.unlink()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ancien = os.umask(0o177)
        try:
            s.bind(str(chemin))
        finally:
            os.umask(ancien)
        s.listen(8)
        self._socket = s
        threading.Thread(target=self._accepter, daemon=True).start()
        return True

    def fermer(self):
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None
                chemin_socket().unlink(missing_ok=True)

    def _accepter(self):
        while self._socket is not None:
            try:
                conn, _ = self._socket.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        with conn:
            conn.settimeout(30)
            try:
                if not _meme_utilisateur(conn):
                    return
                requete = json.loads(_lire_ligne(conn).decode("utf-8"))
                if not isinstance(requete, dict):
                    raise ValueError("requête invalide")
                reponse = self.traiter(requete)
            except (OSError, ValueError) as e:
                reponse = {"erreur": str(e)}
            try:
                conn.sendall(json.dumps(reponse).encode("utf-8") + b"\n")
            except OSError:
                pass
