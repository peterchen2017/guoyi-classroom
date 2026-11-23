# -*- coding: utf-8 -*-
"""学生端首次连接设置窗口（Win32，不依赖 tkinter，兼容 Windows 7）。"""

import ctypes
import sys
import threading
from ctypes import Structure, byref, sizeof

if sys.platform != "win32":
    raise ImportError("win_config 仅在 Windows 上使用")

from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

IS_64 = sizeof(ctypes.c_void_p) == 8
WNDPROCTYPE = ctypes.WINFUNCTYPE(
    ctypes.c_longlong if IS_64 else ctypes.c_long,
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_SETFONT = 0x0030
ES_AUTOHSCROLL = 0x0080
ES_LEFT = 0
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_BORDER = 0x00800000
WS_TABSTOP = 0x00010000
WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_DLGFRAME = 0x00400000
DS_MODALFRAME = 0x80
BS_PUSHBUTTON = 0
BS_DEFPUSHBUTTON = 1
SS_LEFT = 0
WHITE_BRUSH = 0
DEFAULT_GUI_FONT = 17
IDOK = 1
IDCANCEL = 2
ID_DISCOVER = 3
ID_NAME = 101
ID_SERVER = 102
ID_PORT = 103
ID_CODE = 104

user32.CreateWindowExW.restype = wintypes.HWND
user32.GetDlgItem.restype = wintypes.HWND
user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]


def _text(hwnd):
    n = user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(n)
    user32.GetWindowTextW(hwnd, buf, n)
    return buf.value.strip()


def _set(hwnd, text):
    user32.SetWindowTextW(hwnd, text or "")


def ask_connection(server="", port=8765, name="", code=""):
    """弹出设置窗口，确定则返回 (server, port, name, code)，取消返回 None。"""
    result = {"value": None}
    done = threading.Event()

    def run():
        result["value"] = _run_dialog(server, port, name, code)
        done.set()

    if threading.current_thread() is threading.main_thread():
        return _run_dialog(server, port, name, code)
    t = threading.Thread(target=run)
    t.start()
    t.join()
    return result["value"]


def _run_dialog(server, port, name, code):
    hinst = kernel32.GetModuleHandleW(None)
    proc = WNDPROCTYPE(_make_proc())
    # keep reference
    _run_dialog._proc = proc  # type: ignore

    class WNDCLASSW(Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROCTYPE),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HCURSOR),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    cls = WNDCLASSW()
    cls.lpfnWndProc = proc
    cls.hInstance = hinst
    cls.hbrBackground = gdi32.GetStockObject(WHITE_BRUSH)
    cls.lpszClassName = "GuoyiClassroomConnect"
    cls.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
    user32.RegisterClassW(byref(cls))

    hwnd = user32.CreateWindowExW(
        0, "GuoyiClassroomConnect", "加入课堂 - 乐昌国艺书院",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
        200, 160, 460, 340,
        None, None, hinst, None,
    )
    font = gdi32.GetStockObject(DEFAULT_GUI_FONT)
    state = {
        "hwnd": hwnd,
        "hinst": hinst,
        "font": font,
        "result": None,
        "edits": {},
    }
    _run_dialog._state = state

    def add_label(text, x, y, w=120, h=22):
        hctl = user32.CreateWindowExW(0, "STATIC", text, WS_CHILD | WS_VISIBLE | SS_LEFT,
                                      x, y, w, h, hwnd, None, hinst, None)
        user32.SendMessageW(hctl, WM_SETFONT, font, 1)
        return hctl

    def add_edit(cid, x, y, w=260, text=""):
        hctl = user32.CreateWindowExW(
            0x200, "EDIT", text or "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL | ES_LEFT,
            x, y, w, 24, hwnd, wintypes.HMENU(cid), hinst, None,
        )
        user32.SendMessageW(hctl, WM_SETFONT, font, 1)
        state["edits"][cid] = hctl
        return hctl

    def add_btn(cid, text, x, y, w=100, default=False):
        style = WS_CHILD | WS_VISIBLE | WS_TABSTOP | (BS_DEFPUSHBUTTON if default else BS_PUSHBUTTON)
        hctl = user32.CreateWindowExW(0, "BUTTON", text, style,
                                      x, y, w, 30, hwnd, wintypes.HMENU(cid), hinst, None)
        user32.SendMessageW(hctl, WM_SETFONT, font, 1)
        return hctl

    add_label("课堂管理运行中，请填写连接信息：", 24, 16, 400, 22)
    add_label("学生姓名 / 机位", 24, 52)
    add_edit(ID_NAME, 160, 48, 250, name)
    add_label("教师机 IP", 24, 92)
    add_edit(ID_SERVER, 160, 88, 250, server)
    add_label("端口", 24, 132)
    add_edit(ID_PORT, 160, 128, 250, str(port or 8765))
    add_label("课堂加入码", 24, 172)
    add_edit(ID_CODE, 160, 168, 250, code)
    add_label("加入码可向老师询问；也可留空，由老师在控制台允许加入。", 24, 200, 400, 28)
    add_label("版权所有 © 乐昌国艺书院    开发者：陈老师", 24, 228, 400, 22)
    add_btn(ID_DISCOVER, "自动发现", 24, 250, 100)
    add_btn(IDOK, "连接", 200, 250, 100, default=True)
    add_btn(IDCANCEL, "取消", 314, 250, 100)

    user32.ShowWindow(hwnd, 1)
    user32.UpdateWindow(hwnd)
    msg = wintypes.MSG()
    while user32.GetMessageW(byref(msg), None, 0, 0) != 0:
        if not user32.IsDialogMessageW(hwnd, byref(msg)):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
    return state["result"]


def _make_proc():
    def wndproc(hwnd, msg, wparam, lparam):
        state = getattr(_run_dialog, "_state", None)
        if msg == WM_COMMAND and state is not None:
            cmd = wparam & 0xFFFF
            if cmd == IDCANCEL:
                state["result"] = None
                user32.DestroyWindow(hwnd)
                return 0
            if cmd == IDOK:
                name = _text(state["edits"][ID_NAME])
                server = _text(state["edits"][ID_SERVER])
                port_s = _text(state["edits"][ID_PORT]) or "8765"
                code = _text(state["edits"][ID_CODE])
                try:
                    port = int(port_s)
                except ValueError:
                    user32.MessageBoxW(hwnd, "端口必须是数字", "提示", 0x10)
                    return 0
                if not name:
                    user32.MessageBoxW(hwnd, "请填写学生姓名或机位号", "提示", 0x30)
                    return 0
                if not server:
                    user32.MessageBoxW(hwnd, "请填写教师机 IP，或先点「自动发现」", "提示", 0x30)
                    return 0
                state["result"] = (server, port, name, code)
                user32.DestroyWindow(hwnd)
                return 0
            if cmd == ID_DISCOVER:
                from student.client import discover_teacher
                found = discover_teacher()
                if found:
                    _set(state["edits"][ID_SERVER], found[0])
                    _set(state["edits"][ID_PORT], str(found[1]))
                    user32.MessageBoxW(hwnd, "已发现教师机 %s:%s" % found, "自动发现", 0x40)
                else:
                    user32.MessageBoxW(hwnd, "没有发现教师机，请确认已在同一 WiFi，且教师端已启动。", "自动发现", 0x30)
                return 0
        if msg == WM_CLOSE:
            if state is not None:
                state["result"] = None
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    return wndproc
