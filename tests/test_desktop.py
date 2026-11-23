# -*- coding: utf-8 -*-
"""Linux 可测的默认桌面设置 / 锁定 / 解锁与持久化（模拟实现）。"""

from __future__ import print_function

import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from student.wallpaper import DesktopManager, image_to_bmp


class Checker(object):
    def __init__(self):
        self.ok = 0
        self.fail = 0
        self.rows = []

    def check(self, name, cond, detail=""):
        if cond:
            self.ok += 1
            status = "通过"
        else:
            self.fail += 1
            status = "失败"
        line = "[%s] %s%s" % (status, name, (" — " + detail) if detail else "")
        self.rows.append(line)
        print(line, flush=True)
        return cond

    def summary(self):
        print("", flush=True)
        print("合计：通过 %s，失败 %s" % (self.ok, self.fail), flush=True)
        return self.fail == 0


def make_jpeg(text, dest=None):
    img = Image.new("RGB", (320, 180), (20, 90, 160))
    dest = Path(dest) if dest else None
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    data = buf.getvalue()
    if dest:
        dest.write_bytes(data)
    return data


def main():
    chk = Checker()
    tmp = Path(tempfile.mkdtemp(prefix="classroom-desktop-"))
    try:
        # Linux 下可以导入 desktop 模块，且不会误加载 Windows API。
        import student.wallpaper as wp
        chk.check("Linux 可导入 student.wallpaper", wp is not None)
        win_failed = False
        try:
            import student.win_wallpaper  # noqa: F401
        except ImportError:
            win_failed = True
        chk.check("Linux 不加载 Windows 壁纸 API", win_failed or sys.platform == "win32")

        original = tmp / "original.bmp"
        image_to_bmp(make_jpeg("OLD"), original)

        mgr = DesktopManager(tmp / "stu")
        mgr.simulate_current(str(original))
        data = make_jpeg("LAB")
        bmp = mgr.apply_image(data, filename="lab_wallpaper.jpg", lock=True)
        chk.check("设置默认桌面并锁定", mgr.is_locked() and Path(bmp).is_file())
        sim = (mgr.dir / "simulated_current.txt").read_text(encoding="utf-8").strip()
        chk.check("模拟记录已设壁纸路径", sim == str(Path(bmp).resolve()) or sim == bmp)
        state = json.loads((mgr.dir / "desktop_lock.json").read_text(encoding="utf-8"))
        chk.check("锁定状态已持久化", state.get("locked") is True and bool(state.get("backup")))
        backup_file = (state.get("backup") or {}).get("backup_file") or ""
        chk.check("锁定前壁纸已备份", Path(backup_file).is_file() if backup_file else False)

        # 假装学生改了壁纸
        other = tmp / "other.bmp"
        image_to_bmp(make_jpeg("HACK"), other)
        mgr.simulate_current(str(other))
        changed = mgr.enforce()
        sim2 = (mgr.dir / "simulated_current.txt").read_text(encoding="utf-8").strip()
        chk.check("检测到壁纸被改后恢复", changed is True and (sim2 == bmp or sim2 == str(Path(bmp).resolve())))
        unchanged = mgr.enforce()
        chk.check("壁纸未改时不必重复设置", unchanged is False)

        # 模拟重启：新进程读取同一目录
        mgr.stop()
        mgr2 = DesktopManager(tmp / "stu")
        chk.check("重启后自动重新应用锁定", mgr2.is_locked() is True)
        sim3 = (mgr2.dir / "simulated_current.txt").read_text(encoding="utf-8").strip()
        chk.check("重启后壁纸仍是教师下发的图片", sim3 == bmp or sim3 == str(Path(bmp).resolve()))

        mgr2.unlock()
        chk.check("解除锁定后开关关闭", mgr2.is_locked() is False)
        state2 = json.loads((mgr2.dir / "desktop_lock.json").read_text(encoding="utf-8"))
        chk.check("解锁后持久化不再锁定", state2.get("locked") is False)
        restored = (mgr2.dir / "simulated_current.txt").read_text(encoding="utf-8").strip()
        chk.check("解锁后恢复锁定前壁纸", restored == backup_file or Path(restored).name.startswith("original_wallpaper_backup"))

        mgr2.stop()

        # 解锁后新建管理器不应再自动锁定
        mgr3 = DesktopManager(tmp / "stu")
        chk.check("解锁后重启不再自动锁定", mgr3.is_locked() is False)
        mgr3.stop()
    except Exception as exc:
        chk.check("测试过程未异常中断", False, str(exc))
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    report = Path(os.environ.get("CLASSROOM_TEST_DIR", "/tmp/classroom-lab-verify"))
    try:
        report.mkdir(parents=True, exist_ok=True)
        (report / "desktop_report.txt").write_text(
            "\n".join(chk.rows) + "\n合计：通过 %s，失败 %s\n" % (chk.ok, chk.fail),
            encoding="utf-8",
        )
    except OSError:
        pass
    ok = chk.summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
