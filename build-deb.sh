#!/usr/bin/env bash
# =============================================================================
# Motivnavi Updater - .deb パッケージ作成スクリプト (build-deb.sh)
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
#
# 使い方:  ./build-deb.sh   →  dist/motivnavi-updater_<版>_all.deb
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$SCRIPT_DIR/src/motivnavi_updater.py")"
PKG="motivnavi-updater"
BUILD="$(mktemp -d)"
ROOT="$BUILD/${PKG}_${VERSION}_all"
trap 'rm -rf "$BUILD"' EXIT

install -d "$ROOT/DEBIAN" "$ROOT/usr/lib/$PKG" "$ROOT/usr/bin" "$ROOT/etc/$PKG" \
           "$ROOT/usr/share/applications" "$ROOT/usr/share/icons/hicolor/scalable/apps" \
           "$ROOT/usr/share/doc/$PKG"
install -m 644 "$SCRIPT_DIR/src/motivnavi_updater.py"      "$ROOT/usr/lib/$PKG/"
install -m 755 "$SCRIPT_DIR/src/motivnavi-updater-helper"  "$ROOT/usr/lib/$PKG/"
install -m 755 "$SCRIPT_DIR/data/motivnavi-updater"        "$ROOT/usr/bin/"
install -m 644 "$SCRIPT_DIR/src/targets.json"              "$ROOT/etc/$PKG/"
install -m 644 "$SCRIPT_DIR/data/motivnavi-updater.desktop" "$ROOT/usr/share/applications/"
install -m 644 "$SCRIPT_DIR/data/motivnavi-updater.svg"    "$ROOT/usr/share/icons/hicolor/scalable/apps/"
install -m 644 "$SCRIPT_DIR/README.md"                     "$ROOT/usr/share/doc/$PKG/"

echo "/etc/$PKG/targets.json" > "$ROOT/DEBIAN/conffiles"

cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: admin
Priority: optional
Architecture: all
Depends: python3, python3-pyqt6 | python3-pyqt5, git, sudo | sudo-rs
Suggests: docker.io | docker-ce, docker-compose-v2 | docker-compose-plugin
Maintainer: ENOKI ELECTRONICS <https://enoki.xyz>
Homepage: https://enoki.xyz
Description: Motivnavi OS アプリのアップデーター
 Motivnavi OS にプリインストールされたアプリ (Mediablue / Linux Auto など) の
 アップデート確認と、一括・個別アップデートを GUI で行います。
 製作: エノキ電気 ENOKI ELECTRONICS
EOF

cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
exit 0
EOF
cp "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"

mkdir -p "$SCRIPT_DIR/dist"
dpkg-deb --root-owner-group --build "$ROOT" "$SCRIPT_DIR/dist/${PKG}_${VERSION}_all.deb"
echo "[完了] dist/${PKG}_${VERSION}_all.deb を作成しました"
echo "       インストール: sudo apt install ./dist/${PKG}_${VERSION}_all.deb"
