#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
if [[ "$(uname -m)" != "x86_64" ]]; then
  echo "Only x86_64 builds are currently supported" >&2
  exit 1
fi
VERSION="$(python -c 'import importlib.metadata; print(importlib.metadata.version("mirrorpilot"))')"
mkdir -p dist
python -m PyInstaller --noconfirm --clean --onedir \
  --name mirrorpilot --collect-all PySide6 \
  mirrorpilot/__main__.py
APPDIR="$ROOT/dist/MirrorPilot.AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$ROOT/dist/mirrorpilot/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/mirrorpilot.desktop" "$APPDIR/mirrorpilot.desktop"
mkdir -p "$APPDIR/usr/share/metainfo"
cp "$ROOT/packaging/mirrorpilot.appdata.xml" "$APPDIR/usr/share/metainfo/mirrorpilot.appdata.xml"
cp "$ROOT/assets/mirrorpilot.svg" "$APPDIR/mirrorpilot.svg"
if ! command -v rsvg-convert >/dev/null 2>&1; then
  echo "rsvg-convert is required to generate the AppImage PNG icon (install librsvg2-bin)." >&2
  exit 1
fi
rsvg-convert --width 256 --height 256 --output "$APPDIR/mirrorpilot.png" "$ROOT/assets/mirrorpilot.svg"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp "$APPDIR/mirrorpilot.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/mirrorpilot.png"
cp "$ROOT/assets/mirrorpilot.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/mirrorpilot.svg"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$HERE/usr/bin/mirrorpilot" "$@"
EOF
chmod +x "$APPDIR/AppRun"
TOOL="$ROOT/dist/appimagetool-x86_64.AppImage"
curl -fL --retry 3 -o "$TOOL" \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
chmod +x "$TOOL"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" \
  "$APPDIR" "$ROOT/dist/MirrorPilot-$VERSION-x86_64.AppImage"
(cd "$ROOT/dist" && sha256sum MirrorPilot-*.AppImage > SHA256SUMS)
