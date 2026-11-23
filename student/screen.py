# -*- coding: utf-8 -*-
"""屏幕采集：Windows 使用 GDI BitBlt；Linux / --sim 使用带姓名的素色模拟帧。"""

import hashlib
import sys
import time

from shared.images import resize_bilinear, text_image, to_jpeg


def _color_for(name):
    digest = hashlib.md5(name.encode("utf-8")).digest()
    r = 30 + digest[0] % 80
    g = 50 + digest[1] % 90
    b = 80 + digest[2] % 100
    return (r, g, b)


def sim_frame(name, extra_lines=None, width=960, height=540, quality=60):
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "课堂管理运行中",
        name,
        now,
        "模拟画面（非隐蔽采集）",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    return text_image(lines, width, height, _color_for(name), quality=quality)


def capture_jpeg(name, max_width=960, quality=60, sim=False, extra_lines=None):
    if not sim and sys.platform == "win32":
        try:
            from shared.win_gdi import grab_jpeg
            data = grab_jpeg(max_width=max_width, quality=quality)
            if data:
                return data
        except Exception:
            pass
    if not sim and sys.platform != "win32":
        try:
            from PIL import ImageGrab
            from shared.images import resize_bilinear
            image = ImageGrab.grab()
            if image.width > max_width:
                ratio = max_width / float(image.width)
                image = resize_bilinear(image, (max_width, max(1, int(image.height * ratio))))
            return to_jpeg(image, quality=quality)
        except Exception:
            pass
    return sim_frame(name, extra_lines=extra_lines, quality=quality)
