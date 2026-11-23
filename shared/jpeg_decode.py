# -*- coding: utf-8 -*-
"""JPEG 解码：先试 Pillow，Windows 上再回退 GDI+。Linux 不会导入 GDI+。"""
from __future__ import print_function

import sys


def decode_jpeg_bgrx(image_bytes):
    """返回 (width, height, bgrx_bytes) 或 None。"""
    if not image_bytes:
        return None
    result = _decode_pillow(image_bytes)
    if result is not None:
        return result
    if sys.platform == "win32":
        return _decode_gdiplus(image_bytes)
    return None


def _decode_pillow(image_bytes):
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = im.size
        if w <= 0 or h <= 0:
            return None
        return w, h, im.tobytes("raw", "BGRX")
    except Exception:
        return None


def _decode_gdiplus(image_bytes):
    """Win7 自带 GDI+。失败返回 None，不抛给调用方。"""
    try:
        import ctypes
        from ctypes import POINTER, Structure, byref, c_void_p, c_uint32, c_int, c_uint
        ole32 = ctypes.windll.ole32
        gdiplus = ctypes.windll.gdiplus
        kernel32 = ctypes.windll.kernel32

        class GdiplusStartupInput(Structure):
            _fields_ = [
                ("GdiplusVersion", c_uint32),
                ("DebugEventCallback", c_void_p),
                ("SuppressBackgroundThread", c_int),
                ("SuppressExternalCodecs", c_int),
            ]

        class BitmapData(Structure):
            _fields_ = [
                ("Width", c_uint),
                ("Height", c_uint),
                ("Stride", c_int),
                ("PixelFormat", c_int),
                ("Scan0", c_void_p),
                ("Reserved", c_void_p),
            ]

        startup = GdiplusStartupInput()
        startup.GdiplusVersion = 1
        token = ctypes.c_ulonglong(0) if ctypes.sizeof(c_void_p) == 8 else ctypes.c_ulong(0)
        if gdiplus.GdiplusStartup(byref(token), byref(startup), None) != 0:
            return None

        hglobal = kernel32.GlobalAlloc(0x0002, len(image_bytes))  # GMEM_MOVEABLE
        if not hglobal:
            gdiplus.GdiplusShutdown(token)
            return None
        ptr = kernel32.GlobalLock(hglobal)
        ctypes.memmove(ptr, image_bytes, len(image_bytes))
        kernel32.GlobalUnlock(hglobal)
        stream = c_void_p()
        # fDeleteOnRelease = True，释放 stream 时会 GlobalFree
        hr = ole32.CreateStreamOnHGlobal(hglobal, True, byref(stream))
        if hr != 0 or not stream:
            kernel32.GlobalFree(hglobal)
            gdiplus.GdiplusShutdown(token)
            return None
        image = c_void_p()
        st = gdiplus.GdipCreateBitmapFromStream(stream, byref(image))
        if st != 0 or not image:
            # IStream Release
            try:
                ctypes.cast(stream, POINTER(c_void_p))  # noqa
                # Use IUnknown Release via Query: call vtbl is messy; let process leak stream only on failure?
                pass
            except Exception:
                pass
            gdiplus.GdiplusShutdown(token)
            return None
        w = c_uint(0)
        h = c_uint(0)
        gdiplus.GdipGetImageWidth(image, byref(w))
        gdiplus.GdipGetImageHeight(image, byref(h))
        width, height = int(w.value), int(h.value)
        if width <= 0 or height <= 0:
            gdiplus.GdipDisposeImage(image)
            gdiplus.GdiplusShutdown(token)
            return None
        # PixelFormat32bppRGB = 0x00022009 ; 32bppARGB = 0x26200A
        fmt = 0x26200A
        rect = (ctypes.c_int * 4)(0, 0, width, height)

        class GpRect(Structure):
            _fields_ = [("X", c_int), ("Y", c_int), ("Width", c_int), ("Height", c_int)]

        rc = GpRect(0, 0, width, height)
        data = BitmapData()
        # ImageLockModeRead = 1
        if gdiplus.GdipBitmapLockBits(image, byref(rc), 1, fmt, byref(data)) != 0:
            gdiplus.GdipDisposeImage(image)
            gdiplus.GdiplusShutdown(token)
            return None
        stride = int(data.Stride)
        buf = (ctypes.c_char * (abs(stride) * height))()
        src = data.Scan0
        for row in range(height):
            ctypes.memmove(
                ctypes.addressof(buf) + row * width * 4,
                src + row * stride,
                width * 4,
            )
        gdiplus.GdipBitmapUnlockBits(image, byref(data))
        gdiplus.GdipDisposeImage(image)
        gdiplus.GdiplusShutdown(token)
        # ARGB/BGRA already 4 bytes; treat as BGRX for SetDIBits
        return width, height, bytes(buf)
    except Exception:
        return None
