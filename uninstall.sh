#!/usr/bin/env bash
# =============================================================================
# Motivnavi Updater - アンインストールスクリプト (uninstall.sh)
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
#
# 使い方:
#   sudo ./uninstall.sh          アンインストール (設定ファイルは残す)
#   sudo ./uninstall.sh --purge  設定ファイルも削除する
# =============================================================================
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "[エラー] root 権限が必要です: sudo ./uninstall.sh"
    exit 1
fi

rm -f /usr/bin/motivnavi-updater
rm -rf /usr/lib/motivnavi-updater
rm -f /usr/share/applications/motivnavi-updater.desktop
rm -f /usr/share/icons/hicolor/scalable/apps/motivnavi-updater.svg
if [ "${1:-}" = "--purge" ]; then
    rm -rf /etc/motivnavi-updater
fi

command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true

echo "[完了] Motivnavi Updater をアンインストールしました。"
