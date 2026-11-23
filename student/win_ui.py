# -*- coding: utf-8 -*-
"""Windows 7+ 可见窗口、锁屏覆盖层、托盘（Shell_NotifyIcon）。不依赖 tkinter / Win10 API。"""

import ctypes
import queue
import sys
import threading
from ctypes import POINTER, Structure, byref, sizeof

from shared.version import STUDENT_WINDOW_TITLE

if sys.platform != "win32":
    raise ImportError("win_ui 仅在 Windows 上使用")

from shared.win_types import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

IS_64 = sizeof(ctypes.c_void_p) == 8

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_TRAY = WM_APP + 20
WM_UI_STATUS = WM_APP + 1
WM_UI_LOCK = WM_APP + 2
WM_UI_UNLOCK = WM_APP + 3
WM_UI_ANNOUNCE = WM_APP + 4
WM_UI_BROADCAST = WM_APP + 5
WM_UI_QUIT = WM_APP + 6

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
CW_USEDEFAULT = 0x80000000
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SW_SHOW = 5
SW_SHOWNORMAL = 1
SW_HIDE = 0
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010
COLOR_WINDOW = 5
DT_CENTER = 0x00000001
DT_VCENTER = 0x00000004
DT_WORDBREAK = 0x00000010
DT_SINGLELINE = 0x00000020
IDI_APPLICATION = 32512
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
MF_STRING = 0x00000000
ID_TRAY_SHOW = 1001
ID_TRAY_EXIT = 1002
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0

WNDPROCTYPE = ctypes.WINFUNCTYPE(
    ctypes.c_longlong if IS_64 else ctypes.c_long,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


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


class NOTIFYICONDATAW(Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_ubyte * 16),
        ("hBalloonIcon", wintypes.HICON),
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


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = wintypes.LPARAM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL


def _virtual_screen():
    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if width <= 0 or height <= 0:
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        left = 0
        top = 0
    return left, top, width, height


class WinUI(object):
    """课堂管理运行中：可见状态窗 + 托盘；锁屏为置顶全屏窗口。"""

    def __init__(self, title=None):
        self.title = title or STUDENT_WINDOW_TITLE
        self._queue = queue.Queue()
        self._thread = None
        self._tid = 0
        self._ready = threading.Event()
        self.status_hwnd = None
        self.lock_hwnd = None
        self._status_text = title + "\n正在连接教师机…"
        self._lock_text = "请看老师"
        self._broadcast_bits = None  # (w, h, bgra)
        self._locked = False
        self._nid = None
        self._wndproc = None
        self._lockproc = None
        self._stopped = False
        self._font = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, name="classroom-win-ui", daemon=True)
        self._thread.start()
        self._ready.wait(5)

    def stop(self):
        self._stopped = True
        if self.status_hwnd:
            user32.PostMessageW(self.status_hwnd, WM_UI_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)

    def _post(self, msg, item=None):
        if item is not None:
            self._queue.put(item)
        if self.status_hwnd:
            user32.PostMessageW(self.status_hwnd, msg, 0, 0)

    def set_status(self, text):
        self._status_text = text
        self._post(WM_UI_STATUS)

    def show_lock(self, message="请看老师"):
        self._lock_text = message or "请看老师"
        self._locked = True
        self._post(WM_UI_LOCK)

    def hide_lock(self):
        self._locked = False
        self._post(WM_UI_UNLOCK)

    def show_announce(self, title, text):
        self._post(WM_UI_ANNOUNCE, (title, text))

    def show_broadcast_frame(self, jpeg_bytes):
        try:
            from PIL import Image
            import io
            image = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
            # 缩放到不超过 1280，再转 BGRA
            if image.width > 1280:
                ratio = 1280 / float(image.width)
                from shared.images import resize_bilinear
                image = resize_bilinear(image, (1280, max(1, int(image.height * ratio))))
            bgra = image.tobytes("raw", "BGRX")
            self._broadcast_bits = (image.width, image.height, bgra)
        except Exception:
            return
        self._post(WM_UI_BROADCAST)

    def clear_broadcast(self):
        self._broadcast_bits = None
        self._post(WM_UI_BROADCAST)

    def _loop(self):
        self._tid = kernel32.GetCurrentThreadId()
        hinst = kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROCTYPE(self._status_proc)
        self._lockproc = WNDPROCTYPE(self._lock_proc)

        cls = WNDCLASSW()
        cls.style = 0
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = hinst
        cls.hIcon = user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))
        cls.hCursor = user32.LoadCursorW(None, wintypes.LPCWSTR(32512))
        cls.hbrBackground = gdi32.CreateSolidBrush(0xF3F4F1)  # BGR
        cls.lpszClassName = "GuoyiClassroomStatus"
        if not user32.RegisterClassW(byref(cls)):
            # 可能重复注册
            pass

        lock_cls = WNDCLASSW()
        lock_cls.lpfnWndProc = self._lockproc
        lock_cls.hInstance = hinst
        lock_cls.hCursor = user32.LoadCursorW(None, wintypes.LPCWSTR(32512))
        lock_cls.hbrBackground = gdi32.CreateSolidBrush(0x1A1A12)
        lock_cls.lpszClassName = "GuoyiClassroomLock"
        user32.RegisterClassW(byref(lock_cls))

        style = WS_OVERLAPPEDWINDOW ^ WS_SYSMENU | WS_CAPTION | WS_MINIMIZEBOX
        # 保留关闭按钮但在 WM_CLOSE 中只最小化，避免学生误以为程序已退出。
        style = WS_CAPTION | WS_MINIMIZEBOX | WS_SYSMENU | 0x00C00000
        self.status_hwnd = user32.CreateWindowExW(
            0,
            "GuoyiClassroomStatus",
            self.title,
            WS_OVERLAPPEDWINDOW,
            80, 80, 480, 260,
            None, None, hinst, None,
        )
        user32.ShowWindow(self.status_hwnd, SW_SHOWNORMAL)
        user32.UpdateWindow(self.status_hwnd)
        self._add_tray()
        self._ready.set()

        msg = wintypes.MSG()
        while not self._stopped and user32.GetMessageW(byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
        self._remove_tray()

    def _add_tray(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.status_hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))
        tip = "课堂管理运行中"
        nid.szTip = tip
        shell32.Shell_NotifyIconW(NIM_ADD, byref(nid))
        self._nid = nid

    def _remove_tray(self):
        if self._nid is not None:
            try:
                shell32.Shell_NotifyIconW(NIM_DELETE, byref(self._nid))
            except Exception:
                pass
            self._nid = None

    def _status_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_UI_STATUS:
            user32.InvalidateRect(hwnd, None, True)
            return 0
        if msg == WM_UI_LOCK:
            self._ensure_lock()
            return 0
        if msg == WM_UI_UNLOCK:
            if self.lock_hwnd:
                user32.ShowWindow(self.lock_hwnd, SW_HIDE)
            user32.InvalidateRect(hwnd, None, True)
            return 0
        if msg == WM_UI_BROADCAST:
            if self.lock_hwnd:
                user32.InvalidateRect(self.lock_hwnd, None, True)
            user32.InvalidateRect(hwnd, None, True)
            return 0
        if msg == WM_UI_ANNOUNCE:
            try:
                title, text = self._queue.get_nowait()
            except queue.Empty:
                title, text = "课堂公告", ""
            user32.MessageBoxW(hwnd, text, title, 0x00000040)
            return 0
        if msg == WM_UI_QUIT:
            user32.DestroyWindow(hwnd)
            if self.lock_hwnd:
                user32.DestroyWindow(self.lock_hwnd)
            user32.PostQuitMessage(0)
            return 0
        if msg == WM_TRAY:
            ev = lparam & 0xFFFF
            if ev == WM_RBUTTONUP or ev == WM_LBUTTONUP:
                if ev == WM_LBUTTONUP:
                    user32.ShowWindow(hwnd, SW_SHOWNORMAL)
                    user32.SetForegroundWindow(hwnd)
                else:
                    self._tray_menu(hwnd)
            return 0
        if msg == WM_CLOSE:
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            return 0
        if msg == WM_PAINT:
            self._paint_status(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _tray_menu(self, hwnd):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, ID_TRAY_SHOW, "显示窗口")
        user32.AppendMenuW(menu, MF_STRING, ID_TRAY_EXIT, "退出客户端")
        pt = wintypes.POINT()
        user32.GetCursorPos(byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, hwnd, None)
        user32.DestroyMenu(menu)
        if cmd == ID_TRAY_SHOW:
            user32.ShowWindow(hwnd, SW_SHOWNORMAL)
        elif cmd == ID_TRAY_EXIT:
            user32.PostMessageW(hwnd, WM_UI_QUIT, 0, 0)

    def _ensure_lock(self):
        if not self.lock_hwnd:
            left, top, width, height = _virtual_screen()
            hinst = kernel32.GetModuleHandleW(None)
            self.lock_hwnd = user32.CreateWindowExW(
                WS_EX_TOPMOST,
                "GuoyiClassroomLock",
                "请看老师",
                WS_POPUP | WS_VISIBLE,
                left, top, width, height,
                None, None, hinst, None,
            )
        left, top, width, height = _virtual_screen()
        user32.SetWindowPos(
            self.lock_hwnd, HWND_TOPMOST, left, top, width, height, SWP_SHOWWINDOW
        )
        user32.ShowWindow(self.lock_hwnd, SW_SHOW)
        user32.InvalidateRect(self.lock_hwnd, None, True)

    def _lock_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_CLOSE:
            return 0  # 只能由教师端解锁关闭
        if msg == WM_PAINT:
            self._paint_lock(hwnd)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _paint_status(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, byref(rect))
        brush = gdi32.CreateSolidBrush(0xF8F4F1)
        user32.FillRect(hdc, byref(rect), brush)
        gdi32.DeleteObject(brush)
        gdi32.SetBkMode(hdc, 1)  # TRANSPARENT
        gdi32.SetTextColor(hdc, 0x3D1A14)
        text = self._status_text or ""
        user32.DrawTextW(hdc, text, -1, byref(rect), DT_WORDBREAK)
        foot = wintypes.RECT()
        foot.left = 8
        foot.top = max(rect.bottom - 36, rect.top)
        foot.right = rect.right - 8
        foot.bottom = rect.bottom - 4
        gdi32.SetTextColor(hdc, 0x555555)
        user32.DrawTextW(hdc, "版权所有 © 乐昌国艺书院    开发者：陈老师", -1, byref(foot), DT_SINGLELINE)
        user32.EndPaint(hwnd, byref(ps))

    def _paint_lock(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, byref(rect))
        brush = gdi32.CreateSolidBrush(0x2B1A12)
        user32.FillRect(hdc, byref(rect), brush)
        gdi32.DeleteObject(brush)
        bits = self._broadcast_bits
        if bits:
            bw, bh, bgra = bits
            self._blit_bgra(hdc, rect, bw, bh, bgra)
        else:
            gdi32.SetBkMode(hdc, 1)
            gdi32.SetTextColor(hdc, 0x00FFFFFF)
            text = "请看老师\r\n\r\n" + (self._lock_text or "")
            user32.DrawTextW(hdc, text, -1, byref(rect), DT_CENTER | DT_VCENTER | DT_WORDBREAK)
        user32.EndPaint(hwnd, byref(ps))

    def _blit_bgra(self, hdc, rect, width, height, bgra):
        bmi = BITMAPINFO()
        ctypes.memset(byref(bmi), 0, sizeof(bmi))
        bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        dest_w = rect.right - rect.left
        dest_h = rect.bottom - rect.top
        buf = (ctypes.c_ubyte * len(bgra)).from_buffer_copy(bgra)
        gdi32.StretchDIBits(
            hdc, 0, 0, dest_w, dest_h, 0, 0, width, height,
            buf, byref(bmi), DIB_RGB_COLORS, SRCCOPY,
        )
