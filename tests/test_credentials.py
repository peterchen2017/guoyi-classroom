# -*- coding: utf-8 -*-
"""记住密码存储、登录 401 提示、重置默认密码。Linux 可跑，不打开 Win32 窗口。"""
from __future__ import print_function

import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKDIR = Path(os.environ.get("CLASSROOM_CRED_TEST_DIR", "/tmp/classroom-lab-credentials"))

if WORKDIR.exists():
    import shutil
    shutil.rmtree(WORKDIR)
WORKDIR.mkdir(parents=True)
os.environ["CLASSROOM_DATA_DIR"] = str(WORKDIR / "server-data")
os.environ["CLASSROOM_CREDENTIALS_PATH"] = str(WORKDIR / "creds.dpapi")
os.environ["CLASSROOM_HOST"] = "127.0.0.1"
os.environ["CLASSROOM_PORT"] = os.environ.get("CLASSROOM_CRED_TEST_PORT", "18785")
os.environ["CLASSROOM_DISCOVERY_PORT"] = os.environ.get("CLASSROOM_CRED_TEST_DISCOVERY", "18786")
Path(os.environ["CLASSROOM_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from teacher.api_client import AuthExpired, TeacherApiError, TeacherClient
from teacher.credentials import CredentialStore, apply_remember_choice
from server import auth, config
from server.store import Store


class Checker(object):
    def __init__(self):
        self.ok = 0
        self.fail = 0

    def check(self, name, cond, detail=""):
        if cond:
            self.ok += 1
            status = "通过"
        else:
            self.fail += 1
            status = "失败"
        line = "[%s] %s%s" % (status, name, (" — " + detail) if detail else "")
        print(line, flush=True)
        return cond

    def summary(self):
        print("", flush=True)
        print("合计：通过 %s，失败 %s" % (self.ok, self.fail), flush=True)
        return self.fail == 0


def _xor_protect(plain):
    key = 0x5A
    return bytes((b ^ key) for b in plain)


def _xor_unprotect(blob):
    return _xor_protect(blob)


def _store(name):
    path = WORKDIR / (name + ".bin")
    if path.exists():
        path.unlink()
    return CredentialStore(path=path, protector=_xor_protect, unprotector=_xor_unprotect)


def test_store_save_load_clear(c):
    secret = "unit-test-secret-alpha"
    store = _store("save-load")
    store.save("teacher-a", secret)
    loaded = store.load()
    c.check("保存后 remember 为真", loaded.get("remember") is True)
    c.check("预填账号", loaded.get("username") == "teacher-a")
    c.check("预填密码一致", loaded.get("password") == secret)
    raw = store.path.read_bytes()
    c.check("加密文件不含明文密码", secret.encode("utf-8") not in raw)
    c.check("加密文件不含明文账号JSON常见形态", b'"password": "unit-test-secret-alpha"' not in raw)
    store.clear()
    loaded = store.load()
    c.check("清除后不再自动填写", loaded.get("remember") is False and loaded.get("password") == "")
    c.check("清除后文件已删除", not store.path.exists())


def test_apply_remember_choice(c):
    secret = "unit-test-secret-beta"
    other = "unit-test-secret-gamma"
    store = _store("apply")
    store.save("teacher", secret)
    result = apply_remember_choice(store, True, "teacher", other, success=False)
    loaded = store.load()
    c.check("登录失败不保存新密码", result == "unchanged" and loaded.get("password") == secret)
    result = apply_remember_choice(store, False, "teacher", other, success=False)
    loaded = store.load()
    c.check("取消勾选后清除", result == "cleared" and loaded.get("remember") is False)
    c.check("取消勾选后文件删除", not store.path.exists())
    result = apply_remember_choice(store, True, "teacher", secret, success=True)
    loaded = store.load()
    c.check("登录成功且勾选则保存", result == "saved" and loaded.get("password") == secret)
    ok = store.update_saved_password(other)
    loaded = store.load()
    c.check("改密后更新已保存密码", ok and loaded.get("password") == other and loaded.get("username") == "teacher")
    store.clear()
    ok = store.update_saved_password(secret)
    c.check("未记住时改密不新建凭据", ok is False and not store.path.exists())


def test_linux_permissions(c):
    if sys.platform == "win32":
        c.check("非 Windows 才测文件权限", True)
        return
    path = WORKDIR / "perm-test.bin"
    if path.exists():
        path.unlink()
    # 使用非默认的测试口令，且只写到临时目录
    dummy = "perm-check-only"
    store = CredentialStore(path=path)
    store.save("demo-user", dummy)
    mode = stat.S_IMODE(path.stat().st_mode)
    c.check("Linux 测试文件权限为 0600", mode == 0o600, oct(mode))
    store.clear()
    c.check("权限测试文件已删除", not path.exists())


def test_login_401_and_reset(c):
    from server.app import app, store as live_store
    from starlette.testclient import TestClient

    http = TestClient(app)
    # 错误密码：服务端文案
    resp = http.post("/api/login", json={"username": "teacher", "password": "wrong-password"})
    c.check("登录接口 401", resp.status_code == 401)
    detail = ""
    try:
        detail = (resp.json() or {}).get("detail") or ""
    except Exception:
        detail = resp.text or ""
    c.check("服务端提示账号或密码不正确", detail == "账号或密码不正确", detail)

    client = TeacherClient("http://testserver", timeout=10)

    # 用 TestClient 走 ASGI 不方便直接给 urllib。改为对 live_store 改密后再用
    # TeacherClient 需要真实 HTTP。这里先测 request() 的分类逻辑：构造 HTTP 错误不便，
    # 下面启动线程里的 uvicorn 再测 TeacherClient。
    # 先用 Store 对象测重置。
    live_store.password_hash = auth.hash_password("ChangedTemp@2026")
    live_store.save()
    live_store.reset_password_to_default()
    c.check(
        "重置后默认密码哈希可校验",
        auth.verify_password(config.DEFAULT_TEACHER_PASSWORD, live_store.password_hash),
    )
    c.check("重置后教师会话已清空", live_store.sessions == {})

    # 再用 TestClient 登录默认密码（不经过 urllib）
    ok = http.post(
        "/api/login",
        json={"username": "teacher", "password": config.DEFAULT_TEACHER_PASSWORD},
    )
    c.check("重置后可用默认密码登录", ok.status_code == 200 and bool((ok.json() or {}).get("token")))
    token = (ok.json() or {}).get("token") or ""
    changed = http.post(
        "/api/password",
        json={"old_password": config.DEFAULT_TEACHER_PASSWORD, "new_password": "ChangedTemp@2026"},
        headers={"Authorization": "Bearer " + token},
    )
    c.check("可通过接口改密", changed.status_code == 200, str(changed.status_code))
    live_store.reset_password_to_default()
    again = http.post(
        "/api/login",
        json={"username": "teacher", "password": config.DEFAULT_TEACHER_PASSWORD},
    )
    c.check("改密后再重置仍可用默认密码", again.status_code == 200 and bool((again.json() or {}).get("token")))
    stale = http.post(
        "/api/login",
        json={"username": "teacher", "password": "ChangedTemp@2026"},
    )
    stale_detail = ""
    try:
        stale_detail = (stale.json() or {}).get("detail") or ""
    except Exception:
        stale_detail = ""
    c.check("重置后旧密码不可用", stale.status_code == 401 and stale_detail == "账号或密码不正确")


def test_teacher_client_login_error_class(c):
    """login() 的 401 是普通 TeacherApiError；已带鉴权的 401 才是 AuthExpired。"""
    import json
    from io import BytesIO
    from urllib.error import HTTPError
    from unittest import mock

    class _Headers(object):
        def __init__(self, ctype):
            self._ctype = ctype

        def get(self, name, default=""):
            if (name or "").lower() == "content-type":
                return self._ctype
            return default

    def _http_error(url, status, payload, ctype="application/json"):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        fp = BytesIO(body)
        return HTTPError(url, status, "Error", _Headers(ctype), fp)

    client = TeacherClient("http://127.0.0.1:9", timeout=2)

    def boom_login(req, timeout=None):
        raise _http_error(req.full_url, 401, {"detail": "账号或密码不正确"})

    try:
        with mock.patch("teacher.api_client.urlopen", boom_login):
            client.login("teacher", "wrong-password")
        c.check("错误密码应失败", False)
    except AuthExpired:
        c.check("登录 401 不应是 AuthExpired", False)
    except TeacherApiError as exc:
        c.check("登录失败是 TeacherApiError", type(exc) is TeacherApiError)
        c.check("登录失败状态 401", exc.status == 401, str(exc.status))
        c.check("登录失败文案为账号或密码不正确", str(exc) == "账号或密码不正确")

    bad = TeacherClient("http://127.0.0.1:9", timeout=2)
    bad.token = "not-a-real-token"

    def boom_auth(req, timeout=None):
        raise _http_error(req.full_url, 401, {"detail": "登录已过期，请重新登录"})

    try:
        with mock.patch("teacher.api_client.urlopen", boom_auth):
            bad.get_state()
        c.check("无效令牌应失败", False)
    except AuthExpired as exc:
        c.check("已带鉴权的 401 仍是 AuthExpired", exc.status == 401)
    except TeacherApiError as exc:
        c.check("已带鉴权的 401 仍是 AuthExpired", False, type(exc).__name__)


def test_source_safety(c):
    cred_src = (ROOT / "teacher" / "credentials.py").read_text(encoding="utf-8")
    win_src = (ROOT / "teacher" / "win_console.py").read_text(encoding="utf-8")
    c.check("credentials 使用 DPAPI", "CryptProtectData" in cred_src and "CryptUnprotectData" in cred_src)
    c.check("登录窗口有记住密码", "记住密码" in win_src and "IDD_REMEMBER" in win_src)
    c.check("登录窗口有重置按钮", "重置为默认密码" in win_src)
    c.check("窗口提示含默认账号但不含默认密码", "默认账号 teacher" in win_src and "ChangeMe@2026" not in win_src)
    c.check("登录窗口提示升级后仍用改过的密码", "改过的那个" in win_src)
    c.check("request 仅在已带鉴权时把 401 当过期", "_auth_was_sent" in (ROOT / "teacher" / "api_client.py").read_text(encoding="utf-8"))


def main():
    c = Checker()
    test_store_save_load_clear(c)
    test_apply_remember_choice(c)
    test_linux_permissions(c)
    test_login_401_and_reset(c)
    test_teacher_client_login_error_class(c)
    test_source_safety(c)
    if not c.summary():
        sys.exit(1)


if __name__ == "__main__":
    main()
