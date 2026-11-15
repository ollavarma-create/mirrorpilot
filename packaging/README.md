# Experimental AppImage build

Run `bash packaging/build-appimage.sh` after installing the project, PyInstaller, and `rsvg-convert` (`librsvg2-bin` on Ubuntu/Debian, `librsvg2-tools` on Fedora). The GitHub Actions **AppImage (experimental)** workflow runs tests, builds on Ubuntu 22.04 x86_64, and uploads an AppImage and SHA256SUMS as workflow artifacts. No release is published automatically.

The bundle contains Python, MirrorPilot and PySide6. DNF5 and repository configuration remain on the host. The application remains read-only.

**Not yet validated on a GitHub Actions runner or Fedora.** Test Qt plugin loading, launch, repository discovery, DNF5 subprocess calls and desktop integration before public distribution. The AppImageKit download uses an upstream continuous release; pin a reviewed binary and checksum before a trusted release build. Broader compatibility is not guaranteed.
