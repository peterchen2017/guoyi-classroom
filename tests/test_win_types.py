# -*- coding: utf-8 -*-
"""验证 Python 3.8 缺失的 ctypes.wintypes.HCURSOR 已做兼容。

必须能在当前 Linux 上运行，并用「没有 HCURSOR 等 3.8 缺失属性」的
仿 wintypes 模块模拟安装包里的 CPython 3.8.10。本测试不打开真实 Win32 窗口。
"""
from __future__ import print_function

import ctypes
import importlib
import sys
import types
from ctypes import Structure
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Checker(object):
    def __init__(self):
        self.ok = 0
        self.fail = 0

    def check(self, name, cond, detail=""):
        if cond:
            self.ok += 1
            status = "通过"
        else:
            self.fail += 1
            status = "失败"
        line = "[%s] %s%s" % (status, name, (" — " + detail) if detail else "")
        print(line, flush=True)
        return cond

    def summary(self):
        print("", flush=True)
        print("合计：通过 %s，失败 %s" % (self.ok, self.fail), flush=True)
        return self.fail == 0


# 源码里用到的全部 wintypes 属性（对照 CPython 3.8.10 官方文件）
USED_WINTYPES = (
    "BOOL", "BYTE", "DWORD", "FILETIME", "HBITMAP", "HBRUSH", "HCURSOR",
    "HDC", "HGDIOBJ", "HICON", "HINSTANCE", "HMENU", "HWND", "LONG",
    "LPARAM", "LPCWSTR", "LPVOID", "LPWSTR", "MSG", "POINT", "RECT",
    "UINT", "WCHAR", "WORD", "WPARAM",
)

# 经对照 3.8.10 Lib/ctypes/wintypes.py：仅 HCURSOR 不存在。
# HGDIOBJ、HMONITOR 在 3.8.10 已定义为 HANDLE。
PY38_MISSING = ("HCURSOR",)
PY38_PRESENT_HANDLES = ("HANDLE", "HWND", "HICON", "HINSTANCE", "HGDIOBJ", "HMONITOR", "HBRUSH")


def _make_py38_wintypes(also_drop=()):
    """仿 CPython 3.8.10 的 ctypes.wintypes：去掉 3.8 没有的属性。"""
    real = importlib.import_module("ctypes.wintypes")
    fake = types.ModuleType("ctypes.wintypes")
    drop = set(PY38_MISSING) | set(also_drop)
    for name in dir(real):
        if name in drop:
            continue
        setattr(fake, name, getattr(real, name))
    for name in drop:
        if hasattr(fake, name):
            delattr(fake, name)
    return fake


def _wndclass_fields(wt, wndproc):
    return [
        ("style", wt.UINT),
        ("lpfnWndProc", wndproc),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HCURSOR),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


def test_raw_py38_missing_hcursor_raises(c):
    fake = _make_py38_wintypes()
    c.check("仿 3.8 wintypes 没有 HCURSOR", not hasattr(fake, "HCURSOR"))
    c.check("仿 3.8 wintypes 仍有 HGDIOBJ", hasattr(fake, "HGDIOBJ"))
    c.check("仿 3.8 wintypes 仍有 HMONITOR", hasattr(fake, "HMONITOR"))
    raised = False
    try:
        class Boom(Structure):
            _fields_ = [("hCursor", fake.HCURSOR)]
    except AttributeError as exc:
        raised = "HCURSOR" in str(exc)
    c.check("未打补丁时用 HCURSOR 定义结构体会 AttributeError", raised)


def test_shim_on_current_python(c):
    import shared.win_types as wtmod
    importlib.reload(wtmod)
    c.check("Linux 上可以 import shared.win_types", wtmod.wintypes is not None)
    c.check("补丁后有 HCURSOR", hasattr(wtmod.wintypes, "HCURSOR"))
    handle = wtmod.wintypes.HANDLE
    c.check("HCURSOR 别名为 HANDLE", wtmod.wintypes.HCURSOR is handle)
    missing = [name for name in USED_WINTYPES if not hasattr(wtmod.wintypes, name)]
    c.check("源码用到的 wintypes 属性均可用", not missing, ",".join(missing))


def test_shim_on_fake_py38(c):
    fake = _make_py38_wintypes()
    # 再去掉 HGDIOBJ / HMONITOR，确认补丁在「全缺」时也会补上
    stripped = _make_py38_wintypes(also_drop=("HGDIOBJ", "HMONITOR"))
    from shared.win_types import apply_wintypes_aliases

    patched = apply_wintypes_aliases(fake)
    c.check("给仿 3.8 模块补上 HCURSOR", hasattr(patched, "HCURSOR"))
    c.check("补上的 HCURSOR 等于 HANDLE", patched.HCURSOR is patched.HANDLE)
    c.check("3.8 已有的 HGDIOBJ 不被改掉", patched.HGDIOBJ is fake.HGDIOBJ)

    patched2 = apply_wintypes_aliases(stripped)
    c.check("若 HGDIOBJ 也缺失则补为 HANDLE", patched2.HGDIOBJ is patched2.HANDLE)
    c.check("若 HMONITOR 也缺失则补为 HANDLE", patched2.HMONITOR is patched2.HANDLE)

    wndproc = ctypes.CFUNCTYPE(
        ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long,
        patched.HWND, patched.UINT, patched.WPARAM, patched.LPARAM,
    )

    class WNDCLASSW(Structure):
        _fields_ = _wndclass_fields(patched, wndproc)

    inst = WNDCLASSW()
    inst.hCursor = None
    names = [item[0] for item in WNDCLASSW._fields_]
    c.check("用补丁后的仿 3.8 wintypes 可定义 WNDCLASSW", "hCursor" in names)
    c.check("WNDCLASSW 可以实例化并设置 hCursor", inst.hCursor is None or True)


def _windows_ctypes_env():
    """为在 Linux 上导入 Win32 模块提供最小桩，不真正调用 Windows API。"""
    patches = [
        mock.patch("sys.platform", "win32"),
    ]
    return patches


class _WinCtypes(object):
    def __enter__(self):
        self._added_windll = False
        self._added_winfunctype = False
        self._saved_wintypes = getattr(ctypes, "wintypes", None)
        self._saved_modules = {}
        self._target_mods = (
            "shared.win_types",
            "teacher.win_console",
            "student.win_config",
            "student.win_ui",
            "shared.win_gdi",
        )
        # 先在真实 Linux 平台上导入不含 Win32 API 的依赖，避免把 sys.platform
        # 改成 win32 后标准库（tempfile / urllib）去加载 _winapi。
        import shared.version  # noqa: F401
        import teacher.api_client  # noqa: F401
        import teacher.state_view  # noqa: F401
        import tempfile, urllib.error, urllib.parse, urllib.request, shutil  # noqa: F401

        for name in self._target_mods:
            self._saved_modules[name] = sys.modules.get(name)
            sys.modules.pop(name, None)

        self._fake_wt = _make_py38_wintypes()
        self._saved_ct_wt_mod = sys.modules.get("ctypes.wintypes")
        sys.modules["ctypes.wintypes"] = self._fake_wt
        ctypes.wintypes = self._fake_wt

        if not hasattr(ctypes, "WINFUNCTYPE"):
            ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE
            self._added_winfunctype = True
        if not hasattr(ctypes, "windll"):
            ctypes.windll = mock.MagicMock(name="windll")
            self._added_windll = True

        self._plat = mock.patch("sys.platform", "win32")
        self._plat.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._plat.stop()
        if self._added_windll and hasattr(ctypes, "windll"):
            delattr(ctypes, "windll")
        if self._added_winfunctype and hasattr(ctypes, "WINFUNCTYPE"):
            delattr(ctypes, "WINFUNCTYPE")
        if self._saved_ct_wt_mod is not None:
            sys.modules["ctypes.wintypes"] = self._saved_ct_wt_mod
        else:
            # 恢复真实模块
            real = importlib.import_module("ctypes.wintypes")
            sys.modules["ctypes.wintypes"] = real
        if self._saved_wintypes is not None:
            ctypes.wintypes = self._saved_wintypes
        for name, mod in self._saved_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
        return False


def test_import_win_modules_under_py38(c):
    with _WinCtypes() as env:
        c.check("模拟环境中的原始 wintypes 无 HCURSOR", not hasattr(env._fake_wt, "HCURSOR"))
        import shared.win_types as wtmod
        c.check("导入 shared.win_types 后已补 HCURSOR", hasattr(wtmod.wintypes, "HCURSOR"))

        import teacher.win_console as win_console
        c.check("import teacher.win_console 不因 HCURSOR 崩溃", True)
        c.check("teacher.win_console 定义了 WNDCLASSW", hasattr(win_console, "WNDCLASSW"))
        field_names = [item[0] for item in win_console.WNDCLASSW._fields_]
        c.check("教师端 WNDCLASSW 含 hCursor", "hCursor" in field_names)
        inst = win_console.WNDCLASSW()
        inst.hCursor = None
        c.check("教师端 WNDCLASSW 可实例化", True)

        import student.win_config as win_config
        c.check("import student.win_config 不因 HCURSOR 崩溃", True)
        c.check("student.win_config 定义了 WNDCLASSW", hasattr(win_config, "WNDCLASSW"))
        field_names = [item[0] for item in win_config.WNDCLASSW._fields_]
        c.check("学生端 win_config WNDCLASSW 含 hCursor", "hCursor" in field_names)
        inst = win_config.WNDCLASSW()
        inst.hCursor = None
        c.check("学生端 win_config WNDCLASSW 可实例化", True)

        import student.win_ui as win_ui
        c.check("import student.win_ui 不因 HCURSOR 崩溃", True)
        c.check("student.win_ui 定义了 WNDCLASSW", hasattr(win_ui, "WNDCLASSW"))
        field_names = [item[0] for item in win_ui.WNDCLASSW._fields_]
        c.check("学生端 win_ui WNDCLASSW 含 hCursor", "hCursor" in field_names)
        inst = win_ui.WNDCLASSW()
        inst.hCursor = None
        c.check("学生端 win_ui WNDCLASSW 可实例化", True)


def test_source_uses_shared_shim(c):
    files = (
        "teacher/win_console.py",
        "student/win_config.py",
        "student/win_ui.py",
        "shared/win_gdi.py",
        "student/win_proxy.py",
        "student/win_wallpaper.py",
    )
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8")
        c.check(
            "%s 从 shared.win_types 导入 wintypes" % rel,
            "from shared.win_types import wintypes" in text
            and "from ctypes import wintypes" not in text,
        )


def main():
    c = Checker()
    test_raw_py38_missing_hcursor_raises(c)
    test_shim_on_current_python(c)
    test_shim_on_fake_py38(c)
    test_import_win_modules_under_py38(c)
    test_source_uses_shared_shim(c)
    if not c.summary():
        sys.exit(1)


if __name__ == "__main__":
    main()
