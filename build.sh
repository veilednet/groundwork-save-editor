#!/usr/bin/env bash
# ------------------------------------------------------------
# Build a standalone macOS app for Groundwork Save Editor
# ------------------------------------------------------------
# 1️⃣  Change to the directory where this script lives
# 2️⃣  Install the required Python packages (pyinstaller + deps)
# 3️⃣  Run PyInstaller with macOS-specific flags
# ------------------------------------------------------------

set -e   # abort on any error

# Resolve the script's own directory (so relative paths work)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 1️⃣ Install dependencies ---------------------------------
python3 -m pip install -r requirements.txt pyinstaller

# ---- 2️⃣ Build the app ----------------------------------------
#   --onefile      : bundle everything into a single executable
#   --windowed    : hide the terminal window (GUI app)
#   --name         : name of the app bundle
#   --icon         : macOS icon (must be .icns)
#   --add-data     : include the icon file inside the bundle
#   --collect-all  : pull in all customtkinter resources
#   --exclude-module pkg_resources : avoid unnecessary modules
pyinstaller \
  --noconfirm \
  --onefile \
  --windowed \
  --name "Groundwork Save Editor" \
  --icon "media/icon.icns" \
  --add-data "media/icon.icns:media" \
  --collect-all customtkinter \
  --exclude-module pkg_resources \
  app.py

# ------------------------------------------------------------
echo "✅ macOS build complete."
echo "📦 The app is located at: ./dist/Groundwork Save Editor.app"