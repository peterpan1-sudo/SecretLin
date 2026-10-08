# SecretLin

Gestionnaire de mots de passe sécurisé.

Application de bureau pour ranger ses identifiants (site, nom d'utilisateur, mot de passe),
classés par ordre alphabétique et protégés par un mot de passe maître.

## Installation sur Kali Linux / Debian

Télécharger les 3 fichiers `.deb` de la [dernière version](https://github.com/peterpan1-sudo/SecretLin/releases/latest)
(SecretLin et les bibliothèques `customtkinter` et `darkdetect`, absentes des dépôts), puis dans le dossier du téléchargement :

```
sudo apt install ./python3-darkdetect_*_all.deb ./python3-customtkinter_*_all.deb ./secretlin_*_all.deb
```

Lancer ensuite `secretlin`, ou chercher « SecretLin » dans le menu des applications.

Pour construire le paquet soi-même : `dpkg-buildpackage -us -uc -b` (dossier `debian/`).

## Lancer depuis le code

```
.venv/bin/python lancer.py
```

## Compatibilité

| Système | État |
|---|---|
| Linux | Testé (Kali Linux). Paquet `.deb` disponible (voir plus haut). `./construire.sh` crée l'exécutable `SecretLin` et l'ajoute au menu et au Bureau. |
| Windows, macOS | Non testé. Devrait fonctionner en lançant le code avec Python, sans garantie. `construire.sh` ne fonctionne que sous Linux. |

Pour lancer depuis le code (Python 3 avec Tkinter requis) :

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python lancer.py
```

Sous Windows, remplacer `.venv/bin/` par `.venv\Scripts\`.

## Sécurité

- Coffre chiffré en AES-256-GCM ; clé dérivée du mot de passe maître avec Argon2id.
- Le mot de passe maître n'est jamais enregistré : s'il est perdu, le coffre est irrécupérable.
- Toute modification du fichier du coffre est détectée.
- Après 3 mauvais essais, attente de 1 min, puis 3, 5, 10, 15, 30 min et 1 h ; conservée même si on ferme et relance SecretLin.
- Verrouillage automatique : 5 min sans bouger la souris sur la fenêtre, ou 2 min avec la souris en dehors.
- Presse-papier vidé 20 secondes après la copie d'un mot de passe.

Le coffre est stocké dans `~/.local/share/GestionnaireMDP/coffre.vault`
(Windows : `%APPDATA%\GestionnaireMDP\coffre.vault`).
Avant chaque enregistrement, la version précédente est copiée à côté dans
`coffre.vault.bak`. À chaque déverrouillage, une copie datée est aussi rangée dans
le sous-dossier `sauvegardes/` (les 5 plus récentes sont gardées, et aucune copie
n'est refaite si le coffre n'a pas changé). Toutes ces copies restent chiffrées.

Le bouton « Sauvegarde » de l'écran principal permet de :
- **exporter** le coffre dans un fichier chiffré avec un mot de passe d'export
  distinct, enregistré à l'endroit de votre choix (clé USB, autre disque…) ;
- **importer** un tel fichier : les entrées déjà présentes à l'identique sont ignorées ;
- **restaurer** l'une des copies automatiques. Le coffre actuel devient alors la copie
  « avant le dernier enregistrement » : la restaurer annule l'opération.

## Logos des marques

Les logos des sites (Discord, Netflix, Steam…) proviennent de [Simple Icons](https://simpleicons.org)
(licence CC0) et sont intégrés dans `gestionnaire/logos.zip` : rien n'est téléchargé à l'utilisation.
Pour les régénérer : `python outils/preparer_logos.py <dossier package de simple-icons>`.
Les marques citées appartiennent à leurs propriétaires respectifs.

## Licence

Ce projet est distribué sous licence [MIT](LICENSE).
