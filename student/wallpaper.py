# -*- coding: utf-8 -*-
"""默认桌面：保存、下发、锁定与解锁。Windows 走 SPI/注册表；Linux 为可测试的模拟实现。"""

from __future__ import print_function

import io
import json
import os
import sys
import threading
import time
from pathlib import Path

from PIL import Image

STATE_NAME = "desktop_lock.json"
WATCH_INTERVAL = 20


def image_to_bmp(data, dest):
    """把 jpg/png/bmp 转为 Windows 7 较稳妥的 BMP 文件。"""
    image = Image.open(io.BytesIO(data))
    if image.mode != "RGB":
        image = image.convert("RGB")
    # 超大图缩小，避免 BMP 过大
    max_w = 2560
    if image.width > max_w:
        ratio = max_w / float(image.width)
        new_h = max(1, int(image.height * ratio))
        resample = Image.BILINEAR
        if hasattr(Image, "Resampling"):
            resample = Image.Resampling.BILINEAR
        image = image.resize((max_w, new_h), resample)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(dest), format="BMP")
    return dest, image.width, image.height


def sniff_ext(filename, data):
    name = (filename or "wallpaper.jpg").lower()
    if name.endswith(".png"):
        return ".png"
    if name.endswith(".bmp"):
        return ".bmp"
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return ".jpg"
    # 看文件头
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"BM":
        return ".bmp"
    return ".jpg"


class DesktopManager(object):
    def __init__(self, data_dir, log=None, ui=None):
        self.data_dir = Path(data_dir)
        self.dir = self.data_dir / "desktop"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.ui = ui
        self.locked = False
        self.intended_bmp = None
        self._watch_stop = threading.Event()
        self._watch = None
        self._lock = threading.Lock()
        self.load_and_reapply()

    def _state_path(self):
        return self.dir / STATE_NAME

    def _write_log(self, event, **kwargs):
        if self.log is not None:
            self.log.write(event, **kwargs)

    def _announce(self, title, text):
        if self.ui is not None:
            try:
                self.ui.show_announce(title, text)
            except Exception:
                pass

    def _load_state(self):
        path = self._state_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, payload):
        path = self._state_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def is_locked(self):
        return bool(self.locked)

    def status_label(self):
        if self.locked:
            return "已锁定默认桌面"
        return "未锁定"

    def load_and_reapply(self):
        """开机/启动时：若本地仍处于锁定，重新应用壁纸和策略。"""
        state = self._load_state()
        if not state.get("locked"):
            self.locked = False
            return
        bmp = state.get("intended_bmp") or ""
        if bmp and Path(bmp).is_file():
            self.intended_bmp = bmp
            self.locked = True
            self._apply_os(bmp, lock=True)
            self._start_watch()
            self._write_log("desktop_reapplied", path=bmp, reason="startup")
        else:
            self.locked = False

    def apply_image(self, data, filename="wallpaper.jpg", lock=True):
        if not data:
            raise ValueError("壁纸为空")
        ext = sniff_ext(filename, data)
        src = self.dir / ("classroom_wallpaper" + ext)
        src.write_bytes(data)
        bmp = self.dir / "classroom_wallpaper.bmp"
        image_to_bmp(data, bmp)
        self.intended_bmp = str(bmp.resolve())

        state = self._load_state()
        if not state.get("backup"):
            state["backup"] = self._snapshot_current()
        state["locked"] = bool(lock)
        state["intended_bmp"] = self.intended_bmp
        state["source"] = str(src)
        state["filename"] = Path(filename).name
        self._save_state(state)

        self._apply_os(self.intended_bmp, lock=bool(lock))
        self.locked = bool(lock)
        if self.locked:
            self._start_watch()
        else:
            self._stop_watch()
        self._write_log("desktop_applied", filename=Path(filename).name, locked=self.locked, path=self.intended_bmp)
        if self.locked:
            self._announce("课堂管理", "已设置机房默认桌面，并锁定壁纸。学生不能自行更改。")
        else:
            self._announce("课堂管理", "已设置机房默认桌面。")
        return self.intended_bmp

    def unlock(self):
        state = self._load_state()
        self._stop_watch()
        backup = state.get("backup") or {}
        self._restore_os(backup)
        self.locked = False
        state["locked"] = False
        # 保留 backup 直至下次重新锁定时覆盖；解锁后清空 backup，以免下次误用旧快照。
        state["backup"] = None
        self._save_state(state)
        self._write_log("desktop_unlocked", restored=True)
        self._announce("课堂管理", "已解除桌面锁定，并尝试恢复原来的壁纸。")

    def enforce(self):
        """若锁定期间壁纸被改，则恢复。返回是否进行了恢复。"""
        if not self.locked or not self.intended_bmp:
            return False
        if not Path(self.intended_bmp).is_file():
            return False
        if self._matches(self.intended_bmp):
            # 仍确保策略在
            if sys.platform == "win32":
                try:
                    from student.win_wallpaper import apply_lock_policies
                    apply_lock_policies()
                except Exception:
                    pass
            return False
        self._apply_os(self.intended_bmp, lock=True)
        self._write_log("desktop_reapplied", path=self.intended_bmp, reason="changed")
        return True

    def simulate_current(self, path):
        """Linux 测试：假装当前壁纸被改成 path。"""
        cur = self.dir / "simulated_current.txt"
        cur.write_text(str(path), encoding="utf-8")

    def _simulated_current(self):
        cur = self.dir / "simulated_current.txt"
        if cur.exists():
            return cur.read_text(encoding="utf-8").strip()
        return ""

    def _snapshot_current(self):
        if sys.platform == "win32":
            try:
                from student.win_wallpaper import copy_wallpaper_file, get_wallpaper_path, snapshot
                snap = snapshot()
                backup_file = ""
                src = get_wallpaper_path()
                if src:
                    backup_file = copy_wallpaper_file(src, self.dir / "original_wallpaper_backup")
                snap["backup_file"] = backup_file
                return snap
            except Exception as exc:
                self._write_log("desktop_snapshot_error", error=str(exc))
                return {"backup_file": "", "wallpaper_path": ""}
        current = self._simulated_current()
        backup_file = ""
        if current and Path(current).is_file():
            dest = self.dir / "original_wallpaper_backup"
            try:
                dest.write_bytes(Path(current).read_bytes())
                backup_file = str(dest)
            except OSError:
                backup_file = current
        return {"wallpaper_path": current, "backup_file": backup_file, "simulated": True}

    def _apply_os(self, bmp_path, lock=True):
        if sys.platform == "win32":
            from student.win_wallpaper import apply_lock_policies, set_wallpaper
            set_wallpaper(bmp_path, style="10")
            if lock:
                apply_lock_policies()
            return
        # Linux 模拟：记录「当前壁纸」
        self.simulate_current(bmp_path)

    def _restore_os(self, backup):
        backup = backup or {}
        if sys.platform == "win32":
            from student.win_wallpaper import restore_policies, restore_wallpaper
            restore_policies(backup)
            restore_wallpaper(backup, backup.get("backup_file") or "")
            return
        restored = backup.get("backup_file") or backup.get("wallpaper_path") or ""
        self.simulate_current(restored)

    def _matches(self, intended):
        if sys.platform == "win32":
            try:
                from student.win_wallpaper import wallpaper_matches
                return wallpaper_matches(intended)
            except Exception:
                return False
        return self._simulated_current() == str(intended)

    def _start_watch(self):
        self._stop_watch()
        self._watch_stop = threading.Event()
        self._watch = threading.Thread(target=self._watch_loop, name="desktop-lock-watch", daemon=True)
        self._watch.start()

    def _stop_watch(self):
        ev = self._watch_stop
        ev.set()
        th = self._watch
        self._watch = None
        if th and th.is_alive() and threading.current_thread() is not th:
            th.join(timeout=1)

    def _watch_loop(self):
        while not self._watch_stop.wait(WATCH_INTERVAL):
            try:
                with self._lock:
                    self.enforce()
            except Exception:
                pass

    def stop(self):
        """进程退出时只停检测线程，不解除锁定（重启后仍要保持）。"""
        self._stop_watch()
