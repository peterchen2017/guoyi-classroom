# -*- coding: utf-8 -*-
"""ctypes.wintypes 兼容层，供教师端和学生端统一使用。

Windows 安装包内置的是 embeddable CPython 3.8.10。该版本的
Lib/ctypes/wintypes.py 没有 HCURSOR（CPython 3.14 才加入，别名为 HANDLE）。
较新的 Linux 开发机有时也没有这个属性，或有但此前未在 3.8 环境验证，
因此会把「教师主窗口 / 加入课堂」对话框在 Win7 上直接打不开。

对照 3.8.10 官方 wintypes：HGDIOBJ、HMONITOR、HICON、HINSTANCE、HWND、
HANDLE 均已存在。源码里用到、但 3.8.10 没有的属性目前只有 HCURSOR。

本模块在属性缺失时将其别名到已有的 HANDLE（或 HWND），并且在 Linux 上
也可 import，不会因为没有 Windows 而失败。
"""
from __future__ import print_function

try:
    from ctypes import wintypes as _raw_wintypes
except ImportError:  # pragma: no cover
    _raw_wintypes = None

# 仅在目标模块上确实没有该属性时才补。HGDIOBJ / HMONITOR 在 3.8 已有，
# 列在这里是为了防备被替换成「缺属性的仿 3.8 模块」时仍能工作。
_HANDLE_ALIASES = (
    "HCURSOR",
    "HGDIOBJ",
    "HMONITOR",
)


def apply_wintypes_aliases(ns):
    """把 3.8 缺失的 HANDLE 别名补到 ns 上，并返回 ns。"""
    if ns is None:
        return None
    handle = getattr(ns, "HANDLE", None)
    if handle is None:
        handle = getattr(ns, "HWND", None)
    if handle is None:
        import ctypes
        handle = ctypes.c_void_p
    for name in _HANDLE_ALIASES:
        if not hasattr(ns, name):
            setattr(ns, name, handle)
    return ns


wintypes = apply_wintypes_aliases(_raw_wintypes)
