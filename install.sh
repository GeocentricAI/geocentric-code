#!/usr/bin/env bash
# Installs Geocentric: fetches the latest release build from GitHub, installs
# the Python engine it needs into a private virtualenv, makes sure Ollama is
# available, and points the app at all of it. Safe to re-run to upgrade.
#
#   curl -fsSL https://raw.githubusercontent.com/KiwiOnGit/Geocentric-Code/main/install.sh | bash
#
set -euo pipefail

REPO="KiwiOnGit/Geocentric-Code"
BUNDLE_ID="local.geocentric.app"
ENGINE_ROOT="$HOME/Library/Application Support/Geocentric"
PROJECT_ROOT_DEFAULT="$HOME/Documents"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "Geocentric is a macOS app - this installer won't help on $(uname -s)."
[[ "$(uname -m)" == "arm64" ]] || warn "This installer targets Apple Silicon; an Intel Mac may not have a matching release build."

# ---------------------------------------------------------------- find the release
say "Looking up the latest release of $REPO..."
RELEASE_JSON="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest")" \
    || die "Couldn't reach the GitHub API. Check your connection and try again."
TAG="$(printf '%s' "$RELEASE_JSON" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)"
APP_ZIP_URL="$(printf '%s' "$RELEASE_JSON" | sed -n 's/.*"browser_download_url": *"\([^"]*\.app\.zip\)".*/\1/p' | head -1)"
[[ -n "$TAG" ]] || die "Couldn't find a release tag - is $REPO public and does it have a published release?"
[[ -n "$APP_ZIP_URL" ]] || die "Release $TAG has no *.app.zip asset attached."
say "Found $TAG"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# ---------------------------------------------------------------------- the app
say "Downloading the app..."
curl -fsSL "$APP_ZIP_URL" -o "$WORKDIR/app.zip"
unzip -q "$WORKDIR/app.zip" -d "$WORKDIR"
APP_BUNDLE="$(find "$WORKDIR" -maxdepth 1 -iname '*.app' | head -1)"
[[ -n "$APP_BUNDLE" ]] || die "The downloaded zip didn't contain a .app bundle."

if [[ -w /Applications ]]; then
    INSTALL_DIR="/Applications"
else
    INSTALL_DIR="$HOME/Applications"
    mkdir -p "$INSTALL_DIR"
fi
DEST="$INSTALL_DIR/$(basename "$APP_BUNDLE")"
say "Installing to $DEST..."
rm -rf "$DEST"
cp -R "$APP_BUNDLE" "$DEST"

# A fresh download is quarantined by Gatekeeper and unsigned (or signed by
# someone else's ad-hoc identity, which doesn't count as "yours" either way).
# Left in place, quarantine can make Gatekeeper run the app from a randomized,
# read-only translocated copy instead of $DEST - on some Macs that's just a
# "damaged, move to Trash" error, on others it's silently there and breaks
# anything that expects to find its own bundle contents at a normal path.
# `cp -R` above preserves xattrs, so this isn't optional cleanup - verify it
# actually took rather than assuming.
xattr -cr "$DEST" 2>/dev/null
if xattr -p com.apple.quarantine "$DEST" >/dev/null 2>&1; then
    warn "Quarantine flag is still set on $DEST after clearing it once."
    warn "The app may run from a Gatekeeper-translocated copy - if anything looks off, quit it and run: xattr -cr \"$DEST\""
fi
codesign --force --deep --sign - "$DEST" 2>/dev/null || warn "Ad-hoc codesign failed - the app may refuse to open until you right-click → Open it once."

# ------------------------------------------------------------------ the engine
say "Setting up the Python engine..."
command -v python3 >/dev/null 2>&1 || die "python3 not found. Install it (Xcode Command Line Tools: xcode-select --install) and re-run this script."

# The app carries its own copy of the Python backend as a bundled resource
# (Contents/Resources/*.bundle/PythonEngine) specifically so this installer -
# and a plain double-click on a fresh download - never depend on the repo
# itself containing source.
BUNDLED_ENGINE="$(find "$DEST/Contents/Resources" -maxdepth 2 -type d -name PythonEngine | head -1)"
[[ -n "$BUNDLED_ENGINE" && -d "$BUNDLED_ENGINE/geocentric" ]] \
    || die "This build doesn't have the Python engine bundled - it may predate that change. Re-download the latest release."

mkdir -p "$ENGINE_ROOT"
rm -rf "$ENGINE_ROOT/geocentric"
cp -R "$BUNDLED_ENGINE/geocentric" "$ENGINE_ROOT/geocentric"
[[ -f "$BUNDLED_ENGINE/pyproject.toml" ]] && cp "$BUNDLED_ENGINE/pyproject.toml" "$ENGINE_ROOT/pyproject.toml"

if [[ ! -x "$ENGINE_ROOT/.venv/bin/python3" ]]; then
    say "Creating a virtualenv at $ENGINE_ROOT/.venv..."
    python3 -m venv "$ENGINE_ROOT/.venv"
fi
say "Installing engine dependencies..."
"$ENGINE_ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$ENGINE_ROOT/.venv/bin/pip" install --quiet "rich>=13.7" "prompt_toolkit>=3.0.43" "requests>=2.31" "urllib3<2" "pygments>=2.17"

# -------------------------------------------------------------------- ollama
say "Checking for Ollama..."
if command -v ollama >/dev/null 2>&1; then
    say "Ollama is already installed."
elif command -v brew >/dev/null 2>&1; then
    say "Installing Ollama via Homebrew..."
    brew install ollama || warn "Homebrew install of Ollama failed - install it manually from https://ollama.com/download"
    brew services start ollama >/dev/null 2>&1 || true
else
    warn "Ollama isn't installed and Homebrew isn't available to install it automatically."
    warn "Download it yourself from https://ollama.com/download, then launch Geocentric again."
fi

# --------------------------------------------------------------- point the app at it
say "Configuring the app..."
mkdir -p "$PROJECT_ROOT_DEFAULT"
defaults write "$BUNDLE_ID" engineRoot -string "$ENGINE_ROOT"
defaults write "$BUNDLE_ID" projectRoot -string "$PROJECT_ROOT_DEFAULT"

say "Done. Launching Geocentric..."
open "$DEST"

cat <<EOF

Geocentric ($TAG) is installed at:
  $DEST
Engine files live at:
  $ENGINE_ROOT

To link this Mac with another one running Geocentric, open the app's
Machines panel (the network icon in the left rail) once both are running.

Re-run this same command any time to upgrade to the latest release.
EOF
