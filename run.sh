#!/usr/bin/env bash
# ------------------------------------------------------------
# Run the Groundwork Save Editor on macOS
# ------------------------------------------------------------
# If the app has already been built, open it with Finder.
# If not, remind the user to run build.sh first.
# ------------------------------------------------------------

set -e

APP_BUNDLE="dist/Groundwork Save Editor.app"

if [ ! -d "$APP_BUNDLE" ]; then
  echo "❌ The app has not been built yet."
  echo "🛠️  Run './build.sh' to create the macOS bundle."
  exit 1
fi

# Use `open` to launch the app in the default way (double-clickable)
open "$APP_BUNDLE"