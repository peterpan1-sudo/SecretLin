# SecretLin

Gestionnaire de mots de passe sécurisé.

Application de bureau pour ranger ses identifiants (site, nom d'utilisateur, mot de passe),
classés par ordre alphabétique et protégés par un mot de passe maître.

## Lancer l'application

```
.venv/bin/python lancer.py
```

## Sécurité

- Coffre chiffré en AES-256-GCM ; clé dérivée du mot de passe maître avec Argon2id.
- Le mot de passe maître n'est jamais enregistré : s'il est perdu, le coffre est irrécupérable.
- Toute modification du fichier du coffre est détectée.
- Délai croissant après plusieurs mauvais essais.
- Verrouillage automatique : 30 s sans bouger la souris sur la fenêtre, ou 15 s avec la souris en dehors.
- Presse-papier vidé 20 secondes après la copie d'un mot de passe.

Le coffre est stocké dans `~/.local/share/GestionnaireMDP/coffre.vault`
(Windows : `%APPDATA%\GestionnaireMDP\coffre.vault`).

## Logos des marques

Les logos des sites (Discord, Netflix, Steam…) proviennent de [Simple Icons](https://simpleicons.org)
(licence CC0) et sont intégrés dans `gestionnaire/logos.zip` : rien n'est téléchargé à l'utilisation.
Pour les régénérer : `python outils/preparer_logos.py <dossier package de simple-icons>`.
Les marques citées appartiennent à leurs propriétaires respectifs.

## Licence

Ce projet est distribué sous licence [MIT](LICENSE).
