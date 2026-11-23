# -*- coding: utf-8 -*-
"""把老师发来的鼠标/键盘事件注入本机。Win7 用 SendInput；Linux 只记录不注入。

不做键盘记录，不读剪贴板。仅在远程控制会话开启时由上层调用。
"""
from __future__ import print_function

import sys

from shared.remote_protocol import sanitize_events


def screen_size():
    if sys.platform != "win32":
        return 1024, 768
    import ctypes
    user32 = ctypes.windll.user32
    # 虚拟屏幕，兼容多显示器；单屏等同主屏。
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) or user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN) or user32.GetSystemMetrics(1)
    return max(1, int(w)), max(1, int(h))


def apply_events(events, injector=None):
    """injector(ev) 可注入以便测试。默认在 Windows 上走 SendInput。"""
    cleaned = sanitize_events(events)
    applied = []
    send = injector
    if send is None:
        send = _win_send if sys.platform == "win32" else _noop
    for ev in cleaned:
        try:
            send(ev)
            applied.append(ev)
        except Exception:
            continue
    return applied


def _noop(ev):
    return None


def _win_send(ev):
    import ctypes
    from ctypes import Union, Structure, POINTER, byref, sizeof
    from ctypes import wintypes

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_MOVED = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000
    KEYEVENTF_KEYUP = 0x0002
    WHEEL_DELTA = 120

    class MOUSEINPUT(Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class KEYBDINPUT(Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class HARDWAREINPUT(Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INP(Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", _INP)]

    user32 = ctypes.windll.user32
    kind = ev.get("kind")
    inp = INPUT()
    if kind in ("move", "down", "up", "wheel"):
        x = ev.get("x", 0.0)
        y = ev.get("y", 0.0)
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = int(x * 65535)
        inp.union.mi.dy = int(y * 65535)
        flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        if kind == "move":
            flags |= MOUSEEVENTF_MOVED
        elif kind == "down":
            flags |= MOUSEEVENTF_MOVED
            btn = ev.get("btn") or "left"
            flags |= {"right": MOUSEEVENTF_RIGHTDOWN, "middle": MOUSEEVENTF_MIDDLEDOWN}.get(
                btn, MOUSEEVENTF_LEFTDOWN
            )
        elif kind == "up":
            flags |= MOUSEEVENTF_MOVED
            btn = ev.get("btn") or "left"
            flags |= {"right": MOUSEEVENTF_RIGHTUP, "middle": MOUSEEVENTF_MIDDLEUP}.get(
                btn, MOUSEEVENTF_LEFTUP
            )
        elif kind == "wheel":
            flags |= MOUSEEVENTF_MOVED | MOUSEEVENTF_WHEEL
            inp.union.mi.mouseData = int(ev.get("delta") or 0) or WHEEL_DELTA
        inp.union.mi.dwFlags = flags
    elif kind in ("keydown", "keyup"):
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = int(ev.get("vk") or 0)
        if kind == "keyup":
            inp.union.ki.dwFlags = KEYEVENTF_KEYUP
    else:
        return
    user32.SendInput(1, byref(inp), sizeof(INPUT))
