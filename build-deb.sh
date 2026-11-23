#!/usr/bin/env bash
# =============================================================================
# Motivnavi Updater - .deb パッケージ作成スクリプト (build-deb.sh)
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
#
# 使い方:
#   ./build-deb.sh            dist/motivnavi-updater_<版>_all.deb を作成
#   ./build-deb.sh --install  最新の .deb をビルドしてそのままインストール
#                             (一時フォルダでビルドするのでリポジトリは汚れません)
#
# 版番号は「APP_VERSION + git のコミット日時とハッシュ」です
# (例: 1.0.0+git20261123174200.abc1234)。git pull するたびに版が上がるので
# apt で正しくアップグレードされます。
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="motivnavi-updater"
INSTALL=0
for arg in "$@"; do
    case "$arg" in
        --install|-i) INSTALL=1 ;;
        --help|-h) sed -n '6,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "[エラー] 不明なオプション: $arg"; exit 1 ;;
    esac
done

command -v dpkg-deb >/dev/null 2>&1 || { echo "[エラー] dpkg-deb が見つかりません"; exit 1; }

BASE_VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$SCRIPT_DIR/src/motivnavi_updater.py")"
VERSION="$BASE_VERSION"
GIT=(git -c "safe.directory=$SCRIPT_DIR" -C "$SCRIPT_DIR")
if command -v git >/dev/null 2>&1 && "${GIT[@]}" rev-parse HEAD >/dev/null 2>&1; then
    STAMP="$(TZ=UTC "${GIT[@]}" log -1 --format=%cd --date=format-local:%Y%m%d%H%M%S)"
    SHORT="$("${GIT[@]}" rev-parse --short=7 HEAD)"
    VERSION="${BASE_VERSION}+git${STAMP}.${SHORT}"
fi

BUILD="$(mktemp -d)"
chmod 755 "$BUILD"
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
 Motivnavi OS にプリインストールされたアプリ (Mediablue / Linux Auto など) と
 このアップデーター自身の、アップデート確認と一括・個別アップデートを GUI で行います。
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

if [ "$INSTALL" = "1" ]; then
    DEB="$BUILD/${PKG}_${VERSION}_all.deb"
else
    mkdir -p "$SCRIPT_DIR/dist"
    DEB="$SCRIPT_DIR/dist/${PKG}_${VERSION}_all.deb"
fi
dpkg-deb --root-owner-group --build "$ROOT" "$DEB" >/dev/null
chmod 644 "$DEB"
echo "[ビルド] ${PKG} ${VERSION} を作成しました"

if [ "$INSTALL" = "0" ]; then
    echo "[完了] $DEB"
    echo "       インストール: sudo apt install $DEB"
    exit 0
fi

# --- インストール -------------------------------------------------------------
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"
echo "[導入] ${PKG} ${VERSION} をインストールします..."
# 設定ファイル (targets.json) を手で編集している場合はそれを残し、未編集なら新しいものに更新
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --reinstall --allow-downgrades -o Dpkg::Use-Pty=0 \
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold "$DEB"
echo "[完了] ${PKG} ${VERSION} をインストールしました"
