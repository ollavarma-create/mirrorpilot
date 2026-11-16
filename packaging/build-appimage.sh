#!/usr/bin/env bash
set -euo pipefail

# Mene aina repon juureen (sieltä missä pyproject.toml on)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR" && while [[ ! -f pyproject.toml && "$PWD" != / ]]; do cd ..; done && pwd)"

if [[ ! -f "$ROOT/pyproject.toml" ]]; then
  echo "ERROR: pyproject.toml not found – cannot locate repo root" >&2
  exit 1
fi

echo "ROOT=$ROOT"
cd "$ROOT"

if [[ "$(uname -m)" != "x86_64" ]]; then
  echo "Only x86_64 is supported" >&2
  exit 1
fi

VERSION="$(python -c 'import importlib.metadata; print(importlib.metadata.version("mirrorpilot"))')"
mkdir -p dist

python -m nuitka \
  --standalone \
  --assume-yes-for-downloads \
  --enable-plugin=pyside6 \
  --include-qt-plugins=platforms,platformthemes,imageformats,iconengines,xcbglintegrations \
  --include-package=mirrorpilot \
  --output-dir="$ROOT/dist" \
  --output-filename=mirrorpilot \
  "$ROOT/mirrorpilot/app.py"

# --- AppDir ---
APPDIR="$ROOT/dist/MirrorPilot.AppDir"
rm -rf "$APPDIR"
mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/metainfo" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Nuitka-tuotokset
DIST_DIR=$(find "$ROOT/dist" -maxdepth 1 -type d -name '*.dist' | head -n1)
if [[ -z "$DIST_DIR" ]]; then
  echo "ERROR: no *.dist directory found" >&2
  exit 1
fi
echo "Using dist dir: $DIST_DIR"
cp -a "$DIST_DIR/." "$APPDIR/usr/bin/"

# --- Desktop (pakollinen) ---
DESKTOP_SRC="$ROOT/packaging/io.github.ollavarma_create.MirrorPilot.desktop"
if [[ -f "$DESKTOP_SRC" ]]; then
  cp "$DESKTOP_SRC" "$APPDIR/io.github.ollavarma_create.MirrorPilot.desktop"
else
  cat > "$APPDIR/io.github.ollavarma_create.MirrorPilot.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=MirrorPilot
Comment=Fedora DNF5 mirror diagnostics
Exec=mirrorpilot
Icon=mirrorpilot
Terminal=false
Categories=System;
StartupNotify=true
EOF
fi
cp "$APPDIR/io.github.ollavarma_create.MirrorPilot.desktop" "$APPDIR/usr/share/applications/"

# --- AppStream (match desktop file ID) ---
if [[ -f "$ROOT/packaging/mirrorpilot.appdata.xml" ]]; then
  cp "$ROOT/packaging/mirrorpilot.appdata.xml" \
     "$APPDIR/usr/share/metainfo/io.github.ollavarma_create.MirrorPilot.appdata.xml"
fi

# --- Ikonit ---
if [[ -f "$ROOT/assets/mirrorpilot.svg" ]]; then
  cp "$ROOT/assets/mirrorpilot.svg" "$APPDIR/mirrorpilot.svg"
  cp "$ROOT/assets/mirrorpilot.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/mirrorpilot.svg"
  rsvg-convert -w 256 -h 256 -o "$APPDIR/mirrorpilot.png" "$ROOT/assets/mirrorpilot.svg"
else
  # yksinkertainen placeholder jos svg puuttuu
  python -c "
from pathlib import Path
png = bytes.fromhex(
  '89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de'
  '0000000c49444154789c63f80f00000101000518d84e0000000049454e44ae426082'
)
Path('$APPDIR/mirrorpilot.png').write_bytes(png)
"
fi
cp "$APPDIR/mirrorpilot.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/mirrorpilot.png"

# --- AppRun ---
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BIN="$HERE/usr/bin"

# Nuitka laittaa pluginit polkuun PySide6/qt-plugins
export LD_LIBRARY_PATH="$BIN:$BIN/PySide6/Qt/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$BIN/PySide6/qt-plugins"

unset FONTCONFIG_FILE FONTCONFIG_PATH

if [ -z "${SSL_CERT_FILE+x}" ]; then
  for ca in \
    /etc/ssl/certs/ca-certificates.crt \
    /etc/pki/tls/certs/ca-bundle.crt \
    /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem \
    /etc/ssl/cert.pem
  do
    if [ -r "$ca" ]; then
      export SSL_CERT_FILE="$ca"
      break
    fi
  done
fi

exec "$BIN/mirrorpilot" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# --- appimagetool ---
TOOL="$ROOT/dist/appimagetool-x86_64.AppImage"
curl -fL --retry 3 -o "$TOOL" \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
chmod +x "$TOOL"

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" \
  "$APPDIR" "$ROOT/dist/MirrorPilot-$VERSION-x86_64.AppImage"

(cd "$ROOT/dist" && sha256sum MirrorPilot-*.AppImage > SHA256SUMS)

echo "Valmis: dist/MirrorPilot-$VERSION-x86_64.AppImage"
