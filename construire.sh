#!/bin/sh
# Fabrique l'application SecretLin et l'ajoute au menu des applications et au Bureau.
set -e
cd "$(dirname "$0")"

.venv/bin/pip install -q -r requirements.txt pyinstaller
.venv/bin/pyinstaller --noconfirm --onefile --windowed --name SecretLin \
    --collect-data customtkinter --hidden-import PIL._tkinter_finder \
    --add-data "gestionnaire/logos.zip:gestionnaire" lancer.py

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons"
cp dist/SecretLin "$HOME/.local/bin/SecretLin"
cp dist/SecretLin ./SecretLin
rm -rf build dist SecretLin.spec
.venv/bin/python -m gestionnaire.logo "$HOME/.local/share/icons/secretlin.png" 256

cat > "$HOME/.local/share/applications/secretlin.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SecretLin
Comment=Gestionnaire de mots de passe chiffré
Exec=$HOME/.local/bin/SecretLin
Icon=$HOME/.local/share/icons/secretlin.png
StartupWMClass=SecretLin
Terminal=false
Categories=Utility;Security;
EOF

BUREAU="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Bureau")"
cp "$HOME/.local/share/applications/secretlin.desktop" "$BUREAU/"
chmod +x "$BUREAU/secretlin.desktop"
gio set "$BUREAU/secretlin.desktop" metadata::trusted true 2>/dev/null || true

# Anciennes versions (nom « Gestionnaire MDP »)
rm -f "$HOME/.local/bin/GestionnaireMDP" "$HOME/.local/share/applications/gestionnaire-mdp.desktop" \
      "$BUREAU/gestionnaire-mdp.desktop" ./GestionnaireMDP
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "SecretLin installé : cherchez « SecretLin » dans le menu ou sur le Bureau."
