# -*- coding: utf-8 -*-
"""Windows 7+ 屏幕采集：只用 GDI BitBlt / GetDIBits，不用 Win10 Graphics.Capture。"""

import ctypes
import sys
from ctypes import POINTER, Structure, byref, sizeof

if sys.platform != "win32":
    raise ImportError("win_gdi 仅在 Windows 上使用")

from shared.win_types import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_CXSCREEN = 0
SM_CYSCREEN = 1
SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0
HORZRES = 8
VERTRES = 10

try:
    user32.SetProcessDPIAware()
except Exception:
    pass


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


# 避免 32 位下句柄被截断。
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, POINTER(BITMAPINFO), wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.GetDeviceCaps.restype = ctypes.c_int


def _screen_rect():
    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if width <= 0 or height <= 0:
        width = user32.GetSystemMetrics(SM_CXSCREEN)
        height = user32.GetSystemMetrics(SM_CYSCREEN)
        left = 0
        top = 0
    return left, top, width, height


def grab_rgb():
    """用 BitBlt 采集虚拟桌面，返回 (width, height, rgb_bytes)。失败返回 None。"""
    left, top, width, height = _screen_rect()
    if width <= 0 or height <= 0:
        return None
    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        return None
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    if not hdc_mem or not hbmp:
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)
        return None
    old = gdi32.SelectObject(hdc_mem, hbmp)
    ok = gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, left, top, SRCCOPY)
    if not ok:
        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)
        return None

    bmi = BITMAPINFO()
    ctypes.memset(byref(bmi), 0, sizeof(bmi))
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    buf_len = width * height * 4
    buf = (ctypes.c_ubyte * buf_len)()
    got = gdi32.GetDIBits(
        hdc_mem, hbmp, 0, height, ctypes.byref(buf), byref(bmi), DIB_RGB_COLORS
    )

    gdi32.SelectObject(hdc_mem, old)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc_screen)

    if got == 0:
        return None

    # BGRA -> RGB
    raw = memoryview(buf)
    rgb = bytearray(width * height * 3)
    src = 0
    dst = 0
    total = width * height
    for _ in range(total):
        rgb[dst] = raw[src + 2]
        rgb[dst + 1] = raw[src + 1]
        rgb[dst + 2] = raw[src]
        src += 4
        dst += 3
    return width, height, bytes(rgb)


def grab_jpeg(max_width=1280, quality=65):
    from PIL import Image
    from shared.images import to_jpeg

    grabbed = grab_rgb()
    if not grabbed:
        return None
    width, height, rgb = grabbed
    image = Image.frombytes("RGB", (width, height), rgb)
    if image.width > max_width:
        ratio = max_width / float(image.width)
        new_h = max(1, int(image.height * ratio))
        image = image.resize((max_width, new_h), Image.BILINEAR)
    return to_jpeg(image, quality=quality)
