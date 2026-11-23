# -*- coding: utf-8 -*-
"""Windows 7+ 壁纸设置与锁定：SystemParametersInfo + HKCU 策略，不用 Win10 专有 API。"""

import ctypes
import shutil
import sys
from pathlib import Path

if sys.platform != "win32":
    raise ImportError("win_wallpaper 仅在 Windows 上使用")

import winreg
from ctypes import wintypes

user32 = ctypes.windll.user32

SPI_SETDESKWALLPAPER = 0x0014
SPI_GETDESKWALLPAPER = 0x0073
SPIF_UPDATEINIFILE = 0x0001
SPIF_SENDWININICHANGE = 0x0002

user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT
]
user32.SystemParametersInfoW.restype = wintypes.BOOL

# HKCU 策略（Win7 即有效）
REG_ACTIVE_DESKTOP = r"Software\Microsoft\Windows\CurrentVersion\Policies\ActiveDesktop"
REG_POLICIES_SYSTEM = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
REG_DESKTOP = r"Control Panel\Desktop"
# NoChangingWallpaper：禁止更改壁纸
# NoDispBackgroundPage：Win7 显示属性中隐藏「背景」页
LOCK_VALUES = (
    (REG_ACTIVE_DESKTOP, "NoChangingWallpaper", 1),
    (REG_POLICIES_SYSTEM, "NoDispBackgroundPage", 1),
)


def _read_sz(key, name, default=""):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ) as k:
            val, typ = winreg.QueryValueEx(k, name)
            return str(val)
    except OSError:
        return default


def _write_sz(key, name, value):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _read_dword_maybe(key, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ) as k:
            val, typ = winreg.QueryValueEx(k, name)
            return True, int(val)
    except OSError:
        return False, None


def _write_dword(key, name, value):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))


def _delete_value(key, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def get_wallpaper_path():
    buf = ctypes.create_unicode_buffer(520)
    ok = user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 520, buf, 0)
    if ok and buf.value:
        return buf.value
    return _read_sz(REG_DESKTOP, "Wallpaper", "")


def snapshot():
    """保存锁定前的壁纸路径、样式和策略值。"""
    policies = []
    for key, name, _default in LOCK_VALUES:
        exists, val = _read_dword_maybe(key, name)
        policies.append({"key": key, "name": name, "exists": exists, "value": val})
    return {
        "wallpaper_path": get_wallpaper_path(),
        "wallpaper_style": _read_sz(REG_DESKTOP, "WallpaperStyle", "2"),
        "tile_wallpaper": _read_sz(REG_DESKTOP, "TileWallpaper", "0"),
        "policies": policies,
    }


def copy_wallpaper_file(src_path, dest):
    src = Path(src_path) if src_path else None
    if src is None or not src.is_file():
        return ""
    try:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        return str(dest)
    except OSError:
        return ""


def set_wallpaper(path, style="10"):
    """把 path 设为桌面背景。style: 10=填充(Win7+), 2=拉伸。"""
    path = str(Path(path).resolve())
    _write_sz(REG_DESKTOP, "Wallpaper", path)
    _write_sz(REG_DESKTOP, "WallpaperStyle", style or "10")
    _write_sz(REG_DESKTOP, "TileWallpaper", "0")
    ok = user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE
    )
    if not ok:
        # 再试一次，部分机子需要先 UpdateINIFILE 再发广播
        ok = user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE)
        user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, path, SPIF_SENDWININICHANGE)
    return bool(ok)


def apply_lock_policies():
    for key, name, value in LOCK_VALUES:
        _write_dword(key, name, value)


def restore_policies(snapshot_data):
    items = (snapshot_data or {}).get("policies") or []
    if not items:
        # 没有快照则删除我们写入的策略，避免误留限制。
        for key, name, _v in LOCK_VALUES:
            _delete_value(key, name)
        return
    for item in items:
        key = item.get("key")
        name = item.get("name")
        if not key or not name:
            continue
        if item.get("exists"):
            _write_dword(key, name, int(item.get("value") or 0))
        else:
            _delete_value(key, name)


def restore_wallpaper(snapshot_data, backup_file=""):
    path = ""
    if backup_file and Path(backup_file).is_file():
        path = str(Path(backup_file).resolve())
    elif snapshot_data and snapshot_data.get("wallpaper_path"):
        cand = Path(snapshot_data["wallpaper_path"])
        if cand.is_file():
            path = str(cand)
    if path:
        style = (snapshot_data or {}).get("wallpaper_style") or "2"
        return set_wallpaper(path, style=style)
    # 没有可恢复的文件：设为空背景（黑）比卡住课堂壁纸更接近「解除」。
    user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, "", SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE
    )
    return True


def wallpaper_matches(intended_path):
    if not intended_path:
        return False
    current = get_wallpaper_path() or ""
    try:
        return Path(current).resolve() == Path(intended_path).resolve()
    except OSError:
        return current.replace("/", "\\").lower() == str(intended_path).replace("/", "\\").lower()
