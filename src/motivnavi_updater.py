#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# Motivnavi Updater
# 開発者: エノキ電気 ENOKI ELECTRONICS (https://enoki.xyz)
#
# Motivnavi OS にプリインストールされたアプリ (git リポジトリ) の
# アップデート確認・一括/個別アップデートを行う GUI ツールです。
# =============================================================================

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    QT_API = "PyQt6"
except ImportError:  # PyQt6 が無い環境では PyQt5 を使う
    from PyQt5 import QtCore, QtGui, QtWidgets
    QT_API = "PyQt5"

APP_ID = "motivnavi-updater"
APP_NAME = "Motivnavi Updater"
APP_VERSION = "1.0.0"
VENDOR = "エノキ電気 ENOKI ELECTRONICS"
VENDOR_URL = "https://enoki.xyz"

HERE = os.path.dirname(os.path.realpath(__file__))
INSTALLED_DIR = "/usr/lib/motivnavi-updater"
SYSTEM_CONFIG = "/etc/motivnavi-updater/targets.json"
GIT_TIMEOUT = 90


def qenum(cls, scope, name):
    """PyQt5 / PyQt6 の enum の書き方の違いを吸収する。"""
    s = getattr(cls, scope, None)
    if s is not None and hasattr(s, name):
        return getattr(s, name)
    return getattr(cls, name)


# -----------------------------------------------------------------------------
# 設定・ユーティリティ
# -----------------------------------------------------------------------------
def helper_path():
    p = os.path.join(INSTALLED_DIR, "motivnavi-updater-helper")
    if HERE == INSTALLED_DIR or os.path.exists(p):
        return p
    return os.path.join(HERE, "motivnavi-updater-helper")


def config_path():
    if HERE == INSTALLED_DIR or os.path.exists(SYSTEM_CONFIG):
        return SYSTEM_CONFIG
    return os.path.join(HERE, "targets.json")


def load_targets():
    with open(config_path(), encoding="utf-8") as f:
        return json.load(f).get("targets", [])


def git_env():
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    return env


def git_read(path, *args, timeout=GIT_TIMEOUT):
    """一般ユーザーで git の読み取り系コマンドを実行する。"""
    cmd = ["git", "-c", "safe.directory=*", "-C", path, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, env=git_env(),
                       timeout=timeout, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def parse_date(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def fmt_date(dt):
    if dt is None:
        return "不明"
    return dt.astimezone().strftime("%Y/%m/%d %H:%M")


def fmt_relative(dt):
    if dt is None:
        return ""
    sec = (datetime.now(timezone.utc) - dt).total_seconds()
    if sec < 0:
        return ""
    if sec < 60:
        return "たった今"
    if sec < 3600:
        return f"{int(sec // 60)}分前"
    if sec < 86400:
        return f"{int(sec // 3600)}時間前"
    return f"{int(sec // 86400)}日前"


def fmt_gap(newer, older):
    if newer is None or older is None:
        return ""
    sec = (newer - older).total_seconds()
    if sec <= 0:
        return ""
    if sec < 3600:
        return f"{int(sec // 60)}分"
    if sec < 86400:
        return f"{int(sec // 3600)}時間"
    return f"{int(sec // 86400)}日"


def is_git_writable(path):
    g = os.path.join(path, ".git")
    return all(os.access(os.path.join(g, d), os.W_OK) for d in ("", "objects", "refs"))


def resolve_user_command(cmd, cwd):
    cmd = list(cmd)
    if cmd and cmd[0].startswith("./"):
        p = os.path.join(cwd, cmd[0][2:])
        if os.path.isfile(p) and not os.access(p, os.X_OK):
            cmd = ["bash"] + cmd
    if cmd[:2] == ["docker", "compose"] and not shutil.which("docker") and shutil.which("docker-compose"):
        cmd = ["docker-compose"] + cmd[2:]
    return cmd


# -----------------------------------------------------------------------------
# sudo の管理 (パスワードが必要なときだけ GUI ダイアログを出す)
# -----------------------------------------------------------------------------
class Sudo:
    def __init__(self, parent):
        self.parent = parent
        self.password = None
        self.nopass = False

    @property
    def is_root(self):
        return os.geteuid() == 0

    def ready(self):
        """パスワード入力なしで sudo を使える状態か。"""
        if self.is_root or self.nopass or self.password is not None:
            return True
        try:
            r = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=10,
                               stdin=subprocess.DEVNULL)
            self.nopass = r.returncode == 0
        except Exception:  # noqa: BLE001
            self.nopass = False
        return self.nopass

    def ensure(self):
        """sudo を使えるようにする。必要ならパスワードダイアログを表示。"""
        if self.ready():
            return True
        if not shutil.which("sudo"):
            QtWidgets.QMessageBox.critical(self.parent, APP_NAME, "sudo が見つかりません。")
            return False
        user = os.environ.get("USER") or ""
        message = f"アップデートには管理者権限が必要です。\n{user} のパスワードを入力してください。"
        for attempt in range(3):
            pw, ok = PasswordDialog.ask(self.parent, message)
            if not ok:
                return False
            try:
                r = subprocess.run(["sudo", "-S", "true"], input=pw + "\n", text=True,
                                   capture_output=True, timeout=20)
            except subprocess.TimeoutExpired:
                r = None
            if r is not None and r.returncode == 0:
                self.password = pw
                return True
            message = "パスワードが違います。もう一度入力してください。"
        QtWidgets.QMessageBox.warning(self.parent, APP_NAME, "認証に失敗しました。")
        return False

    def wrap(self, args):
        """(プログラム, 引数, 標準入力に書くデータ) を返す。"""
        if self.is_root:
            return args[0], args[1:], None
        if self.password is not None:
            return "sudo", ["-S"] + args, self.password + "\n"
        return "sudo", ["-n"] + args, None

    def run_sync(self, args, timeout=GIT_TIMEOUT):
        prog, a, data = self.wrap(args)
        r = subprocess.run([prog] + a, input=data or "", text=True, capture_output=True,
                           timeout=timeout, env=git_env())
        out = strip_sudo_prompt(r.stdout + r.stderr)
        return r.returncode, out


SUDO_PROMPT_RE = re.compile(r"^\[sudo[^\]]*\][^:\n]*:\s*", re.MULTILINE)


def strip_sudo_prompt(text):
    return SUDO_PROMPT_RE.sub("", text)


class PasswordDialog(QtWidgets.QDialog):
    def __init__(self, parent, message):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - 認証")
        self.setModal(True)
        self.setMinimumWidth(420)
        lay = QtWidgets.QVBoxLayout(self)
        icon = QtWidgets.QLabel("🔒")
        icon.setStyleSheet("font-size: 32px;")
        lay.addWidget(icon, 0, qenum(QtCore.Qt, "AlignmentFlag", "AlignHCenter"))
        lbl = QtWidgets.QLabel(message)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setEchoMode(qenum(QtWidgets.QLineEdit, "EchoMode", "Password"))
        self.edit.setMinimumHeight(44)
        self.edit.setPlaceholderText("パスワード")
        lay.addWidget(self.edit)
        self.show_pw = QtWidgets.QCheckBox("パスワードを表示")
        self.show_pw.toggled.connect(self._toggle)
        lay.addWidget(self.show_pw)
        bb = QtWidgets.QDialogButtonBox()
        ok = bb.addButton("OK", qenum(QtWidgets.QDialogButtonBox, "ButtonRole", "AcceptRole"))
        cancel = bb.addButton("キャンセル", qenum(QtWidgets.QDialogButtonBox, "ButtonRole", "RejectRole"))
        for b in (ok, cancel):
            b.setMinimumHeight(44)
            b.setMinimumWidth(120)
        ok.setDefault(True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.edit.setFocus()

    def _toggle(self, on):
        mode = "Normal" if on else "Password"
        self.edit.setEchoMode(qenum(QtWidgets.QLineEdit, "EchoMode", mode))

    @classmethod
    def ask(cls, parent, message):
        d = cls(parent, message)
        ok = d.exec() == qenum(QtWidgets.QDialog, "DialogCode", "Accepted")
        return d.edit.text(), ok


# -----------------------------------------------------------------------------
# アップデート確認 (別スレッド)
# -----------------------------------------------------------------------------
def commit_info(path, ref):
    rc, out, _ = git_read(path, "log", "-1", "--format=%H%x1f%h%x1f%cI%x1f%an%x1f%s", ref)
    if rc != 0 or not out:
        return None
    full, short, date, author, subject = (out.split("\x1f") + [""] * 5)[:5]
    return {"hash": full, "short": short, "date": parse_date(date), "author": author, "subject": subject}


def check_target(t, sudo, allow_sudo_fetch):
    """1つの対象のアップデート状況を調べて dict で返す。"""
    path = t["path"]
    res = {"id": t["id"], "status": "error", "message": "", "local": None, "remote": None,
           "behind": None, "ahead": 0, "incoming": [], "fetched": False}
    if not os.path.isdir(os.path.join(path, ".git")):
        res["status"] = "missing"
        res["message"] = f"{path} に git リポジトリが見つかりません"
        return res
    try:
        res["local"] = commit_info(path, "HEAD")
        if res["local"] is None:
            res["message"] = "現在のコミットを取得できません"
            return res

        # 追跡ブランチを決める
        if t.get("branch"):
            remote, branch = "origin", t["branch"]
        else:
            rc, up, _ = git_read(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
            if rc == 0 and "/" in up:
                remote, branch = up.split("/", 1)
            else:
                _, cur, _ = git_read(path, "rev-parse", "--abbrev-ref", "HEAD")
                remote, branch = "origin", cur
        upref = f"{remote}/{branch}"

        # リモートの最新を取得 (fetch)
        fetch_err = ""
        if is_git_writable(path):
            rc, _, err = git_read(path, "fetch", "--prune", remote)
            res["fetched"] = rc == 0
            fetch_err = err
        elif allow_sudo_fetch:
            rc, out = sudo.run_sync([helper_path(), "fetch", t["id"]])
            res["fetched"] = rc == 0
            fetch_err = out

        if res["fetched"]:
            remote_hash = None
        else:
            # fetch できない (権限が無い / ネットワーク不可) → ls-remote で最新ハッシュだけ確認
            rc, out, err = git_read(path, "ls-remote", remote, f"refs/heads/{branch}", timeout=30)
            if rc != 0 or not out:
                detail = (fetch_err or err or "").strip().splitlines()
                res["message"] = "リモートに接続できません" + (f": {detail[-1]}" if detail else "")
                return res
            remote_hash = out.split()[0]

        if remote_hash is not None:
            rc, _, _ = git_read(path, "cat-file", "-e", remote_hash + "^{commit}")
            if rc != 0:
                # 最新コミットの中身がまだ手元に無い
                if remote_hash == res["local"]["hash"]:
                    res["status"] = "latest"
                else:
                    res["status"] = "update"
                    res["remote"] = {"hash": remote_hash, "short": remote_hash[:7], "date": None,
                                     "author": "", "subject": "（詳細は「更新を確認」で取得）"}
                    res["message"] = "最新コミットの日時は、管理者権限で取得できます"
                return res
            target_ref = remote_hash
        else:
            target_ref = upref

        res["remote"] = commit_info(path, target_ref)
        _, behind, _ = git_read(path, "rev-list", "--count", f"HEAD..{target_ref}")
        _, ahead, _ = git_read(path, "rev-list", "--count", f"{target_ref}..HEAD")
        res["behind"] = int(behind or 0)
        res["ahead"] = int(ahead or 0)
        if res["behind"]:
            _, log, _ = git_read(path, "log", "-n", "50", "--format=%h%x1f%cI%x1f%an%x1f%s",
                                 f"HEAD..{target_ref}")
            for line in log.splitlines():
                h, d, a, s = (line.split("\x1f") + [""] * 4)[:4]
                res["incoming"].append({"short": h, "date": parse_date(d), "author": a, "subject": s})
            res["status"] = "update"
        elif res["ahead"]:
            res["status"] = "ahead"
        else:
            res["status"] = "latest"
    except subprocess.TimeoutExpired:
        res["status"] = "error"
        res["message"] = "タイムアウトしました"
    except Exception as e:  # noqa: BLE001
        res["status"] = "error"
        res["message"] = str(e)
    return res


class CheckWorker(QtCore.QThread):
    result = QtCore.pyqtSignal(object)

    def __init__(self, targets, sudo, allow_sudo_fetch):
        super().__init__()
        self.targets = targets
        self.sudo = sudo
        self.allow_sudo_fetch = allow_sudo_fetch

    def run(self):
        for t in self.targets:
            self.result.emit(check_target(t, self.sudo, self.allow_sudo_fetch))


# -----------------------------------------------------------------------------
# アップデート実行 (QProcess で順番に実行し、ログを流す)
# -----------------------------------------------------------------------------
class StepRunner(QtCore.QObject):
    output = QtCore.pyqtSignal(str)
    target_started = QtCore.pyqtSignal(str)
    target_finished = QtCore.pyqtSignal(str, bool)
    all_finished = QtCore.pyqtSignal()

    def __init__(self, sudo, parent=None):
        super().__init__(parent)
        self.sudo = sudo
        self.queue = []       # [(target, [steps])]
        self.steps = []
        self.current = None
        self.proc = None
        self.ok = True

    def start(self, targets):
        self.queue = []
        for t in targets:
            steps = [("root", [helper_path(), "pull", t["id"]], "git pull")]
            for i, s in enumerate(t.get("post_update", [])):
                label = s.get("label", " ".join(s["command"]))
                if s.get("as", "root") == "root":
                    steps.append(("root", [helper_path(), "post", t["id"], str(i)], label))
                else:
                    steps.append(("user", resolve_user_command(s["command"], t["path"]), label))
            self.queue.append((t, steps))
        self._next_target()

    def running(self):
        return self.proc is not None

    def _next_target(self):
        if not self.queue:
            self.current = None
            self.all_finished.emit()
            return
        self.current, self.steps = self.queue.pop(0)
        self.ok = True
        self.target_started.emit(self.current["id"])
        self._next_step()

    def _next_step(self):
        if not self.steps or not self.ok:
            self.target_finished.emit(self.current["id"], self.ok)
            self._next_target()
            return
        kind, args, label = self.steps.pop(0)
        t = self.current
        self.proc = QtCore.QProcess(self)
        self.proc.setProcessChannelMode(qenum(QtCore.QProcess, "ProcessChannelMode", "MergedChannels"))
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert("GIT_TERMINAL_PROMPT", "0")
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        if kind == "root":
            prog, a, data = self.sudo.wrap(args)
        else:
            if self.sudo.is_root:
                self.output.emit(f"[スキップ] 「{label}」は一般ユーザーで実行する必要があります。"
                                 "このアプリを sudo なしで起動してください。\n")
                self.ok = False
                self.proc = None
                self._next_step()
                return
            self.output.emit(f"==> {t.get('name', t['id'])}: {label}\n$ {' '.join(args)}\n")
            prog, a, data = args[0], args[1:], None
            self.proc.setWorkingDirectory(t["path"])
        self.proc.start(prog, a)
        if data:
            self.proc.write(data.encode())
        self.proc.closeWriteChannel()

    def _read(self):
        if self.proc is None:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.output.emit(strip_sudo_prompt(text))

    def _error(self, err):
        if err == qenum(QtCore.QProcess, "ProcessError", "FailedToStart"):
            self.output.emit("[エラー] コマンドを起動できませんでした\n")
            self.ok = False
            self.proc = None
            QtCore.QTimer.singleShot(0, self._next_step)

    def _finished(self, code, _status=None):
        if self.proc is None:
            return
        self._read()
        if code != 0:
            self.output.emit(f"[失敗] 終了コード {code}\n")
            self.ok = False
        self.proc.deleteLater()
        self.proc = None
        self._next_step()


# -----------------------------------------------------------------------------
# 画面
# -----------------------------------------------------------------------------
STATUS_STYLE = {
    "unknown": ("未確認", "#7a7f87"),
    "checking": ("確認中…", "#3d7fd9"),
    "latest": ("最新です", "#2e9d57"),
    "update": ("アップデートあり", "#e08a00"),
    "ahead": ("ローカルの方が新しい", "#3d7fd9"),
    "missing": ("未インストール", "#7a7f87"),
    "error": ("エラー", "#d64545"),
    "updating": ("アップデート中…", "#3d7fd9"),
}


class TargetCard(QtWidgets.QFrame):
    update_clicked = QtCore.pyqtSignal(str)
    details_clicked = QtCore.pyqtSignal(str)

    def __init__(self, target):
        super().__init__()
        self.target = target
        self.result = None
        self.setObjectName("card")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(16)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(4)
        head = QtWidgets.QHBoxLayout()
        name = QtWidgets.QLabel(target.get("name", target["id"]))
        name.setObjectName("cardTitle")
        head.addWidget(name)
        self.badge = QtWidgets.QLabel()
        self.badge.setObjectName("badge")
        head.addWidget(self.badge)
        head.addStretch(1)
        left.addLayout(head)
        sub = QtWidgets.QLabel(f"{target.get('description', '')}  ·  {target['path']}")
        sub.setObjectName("muted")
        left.addWidget(sub)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        grid.addWidget(self._key("現在のコミット"), 0, 0)
        grid.addWidget(self._key("リモートの最新"), 1, 0)
        self.local_lbl = QtWidgets.QLabel("—")
        self.remote_lbl = QtWidgets.QLabel("—")
        for w in (self.local_lbl, self.remote_lbl):
            w.setTextFormat(qenum(QtCore.Qt, "TextFormat", "RichText"))
            w.setTextInteractionFlags(qenum(QtCore.Qt, "TextInteractionFlag", "TextSelectableByMouse"))
        grid.addWidget(self.local_lbl, 0, 1)
        grid.addWidget(self.remote_lbl, 1, 1)
        grid.setColumnStretch(1, 1)
        left.addLayout(grid)
        self.note = QtWidgets.QLabel("")
        self.note.setObjectName("note")
        self.note.setWordWrap(True)
        left.addWidget(self.note)
        lay.addLayout(left, 1)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(8)
        self.update_btn = QtWidgets.QPushButton("アップデート")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(lambda: self.update_clicked.emit(target["id"]))
        self.details_btn = QtWidgets.QPushButton("変更内容")
        self.details_btn.clicked.connect(lambda: self.details_clicked.emit(target["id"]))
        for b in (self.update_btn, self.details_btn):
            b.setMinimumSize(150, 48)
            right.addWidget(b)
        right.addStretch(1)
        lay.addLayout(right)
        self.set_status("unknown")
        self.details_btn.setEnabled(False)

    @staticmethod
    def _key(text):
        l = QtWidgets.QLabel(text)
        l.setObjectName("key")
        return l

    def set_status(self, status, text=None):
        label, color = STATUS_STYLE.get(status, STATUS_STYLE["unknown"])
        self.badge.setText(text or label)
        self.badge.setStyleSheet(f"background:{color};")

    @staticmethod
    def _commit_text(c):
        if not c:
            return "—"
        rel = fmt_relative(c["date"])
        date = fmt_date(c["date"]) + (f"（{rel}）" if rel else "")
        subject = c["subject"]
        if len(subject) > 60:
            subject = subject[:59] + "…"
        return f"<b>{date}</b>  <code>{c['short']}</code>  {_esc(subject)}"

    def apply_result(self, res):
        self.result = res
        st = res["status"]
        self.local_lbl.setText(self._commit_text(res.get("local")))
        self.remote_lbl.setText(self._commit_text(res.get("remote") or (res.get("local") if st == "latest" else None)))
        note = res.get("message", "")
        if st == "update":
            text = "アップデートあり" + (f"（{res['behind']}件）" if res.get("behind") else "")
            self.set_status(st, text)
            loc, rem = res.get("local"), res.get("remote")
            gap = fmt_gap(rem and rem["date"], loc and loc["date"])
            if gap:
                note = f"リモートの最新コミットは、現在のコミットより {gap} 新しいです。" + (f"\n{note}" if note else "")
        elif st == "ahead":
            self.set_status(st)
            note = f"手元に未プッシュのコミットが {res['ahead']} 件あります。"
        else:
            self.set_status(st)
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self.details_btn.setEnabled(bool(res.get("incoming")))
        self.update_btn.setEnabled(st not in ("missing",))

    def has_update(self):
        return self.result is not None and self.result["status"] == "update"


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


STYLE = """
QWidget { font-size: 15px; }
QMainWindow, #root { background: #f3f5f8; }
#title { font-size: 24px; font-weight: 700; color: #1d2733; }
#subtitle { color: #5d6875; }
#card { background: #ffffff; border: 1px solid #dfe4ea; border-radius: 14px; }
#cardTitle { font-size: 19px; font-weight: 700; color: #1d2733; }
#badge { color: white; border-radius: 10px; padding: 3px 10px; font-size: 13px; font-weight: 600; }
#muted { color: #6b7684; font-size: 13px; }
#key { color: #6b7684; font-size: 13px; }
#note { color: #9a5b00; font-size: 13px; }
QPushButton { background: #ffffff; border: 1px solid #c9d1db; border-radius: 10px; padding: 8px 18px; }
QPushButton:hover { background: #eef2f7; }
QPushButton:disabled { color: #a6adb6; background: #f2f4f7; }
QPushButton#primary { background: #1f6feb; color: white; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #2b7bff; }
QPushButton#primary:disabled { background: #9db9e6; }
QPlainTextEdit { background: #10151c; color: #d6dde6; border-radius: 10px; font-family: monospace; font-size: 13px; }
#footer { color: #6b7684; font-size: 13px; }
"""


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QtGui.QIcon.fromTheme(APP_ID, QtGui.QIcon.fromTheme("system-software-update")))
        self.resize(980, 720)
        self.sudo = Sudo(self)
        self.runner = StepRunner(self.sudo, self)
        self.runner.output.connect(self.log)
        self.runner.target_started.connect(self._on_target_started)
        self.runner.target_finished.connect(self._on_target_finished)
        self.runner.all_finished.connect(self._on_all_finished)
        self.worker = None
        self.results_ok = []

        try:
            self.targets = load_targets()
        except Exception as e:  # noqa: BLE001
            self.targets = []
            QtWidgets.QMessageBox.critical(self, APP_NAME, f"設定ファイルを読み込めません:\n{config_path()}\n{e}")

        root = QtWidgets.QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QtWidgets.QVBoxLayout(root)
        v.setContentsMargins(22, 18, 22, 12)
        v.setSpacing(12)

        # ヘッダー
        head = QtWidgets.QHBoxLayout()
        tbox = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel(APP_NAME)
        title.setObjectName("title")
        tbox.addWidget(title)
        self.subtitle = QtWidgets.QLabel("Motivnavi OS のアプリを最新の状態に保ちます")
        self.subtitle.setObjectName("subtitle")
        tbox.addWidget(self.subtitle)
        head.addLayout(tbox, 1)
        self.check_btn = QtWidgets.QPushButton("更新を確認")
        self.check_btn.clicked.connect(lambda: self.check(full=True))
        self.all_btn = QtWidgets.QPushButton("すべてアップデート")
        self.all_btn.setObjectName("primary")
        self.all_btn.clicked.connect(self.update_all)
        for b in (self.check_btn, self.all_btn):
            b.setMinimumSize(170, 52)
            head.addWidget(b)
        v.addLayout(head)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        self.progress.setVisible(False)
        v.addWidget(self.progress)

        # 対象カード
        self.cards = {}
        cards_box = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(cards_box)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)
        for t in self.targets:
            c = TargetCard(t)
            c.update_clicked.connect(self.update_one)
            c.details_clicked.connect(self.show_details)
            self.cards[t["id"]] = c
            cl.addWidget(c)
        cl.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qenum(QtWidgets.QFrame, "Shape", "NoFrame"))
        scroll.setWidget(cards_box)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        v.addWidget(scroll, 3)

        # ログ
        logbar = QtWidgets.QHBoxLayout()
        self.log_toggle = QtWidgets.QToolButton()
        self.log_toggle.setText("▼ ログ")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(False)
        self.log_toggle.setStyleSheet("QToolButton { border: none; font-weight: 600; padding: 4px; }")
        self.log_toggle.toggled.connect(self._toggle_log)
        logbar.addWidget(self.log_toggle)
        logbar.addStretch(1)
        clear = QtWidgets.QPushButton("ログを消去")
        clear.setMinimumHeight(36)
        logbar.addWidget(clear)
        v.addLayout(logbar)
        self.logview = QtWidgets.QPlainTextEdit()
        self.logview.setReadOnly(True)
        self.logview.setMaximumBlockCount(5000)
        clear.clicked.connect(self.logview.clear)
        self.logview.setVisible(False)
        v.addWidget(self.logview, 2)

        # フッター (製作者情報)
        footer = QtWidgets.QLabel(
            f'{APP_NAME} v{APP_VERSION} — 製作: {VENDOR} '
            f'<a href="{VENDOR_URL}">{VENDOR_URL}</a>')
        footer.setObjectName("footer")
        footer.setOpenExternalLinks(True)
        footer.setAlignment(qenum(QtCore.Qt, "AlignmentFlag", "AlignHCenter"))
        v.addWidget(footer)

        self._build_menu()
        self.setStyleSheet(STYLE)
        self.log(f"{APP_NAME} v{APP_VERSION} ({QT_API})\n設定ファイル: {config_path()}\n")
        QtCore.QTimer.singleShot(200, lambda: self.check(full=False))

    # --- メニュー -------------------------------------------------------------
    def _build_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("ファイル")
        a = m.addAction("更新を確認")
        a.triggered.connect(lambda: self.check(full=True))
        a = m.addAction("すべてアップデート")
        a.triggered.connect(self.update_all)
        m.addSeparator()
        a = m.addAction("終了")
        a.triggered.connect(self.close)
        h = mb.addMenu("ヘルプ")
        a = h.addAction("エノキ電気のWebサイト")
        a.triggered.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(VENDOR_URL)))
        a = h.addAction("このアプリについて")
        a.triggered.connect(self.about)

    def about(self):
        QtWidgets.QMessageBox.about(
            self, f"{APP_NAME} について",
            f"<h3>{APP_NAME} v{APP_VERSION}</h3>"
            f"<p>Motivnavi OS のアプリをアップデートするツールです。</p>"
            f"<p>製作: <b>{VENDOR}</b><br><a href='{VENDOR_URL}'>{VENDOR_URL}</a></p>"
            f"<p style='color:#777'>Qt: {QT_API} / 設定: {config_path()}</p>")

    def _toggle_log(self, on):
        self.logview.setVisible(on)
        self.log_toggle.setText(("▼" if on else "▶") + " ログ")

    def log(self, text):
        self.logview.moveCursor(qenum(QtGui.QTextCursor, "MoveOperation", "End"))
        self.logview.insertPlainText(text)
        self.logview.moveCursor(qenum(QtGui.QTextCursor, "MoveOperation", "End"))

    def busy(self, on, message=None):
        self.progress.setVisible(on)
        for w in [self.check_btn, self.all_btn] + [c.update_btn for c in self.cards.values()]:
            w.setEnabled(not on)
        if not on:
            for c in self.cards.values():
                if c.result:
                    c.update_btn.setEnabled(c.result["status"] != "missing")
        if message:
            self.statusBar().showMessage(message)

    # --- 確認 -----------------------------------------------------------------
    def check(self, full=True):
        if self.runner.running() or (self.worker and self.worker.isRunning()):
            return
        needs_sudo = any(os.path.isdir(os.path.join(t["path"], ".git")) and not is_git_writable(t["path"])
                         for t in self.targets)
        allow_sudo = False
        if needs_sudo:
            # 起動直後の自動確認ではパスワードを聞かない (ls-remote で簡易確認)
            allow_sudo = self.sudo.ensure() if full else self.sudo.ready()
        self.busy(True, "アップデートを確認しています…")
        self.log("\n--- アップデートを確認 ---\n")
        for c in self.cards.values():
            c.set_status("checking")
        self.worker = CheckWorker(self.targets, self.sudo, allow_sudo)
        self.worker.result.connect(self._on_check_result)
        self.worker.finished.connect(self._on_check_done)
        self.worker.start()

    def _on_check_result(self, res):
        card = self.cards.get(res["id"])
        if card:
            card.apply_result(res)
        label = STATUS_STYLE.get(res["status"], ("?", ""))[0]
        extra = f"（{res['behind']}件）" if res.get("behind") else ""
        msg = f" - {res['message']}" if res.get("message") else ""
        self.log(f"[{res['id']}] {label}{extra}{msg}\n")

    def _on_check_done(self):
        self.busy(False)
        n = sum(1 for c in self.cards.values() if c.has_update())
        now = datetime.now().strftime("%H:%M")
        if n:
            self.subtitle.setText(f"{n} 件のアップデートがあります（{now} 確認）")
        else:
            self.subtitle.setText(f"すべて最新です（{now} 確認）")
        self.statusBar().showMessage("確認が完了しました", 5000)

    # --- アップデート ---------------------------------------------------------
    def update_all(self):
        checked = [c for c in self.cards.values() if c.result is not None]
        if checked:
            targets = [c.target for c in self.cards.values() if c.has_update()]
            if not targets:
                QtWidgets.QMessageBox.information(self, APP_NAME, "すべて最新です。")
                return
        else:
            targets = [t for t in self.targets if os.path.isdir(os.path.join(t["path"], ".git"))]
        names = "\n".join(f"・{t.get('name', t['id'])}" for t in targets)
        if not self._confirm(f"次のアプリをアップデートします。\n\n{names}\n\nよろしいですか？"):
            return
        self._run_update(targets)

    def update_one(self, tid):
        card = self.cards[tid]
        t = card.target
        if card.result and card.result["status"] in ("latest", "ahead"):
            if not self._confirm(f"{t.get('name', tid)} は最新です。\ngit pull と後処理をもう一度実行しますか？"):
                return
        elif not self._confirm(f"{t.get('name', tid)} をアップデートしますか？"):
            return
        self._run_update([t])

    def _confirm(self, text):
        yes = qenum(QtWidgets.QMessageBox, "StandardButton", "Yes")
        no = qenum(QtWidgets.QMessageBox, "StandardButton", "No")
        return QtWidgets.QMessageBox.question(self, APP_NAME, text, yes | no, yes) == yes

    def _run_update(self, targets):
        if not self.sudo.ensure():
            self.log("[中止] 管理者権限を取得できませんでした\n")
            return
        self.results_ok = []
        self.log_toggle.setChecked(True)
        self.busy(True, "アップデートしています…")
        self.log("\n--- アップデート開始 ---\n")
        self.runner.start(targets)

    def _on_target_started(self, tid):
        self.cards[tid].set_status("updating")

    def _on_target_finished(self, tid, ok):
        self.results_ok.append((tid, ok))
        self.log(f"[{tid}] {'完了しました' if ok else '失敗しました'}\n")
        if not ok:
            self.cards[tid].set_status("error", "アップデート失敗")

    def _on_all_finished(self):
        self.busy(False)
        failed = [tid for tid, ok in self.results_ok if not ok]
        self.log("--- アップデート終了 ---\n")
        if failed:
            QtWidgets.QMessageBox.warning(self, APP_NAME,
                                          "次のアップデートに失敗しました。ログを確認してください。\n\n"
                                          + "\n".join(failed))
        else:
            self.statusBar().showMessage("アップデートが完了しました", 8000)
        self.check(full=True)

    # --- 変更内容 -------------------------------------------------------------
    def show_details(self, tid):
        card = self.cards[tid]
        res = card.result or {}
        rows = "".join(
            f"<tr><td style='white-space:nowrap'>{fmt_date(c['date'])}</td>"
            f"<td><code>{c['short']}</code></td><td>{_esc(c['subject'])}</td>"
            f"<td style='color:#777'>{_esc(c['author'])}</td></tr>"
            for c in res.get("incoming", []))
        d = QtWidgets.QDialog(self)
        d.setWindowTitle(f"{card.target.get('name', tid)} の変更内容")
        d.resize(760, 460)
        lay = QtWidgets.QVBoxLayout(d)
        lay.addWidget(QtWidgets.QLabel(f"未適用のコミット: {res.get('behind', 0)} 件（新しい順）"))
        tb = QtWidgets.QTextBrowser()
        tb.setHtml(f"<table cellspacing='0' cellpadding='4'>{rows}</table>")
        lay.addWidget(tb)
        btn = QtWidgets.QPushButton("閉じる")
        btn.setMinimumHeight(44)
        btn.clicked.connect(d.accept)
        lay.addWidget(btn)
        d.exec()

    def closeEvent(self, e):
        if self.runner.running():
            if not self._confirm("アップデート中です。終了してもよろしいですか？"):
                e.ignore()
                return
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        self.sudo.password = None
        e.accept()


def main():
    if hasattr(QtCore.Qt, "AA_EnableHighDpiScaling") and QT_API == "PyQt5":
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(VENDOR)
    app.setOrganizationDomain("enoki.xyz")
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName(APP_ID)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
