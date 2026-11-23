#!/usr/bin/env bash
# =============================================================================
# Motivnavi Updater - インストールスクリプト (install.sh)
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
#
# 使い方:
#   sudo ./install.sh                 インストール (既存の設定ファイルは残す)
#   sudo ./install.sh --force-config  設定ファイル (targets.json) も上書きする
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORCE_CONFIG=0
[ "${1:-}" = "--force-config" ] && FORCE_CONFIG=1

if [ "$(id -u)" -ne 0 ]; then
    echo "[エラー] root 権限が必要です: sudo ./install.sh"
    exit 1
fi

# --- 依存パッケージ -----------------------------------------------------------
if ! python3 -c "import PyQt6" 2>/dev/null && ! python3 -c "import PyQt5" 2>/dev/null; then
    echo "[準備] PyQt をインストールします..."
    apt-get update
    apt-get install -y python3-pyqt6 || apt-get install -y python3-pyqt5
fi
command -v git >/dev/null 2>&1 || apt-get install -y git

# --- 本体 ---------------------------------------------------------------------
echo "[導入] ファイルを配置します..."
install -d -m 755 /usr/lib/motivnavi-updater
install -m 644 "$SCRIPT_DIR/src/motivnavi_updater.py" /usr/lib/motivnavi-updater/motivnavi_updater.py
install -m 755 -o root -g root "$SCRIPT_DIR/src/motivnavi-updater-helper" /usr/lib/motivnavi-updater/motivnavi-updater-helper
install -m 755 "$SCRIPT_DIR/data/motivnavi-updater" /usr/bin/motivnavi-updater

install -d -m 755 /etc/motivnavi-updater
if [ ! -f /etc/motivnavi-updater/targets.json ] || [ "$FORCE_CONFIG" = "1" ]; then
    install -m 644 -o root -g root "$SCRIPT_DIR/src/targets.json" /etc/motivnavi-updater/targets.json
else
    echo "[導入] 既存の設定ファイルを残しました: /etc/motivnavi-updater/targets.json"
fi

install -D -m 644 "$SCRIPT_DIR/data/motivnavi-updater.desktop" /usr/share/applications/motivnavi-updater.desktop
install -D -m 644 "$SCRIPT_DIR/data/motivnavi-updater.svg" /usr/share/icons/hicolor/scalable/apps/motivnavi-updater.svg

command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true

echo "[完了] Motivnavi Updater をインストールしました。"
echo "       アプリメニューの「Motivnavi Updater」、または motivnavi-updater コマンドで起動できます。"
