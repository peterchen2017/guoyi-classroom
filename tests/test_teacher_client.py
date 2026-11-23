# -*- coding: utf-8 -*-
"""验证教师 API 客户端与状态映射（Linux 可跑）。不启动 Win32 窗口。"""

from __future__ import print_function

import io
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from teacher.api_client import AuthExpired, TeacherApiError, TeacherClient, encode_multipart
from teacher import state_view

PORT = int(os.environ.get("CLASSROOM_CLIENT_TEST_PORT", "18775"))
BASE = "http://127.0.0.1:%s" % PORT
WORKDIR = Path(os.environ.get("CLASSROOM_CLIENT_TEST_DIR", "/tmp/classroom-lab-teacher-client"))


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


def wait_http(timeout=20):
    deadline = time.time() + timeout
    last = None
    client = TeacherClient(BASE, timeout=1.5)
    while time.time() < deadline:
        try:
            info = client.info()
            if info and info.get("school"):
                return info
        except Exception as exc:
            last = str(exc)
        time.sleep(0.2)
    raise RuntimeError("服务端未能在 %s 秒内启动：%s" % (timeout, last))


def make_jpeg(path, text="wall"):
    img = Image.new("RGB", (320, 200), (40, 80, 160))
    img.save(path, format="JPEG", quality=80)
    return path


def test_state_helpers(chk):
    pending = {"name": "甲", "approved": False, "online": True, "ip": "10.0.0.2"}
    locked = {"name": "乙", "approved": True, "online": True, "locked": True, "hostname": "PC-02"}
    offline = {"name": "丙", "approved": True, "online": False}
    chk.check("待批准标签", state_view.status_label(pending) == "待批准")
    chk.check("锁屏标签", state_view.status_label(locked) == "在线 · 已锁屏")
    chk.check("离线标签", state_view.status_label(offline) == "离线")
    state = {
        "class_active": True,
        "broadcast_active": True,
        "broadcast_shrink": True,
        "class_code": "ABC123",
        "web_restrict": {"enabled": True},
        "desktop": {"locked": True},
        "students": [
            dict(pending, device_id="d1"),
            dict(locked, device_id="d2", thumb_at=1),
            dict(offline, device_id="d3"),
        ],
    }
    chk.check("上课且广播文案", state_view.class_pill_text(state) == "上课中 · 正在广播")
    caps = state_view.toolbar_captions(state)
    chk.check("下课按钮文案", caps["class"] == "下课")
    chk.check("停止广播文案", caps["broadcast"] == "停止广播")
    chk.check("关闭限制文案", caps["restrict"] == "关闭网页/下载限制")
    chk.check("已锁定桌面文案", "已锁定" in caps["desktop"] and caps["desktop_unlock_enabled"])
    chk.check("缩小屏幕勾选", caps["shrink"] is True)
    chk.check("学生汇总含待批准", "待批准 1" in state_view.student_summary(state) and "在线 2" in state_view.student_summary(state))
    wall = state_view.wall_students(state)
    chk.check("屏幕墙只含已批准在线且有缩略图的学生", [s["device_id"] for s in wall] == ["d2"])
    idle = {"class_active": False, "students": state["students"]}
    chk.check("未上课不显示屏幕墙", state_view.wall_students(idle) == [])
    banner = state_view.format_lan_banner(["192.168.1.10"], 8765)
    chk.check("局域网 IP 文案含地址", "192.168.1.10" in banner and "8765" in banner)
    chk.check("名单分行", state_view.split_lines("a\n\nb\r\n c ") == ["a", "b", "c"])


def test_linux_win_console(chk):
    try:
        import teacher.win_console  # noqa: F401
        chk.check("Linux 导入 win_console 应失败", False)
    except ImportError as exc:
        chk.check("Linux 导入 win_console 明确提示仅 Windows", "Windows" in str(exc), str(exc))


def test_multipart(chk):
    ctype, body = encode_multipart(files=[("file", "demo.cpp", b"int main(){}\n")])
    chk.check("multipart Content-Type 含 boundary", ctype.startswith("multipart/form-data; boundary="))
    chk.check("multipart 含文件名与内容", b"filename=\"demo.cpp\"" in body and b"int main(){}" in body)


def main():
    chk = Checker()
    test_state_helpers(chk)
    test_linux_win_console(chk)
    test_multipart(chk)

    if WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    WORKDIR.mkdir(parents=True)
    data_dir = WORKDIR / "server-data"
    data_dir.mkdir()

    import subprocess
    py = Path(os.environ.get("CLASSROOM_PYTHON", sys.executable))
    env = os.environ.copy()
    env["CLASSROOM_DATA_DIR"] = str(data_dir)
    env["CLASSROOM_TEACHER_USER"] = "teacher"
    env["CLASSROOM_TEACHER_PASSWORD"] = "ChangeMe@2026"
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    logf = open(WORKDIR / "server.log", "w", encoding="utf-8")
    server = subprocess.Popen(
        [str(py), "-m", "server", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
    )
    try:
        info = wait_http()
        chk.check("公开信息学校名", info.get("school") == "乐昌国艺书院")
        chk.check("公开信息版本", info.get("version") == "1.2.4", str(info.get("version")))
        chk.check("公开信息开发者", info.get("developer") == "陈老师")

        client = TeacherClient(BASE, timeout=10)
        try:
            client.login("teacher", "wrong-password")
            chk.check("错误密码被拒绝", False)
        except AuthExpired as exc:
            chk.check("错误密码返回 401", exc.status == 401, str(exc))
        except TeacherApiError as exc:
            chk.check("错误密码被拒绝", exc.status == 401, str(exc))

        data = client.login("teacher", "ChangeMe@2026")
        chk.check("教师登录成功", bool(client.token) and data.get("username") == "teacher")
        chk.check("登录响应含课堂状态", isinstance(data.get("state"), dict) and "class_code" in data["state"])
        chk.check("Authorization 使用 Bearer", client._headers()["Authorization"].startswith("Bearer "))

        st = client.get_state()
        code = st.get("class_code")
        chk.check("读取加入码", bool(code), str(code))

        refreshed = client.refresh_code()
        chk.check("换码后加入码变化", refreshed.get("class_code") and refreshed["class_code"] != code, str(refreshed))

        try:
            client.broadcast_start()
            chk.check("未上课时广播应失败", False)
        except TeacherApiError as exc:
            chk.check("未上课时广播被拒绝", exc.status == 400, str(exc))

        st = client.class_start()
        chk.check("开始上课", st.get("class_active") is True)
        chk.check("上课后默认开启网页限制", (st.get("web_restrict") or {}).get("enabled") is True)

        client.announce("请看黑板", "announce")
        client.announce("计算 1+1", "question")
        st = client.get_state()
        chk.check("公告已写入状态", st.get("announcement") == "计算 1+1")

        cpp_path = WORKDIR / "hello.cpp"
        cpp_path.write_text("int main(){return 0;}\n", encoding="utf-8")
        sent = client.upload_file(cpp_path)
        chk.check("发文件返回成功", sent.get("ok") is True and sent.get("filename") == "hello.cpp")

        listed = client.restrict_lists(game_domains=["example-game.test"], whitelist_domains=["school.test"])
        wr = listed.get("web_restrict") or {}
        chk.check("编辑限制名单生效", "example-game.test" in (wr.get("game_domains") or []) and "school.test" in (wr.get("whitelist_domains") or []))
        reset = client.restrict_lists(reset_defaults=True)
        wr2 = reset.get("web_restrict") or {}
        chk.check("恢复默认名单后自定义域名移除", "example-game.test" not in (wr2.get("game_domains") or []))

        off = client.restrict_web(False)
        chk.check("上课期间可临时关闭限制", (off.get("web_restrict") or {}).get("enabled") is False)
        on = client.restrict_web(True)
        chk.check("可重新打开限制", (on.get("web_restrict") or {}).get("enabled") is True)

        started = client.broadcast_start(shrink=True)
        chk.check("开始广播", started.get("ok") is True or started.get("broadcast_active") is True or client.get_state().get("broadcast_active") is True)
        settings = client.broadcast_settings(False)
        chk.check("取消缩小屏幕", settings.get("shrink") is False or client.get_state().get("broadcast_shrink") is False, str(settings))
        img = WORKDIR / "frame.jpg"
        make_jpeg(img)
        frame = client.broadcast_frame(img)
        chk.check("广播图片成功", frame.get("ok") is True or "at" in (frame or {}), str(frame))
        client.broadcast_end()
        chk.check("停止广播", client.get_state().get("broadcast_active") is False)

        wall = WORKDIR / "desk.jpg"
        make_jpeg(wall, "desk")
        desk = client.set_desktop_wallpaper(wall, lock=True)
        chk.check("设置并锁定默认桌面", (desk.get("desktop") or {}).get("locked") is True)
        body, status, ctype = client.desktop_image()
        chk.check("可读取桌面预览图", status == 200 and body and len(body) > 20, "status=%s ctype=%s" % (status, ctype))
        unlocked = client.desktop_unlock()
        chk.check("解除桌面锁定", (unlocked.get("desktop") or {}).get("locked") is False)

        ended = client.class_end()
        chk.check("下课", ended.get("class_active") is False)

        client.change_password("ChangeMe@2026", "NewPass@2026")
        other = TeacherClient(BASE, timeout=10)
        other.login("teacher", "NewPass@2026")
        chk.check("改密码后可用新密码登录", bool(other.token))
        try:
            TeacherClient(BASE, timeout=10).login("teacher", "ChangeMe@2026")
            chk.check("旧密码已失效", False)
        except (AuthExpired, TeacherApiError):
            chk.check("旧密码已失效", True)

        bad = TeacherClient(BASE, timeout=10)
        bad.token = "not-a-real-token"
        try:
            bad.get_state()
            chk.check("无效令牌应 401", False)
        except AuthExpired:
            chk.check("无效令牌触发 AuthExpired", True)
        except TeacherApiError as exc:
            chk.check("无效令牌被拒绝", exc.status == 401, str(exc))
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()
        logf.close()

    if not chk.summary():
        sys.exit(1)


if __name__ == "__main__":
    main()
