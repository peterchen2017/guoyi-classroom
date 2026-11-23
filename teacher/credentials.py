# -*- coding: utf-8 -*-
"""教师机本机记住密码。Windows 用 DPAPI 加密；不要把明文密码写入仓库或日志。

登录成功且勾选「记住密码」后保存账号和密码，下次打开自动填写，仍需点登录。
取消勾选会清除已保存的凭据。登录失败不会写入新密码。
"""
from __future__ import print_function

import json
import os
import sys
from pathlib import Path

MAGIC = b"GYCL1\n"
FILE_NAME = "saved_login.dpapi"


def default_credentials_path():
    raw = os.environ.get("CLASSROOM_CREDENTIALS_PATH")
    if raw:
        return Path(raw)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        folder = Path(base) / "GuoyiClassroom" / "Teacher"
    else:
        base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
        folder = Path(base) / "GuoyiClassroom" / "Teacher"
    return folder / FILE_NAME


def _dpapi_protect(plain):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(plain, len(plain))
    in_blob = DATA_BLOB(len(plain), ctypes.cast(in_buf, ctypes.c_void_p))
    out_blob = DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "GuoyiClassroomTeacherLogin",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptProtectData 失败")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(blob):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(blob, len(blob))
    in_blob = DATA_BLOB(len(blob), ctypes.cast(in_buf, ctypes.c_void_p))
    out_blob = DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptUnprotectData 失败")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)


def _linux_protect(plain):
    """非 Windows 仅供开发/测试：加头部后原样存放，文件权限收紧为 0600。"""
    return b"PLAIN\n" + plain


def _linux_unprotect(blob):
    if blob.startswith(b"PLAIN\n"):
        return blob[len(b"PLAIN\n"):]
    raise ValueError("无法解密凭据")


def _platform_protect(plain):
    if sys.platform == "win32":
        return _dpapi_protect(plain)
    return _linux_protect(plain)


def _platform_unprotect(blob):
    if sys.platform == "win32":
        return _dpapi_unprotect(blob)
    return _linux_unprotect(blob)


class CredentialStore(object):
    def __init__(self, path=None, protector=None, unprotector=None):
        self.path = Path(path) if path else default_credentials_path()
        self._protect = protector or _platform_protect
        self._unprotect = unprotector or _platform_unprotect

    def __repr__(self):
        return "CredentialStore(path=%r)" % str(self.path)

    def load(self):
        """返回 {'remember': bool, 'username': str, 'password': str}。失败则视为未保存。"""
        path = self.path
        if not path.is_file():
            return {"remember": False, "username": "", "password": ""}
        try:
            raw = path.read_bytes()
            if raw.startswith(MAGIC):
                raw = raw[len(MAGIC):]
            plain = self._unprotect(raw)
            data = json.loads(plain.decode("utf-8"))
            if not isinstance(data, dict):
                return {"remember": False, "username": "", "password": ""}
            username = data.get("username") or ""
            password = data.get("password") or ""
            if not username and not password:
                return {"remember": False, "username": "", "password": ""}
            return {
                "remember": True,
                "username": str(username),
                "password": str(password),
            }
        except Exception:
            return {"remember": False, "username": "", "password": ""}

    def save(self, username, password):
        payload = json.dumps(
            {"version": 1, "username": username or "", "password": password or ""},
            ensure_ascii=False,
        ).encode("utf-8")
        blob = MAGIC + self._protect(payload)
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(blob)
        if os.name != "nt":
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
        tmp.replace(path)
        if os.name != "nt":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def clear(self):
        path = self.path
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
        tmp = path.with_name(path.name + ".tmp")
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass

    def update_saved_password(self, new_password):
        """仅在当前已保存凭据时更新密码。"""
        saved = self.load()
        if not saved.get("remember"):
            return False
        self.save(saved.get("username") or "", new_password)
        return True


def apply_remember_choice(store, remember, username, password, success):
    """根据勾选和登录结果更新本地凭据。失败且仍勾选时不改动已保存内容。"""
    if not remember:
        store.clear()
        return "cleared"
    if success:
        store.save(username, password)
        return "saved"
    return "unchanged"


def reset_teacher_password_to_default():
    """把本机课堂服务中的教师密码重置为默认，并作废已有教师会话。

    必须使用已启动服务里的同一个 Store；只改 data 文件不会让正在运行的服务立刻生效。
    """
    from server.app import store
    store.reset_password_to_default()
