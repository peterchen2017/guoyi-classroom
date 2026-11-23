# -*- coding: utf-8 -*-
"""教师机本机采集（广播教师屏幕）。Windows 使用 GDI BitBlt；Linux 采集失败则返回 None。"""

import sys

from shared.images import load_font, resize_bilinear, text_image, to_jpeg
from server import config


def placeholder_jpeg(text="正在等待教师屏幕", width=1280, height=720):
    return text_image(
        [config.SCHOOL_NAME + " · 教师屏幕广播", text],
        width,
        height,
        (26, 54, 93),
        quality=70,
    )


def grab_teacher_screen(max_width=1280, quality=65):
    """尝试采集本机屏幕。Windows 走 GDI BitBlt；失败返回 None。"""
    if sys.platform == "win32":
        try:
            from shared.win_gdi import grab_jpeg
            return grab_jpeg(max_width=max_width, quality=quality)
        except Exception:
            return None
    # Linux / 其它：可选尝试 Pillow ImageGrab（可能没有可用桌面）。
    try:
        from PIL import ImageGrab
        image = ImageGrab.grab()
        if image.width > max_width:
            ratio = max_width / float(image.width)
            image = resize_bilinear(image, (max_width, max(1, int(image.height * ratio))))
        return to_jpeg(image, quality=quality)
    except Exception:
        return None


def can_grab_screen():
    if sys.platform == "win32":
        return True
    import os
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


NORMAL_WIDTH = 1280
SHRINK_WIDTH = 800
NORMAL_QUALITY = 65
SHRINK_QUALITY = 50


def scale_jpeg(data, max_width=SHRINK_WIDTH, quality=SHRINK_QUALITY):
    """把广播画面缩到指定最大宽度。失败则返回原数据。"""
    if not data:
        return data
    try:
        import io
        from PIL import Image
        image = Image.open(io.BytesIO(data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        if image.width > max_width:
            ratio = max_width / float(image.width)
            image = resize_bilinear(image, (max_width, max(1, int(image.height * ratio))))
        return to_jpeg(image, quality=quality)
    except Exception:
        return data
