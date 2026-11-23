# -*- coding: utf-8 -*-
"""用 WinINET 读写系统代理（Windows 7+），上课结束必须还原，不安装证书、不做中间人。"""

import ctypes
import json
import sys
from ctypes import POINTER, Structure, Union, byref, sizeof
from pathlib import Path

if sys.platform != "win32":
    raise ImportError("win_proxy 仅在 Windows 上使用")

from shared.win_types import wintypes

IS_64 = sizeof(ctypes.c_void_p) == 8

wininet = ctypes.windll.wininet

INTERNET_OPTION_PER_CONNECTION_OPTION = 75
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37
INTERNET_PER_CONN_FLAGS = 1
INTERNET_PER_CONN_PROXY_SERVER = 2
INTERNET_PER_CONN_PROXY_BYPASS = 3
INTERNET_PER_CONN_AUTOCONFIG_URL = 4

PROXY_TYPE_DIRECT = 0x00000001
PROXY_TYPE_PROXY = 0x00000002
PROXY_TYPE_AUTO_PROXY_URL = 0x00000004
PROXY_TYPE_AUTO_DETECT = 0x00000008


class INTERNET_PER_CONN_OPTION(Structure):
    class Value(Union):
        _fields_ = [
            ("dwValue", wintypes.DWORD),
            ("pszValue", ctypes.c_void_p),
            ("ftValue", wintypes.FILETIME),
        ]

    _fields_ = [
        ("dwOption", wintypes.DWORD),
        ("Value", Value),
    ]


if IS_64:
    # 64 位下 DWORD 后需对齐到 8 字节。
    class INTERNET_PER_CONN_OPTION(Structure):
        class Value(Union):
            _fields_ = [
                ("dwValue", wintypes.DWORD),
                ("pszValue", ctypes.c_void_p),
                ("ftValue", wintypes.FILETIME),
            ]

        _fields_ = [
            ("dwOption", wintypes.DWORD),
            ("pad", wintypes.DWORD),
            ("Value", Value),
        ]


class INTERNET_PER_CONN_OPTION_LIST(Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("pszConnection", wintypes.LPWSTR),
        ("dwOptionCount", wintypes.DWORD),
        ("dwOptionError", wintypes.DWORD),
        ("pOptions", POINTER(INTERNET_PER_CONN_OPTION)),
    ]


InternetQueryOptionW = wininet.InternetQueryOptionW
InternetQueryOptionW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, POINTER(wintypes.DWORD)]
InternetQueryOptionW.restype = wintypes.BOOL
InternetSetOptionW = wininet.InternetSetOptionW
InternetSetOptionW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
InternetSetOptionW.restype = wintypes.BOOL


def _query_list():
    option_count = 4
    options = (INTERNET_PER_CONN_OPTION * option_count)()
    options[0].dwOption = INTERNET_PER_CONN_FLAGS
    options[1].dwOption = INTERNET_PER_CONN_PROXY_SERVER
    options[2].dwOption = INTERNET_PER_CONN_PROXY_BYPASS
    options[3].dwOption = INTERNET_PER_CONN_AUTOCONFIG_URL
    lst = INTERNET_PER_CONN_OPTION_LIST()
    lst.dwSize = sizeof(INTERNET_PER_CONN_OPTION_LIST)
    lst.pszConnection = None
    lst.dwOptionCount = option_count
    lst.dwOptionError = 0
    lst.pOptions = ctypes.cast(options, POINTER(INTERNET_PER_CONN_OPTION))
    size = wintypes.DWORD(sizeof(lst))
    ok = InternetQueryOptionW(None, INTERNET_OPTION_PER_CONNECTION_OPTION, byref(lst), byref(size))
    if not ok:
        raise ctypes.WinError()
    return lst, options


def _psz_to_str(ptr):
    if not ptr:
        return ""
    return ctypes.wstring_at(ptr)


def get_proxy():
    """读取当前默认连接的系统代理设置。"""
    _lst, options = _query_list()
    flags = options[0].Value.dwValue
    return {
        "flags": int(flags),
        "proxy_server": _psz_to_str(options[1].Value.pszValue),
        "proxy_bypass": _psz_to_str(options[2].Value.pszValue),
        "autoconfig_url": _psz_to_str(options[3].Value.pszValue),
    }


def _set_options(flags, proxy_server, proxy_bypass, autoconfig_url):
    option_count = 4
    options = (INTERNET_PER_CONN_OPTION * option_count)()
    options[0].dwOption = INTERNET_PER_CONN_FLAGS
    options[0].Value.dwValue = flags

    bufs = []

    def attach(idx, code, text):
        options[idx].dwOption = code
        if text:
            buf = ctypes.create_unicode_buffer(text)
            bufs.append(buf)
            options[idx].Value.pszValue = ctypes.cast(buf, ctypes.c_void_p)
        else:
            options[idx].Value.pszValue = None

    attach(1, INTERNET_PER_CONN_PROXY_SERVER, proxy_server or "")
    attach(2, INTERNET_PER_CONN_PROXY_BYPASS, proxy_bypass or "")
    attach(3, INTERNET_PER_CONN_AUTOCONFIG_URL, autoconfig_url or "")

    lst = INTERNET_PER_CONN_OPTION_LIST()
    lst.dwSize = sizeof(INTERNET_PER_CONN_OPTION_LIST)
    lst.pszConnection = None
    lst.dwOptionCount = option_count
    lst.dwOptionError = 0
    lst.pOptions = ctypes.cast(options, POINTER(INTERNET_PER_CONN_OPTION))
    ok = InternetSetOptionW(
        None, INTERNET_OPTION_PER_CONNECTION_OPTION, byref(lst), sizeof(lst)
    )
    if not ok:
        raise ctypes.WinError()
    InternetSetOptionW(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
    InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0)
    return bufs  # 保持到调用结束后片刻；设置已复制进系统


def set_classroom_proxy(port, extra_bypass=None):
    """把系统代理指到本机过滤端口。返回设置前的原配置。"""
    original = get_proxy()
    bypass = ["127.0.0.1", "localhost", "<local>", "::1"]
    for item in extra_bypass or []:
        if item and item not in bypass:
            bypass.append(item)
    flags = PROXY_TYPE_DIRECT | PROXY_TYPE_PROXY
    _set_options(
        flags,
        "127.0.0.1:%s" % int(port),
        ";".join(bypass),
        "",
    )
    return original


def apply_saved(settings):
    if not settings:
        # 回退为直接连接
        _set_options(PROXY_TYPE_DIRECT, "", "", "")
        return
    flags = int(settings.get("flags") or PROXY_TYPE_DIRECT)
    _set_options(
        flags,
        settings.get("proxy_server") or "",
        settings.get("proxy_bypass") or "",
        settings.get("autoconfig_url") or "",
    )


def save_file(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_file(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clear_file(path):
    path = Path(path)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
