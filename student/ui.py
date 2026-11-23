# -*- coding: utf-8 -*-
"""学生端界面：Windows 用可见窗口+托盘；Linux / 无 UI 模式打印状态。"""

import sys

from shared.version import STUDENT_WINDOW_TITLE


class ConsoleUI(object):
    def __init__(self, title=None):
        self.title = title or STUDENT_WINDOW_TITLE
        self._last = ""

    def start(self):
        self._banner("正在启动…")

    def stop(self):
        print("[%s] 客户端已退出" % self.title, flush=True)

    def _banner(self, detail):
        line = "=" * 58
        parts = [line, "  %s" % self.title, "  %s" % detail, line]
        text = "\n".join(parts)
        print(text, flush=True)
        self._last = detail

    def set_status(self, text):
        compact = text.replace("\n", " | ")
        if compact != self._last:
            self._banner(compact)

    def show_lock(self, message="请看老师"):
        print("[锁屏] %s （Linux 模拟：不创建全屏覆盖层）" % message, flush=True)

    def hide_lock(self):
        print("[解锁] 已解除锁屏", flush=True)

    def show_announce(self, title, text):
        print("[%s] %s" % (title, text), flush=True)

    def show_broadcast_frame(self, jpeg_bytes):
        print("[广播] 收到教师画面 %s 字节" % len(jpeg_bytes or b""), flush=True)

    def clear_broadcast(self):
        print("[广播] 教师屏幕广播已结束", flush=True)


def create_ui(sim=False, no_ui=False):
    if no_ui or sim or sys.platform != "win32":
        return ConsoleUI()
    try:
        from student.win_ui import WinUI
        return WinUI()
    except Exception as exc:
        print("无法启动 Windows 窗口（将改用控制台）：%s" % exc, flush=True)
        return ConsoleUI()
