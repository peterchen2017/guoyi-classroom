# -*- coding: utf-8 -*-
"""运行配置。密码只在首次初始化时写入哈希，明文仅出现在 README。"""

import os
import socket
from pathlib import Path

APP_NAME = "机房课堂管理"
SCHOOL_NAME = "乐昌国艺书院"
DEVELOPER = "陈老师"
VERSION = "1.2.2"
# 安装包、窗口、关于和控制台页脚统一署名。
COPYRIGHT = "版权所有 © 乐昌国艺书院    开发者：陈老师"

# 老师通过课堂软件下发时明确支持的代码/文本类型（不作为拒绝其它类型的名单）。
CLASSROOM_CODE_EXTS = [
    ".cpp", ".h", ".hpp", ".cc", ".cxx", ".c", ".h++", ".hxx", ".hh",
    ".txt", ".in", ".out", ".md",
]

HOST = os.environ.get("CLASSROOM_HOST", "0.0.0.0")
PORT = int(os.environ.get("CLASSROOM_PORT", "8765"))
DISCOVERY_PORT = int(os.environ.get("CLASSROOM_DISCOVERY_PORT", "8766"))

DEFAULT_TEACHER_USER = os.environ.get("CLASSROOM_TEACHER_USER", "teacher")
# 仅用于首次生成 data/state.json；之后以文件中的哈希为准。
DEFAULT_TEACHER_PASSWORD = os.environ.get("CLASSROOM_TEACHER_PASSWORD", "ChangeMe@2026")

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"

DISCOVERY_MAGIC = b"GUOYI_CLASSROOM"
DISCOVERY_PROBE = b"GUOYI_CLASSROOM_PROBE"

HEARTBEAT_INTERVAL = 8
OFFLINE_AFTER = 25
THUMB_INTERVAL = 1.5
FOCUS_INTERVAL = 0.4
BROADCAST_INTERVAL = 0.4

# 兼容目标：Windows 7 / 8.1 / 10 / 11（32/64 位），Python 3.8+。
MIN_PY = (3, 8)


def data_dir():
    raw = os.environ.get("CLASSROOM_DATA_DIR")
    if raw:
        path = Path(raw)
    elif os.name == "nt":
        # 安装在 Program Files 下时不能写安装目录，改存用户目录。
        base = os.environ.get("APPDATA") or str(Path.home())
        path = Path(base) / "GuoyiClassroom" / "teacher"
    else:
        path = ROOT_DIR / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path():
    return data_dir() / "state.json"


def uploads_dir():
    path = data_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def wallpapers_dir():
    path = data_dir() / "wallpapers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def lan_ips():
    """尽量列出教师机在局域网中的 IPv4 地址。"""
    found = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                found.add(ip)
    except OSError:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if not ip.startswith("127."):
            found.add(ip)
    except OSError:
        pass
    return sorted(found)
