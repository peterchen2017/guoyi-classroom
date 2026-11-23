# -*- coding: utf-8 -*-
"""教师端原生主窗口（Win32 + ctypes）。不依赖 tkinter / Qt / WebView。

布局参考常见机房软件：顶部工具栏 + 左侧学生名单 + 右侧屏幕墙。
仅在 Windows 上使用；Linux 导入本模块会失败，属正常。
"""

from __future__ import print_function

import ctypes
import os
import queue
import sys
import threading
from ctypes import Structure, byref, c_void_p, sizeof

if sys.platform != "win32":
    raise ImportError("win_console 仅在 Windows 上使用")

from shared.win_types import wintypes

from shared.version import TEACHER_WINDOW_TITLE, VERSION
from teacher.api_client import AuthExpired, TeacherApiError, TeacherClient
from teacher import state_view

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
comdlg32 = ctypes.windll.comdlg32

IS_64 = sizeof(c_void_p) == 8
WNDPROCTYPE = ctypes.WINFUNCTYPE(
    ctypes.c_longlong if IS_64 else ctypes.c_long,
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
)
LRESULT = ctypes.c_longlong if IS_64 else ctypes.c_long

user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.GetDlgItem.restype = wintypes.HWND
user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.GetStockObject.restype = wintypes.HGDIOBJ
comdlg32.GetOpenFileNameW.argtypes = [ctypes.c_void_p]
comdlg32.GetOpenFileNameW.restype = wintypes.BOOL

# ---------- 常量 ----------
WM_DESTROY = 0x0002
WM_SIZE = 0x0005
WM_CLOSE = 0x0010
WM_SETFONT = 0x0030
WM_GETMINMAXINFO = 0x0024
WM_COMMAND = 0x0111
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_CTLCOLORSTATIC = 0x0138
WM_VSCROLL = 0x0115
WM_MOUSEWHEEL = 0x020A
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_APP = 0x8000
WM_APP_UI = WM_APP + 1

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_BORDER = 0x00800000
WS_TABSTOP = 0x00010000
WS_VSCROLL = 0x00200000
WS_CLIPCHILDREN = 0x02000000
WS_OVERLAPPEDWINDOW = (
    WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
)
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_CONTROLPARENT = 0x00010000

ES_LEFT = 0
ES_AUTOHSCROLL = 0x0080
ES_AUTOVSCROLL = 0x0040
ES_MULTILINE = 0x0004
ES_PASSWORD = 0x0020
ES_WANTRETURN = 0x1000

BS_PUSHBUTTON = 0
BS_DEFPUSHBUTTON = 1
BS_AUTOCHECKBOX = 3
BS_LEFT = 0x00000100
BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1
BST_CHECKED = 1
BST_UNCHECKED = 0

LBS_NOTIFY = 0x0001
LBS_NOINTEGRALHEIGHT = 0x0100
LBS_HASSTRINGS = 0x0040
LB_ADDSTRING = 0x0180
LB_RESETCONTENT = 0x0184
LB_GETCURSEL = 0x0188
LB_SETCURSEL = 0x0186
LBN_SELCHANGE = 1
LBN_DBLCLK = 2

SB_LINEUP = 0
SB_LINEDOWN = 1
SB_PAGEUP = 2
SB_PAGEDOWN = 3
SB_THUMBTRACK = 5
SB_THUMBPOSITION = 4
SB_TOP = 6
SB_BOTTOM = 7
SIF_RANGE = 1
SIF_PAGE = 2
SIF_POS = 4
SB_VERT = 1

SW_SHOWNORMAL = 1
IDC_ARROW = 32512
WHITE_BRUSH = 0
DEFAULT_GUI_FONT = 17
TRANSPARENT = 1
DT_LEFT = 0x00000000
DT_CENTER = 0x00000001
DT_VCENTER = 0x00000004
DT_SINGLELINE = 0x00000020
DT_WORDBREAK = 0x00000010
DT_END_ELLIPSIS = 0x00008000
SRCCOPY = 0x00CC0020

MB_OK = 0
MB_YESNO = 4
MB_ICONERROR = 0x10
MB_ICONQUESTION = 0x20
MB_ICONINFORMATION = 0x40
MB_ICONWARNING = 0x30
MB_TOPMOST = 0x00040000
IDYES = 6
IDOK = 1
IDCANCEL = 2

OFN_FILEMUSTEXIST = 0x00001000
OFN_PATHMUSTEXIST = 0x00000800
OFN_HIDEREADONLY = 0x00000004
OFN_EXPLORER = 0x00080000
OFN_NOCHANGEDIR = 0x00000008

ID_CLASS = 1001
ID_REFRESH_CODE = 1002
ID_PASSWORD = 1003
ID_LOCK_ALL = 1004
ID_UNLOCK_ALL = 1005
ID_ANNOUNCE = 1006
ID_QUESTION = 1007
ID_FILE = 1008
ID_RESTRICT = 1009
ID_RESTRICT_LISTS = 1010
ID_BROADCAST = 1011
ID_SHRINK = 1012
ID_BROADCAST_IMAGE = 1013
ID_DESKTOP = 1014
ID_DESKTOP_UNLOCK = 1015
ID_OPEN_BROWSER = 1016
ID_STUDENT_LIST = 1100
ID_APPROVE = 1201
ID_DENY = 1202
ID_VIEW = 1203
ID_LOCK_ONE = 1204
ID_UNLOCK_ONE = 1205
ID_REVOKE = 1206
ID_HEADER_BRAND = 1301
ID_HEADER_STATUS = 1302
ID_HEADER_CODE = 1303
ID_HEADER_IP = 1304
ID_FOOTER = 1305
ID_SUMMARY = 1306
ID_FOCUS_LOCK = 1401
ID_FOCUS_CLOSE = 1402
IDD_USER = 201
IDD_PASS = 202
IDD_OLD = 203
IDD_NEW = 204
IDD_TEXT = 205
IDD_GAMES = 206
IDD_DOWN = 207
IDD_WHITE = 208
IDD_EXTS = 209
IDD_RESET = 210
IDD_BROWSE = 211
IDD_LOCKDESK = 212
IDD_APPLY = 213
IDD_UNLOCK = 214
IDD_INFO = 215

FILE_FILTER = (
    "课堂资料 (C++ / 文本)\0*.cpp;*.h;*.hpp;*.cc;*.cxx;*.c;*.h++;*.hxx;*.hh;*.txt;*.in;*.out;*.md\0"
    "所有文件\0*.*\0\0"
)
IMAGE_FILTER = "图片文件\0*.jpg;*.jpeg;*.png;*.bmp;*.gif\0所有文件\0*.*\0\0"
WALLPAPER_FILTER = "壁纸图片\0*.jpg;*.jpeg;*.png;*.bmp\0所有文件\0*.*\0\0"

# 颜色（COLORREF = 0x00BBGGRR）
COL_HEADER = 0x00351A12
COL_HEADER_TEXT = 0x00FFFFFF
COL_TOOL = 0x00F5EEE8
COL_WALL = 0x00F8F6F4
COL_TILE_CAP = 0x00333333
COL_OFFLINE = 0x00666666
COL_FOOTER = 0x00EEE8E0

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


class PAINTSTRUCT(Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", wintypes.RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", wintypes.BYTE * 32),
    ]


class MINMAXINFO(Structure):
    _fields_ = [
        ("ptReserved", wintypes.POINT),
        ("ptMaxSize", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("ptMinTrackSize", wintypes.POINT),
        ("ptMaxTrackSize", wintypes.POINT),
    ]


class SCROLLINFO(Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("fMask", wintypes.UINT),
        ("nMin", ctypes.c_int),
        ("nMax", ctypes.c_int),
        ("nPage", wintypes.UINT),
        ("nPos", ctypes.c_int),
        ("nTrackPos", ctypes.c_int),
    ]


class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


class OPENFILENAMEW(Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", c_void_p),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", c_void_p),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


class BITMAP(Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", c_void_p),
    ]


_KEEP = []


def _hiword(val):
    return (int(val) >> 16) & 0xFFFF


def _loword(val):
    return int(val) & 0xFFFF


def _signed_hiword(val):
    x = _hiword(val)
    if x >= 0x8000:
        x -= 0x10000
    return x


def get_text(hwnd):
    if not hwnd:
        return ""
    n = user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(n)
    user32.GetWindowTextW(hwnd, buf, n)
    return buf.value


def set_text(hwnd, text):
    if hwnd:
        user32.SetWindowTextW(hwnd, text or "")


def set_font(hwnd, font):
    if hwnd and font:
        user32.SendMessageW(hwnd, WM_SETFONT, font, 1)


def message_box(title, text, flags=MB_OK | MB_ICONINFORMATION, parent=None):
    return user32.MessageBoxW(parent, str(text), str(title), flags | MB_TOPMOST)


def confirm(parent, title, text):
    return message_box(title, text, MB_YESNO | MB_ICONQUESTION, parent) == IDYES


def default_font():
    font = gdi32.GetStockObject(DEFAULT_GUI_FONT)
    created = gdi32.CreateFontW(-16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "微软雅黑")
    if created:
        _KEEP.append(created)
        return created
    return font


def title_font():
    created = gdi32.CreateFontW(-20, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 0, 0, "微软雅黑")
    if created:
        _KEEP.append(created)
        return created
    return default_font()


def register_class(name, proc, background=None):
    inst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = inst
    if background is None:
        wc.hbrBackground = gdi32.GetStockObject(WHITE_BRUSH)
    else:
        wc.hbrBackground = background
    wc.lpszClassName = name
    wc.hCursor = user32.LoadCursorW(None, c_void_p(IDC_ARROW))
    wc.style = 0x0008 | 0x0002  # CS_DBLCLKS | CS_HREDRAW
    user32.RegisterClassW(byref(wc))
    _KEEP.append(proc)
    _KEEP.append(wc)
    return inst


def _client_size(hwnd):
    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, byref(rc))
    return rc.right - rc.left, rc.bottom - rc.top


def add_ctl(parent, cls, text, style, x, y, w, h, cid=0, ex=0, font=None):
    inst = kernel32.GetModuleHandleW(None)
    hwnd = user32.CreateWindowExW(
        ex, cls, text or "", style,
        int(x), int(y), int(w), int(h),
        parent, wintypes.HMENU(cid) if cid else None, inst, None,
    )
    if font:
        set_font(hwnd, font)
    return hwnd


def jpeg_to_hbitmap(image_bytes, dest_w, dest_h):
    """用已打包的 Pillow 解码缩略图，生成 HBITMAP。失败返回 None。"""
    if not image_bytes:
        return None
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        dest_w = max(1, int(dest_w))
        dest_h = max(1, int(dest_h))
        if im.size != (dest_w, dest_h):
            resample = getattr(Image, "BILINEAR", 2)
            im = im.resize((dest_w, dest_h), resample)
        raw = im.tobytes("raw", "BGRX")
    except Exception:
        return None
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = dest_w
    bmi.bmiHeader.biHeight = -dest_h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    hdc = user32.GetDC(None)
    hbmp = gdi32.CreateCompatibleBitmap(hdc, dest_w, dest_h)
    if not hbmp:
        user32.ReleaseDC(None, hdc)
        return None
    gdi32.SetDIBits(hdc, hbmp, 0, dest_h, raw, byref(bmi), 0)
    user32.ReleaseDC(None, hdc)
    return hbmp


def jpeg_to_hbitmap_fit(image_bytes, hwnd, margin=20, bottom=50):
    if not image_bytes or not hwnd:
        return jpeg_to_hbitmap(image_bytes, 640, 360) if image_bytes else None
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(image_bytes))
        cw, ch = _client_size(hwnd)
        max_w = max(160, cw - margin * 2)
        max_h = max(120, ch - bottom - margin)
        w, h = im.size
        if w <= 0 or h <= 0:
            return None
        scale = min(float(max_w) / w, float(max_h) / h, 1.0)
        return jpeg_to_hbitmap(image_bytes, max(1, int(w * scale)), max(1, int(h * scale)))
    except Exception:
        return jpeg_to_hbitmap(image_bytes, 640, 360)


def delete_bitmap(hbmp):
    if hbmp:
        try:
            gdi32.DeleteObject(hbmp)
        except Exception:
            pass


def open_file_dialog(parent, title, filt, defext=""):
    buf = ctypes.create_unicode_buffer(1024)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = sizeof(OPENFILENAMEW)
    ofn.hwndOwner = parent
    ofn.lpstrFilter = filt
    ofn.nFilterIndex = 1
    ofn.lpstrFile = buf
    ofn.nMaxFile = 1024
    ofn.lpstrTitle = title
    ofn.Flags = (
        OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_HIDEREADONLY | OFN_NOCHANGEDIR
    )
    if defext:
        ofn.lpstrDefExt = defext
    if comdlg32.GetOpenFileNameW(byref(ofn)):
        return buf.value
    return None



def send_list_string(hwnd, text):
    buf = ctypes.create_unicode_buffer(text or "")
    return user32.SendMessageW(hwnd, LB_ADDSTRING, 0, ctypes.addressof(buf))

def modal_loop(hwnd, parent=None):
    if parent:
        user32.EnableWindow(parent, False)
    msg = wintypes.MSG()
    while user32.IsWindow(hwnd) and user32.GetMessageW(byref(msg), None, 0, 0) > 0:
        if msg.message == 0x0012:  # WM_QUIT
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
            user32.PostQuitMessage(int(msg.wParam))
            break
        if not user32.IsDialogMessageW(hwnd, byref(msg)):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
    if parent and user32.IsWindow(parent):
        user32.EnableWindow(parent, True)
        user32.SetForegroundWindow(parent)

def _run_simple_dialog(class_name, title, width, height, build, parent=None, font=None):
    """build(state) 创建控件；state['result'] 为返回值。确定后应 DestroyWindow。"""
    state = {"result": None, "hwnd": None, "edits": {}, "font": font or default_font()}
    inst = kernel32.GetModuleHandleW(None)

    def _proc(hwnd, msg, wparam, lparam):
        if msg == WM_COMMAND:
            cid = _loword(wparam)
            if cid == IDOK:
                if state.get("on_ok"):
                    state["on_ok"]()
                return 0
            if cid == IDCANCEL:
                state["result"] = None
                user32.DestroyWindow(hwnd)
                return 0
            if state.get("on_command"):
                state["on_command"](cid)
                return 0
        if msg == WM_CLOSE:
            state["result"] = None
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    proc = WNDPROCTYPE(_proc)
    register_class(class_name, proc, gdi32.GetStockObject(WHITE_BRUSH))
    style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_VISIBLE
    left, top = 200, 140
    if parent:
        rc = wintypes.RECT()
        user32.GetWindowRect(parent, byref(rc))
        left = rc.left + 40
        top = rc.top + 40
    hwnd = user32.CreateWindowExW(
        0, class_name, title, style,
        int(left), int(top), int(width), int(height),
        parent, None, inst, None,
    )
    state["hwnd"] = hwnd
    build(state)
    user32.ShowWindow(hwnd, SW_SHOWNORMAL)
    user32.UpdateWindow(hwnd)
    user32.SetForegroundWindow(hwnd)
    modal_loop(hwnd, parent)
    return state["result"]


def ask_login(parent=None, username="teacher", error=""):
    def build(state):
        hwnd = state["hwnd"]
        font = state["font"]
        add_ctl(hwnd, "STATIC", "乐昌国艺书院  机房课堂管理  v%s" % VERSION,
                WS_CHILD | WS_VISIBLE, 24, 16, 360, 24, font=font)
        add_ctl(hwnd, "STATIC", "教师账号", WS_CHILD | WS_VISIBLE, 24, 56, 80, 22, font=font)
        ed_user = add_ctl(
            hwnd, "EDIT", username or "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL | ES_LEFT,
            110, 54, 250, 24, IDD_USER, WS_EX_CLIENTEDGE, font,
        )
        add_ctl(hwnd, "STATIC", "密码", WS_CHILD | WS_VISIBLE, 24, 96, 80, 22, font=font)
        ed_pass = add_ctl(
            hwnd, "EDIT", "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL | ES_PASSWORD,
            110, 94, 250, 24, IDD_PASS, WS_EX_CLIENTEDGE, font,
        )
        if error:
            add_ctl(hwnd, "STATIC", error, WS_CHILD | WS_VISIBLE, 24, 128, 350, 40, font=font)
        add_ctl(hwnd, "BUTTON", "登录", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
                110, 176, 100, 30, IDOK, font=font)
        add_ctl(hwnd, "BUTTON", "退出", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                230, 176, 100, 30, IDCANCEL, font=font)
        state["edits"]["user"] = ed_user
        state["edits"]["pass"] = ed_pass
        user32.SetFocus(ed_pass if username else ed_user)

        def on_ok():
            user = get_text(ed_user).strip()
            pw = get_text(ed_pass)
            if not user or not pw:
                message_box("登录", "请输入账号和密码。", MB_OK | MB_ICONWARNING, hwnd)
                return
            state["result"] = (user, pw)
            user32.DestroyWindow(hwnd)

        state["on_ok"] = on_ok

    return _run_simple_dialog("GuoyiTeacherLogin", "教师登录 - 乐昌国艺书院", 420, 260, build, parent)


def ask_text(parent, title, label):
    def build(state):
        hwnd = state["hwnd"]
        font = state["font"]
        add_ctl(hwnd, "STATIC", label, WS_CHILD | WS_VISIBLE, 16, 12, 430, 22, font=font)
        ed = add_ctl(
            hwnd, "EDIT", "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | WS_VSCROLL
            | ES_MULTILINE | ES_WANTRETURN | ES_AUTOVSCROLL,
            16, 38, 440, 150, IDD_TEXT, WS_EX_CLIENTEDGE, font,
        )
        add_ctl(hwnd, "BUTTON", "发送", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
                230, 200, 100, 28, IDOK, font=font)
        add_ctl(hwnd, "BUTTON", "取消", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                346, 200, 100, 28, IDCANCEL, font=font)
        user32.SetFocus(ed)

        def on_ok():
            text = get_text(ed).strip()
            if not text:
                message_box(title, "内容不能为空。", MB_OK | MB_ICONWARNING, hwnd)
                return
            state["result"] = text
            user32.DestroyWindow(hwnd)

        state["on_ok"] = on_ok

    return _run_simple_dialog("GuoyiTeacherText", title, 490, 280, build, parent)


def ask_password(parent):
    def build(state):
        hwnd = state["hwnd"]
        font = state["font"]
        add_ctl(hwnd, "STATIC", "修改教师密码", WS_CHILD | WS_VISIBLE, 20, 16, 300, 22, font=font)
        add_ctl(hwnd, "STATIC", "原密码", WS_CHILD | WS_VISIBLE, 20, 52, 90, 22, font=font)
        ed_old = add_ctl(
            hwnd, "EDIT", "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL | ES_PASSWORD,
            120, 50, 250, 24, IDD_OLD, WS_EX_CLIENTEDGE, font,
        )
        add_ctl(hwnd, "STATIC", "新密码（至少 8 位）", WS_CHILD | WS_VISIBLE, 20, 92, 200, 22, font=font)
        ed_new = add_ctl(
            hwnd, "EDIT", "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL | ES_PASSWORD,
            20, 116, 350, 24, IDD_NEW, WS_EX_CLIENTEDGE, font,
        )
        add_ctl(hwnd, "BUTTON", "保存", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
                160, 164, 100, 28, IDOK, font=font)
        add_ctl(hwnd, "BUTTON", "取消", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                270, 164, 100, 28, IDCANCEL, font=font)
        user32.SetFocus(ed_old)

        def on_ok():
            old = get_text(ed_old)
            new = get_text(ed_new)
            if len(new) < 8:
                message_box("改密码", "新密码至少 8 位。", MB_OK | MB_ICONWARNING, hwnd)
                return
            state["result"] = (old, new)
            user32.DestroyWindow(hwnd)

        state["on_ok"] = on_ok

    return _run_simple_dialog("GuoyiTeacherPassword", "修改教师密码", 420, 250, build, parent)


def ask_restrict_lists(parent, wr):
    wr = wr or {}

    def build(state):
        hwnd = state["hwnd"]
        font = state["font"]
        add_ctl(
            hwnd, "STATIC",
            "每行一个域名。按主机名拦截，不解密 HTTPS。教师机地址和课堂下发文件始终放行。",
            WS_CHILD | WS_VISIBLE, 16, 10, 700, 36, font=font,
        )

        def area(cid, label, x, y, values):
            add_ctl(hwnd, "STATIC", label, WS_CHILD | WS_VISIBLE, x, y, 330, 20, font=font)
            return add_ctl(
                hwnd, "EDIT", "\r\n".join(values or []),
                WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | WS_VSCROLL
                | ES_MULTILINE | ES_WANTRETURN | ES_AUTOVSCROLL,
                x, y + 22, 340, 130, cid, WS_EX_CLIENTEDGE, font,
            )

        ed_g = area(IDD_GAMES, "网页游戏域名", 16, 50, wr.get("game_domains"))
        ed_d = area(IDD_DOWN, "下载站 / 网盘域名", 370, 50, wr.get("download_domains"))
        ed_w = area(IDD_WHITE, "白名单（教学网站）", 16, 220, wr.get("whitelist_domains"))
        ed_e = area(IDD_EXTS, "拦截的下载扩展名", 370, 220, wr.get("extensions"))
        add_ctl(hwnd, "BUTTON", "保存名单", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
                280, 380, 110, 30, IDOK, font=font)
        add_ctl(hwnd, "BUTTON", "恢复默认名单", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                400, 380, 130, 30, IDD_RESET, font=font)
        add_ctl(hwnd, "BUTTON", "关闭", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                540, 380, 100, 30, IDCANCEL, font=font)

        def on_ok():
            state["result"] = {
                "game_domains": state_view.split_lines(get_text(ed_g)),
                "download_domains": state_view.split_lines(get_text(ed_d)),
                "whitelist_domains": state_view.split_lines(get_text(ed_w)),
                "extensions": state_view.split_lines(get_text(ed_e)),
            }
            user32.DestroyWindow(hwnd)

        def on_command(cid):
            if cid == IDD_RESET:
                state["result"] = {"reset_defaults": True}
                user32.DestroyWindow(hwnd)

        state["on_ok"] = on_ok
        state["on_command"] = on_command

    return _run_simple_dialog("GuoyiTeacherRestrict", "网页游戏 / 下载限制名单", 740, 460, build, parent)


def ask_desktop(parent, desk):
    desk = desk or {}
    chosen = {"path": None}

    def build(state):
        hwnd = state["hwnd"]
        font = state["font"]
        add_ctl(
            hwnd, "STATIC",
            "上传 jpg / png / bmp 壁纸，下发到已加入的学生机。锁定后学生不能更改壁纸；下课或重启后仍然保持，直到点「解除桌面锁定」。",
            WS_CHILD | WS_VISIBLE, 16, 12, 450, 70, font=font,
        )
        cur = "尚未设置壁纸"
        if desk.get("has_wallpaper"):
            cur = "当前：" + (desk.get("filename") or "已设置")
            if desk.get("locked"):
                cur += "（已锁定）"
        info = add_ctl(hwnd, "STATIC", cur, WS_CHILD | WS_VISIBLE, 16, 88, 450, 22, IDD_INFO, font=font)
        add_ctl(hwnd, "BUTTON", "选择壁纸图片…", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                16, 118, 160, 28, IDD_BROWSE, font=font)
        chk = add_ctl(
            hwnd, "BUTTON", "锁定桌面（学生不能更改壁纸）",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX | BS_LEFT,
            16, 158, 360, 24, IDD_LOCKDESK, font=font,
        )
        user32.SendMessageW(chk, BM_SETCHECK, BST_CHECKED, 0)
        add_ctl(hwnd, "BUTTON", "下发并应用", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
                16, 210, 120, 30, IDD_APPLY, font=font)
        if desk.get("locked"):
            add_ctl(hwnd, "BUTTON", "解除锁定", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                    150, 210, 100, 30, IDD_UNLOCK, font=font)
        add_ctl(hwnd, "BUTTON", "取消", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                366, 210, 100, 30, IDCANCEL, font=font)

        def on_command(cid):
            if cid == IDD_BROWSE:
                path = open_file_dialog(hwnd, "选择壁纸图片", WALLPAPER_FILTER, "jpg")
                if path:
                    chosen["path"] = path
                    set_text(info, "已选择：" + os.path.basename(path))
            elif cid == IDD_APPLY:
                if not chosen["path"]:
                    message_box("设置默认桌面", "请先选择一张壁纸图片（jpg / png / bmp）。",
                                MB_OK | MB_ICONWARNING, hwnd)
                    return
                lock = user32.SendMessageW(chk, BM_GETCHECK, 0, 0) == BST_CHECKED
                state["result"] = {"path": chosen["path"], "lock": bool(lock)}
                user32.DestroyWindow(hwnd)
            elif cid == IDD_UNLOCK:
                state["result"] = {"unlock": True}
                user32.DestroyWindow(hwnd)

        state["on_command"] = on_command
        state["on_ok"] = lambda: on_command(IDD_APPLY)

    return _run_simple_dialog("GuoyiTeacherDesktop", "设置机房默认桌面", 500, 300, build, parent)

class ScreenWall(object):
    CLASS_NAME = "GuoyiTeacherWall"

    def __init__(self, parent, font, on_click):
        self.parent = parent
        self.font = font
        self.on_click = on_click
        self.hwnd = None
        self.tiles = []
        self.scroll = 0
        self.tile_w = 200
        self.tile_h = 148
        self.gap = 10
        self.img_h = 120
        self._bg = gdi32.CreateSolidBrush(COL_WALL)
        _KEEP.append(self._bg)
        self._proc = WNDPROCTYPE(self._wndproc)
        register_class(self.CLASS_NAME, self._proc, self._bg)
        self.hwnd = user32.CreateWindowExW(
            WS_EX_CLIENTEDGE, self.CLASS_NAME, "",
            WS_CHILD | WS_VISIBLE | WS_VSCROLL | WS_CLIPCHILDREN,
            0, 0, 100, 100, parent, None, kernel32.GetModuleHandleW(None), None,
        )

    def clear_bitmaps(self):
        for t in self.tiles:
            if t.get("hbmp"):
                delete_bitmap(t["hbmp"])
                t["hbmp"] = None

    def destroy(self):
        self.clear_bitmaps()
        self.tiles = []

    def set_tiles(self, entries):
        old = {t["id"]: t for t in self.tiles}
        new_tiles = []
        for item in entries:
            sid = item["id"]
            prev = old.get(sid)
            tile = {
                "id": sid,
                "name": item.get("name") or "学生",
                "locked": bool(item.get("locked")),
                "at": item.get("at"),
                "hbmp": None,
            }
            if prev and prev.get("at") == tile["at"] and prev.get("hbmp"):
                tile["hbmp"] = prev["hbmp"]
                prev["hbmp"] = None
            elif item.get("image_bytes"):
                tile["hbmp"] = jpeg_to_hbitmap(item["image_bytes"], self.tile_w, self.img_h)
            new_tiles.append(tile)
        self.clear_bitmaps()
        self.tiles = new_tiles
        self._update_scroll()
        if self.hwnd:
            user32.InvalidateRect(self.hwnd, None, True)

    def update_image(self, device_id, at, image_bytes):
        for t in self.tiles:
            if t["id"] == device_id:
                if t.get("hbmp") and t.get("at") != at:
                    delete_bitmap(t["hbmp"])
                    t["hbmp"] = None
                t["at"] = at
                if image_bytes:
                    t["hbmp"] = jpeg_to_hbitmap(image_bytes, self.tile_w, self.img_h)
                if self.hwnd:
                    user32.InvalidateRect(self.hwnd, None, True)
                return

    def layout(self, x, y, w, h):
        if self.hwnd:
            user32.MoveWindow(self.hwnd, int(x), int(y), int(w), int(h), True)
            self._update_scroll()
            user32.InvalidateRect(self.hwnd, None, True)

    def _cols_rows(self):
        cw, ch = _client_size(self.hwnd) if self.hwnd else (0, 0)
        cell_w = self.tile_w + self.gap
        cols = max(1, int((cw - self.gap) / cell_w)) if cw else 1
        n = len(self.tiles)
        rows = (n + cols - 1) // cols if n else 0
        content = rows * (self.tile_h + self.gap) + self.gap if rows else 0
        return cols, rows, cw, ch, content

    def _update_scroll(self):
        if not self.hwnd:
            return
        cols, rows, cw, ch, content = self._cols_rows()
        max_pos = max(0, content - ch)
        if self.scroll > max_pos:
            self.scroll = max_pos
        if self.scroll < 0:
            self.scroll = 0
        si = SCROLLINFO()
        si.cbSize = sizeof(SCROLLINFO)
        si.fMask = SIF_RANGE | SIF_PAGE | SIF_POS
        si.nMin = 0
        si.nMax = max(content - 1, 0)
        si.nPage = max(ch, 1)
        si.nPos = int(self.scroll)
        user32.SetScrollInfo(self.hwnd, SB_VERT, byref(si), True)

    def _tile_at(self, x, y):
        cols, rows, cw, ch, content = self._cols_rows()
        y += self.scroll
        for i, t in enumerate(self.tiles):
            col = i % cols
            row = i // cols
            tx = self.gap + col * (self.tile_w + self.gap)
            ty = self.gap + row * (self.tile_h + self.gap)
            if tx <= x < tx + self.tile_w and ty <= y < ty + self.tile_h:
                return t
        return None

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_PAINT:
            self._paint(hwnd)
            return 0
        if msg == WM_ERASEBKGND:
            return 1
        if msg == WM_SIZE:
            self._update_scroll()
            return 0
        if msg == WM_VSCROLL:
            self._vscroll(_loword(wparam), _hiword(wparam))
            return 0
        if msg == WM_MOUSEWHEEL:
            delta = _signed_hiword(wparam)
            self._vscroll(SB_LINEUP if delta > 0 else SB_LINEDOWN, 0, steps=3)
            return 0
        if msg == WM_LBUTTONUP or msg == WM_LBUTTONDBLCLK:
            tile = self._tile_at(_loword(lparam), _hiword(lparam))
            if tile and self.on_click:
                self.on_click(tile["id"])
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _vscroll(self, code, track, steps=1):
        cols, rows, cw, ch, content = self._cols_rows()
        line = 24 * steps
        page = max(ch - 40, 40)
        pos = self.scroll
        if code == SB_LINEUP:
            pos -= line
        elif code == SB_LINEDOWN:
            pos += line
        elif code == SB_PAGEUP:
            pos -= page
        elif code == SB_PAGEDOWN:
            pos += page
        elif code in (SB_THUMBTRACK, SB_THUMBPOSITION):
            pos = track
        elif code == SB_TOP:
            pos = 0
        elif code == SB_BOTTOM:
            pos = content
        max_pos = max(0, content - ch)
        pos = max(0, min(pos, max_pos))
        if pos != self.scroll:
            self.scroll = pos
            self._update_scroll()
            user32.InvalidateRect(self.hwnd, None, True)

    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        cw, ch = _client_size(hwnd)
        rect = wintypes.RECT(0, 0, cw, ch)
        user32.FillRect(hdc, byref(rect), self._bg)
        old_font = gdi32.SelectObject(hdc, self.font) if self.font else None
        gdi32.SetBkMode(hdc, TRANSPARENT)
        if not self.tiles:
            msg_rect = wintypes.RECT(20, 40, max(cw - 20, 40), ch)
            gdi32.SetTextColor(hdc, COL_OFFLINE)
            user32.DrawTextW(
                hdc, "开始上课后，已加入的学生机才会传来屏幕缩略图。",
                -1, byref(msg_rect), DT_WORDBREAK,
            )
        else:
            cols, _rows, _cw, _ch, _content = self._cols_rows()
            memdc = gdi32.CreateCompatibleDC(hdc)
            for i, t in enumerate(self.tiles):
                col = i % cols
                row = i // cols
                x = self.gap + col * (self.tile_w + self.gap)
                y = self.gap + row * (self.tile_h + self.gap) - self.scroll
                if y + self.tile_h < 0 or y > ch:
                    continue
                frame = wintypes.RECT(x, y, x + self.tile_w, y + self.tile_h)
                user32.FillRect(hdc, byref(frame), gdi32.GetStockObject(WHITE_BRUSH))
                img_rect = wintypes.RECT(x, y, x + self.tile_w, y + self.img_h)
                if t.get("hbmp"):
                    old = gdi32.SelectObject(memdc, t["hbmp"])
                    gdi32.BitBlt(hdc, x, y, self.tile_w, self.img_h, memdc, 0, 0, SRCCOPY)
                    gdi32.SelectObject(memdc, old)
                else:
                    user32.FillRect(hdc, byref(img_rect), gdi32.GetStockObject(WHITE_BRUSH))
                    gdi32.SetTextColor(hdc, COL_OFFLINE)
                    user32.DrawTextW(hdc, "暂无画面", -1, byref(img_rect), DT_CENTER | DT_VCENTER | DT_SINGLELINE)
                cap = wintypes.RECT(x + 4, y + self.img_h, x + self.tile_w - 4, y + self.tile_h)
                cap_text = t["name"] + (" · 已锁屏" if t.get("locked") else "")
                gdi32.SetTextColor(hdc, COL_TILE_CAP)
                user32.DrawTextW(
                    hdc, cap_text, -1, byref(cap),
                    DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS,
                )
            gdi32.DeleteDC(memdc)
        if old_font:
            gdi32.SelectObject(hdc, old_font)
        user32.EndPaint(hwnd, byref(ps))


class FocusWindow(object):
    CLASS_NAME = "GuoyiTeacherFocus"

    def __init__(self, parent, client, device_id, font, on_lock, on_close):
        self.parent = parent
        self.client = client
        self.device_id = device_id
        self.font = font
        self.on_lock = on_lock
        self.on_close = on_close
        self.hwnd = None
        self.hbmp = None
        self.btn_lock = None
        self._bg = gdi32.CreateSolidBrush(COL_WALL)
        _KEEP.append(self._bg)
        self._proc = WNDPROCTYPE(self._wndproc)
        register_class(self.CLASS_NAME, self._proc, self._bg)
        student = state_view.find_student(client.state, device_id) or {"name": "学生", "locked": False}
        title = "%s - 查看屏幕" % (student.get("name") or "学生")
        rc = wintypes.RECT()
        user32.GetWindowRect(parent, byref(rc))
        self.hwnd = user32.CreateWindowExW(
            0, self.CLASS_NAME, title,
            WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_VISIBLE | WS_MINIMIZEBOX,
            rc.left + 60, rc.top + 40, 820, 620,
            parent, None, kernel32.GetModuleHandleW(None), None,
        )
        self.btn_lock = add_ctl(
            self.hwnd, "BUTTON", "解锁" if student.get("locked") else "锁屏",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            20, 540, 100, 28, ID_FOCUS_LOCK, font=font,
        )
        add_ctl(self.hwnd, "BUTTON", "关闭", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                130, 540, 100, 28, ID_FOCUS_CLOSE, font=font)
        user32.ShowWindow(self.hwnd, SW_SHOWNORMAL)
        self.layout()

    def layout(self):
        if not self.hwnd:
            return
        cw, ch = _client_size(self.hwnd)
        if self.btn_lock:
            user32.MoveWindow(self.btn_lock, 20, ch - 42, 100, 28, True)
            close = user32.GetDlgItem(self.hwnd, ID_FOCUS_CLOSE)
            if close:
                user32.MoveWindow(close, 130, ch - 42, 100, 28, True)
        user32.InvalidateRect(self.hwnd, None, True)

    def refresh_button(self, locked):
        if self.btn_lock:
            set_text(self.btn_lock, "解锁" if locked else "锁屏")

    def set_image(self, image_bytes):
        hbmp = jpeg_to_hbitmap_fit(image_bytes, self.hwnd)
        if self.hbmp:
            delete_bitmap(self.hbmp)
        self.hbmp = hbmp
        if self.hwnd:
            user32.InvalidateRect(self.hwnd, None, True)

    def close(self):
        if self.hwnd and user32.IsWindow(self.hwnd):
            user32.DestroyWindow(self.hwnd)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_PAINT:
            self._paint(hwnd)
            return 0
        if msg == WM_SIZE:
            self.layout()
            return 0
        if msg == WM_COMMAND:
            cid = _loword(wparam)
            if cid == ID_FOCUS_LOCK and self.on_lock:
                self.on_lock(self.device_id)
                return 0
            if cid == ID_FOCUS_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            if self.hbmp:
                delete_bitmap(self.hbmp)
                self.hbmp = None
            self.hwnd = None
            if self.on_close:
                self.on_close(self.device_id)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        cw, ch = _client_size(hwnd)
        rect = wintypes.RECT(0, 0, cw, ch - 50)
        user32.FillRect(hdc, byref(rect), self._bg)
        if self.hbmp:
            bm = BITMAP()
            gdi32.GetObjectW(self.hbmp, sizeof(BITMAP), byref(bm))
            area_w, area_h = cw, ch - 50
            x = max(0, (area_w - bm.bmWidth) // 2)
            y = max(0, (area_h - bm.bmHeight) // 2)
            memdc = gdi32.CreateCompatibleDC(hdc)
            old = gdi32.SelectObject(memdc, self.hbmp)
            gdi32.BitBlt(hdc, x, y, bm.bmWidth, bm.bmHeight, memdc, 0, 0, SRCCOPY)
            gdi32.SelectObject(memdc, old)
            gdi32.DeleteDC(memdc)
        else:
            gdi32.SetBkMode(hdc, TRANSPARENT)
            gdi32.SetTextColor(hdc, COL_OFFLINE)
            if self.font:
                gdi32.SelectObject(hdc, self.font)
            user32.DrawTextW(hdc, "正在获取屏幕…", -1, byref(rect), DT_CENTER | DT_VCENTER | DT_SINGLELINE)
        user32.EndPaint(hwnd, byref(ps))

class TeacherMainWindow(object):
    CLASS_NAME = "GuoyiTeacherMain"

    def __init__(self, client, open_browser_fn=None, lan_ips=None, port=8765):
        self.client = client
        self.open_browser_fn = open_browser_fn
        self.lan_ips = lan_ips or []
        self.port = port
        self.hwnd = None
        self.font = default_font()
        self.font_title = title_font()
        self.ctrls = {}
        self.list_ids = []
        self.selected_id = ""
        self.wall = None
        self.focus = None
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._busy = False
        self._header_brush = gdi32.CreateSolidBrush(COL_HEADER)
        self._tool_brush = gdi32.CreateSolidBrush(COL_TOOL)
        self._footer_brush = gdi32.CreateSolidBrush(COL_FOOTER)
        self._bg_brush = gdi32.CreateSolidBrush(COL_WALL)
        for b in (self._header_brush, self._tool_brush, self._footer_brush, self._bg_brush):
            _KEEP.append(b)
        self._thumb_at = {}
        self._proc = WNDPROCTYPE(self._wndproc)
        self._poller = None

    def run(self):
        inst = register_class(self.CLASS_NAME, self._proc, self._bg_brush)
        width, height = 1180, 760
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        x = max(20, (sw - width) // 2)
        y = max(20, (sh - height) // 2)
        self.hwnd = user32.CreateWindowExW(
            WS_EX_CONTROLPARENT, self.CLASS_NAME, TEACHER_WINDOW_TITLE,
            WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN | WS_VISIBLE,
            x, y, width, height, None, None, inst, None,
        )
        if not self.hwnd:
            raise RuntimeError("无法创建教师主窗口")
        self._create_children()
        self._apply_state(self.client.state or {})
        self.wall = ScreenWall(self.hwnd, self.font, self._on_tile_click)
        self._layout()
        user32.ShowWindow(self.hwnd, SW_SHOWNORMAL)
        user32.UpdateWindow(self.hwnd)
        self._start_poller()
        msg = wintypes.MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            if not user32.IsDialogMessageW(self.hwnd, byref(msg)):
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
        self._stop.set()
        if self._poller:
            self._poller.join(timeout=1.5)
        if self.wall:
            self.wall.destroy()

    def post(self, kind, payload=None):
        self._queue.put((kind, payload))
        if self.hwnd and user32.IsWindow(self.hwnd):
            user32.PostMessageW(self.hwnd, WM_APP_UI, 0, 0)

    def _start_poller(self):
        def loop():
            while not self._stop.wait(1.0):
                if not self.client.token:
                    continue
                try:
                    state = self.client.get_state()
                    self.post("state", state)
                    self._fetch_thumbs(state)
                    if self.focus and self.focus.hwnd:
                        try:
                            body, status, _ctype = self.client.focus_frame(self.focus.device_id)
                            if status == 200 and body:
                                self.post("focus_image", body)
                        except AuthExpired as exc:
                            self.post("auth", str(exc))
                            return
                        except Exception:
                            pass
                except AuthExpired as exc:
                    self.post("auth", str(exc))
                    return
                except Exception as exc:
                    self.post("status_error", str(exc))

        self._poller = threading.Thread(target=loop, name="teacher-poll", daemon=True)
        self._poller.start()

    def _fetch_thumbs(self, state):
        for s in state_view.wall_students(state):
            sid = s.get("device_id")
            at = s.get("thumb_at")
            if not sid:
                continue
            if self._thumb_at.get(sid) == at:
                continue
            try:
                body, status, _ctype = self.client.thumb(sid, at)
            except Exception:
                continue
            if status == 200 and body:
                self._thumb_at[sid] = at
                self.post("thumb", {"id": sid, "at": at, "bytes": body})

    def call_api(self, fn, done_msg=None):
        if self._busy:
            return

        def work():
            try:
                result = fn()
                self.post("api_ok", (done_msg, result))
            except AuthExpired as exc:
                self.post("auth", str(exc))
            except TeacherApiError as exc:
                self.post("error", str(exc))
            except Exception as exc:
                self.post("error", str(exc))
            finally:
                self.post("busy", False)

        self._busy = True
        threading.Thread(target=work, daemon=True).start()

    def _create_children(self):
        hwnd = self.hwnd
        font = self.font

        def btn(cid, text):
            return add_ctl(hwnd, "BUTTON", text, WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                           0, 0, 80, 26, cid, font=font)

        self.ctrls["brand"] = add_ctl(
            hwnd, "STATIC", "乐昌国艺书院  机房课堂管理",
            WS_CHILD | WS_VISIBLE, 0, 0, 200, 24, ID_HEADER_BRAND, font=self.font_title,
        )
        self.ctrls["status"] = add_ctl(
            hwnd, "STATIC", "未上课", WS_CHILD | WS_VISIBLE, 0, 0, 160, 22, ID_HEADER_STATUS, font=font,
        )
        self.ctrls["code"] = add_ctl(
            hwnd, "STATIC", "加入码 ------", WS_CHILD | WS_VISIBLE, 0, 0, 180, 22, ID_HEADER_CODE, font=font,
        )
        self.ctrls["ip"] = add_ctl(
            hwnd, "STATIC", state_view.format_lan_banner(self.lan_ips, self.port),
            WS_CHILD | WS_VISIBLE, 0, 0, 500, 22, ID_HEADER_IP, font=font,
        )
        self.ctrls["password"] = btn(ID_PASSWORD, "改密码")
        self.ctrls["browser"] = btn(ID_OPEN_BROWSER, "在浏览器打开（手机用）")
        self.ctrls["class"] = btn(ID_CLASS, "开始上课")
        self.ctrls["refresh_code"] = btn(ID_REFRESH_CODE, "换码")
        self.ctrls["lock_all"] = btn(ID_LOCK_ALL, "锁屏全部")
        self.ctrls["unlock_all"] = btn(ID_UNLOCK_ALL, "解锁全部")
        self.ctrls["announce"] = btn(ID_ANNOUNCE, "发公告")
        self.ctrls["question"] = btn(ID_QUESTION, "发题目")
        self.ctrls["file"] = btn(ID_FILE, "发文件")
        self.ctrls["restrict"] = btn(ID_RESTRICT, "限制网页游戏和下载")
        self.ctrls["restrict_lists"] = btn(ID_RESTRICT_LISTS, "编辑限制名单")
        self.ctrls["broadcast"] = btn(ID_BROADCAST, "广播教师屏幕")
        self.ctrls["shrink"] = add_ctl(
            hwnd, "BUTTON", "缩小屏幕",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX | BS_LEFT,
            0, 0, 90, 24, ID_SHRINK, font=font,
        )
        self.ctrls["broadcast_image"] = btn(ID_BROADCAST_IMAGE, "广播图片")
        self.ctrls["desktop"] = btn(ID_DESKTOP, "设置默认桌面")
        self.ctrls["desktop_unlock"] = btn(ID_DESKTOP_UNLOCK, "解除桌面锁定")
        self.ctrls["summary"] = add_ctl(
            hwnd, "STATIC", "在线 0 · 共 0", WS_CHILD | WS_VISIBLE, 0, 0, 260, 20, ID_SUMMARY, font=font,
        )
        self.ctrls["list"] = add_ctl(
            hwnd, "LISTBOX", "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | WS_VSCROLL
            | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT | LBS_HASSTRINGS,
            0, 0, 260, 200, ID_STUDENT_LIST, WS_EX_CLIENTEDGE, font,
        )
        self.ctrls["approve"] = btn(ID_APPROVE, "允许加入")
        self.ctrls["deny"] = btn(ID_DENY, "拒绝")
        self.ctrls["view"] = btn(ID_VIEW, "查看屏幕")
        self.ctrls["lock_one"] = btn(ID_LOCK_ONE, "锁屏")
        self.ctrls["unlock_one"] = btn(ID_UNLOCK_ONE, "解锁")
        self.ctrls["revoke"] = btn(ID_REVOKE, "移出学生")
        self.ctrls["footer"] = add_ctl(
            hwnd, "STATIC", "版权所有 © 乐昌国艺书院    开发者：陈老师    关闭本窗口即退出教师端",
            WS_CHILD | WS_VISIBLE, 0, 0, 800, 22, ID_FOOTER, font=font,
        )

    def _layout(self):
        if not self.hwnd:
            return
        cw, ch = _client_size(self.hwnd)
        header_h = 58
        toolbar_h = 70
        footer_h = 28
        list_w = 280
        pad = 8
        move = user32.MoveWindow
        move(self.ctrls["brand"], 12, 8, 320, 24, True)
        move(self.ctrls["status"], 340, 10, 200, 22, True)
        move(self.ctrls["code"], 550, 10, 200, 22, True)
        move(self.ctrls["password"], cw - 320, 8, 80, 26, True)
        move(self.ctrls["browser"], cw - 230, 8, 210, 26, True)
        move(self.ctrls["ip"], 12, 34, cw - 24, 20, True)
        row1 = [
            "class", "refresh_code", "lock_all", "unlock_all", "announce",
            "question", "file", "restrict", "restrict_lists",
        ]
        row2 = ["broadcast", "shrink", "broadcast_image", "desktop", "desktop_unlock"]
        widths = {
            "class": 90, "refresh_code": 64, "lock_all": 90, "unlock_all": 90,
            "announce": 80, "question": 80, "file": 80, "restrict": 170,
            "restrict_lists": 120, "broadcast": 120, "shrink": 90,
            "broadcast_image": 90, "desktop": 170, "desktop_unlock": 120,
        }

        def place(names, y):
            x = pad
            for name in names:
                w = widths.get(name, 90)
                if x + w > cw - pad:
                    break
                move(self.ctrls[name], x, y, w, 26, True)
                x += w + 6

        place(row1, header_h + 6)
        place(row2, header_h + 36)
        body_y = header_h + toolbar_h
        body_h = max(80, ch - body_y - footer_h)
        move(self.ctrls["summary"], pad, body_y + 4, list_w - 16, 20, True)
        action_h = 150
        list_h = max(60, body_h - 36 - action_h)
        move(self.ctrls["list"], pad, body_y + 26, list_w - 16, list_h, True)
        ay = body_y + 26 + list_h + 6
        aw = (list_w - 22) // 2
        move(self.ctrls["approve"], pad, ay, aw, 26, True)
        move(self.ctrls["deny"], pad + aw + 6, ay, aw, 26, True)
        move(self.ctrls["view"], pad, ay + 30, aw, 26, True)
        move(self.ctrls["lock_one"], pad + aw + 6, ay + 30, aw, 26, True)
        move(self.ctrls["unlock_one"], pad, ay + 60, aw, 26, True)
        move(self.ctrls["revoke"], pad + aw + 6, ay + 60, aw, 26, True)
        if self.wall:
            self.wall.layout(list_w, body_y, max(80, cw - list_w - pad), body_h)
        move(self.ctrls["footer"], pad, ch - footer_h + 4, cw - 16, 20, True)

    def _apply_state(self, state):
        state = state or {}
        self.client.state = state
        set_text(self.ctrls.get("status"), state_view.class_pill_text(state))
        set_text(self.ctrls.get("code"), "加入码  %s" % (state.get("class_code") or "------"))
        set_text(self.ctrls.get("summary"), state_view.student_summary(state))
        caps = state_view.toolbar_captions(state)
        set_text(self.ctrls.get("class"), caps["class"])
        set_text(self.ctrls.get("broadcast"), caps["broadcast"])
        set_text(self.ctrls.get("restrict"), caps["restrict"])
        set_text(self.ctrls.get("desktop"), caps["desktop"])
        if self.ctrls.get("shrink"):
            user32.SendMessageW(
                self.ctrls["shrink"], BM_SETCHECK,
                BST_CHECKED if caps["shrink"] else BST_UNCHECKED, 0,
            )
        if self.ctrls.get("desktop_unlock"):
            user32.EnableWindow(self.ctrls["desktop_unlock"], 1 if caps["desktop_unlock_enabled"] else 0)
        self._reload_list(state)
        self._refresh_actions()
        if self.wall:
            entries = []
            for s in state_view.wall_students(state):
                entries.append({
                    "id": s.get("device_id"),
                    "name": s.get("name") or "学生",
                    "locked": s.get("locked"),
                    "at": s.get("thumb_at"),
                })
            self.wall.set_tiles(entries)
        if self.focus and self.focus.hwnd:
            stu = state_view.find_student(state, self.focus.device_id)
            if stu:
                self.focus.refresh_button(stu.get("locked"))
                set_text(self.focus.hwnd, "%s - 查看屏幕" % (stu.get("name") or "学生"))

    def _reload_list(self, state):
        lb = self.ctrls.get("list")
        if not lb:
            return
        prev = self.selected_id
        user32.SendMessageW(lb, LB_RESETCONTENT, 0, 0)
        self.list_ids = []
        sel = -1
        for s in state.get("students") or []:
            sid = s.get("device_id")
            self.list_ids.append(sid)
            send_list_string(lb, state_view.student_line(s))
            if sid == prev:
                sel = len(self.list_ids) - 1
        if sel >= 0:
            user32.SendMessageW(lb, LB_SETCURSEL, sel, 0)
            self.selected_id = prev
        else:
            self.selected_id = ""

    def _current_student(self):
        return state_view.find_student(self.client.state, self.selected_id)

    def _refresh_actions(self):
        s = self._current_student()

        def en(name, yes):
            hwnd = self.ctrls.get(name)
            if hwnd:
                user32.EnableWindow(hwnd, 1 if yes else 0)

        if not s:
            for name in ("approve", "deny", "view", "lock_one", "unlock_one", "revoke"):
                en(name, False)
            return
        pending = (not s.get("approved")) and s.get("online")
        approved = bool(s.get("approved"))
        online = bool(s.get("online"))
        locked = bool(s.get("locked"))
        en("approve", not s.get("approved"))
        en("deny", pending)
        en("view", approved)
        en("lock_one", approved and online and not locked)
        en("unlock_one", approved and online and locked)
        en("revoke", approved or pending)

    def _selected_from_list(self):
        lb = self.ctrls.get("list")
        idx = int(user32.SendMessageW(lb, LB_GETCURSEL, 0, 0))
        if 0 <= idx < len(self.list_ids):
            self.selected_id = self.list_ids[idx]
        else:
            self.selected_id = ""
        self._refresh_actions()

    def _on_tile_click(self, device_id):
        self.selected_id = device_id
        if device_id in self.list_ids:
            user32.SendMessageW(self.ctrls["list"], LB_SETCURSEL, self.list_ids.index(device_id), 0)
        self._refresh_actions()
        self._open_focus(device_id)

    def _open_focus(self, device_id):
        if not device_id:
            return
        if self.focus and self.focus.hwnd:
            if self.focus.device_id == device_id:
                user32.SetForegroundWindow(self.focus.hwnd)
                return
            self.focus.close()
        self.call_api(lambda: self.client.set_focus(device_id))

        def on_lock(sid):
            stu = state_view.find_student(self.client.state, sid)
            if stu and stu.get("locked"):
                self.call_api(lambda: self.client.unlock([sid]))
            else:
                self.call_api(lambda: self.client.lock([sid]))

        def on_close(_sid):
            self.focus = None
            self.call_api(lambda: self.client.set_focus(None))

        self.focus = FocusWindow(self.hwnd, self.client, device_id, self.font, on_lock, on_close)

    def _handle_command(self, cid):
        if cid == ID_STUDENT_LIST:
            return
        if cid == ID_OPEN_BROWSER:
            url = "http://127.0.0.1:%s" % self.port
            url_hint = "http://%s:%s" % (self.lan_ips[0], self.port) if self.lan_ips else url
            if self.open_browser_fn:
                try:
                    self.open_browser_fn(url)
                except Exception:
                    pass
            message_box(
                "手机网页控制台",
                "已尝试打开本机网页控制台（备用）。\n\n"
                "手机请在同一机房 WiFi 打开：\n%s\n\n"
                "上课请继续使用本窗口，不必依赖浏览器。" % url_hint,
                MB_OK | MB_ICONINFORMATION,
                self.hwnd,
            )
            return
        if cid == ID_PASSWORD:
            pair = ask_password(self.hwnd)
            if not pair:
                return
            old, new = pair
            self.call_api(lambda: self.client.change_password(old, new), "密码已更新")
            return
        if cid == ID_CLASS:
            if (self.client.state or {}).get("class_active"):
                self.call_api(self.client.class_end)
            else:
                self.call_api(self.client.class_start)
            return
        if cid == ID_REFRESH_CODE:
            if not confirm(self.hwnd, "换码", "更换加入码后，旧码将失效。确定吗？"):
                return
            self.call_api(self.client.refresh_code)
            return
        if cid == ID_LOCK_ALL:
            self.call_api(lambda: self.client.lock())
            return
        if cid == ID_UNLOCK_ALL:
            self.call_api(lambda: self.client.unlock())
            return
        if cid == ID_ANNOUNCE:
            text = ask_text(self.hwnd, "发公告", "公告内容")
            if text:
                self.call_api(lambda t=text: self.client.announce(t, "announce"), "已发送公告")
            return
        if cid == ID_QUESTION:
            text = ask_text(self.hwnd, "发题目", "题目内容")
            if text:
                self.call_api(lambda t=text: self.client.announce(t, "question"), "已发送题目")
            return
        if cid == ID_FILE:
            path = open_file_dialog(self.hwnd, "选择要发送的文件", FILE_FILTER)
            if path:
                self.call_api(
                    lambda p=path: self.client.upload_file(p),
                    "已发送：%s" % os.path.basename(path),
                )
            return
        if cid == ID_RESTRICT:
            st = self.client.state or {}
            if not st.get("class_active"):
                message_box(
                    "限制网页游戏和下载",
                    "请先开始上课。开始上课后默认会开启「限制网页游戏和下载」，也可在下课前临时关闭。",
                    MB_OK | MB_ICONINFORMATION,
                    self.hwnd,
                )
                return
            wr = st.get("web_restrict") or {}
            enabled = not wr.get("enabled")
            self.call_api(lambda e=enabled: self.client.restrict_web(e))
            return
        if cid == ID_RESTRICT_LISTS:
            result = ask_restrict_lists(self.hwnd, (self.client.state or {}).get("web_restrict"))
            if not result:
                return
            if result.get("reset_defaults"):
                self.call_api(lambda: self.client.restrict_lists(reset_defaults=True), "已恢复默认名单")
            else:
                self.call_api(lambda r=result: self.client.restrict_lists(
                    game_domains=r.get("game_domains"),
                    download_domains=r.get("download_domains"),
                    whitelist_domains=r.get("whitelist_domains"),
                    extensions=r.get("extensions"),
                ), "限制名单已保存")
            return
        if cid == ID_SHRINK:
            checked = user32.SendMessageW(self.ctrls["shrink"], BM_GETCHECK, 0, 0) == BST_CHECKED
            st = self.client.state or {}
            if st.get("broadcast_active"):
                self.call_api(lambda c=checked: self.client.broadcast_settings(c))
            else:
                st["broadcast_shrink"] = bool(checked)
            return
        if cid == ID_BROADCAST:
            st = self.client.state or {}
            if st.get("broadcast_active"):
                self.call_api(self.client.broadcast_end)
            else:
                shrink = user32.SendMessageW(self.ctrls["shrink"], BM_GETCHECK, 0, 0) == BST_CHECKED
                self.call_api(lambda s=shrink: self.client.broadcast_start(s))
            return
        if cid == ID_BROADCAST_IMAGE:
            path = open_file_dialog(self.hwnd, "选择要广播的图片", IMAGE_FILTER, "jpg")
            if not path:
                return

            def work():
                st = self.client.state or {}
                if not st.get("broadcast_active"):
                    shrink = user32.SendMessageW(self.ctrls["shrink"], BM_GETCHECK, 0, 0) == BST_CHECKED
                    self.client.broadcast_start(shrink)
                return self.client.broadcast_frame(path)

            self.call_api(work, "已广播图片：%s" % os.path.basename(path))
            return
        if cid == ID_DESKTOP:
            result = ask_desktop(self.hwnd, (self.client.state or {}).get("desktop"))
            if not result:
                return
            if result.get("unlock"):
                if confirm(self.hwnd, "解除桌面锁定", "解除后将恢复学生机锁定前保存的壁纸。确定解除？"):
                    self.call_api(self.client.desktop_unlock, "已解除桌面锁定")
                return
            path = result.get("path")
            lock = result.get("lock", True)
            self.call_api(
                lambda p=path, l=lock: self.client.set_desktop_wallpaper(p, lock=l),
                "已下发默认桌面",
            )
            return
        if cid == ID_DESKTOP_UNLOCK:
            if confirm(self.hwnd, "解除桌面锁定", "解除后将恢复学生机锁定前保存的壁纸。确定解除？"):
                self.call_api(self.client.desktop_unlock, "已解除桌面锁定")
            return
        if cid == ID_APPROVE:
            if self.selected_id:
                sid = self.selected_id
                self.call_api(lambda s=sid: self.client.approve(s))
            return
        if cid == ID_DENY or cid == ID_REVOKE:
            if self.selected_id:
                sid = self.selected_id
                self.call_api(lambda s=sid: self.client.revoke(s))
            return
        if cid == ID_VIEW:
            if self.selected_id:
                self._open_focus(self.selected_id)
            return
        if cid == ID_LOCK_ONE:
            if self.selected_id:
                sid = self.selected_id
                self.call_api(lambda s=sid: self.client.lock([s]))
            return
        if cid == ID_UNLOCK_ONE:
            if self.selected_id:
                sid = self.selected_id
                self.call_api(lambda s=sid: self.client.unlock([s]))
            return

    def _drain_queue(self):
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == "state" and payload is not None:
                self._apply_state(payload)
            elif kind == "thumb" and payload and self.wall:
                self.wall.update_image(payload.get("id"), payload.get("at"), payload.get("bytes"))
            elif kind == "focus_image" and self.focus and self.focus.hwnd:
                self.focus.set_image(payload)
            elif kind == "api_ok":
                msg, result = payload if payload else (None, None)
                if isinstance(result, dict) and (
                    "students" in result or "class_active" in result or "class_code" in result
                ):
                    if "students" in result or "class_active" in result:
                        self._apply_state(result)
                    elif "class_code" in result:
                        st = self.client.state or {}
                        st["class_code"] = result["class_code"]
                        self._apply_state(st)
                if msg:
                    message_box("课堂管理", msg, MB_OK | MB_ICONINFORMATION, self.hwnd)
            elif kind == "error":
                message_box("操作失败", payload or "请求失败", MB_OK | MB_ICONERROR, self.hwnd)
            elif kind == "status_error":
                if self.ctrls.get("footer"):
                    set_text(
                        self.ctrls["footer"],
                        "状态刷新失败：%s    版权所有 © 乐昌国艺书院    开发者：陈老师" % payload,
                    )
            elif kind == "auth":
                message_box("登录已过期", payload or "请重新登录", MB_OK | MB_ICONWARNING, self.hwnd)
                user32.DestroyWindow(self.hwnd)
            elif kind == "busy":
                self._busy = bool(payload)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_APP_UI:
            self._drain_queue()
            return 0
        if msg == WM_COMMAND:
            cid = _loword(wparam)
            notify = _hiword(wparam)
            if cid == ID_STUDENT_LIST:
                if notify in (LBN_SELCHANGE, LBN_DBLCLK):
                    self._selected_from_list()
                    if notify == LBN_DBLCLK:
                        s = self._current_student()
                        if s and s.get("approved"):
                            self._open_focus(self.selected_id)
                        elif s and not s.get("approved"):
                            sid = self.selected_id
                            self.call_api(lambda x=sid: self.client.approve(x))
                return 0
            self._handle_command(cid)
            return 0
        if msg == WM_SIZE:
            self._layout()
            return 0
        if msg == WM_GETMINMAXINFO:
            info = MINMAXINFO.from_address(int(lparam))
            info.ptMinTrackSize.x = 860
            info.ptMinTrackSize.y = 560
            return 0
        if msg == WM_CTLCOLORSTATIC:
            ctl = wintypes.HWND(lparam)
            hdc = wintypes.HDC(wparam)
            cid = user32.GetDlgCtrlID(ctl)
            gdi32.SetBkMode(hdc, TRANSPARENT)
            if cid in (ID_HEADER_BRAND, ID_HEADER_STATUS, ID_HEADER_CODE, ID_HEADER_IP):
                gdi32.SetTextColor(hdc, COL_HEADER_TEXT)
                gdi32.SetBkColor(hdc, COL_HEADER)
                return int(self._header_brush)
            if cid == ID_FOOTER:
                gdi32.SetTextColor(hdc, COL_OFFLINE)
                gdi32.SetBkColor(hdc, COL_FOOTER)
                return int(self._footer_brush)
            gdi32.SetTextColor(hdc, 0x00000000)
            return int(self._bg_brush)
        if msg == WM_ERASEBKGND:
            hdc = wintypes.HDC(wparam)
            cw, ch = _client_size(hwnd)
            r = wintypes.RECT(0, 0, cw, 58)
            user32.FillRect(hdc, byref(r), self._header_brush)
            r = wintypes.RECT(0, 58, cw, 128)
            user32.FillRect(hdc, byref(r), self._tool_brush)
            r = wintypes.RECT(0, 128, cw, ch - 28)
            user32.FillRect(hdc, byref(r), self._bg_brush)
            r = wintypes.RECT(0, ch - 28, cw, ch)
            user32.FillRect(hdc, byref(r), self._footer_brush)
            return 1
        if msg == WM_CLOSE:
            if confirm(hwnd, "退出教师端", "关闭教师主窗口将退出课堂管理，学生机将无法连接。确定退出吗？"):
                user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            self._stop.set()
            if self.focus and self.focus.hwnd:
                try:
                    user32.DestroyWindow(self.focus.hwnd)
                except Exception:
                    pass
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def run_main_window(base_url, open_browser_fn=None, lan_ips=None, port=8765):
    """登录后打开教师主窗口，关闭窗口后返回。取消登录也返回。"""
    client = TeacherClient(base_url)
    error = ""
    while True:
        creds = ask_login(None, username=client.username or "teacher", error=error)
        if not creds:
            return
        try:
            client.login(creds[0], creds[1])
            break
        except TeacherApiError as exc:
            error = str(exc)
            message_box("登录失败", error, MB_OK | MB_ICONERROR)
            continue
    window = TeacherMainWindow(
        client, open_browser_fn=open_browser_fn, lan_ips=lan_ips, port=port
    )
    window.run()
