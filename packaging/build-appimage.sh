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
  --name mirrorpilot --collect-all PySide6 --hidden-import mirrorpilot.tls_diagnostics \
  mirrorpilot/__main__.py
APPDIR="$ROOT/dist/MirrorPilot.AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$ROOT/dist/mirrorpilot/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/io.github.ollavarma_create.MirrorPilot.desktop" "$APPDIR/io.github.ollavarma_create.MirrorPilot.desktop"
cp "$ROOT/packaging/io.github.ollavarma_create.MirrorPilot.desktop" "$APPDIR/usr/share/applications/io.github.ollavarma_create.MirrorPilot.desktop"
mkdir -p "$APPDIR/usr/share/metainfo" "$APPDIR/usr/share/applications"
cp "$ROOT/packaging/mirrorpilot.appdata.xml" "$APPDIR/usr/share/metainfo/io.github.ollavarma_create.MirrorPilot.appdata.xml"
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
# Bundled OpenSSL may have CA defaults from the build distribution.
# Prefer the host trust store, but never override a user-supplied setting.
if [ "${SSL_CERT_FILE+x}" != x ]; then
  for ca_bundle in \
    /etc/ssl/certs/ca-certificates.crt \
    /etc/pki/tls/certs/ca-bundle.crt \
    /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem \
    /etc/ssl/cert.pem; do
    if [ -f "$ca_bundle" ] && [ -r "$ca_bundle" ]; then
      export SSL_CERT_FILE="$ca_bundle"
      break
    fi
  done
fi
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
