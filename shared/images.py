# -*- coding: utf-8 -*-
"""JPEG 编码与中文字体（模拟画面、占位图共用）。"""

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font_candidates():
    return [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyh.ttf"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/simsun.ttf"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
    ]


@lru_cache(maxsize=8)
def load_font(size):
    for path in font_candidates():
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size, index=0)
            except OSError:
                continue
    return ImageFont.load_default()


def to_jpeg(image, quality=70):
    if image.mode != "RGB":
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def text_image(lines, width, height, bg, quality=70):
    """画一张带中文说明的素色图，用于模拟屏或占位。"""
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    fonts = [load_font(42), load_font(28), load_font(22)]
    y = height // 2 - 80
    for i, line in enumerate(lines):
        font = fonts[min(i, len(fonts) - 1)]
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = (len(line) * 8, 14)
        draw.text(((width - tw) / 2.0, y), line, fill=(255, 255, 255), font=font)
        y += th + 16
    return to_jpeg(image, quality=quality)


def resize_bilinear(image, size):
    resample = Image.BILINEAR
    if hasattr(Image, "Resampling"):
        resample = Image.Resampling.BILINEAR
    return image.resize(size, resample)
