# Motivnavi Updater

Motivnavi OS にプリインストールされたアプリを、GUI でアップデートするツールです。

製作: **エノキ電気 ENOKI ELECTRONICS** — https://enoki.xyz

## できること

- アップデートがあるかを確認（`git fetch` → 未適用のコミット数を表示）
- **現在入っているコミットの日時** と **リモートの最新コミットの日時** を並べて比較（「◯日新しい」も表示）
- 「変更内容」ボタンで、未適用のコミット一覧（日時・ハッシュ・メッセージ・作者）を表示
- **すべてアップデート**（アップデートがあるものだけ）と、アプリごとの **個別アップデート**
- `git pull` は `sudo` で実行。パスワードが必要なときだけ GUI のパスワードダイアログを表示
- アップデート後の後処理を自動実行
  - `/motivnavi/mediablue` … `scripts/build-deb.sh` で .deb をビルド → `apt install ./dist/mediablue.deb`
  - `/motivnavi/linuxauto` … `build-deb.sh` で .deb をビルド → `apt install ./dist/linux-auto.deb`
  - `/motivnavi/updater` … このアップデーター自身。最新の .deb をビルドしてインストールし、新しい版で再起動
- 実行ログを画面下部に表示（アップデート時は自動で開きます）
- タッチ操作しやすい大きめのボタン

## インストール

### /motivnavi/updater に置いて入れる（おすすめ・自己アップデート対応）

このリポジトリを `/motivnavi/updater` に clone し、そこから .deb をビルドしてインストールします。
以後はアプリの「Motivnavi Updater」カードの **アップデート** ボタン 1 回で、
`git pull` → 最新 .deb のビルド → インストール → 再起動 まで自動で行います。

```bash
sudo git clone <このリポジトリのURL> /motivnavi/updater
cd /motivnavi/updater
sudo bash build-deb.sh --install
```

### .deb パッケージを作って入れる

```bash
./build-deb.sh
sudo apt install ./dist/motivnavi-updater_1.0.0_all.deb
```

### スクリプトで入れる

```bash
sudo ./install.sh
```

`build-deb.sh` の版番号は「`APP_VERSION` + git のコミット日時とハッシュ」
（例: `1.0.0+git20261123174200.abc1234`）になるので、git pull するたびに apt で正しく上書き更新されます。
`--install` を付けると一時フォルダでビルドしてそのままインストールします（リポジトリ内に dist/ は作りません）。

アンインストールは `sudo ./uninstall.sh`（設定も消す場合は `--purge`）、
.deb の場合は `sudo apt remove motivnavi-updater` です。

インストール後は、アプリメニューの「Motivnavi Updater」か、`motivnavi-updater` コマンドで起動します。

### 必要なもの

- Python 3 と PyQt6（無ければ PyQt5）… Kubuntu では `python3-pyqt6`
- git、sudo（sudo-rs でも可）
- 各アプリの .deb のビルドに必要なもの（Mediablue は Rust / Tauri のビルド環境。
  `scripts/build-deb.sh` が不足分を自動で用意します）

## 仕組み

| ファイル | 役割 |
|---|---|
| `/usr/bin/motivnavi-updater` | 起動コマンド |
| `/usr/lib/motivnavi-updater/motivnavi_updater.py` | GUI 本体（一般ユーザーで動く） |
| `/usr/lib/motivnavi-updater/motivnavi-updater-helper` | sudo 経由で呼ばれる特権ヘルパー |
| `/etc/motivnavi-updater/targets.json` | アップデート対象の設定 |

- GUI は一般ユーザーのまま動き、`git pull`・`git fetch`・root 用の後処理だけを
  `sudo /usr/lib/motivnavi-updater/motivnavi-updater-helper ...` で実行します。
- ヘルパーは **設定ファイルに書かれた対象・後処理しか実行しません**（任意のコマンドは受け付けない）。
- パスワードは最初に必要になったときに 1 回だけ聞き、アプリを閉じるまでメモリ上にだけ保持します。
  パスワード不要の sudo が設定されている場合はダイアログを出しません。
- リポジトリの所有者が root 以外の場合、ヘルパーは `git pull` をその所有者の権限で実行します
  （root 所有のファイルが混ざらないようにするため）。
- `git pull` は安全のため `--ff-only`（早送りのみ）で実行します。手元で変更や独自コミットがあると失敗するので、
  その場合はログを確認して手動で解決してください。
- アップデーター自身は「すべてアップデート」でも必ず最後に更新し、終わったら新しい版で再起動するか確認します。
  インストール時、`/etc/motivnavi-updater/targets.json` を手で編集していなければ新しい設定に置き換わり、
  編集していれば編集した内容が残ります。
- Mediablue / Linux Auto の .deb のビルドは **リポジトリの所有者** の権限で実行し（root 所有なら root）、
  できた `dist/*.deb` を root で `apt-get install --reinstall` します。
  .deb のファイル名は毎回同じで版が変わらないこともあるため、`--reinstall` で必ず入れ直します。
- リポジトリが一般ユーザーの所有で、Mediablue のビルドに足りないパッケージがある場合、
  `scripts/build-deb.sh` の中の `sudo apt-get install` がパスワードを聞けずに失敗します。
  その場合は一度だけターミナルで `bash scripts/build-deb.sh` を実行して準備してください。
- このアプリは `sudo` を付けずに起動してください（`"as": "user"` の後処理は起動したユーザーで実行するため）。

### 起動直後の自動確認について

起動直後は、パスワードを聞かずに確認します。リポジトリに書き込み権限が無い場合は `git ls-remote` で
最新コミットのハッシュだけを調べるため、「リモートの最新」の日時が「不明」になることがあります。
その場合は「更新を確認」を押すと、管理者権限で `git fetch` して日時・件数・変更内容を表示します。

### 日付について

git にはプッシュされた日時が記録されないため、「リモートの最新」はリモートの最新コミットの
**コミット日時**（committer date）を表示しています。

## 対象を追加・変更する

`/etc/motivnavi-updater/targets.json` を編集します（root 権限が必要）。

```json
{
  "id": "castify",
  "name": "Castify",
  "description": "AzuraCast ラジオプレイヤー",
  "path": "/motivnavi/castify",
  "branch": "main",
  "post_update": [
    { "label": "後処理の説明", "command": ["./build.sh"], "as": "user" }
  ]
}
```

- `branch` は省略可（省略時は現在のブランチの追跡先）
- `as` は `"root"`（sudo で root として実行）、`"owner"`（sudo 経由でリポジトリの所有者として実行）、
  `"user"`（アプリを起動したユーザーで実行）のどれか

## パスワード入力を省略したい場合（任意）

キーボードの無いタブレットで毎回パスワードを入れたくない場合は、ヘルパーだけをパスワード無しで
実行できるようにできます（セキュリティ上の判断はご自身で行ってください）。

```bash
echo "%sudo ALL=(root) NOPASSWD: /usr/lib/motivnavi-updater/motivnavi-updater-helper" | \
  sudo tee /etc/sudoers.d/motivnavi-updater
sudo chmod 440 /etc/sudoers.d/motivnavi-updater
```

この場合でも、ヘルパーが実行するのは `/etc/motivnavi-updater/targets.json`（root しか編集できない）
に書かれた処理だけです。

## Windows から push する場合

Windows 上で commit すると .sh の実行権限が付かないことがあります（後処理は実行権限が無くても
`bash` で実行するので動きますが）、付けておく場合は次のようにします。

```bash
git update-index --chmod=+x build-deb.sh install.sh uninstall.sh src/motivnavi-updater-helper data/motivnavi-updater
```

## 開発中の動作確認

インストールせずに `src/` から直接起動できます（`src/targets.json` を使います）。

```bash
python3 src/motivnavi_updater.py
```

---

© エノキ電気 ENOKI ELECTRONICS — https://enoki.xyz
