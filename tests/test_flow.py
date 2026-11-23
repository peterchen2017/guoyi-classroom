# -*- coding: utf-8 -*-
"""Linux 核心流程验证：登录、批准、上课、缩略图、锁屏、公告、发文件、广播、默认桌面锁定、下课停传。"""

from __future__ import print_function

import json
import os
import sys
import time
import io
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from PIL import Image, ImageDraw

def http_via_proxy(url, proxy, timeout=5.0):
    try:
        return httpx.get(url, proxy=proxy, timeout=timeout, follow_redirects=False)
    except TypeError:
        return httpx.get(url, proxies={"http://": proxy, "https://": proxy}, timeout=timeout, follow_redirects=False)

PORT = int(os.environ.get("CLASSROOM_TEST_PORT", "18765"))
BASE = "http://127.0.0.1:%s" % PORT
WORKDIR = Path(os.environ.get("CLASSROOM_TEST_DIR", "/tmp/classroom-lab-verify"))


class Checker(object):
    def __init__(self):
        self.ok = 0
        self.fail = 0
        self.rows = []

    def check(self, name, cond, detail=""):
        if cond:
            self.ok += 1
            status = "通过"
        else:
            self.fail += 1
            status = "失败"
        line = "[%s] %s%s" % (status, name, (" — " + detail) if detail else "")
        self.rows.append(line)
        print(line, flush=True)
        return cond

    def summary(self):
        print("", flush=True)
        print("合计：通过 %s，失败 %s" % (self.ok, self.fail), flush=True)
        return self.fail == 0


def wait_http(timeout=20):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            r = httpx.get(BASE + "/api/info", timeout=1.0)
            if r.status_code == 200:
                return True
            last = "HTTP %s" % r.status_code
        except Exception as exc:
            last = str(exc)
        time.sleep(0.2)
    raise RuntimeError("服务端未能在 %s 秒内启动：%s" % (timeout, last))


def make_test_jpeg(text, path):
    img = Image.new("RGB", (640, 360), (180, 40, 40))
    d = ImageDraw.Draw(img)
    d.text((40, 160), text, fill=(255, 255, 255))
    img.save(path, format="JPEG", quality=80)
    return path


def read_events(path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def has_event(events, name):
    for ev in events:
        if ev.get("event") == name:
            return True
    return False


def last_ts(events, name):
    ts = 0
    for ev in events:
        if ev.get("event") == name:
            ts = ev.get("ts") or ts
    return ts


def main():
    chk = Checker()
    if WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    WORKDIR.mkdir(parents=True)
    data_dir = WORKDIR / "server-data"
    data_dir.mkdir()

    py = Path(os.environ.get("CLASSROOM_PYTHON", sys.executable))
    env = os.environ.copy()
    env["CLASSROOM_DATA_DIR"] = str(data_dir)
    env["CLASSROOM_TEACHER_USER"] = "teacher"
    env["CLASSROOM_TEACHER_PASSWORD"] = "ChangeMe@2026"
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"

    log_path = WORKDIR / "server.log"
    logf = open(log_path, "w", encoding="utf-8")
    server = subprocess.Popen(
        [str(py), "-m", "server", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
    )
    students = []
    try:
        wait_http()
        chk.check("服务端启动", True, BASE)

        client = httpx.Client(timeout=10.0)
        info = client.get(BASE + "/api/info").json()
        chk.check("公开信息", info.get("school") == "乐昌国艺书院")
        chk.check("版权与开发者署名",
                  "乐昌国艺书院" in (info.get("copyright") or "") and info.get("developer") == "陈老师")

        bad = client.post(BASE + "/api/login", json={"username": "teacher", "password": "wrong"})
        chk.check("错误密码被拒绝", bad.status_code == 401)

        login = client.post(BASE + "/api/login", json={"username": "teacher", "password": "ChangeMe@2026"})
        chk.check("教师登录", login.status_code == 200, "用户名 teacher")
        token = login.json()["token"]
        headers = {"Authorization": "Bearer " + token}
        st = client.get(BASE + "/api/state", headers=headers).json()
        code = st["class_code"]
        chk.check("读取课堂加入码", bool(code), code)

        def start_student(tag, name, use_code):
            sdir = WORKDIR / tag
            sdir.mkdir(exist_ok=True)
            ev = sdir / "events.jsonl"
            cmd = [
                str(py), "-m", "student",
                "--server", "127.0.0.1",
                "--port", str(PORT),
                "--name", name,
                "--sim", "--no-ui",
                "--event-log", str(ev),
                "--data-dir", str(sdir),
            ]
            if use_code:
                cmd.extend(["--code", code])
            proc = subprocess.Popen(
                cmd, cwd=str(ROOT), env=env,
                stdout=open(sdir / "stdout.log", "w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
            )
            return {"proc": proc, "events": ev, "name": name, "tag": tag}

        students.append(start_student("s1", "学生甲", True))
        students.append(start_student("s2", "学生乙", True))
        students.append(start_student("s3", "学生丙", False))

        pending = None
        approved_n = 0
        deadline = time.time() + 15
        while time.time() < deadline:
            st = client.get(BASE + "/api/state", headers=headers).json()
            names = [s["name"] for s in st["students"] if s["online"]]
            approved_n = len([s for s in st["students"] if s["approved"] and s["online"]])
            pend = [s for s in st["students"] if (not s["approved"]) and s["online"]]
            if len(names) >= 3 and approved_n >= 2 and pend:
                pending = pend[0]
                break
            time.sleep(0.3)
        chk.check("三台模拟学生机上线", pending is not None and approved_n >= 2,
                  "待批准=%s 已批准在线=%s" % (pending["name"] if pending else "无", approved_n))

        if pending:
            r = client.post(BASE + "/api/students/%s/approve" % pending["device_id"],
                            headers=headers, json={})
            chk.check("教师批准待加入学生机", r.status_code == 200)
        else:
            chk.check("教师批准待加入学生机", False, "没有待批准学生")

        r = client.post(BASE + "/api/class/start", headers=headers, json={})
        st0 = r.json()
        chk.check("开始上课", r.status_code == 200 and st0.get("class_active") is True)
        wr = (st0.get("web_restrict") or {})
        chk.check("开始上课后默认开启上网限制", wr.get("enabled") is True)

        thumbs_ok = False
        deadline = time.time() + 12
        while time.time() < deadline:
            st = client.get(BASE + "/api/state", headers=headers).json()
            with_thumb = [s for s in st["students"] if s.get("thumb_at") and s["online"]]
            if len(with_thumb) >= 3:
                ok_img = 0
                for s in with_thumb:
                    img = client.get(BASE + "/api/thumbs/" + s["device_id"], headers=headers)
                    if img.status_code == 200 and img.headers.get("content-type", "").startswith("image/"):
                        ok_img += 1
                if ok_img >= 3:
                    thumbs_ok = True
                    break
            time.sleep(0.4)
        chk.check("收到教室屏幕墙缩略图", thumbs_ok)

        st = client.get(BASE + "/api/state", headers=headers).json()
        focus_stu = None
        for s in st["students"]:
            if s["approved"] and s["online"]:
                focus_stu = s
                break
        if focus_stu:
            r = client.post(BASE + "/api/focus", headers=headers, json={"student_id": focus_stu["device_id"]})
            time.sleep(1.2)
            img = client.get(BASE + "/api/focus/" + focus_stu["device_id"], headers=headers)
            chk.check("单人查看画面", r.status_code == 200 and img.status_code == 200, focus_stu["name"])
        else:
            chk.check("单人查看画面", False, "没有在线学生")

        r = client.post(BASE + "/api/lock", headers=headers, json={})
        time.sleep(1.0)
        evs = [read_events(s["events"]) for s in students]
        lock_ok = all(has_event(e, "lock") for e in evs)
        chk.check("锁屏指令到达全部学生端", r.status_code == 200 and lock_ok)

        r = client.post(BASE + "/api/unlock", headers=headers, json={})
        time.sleep(1.0)
        evs = [read_events(s["events"]) for s in students]
        unlock_ok = all(has_event(e, "unlock") for e in evs)
        chk.check("解锁指令到达全部学生端", r.status_code == 200 and unlock_ok)

        r = client.post(BASE + "/api/announce", headers=headers,
                        json={"text": "请打开练习一", "kind": "announce"})
        time.sleep(1.0)
        evs = [read_events(s["events"]) for s in students]
        ann_ok = all(has_event(e, "announce") for e in evs)
        chk.check("公告到达全部学生端", r.status_code == 200 and ann_ok)

        practice = WORKDIR / "练习题.txt"
        practice.write_text("第一题：输出 Hello, Classroom\n", encoding="utf-8")
        with practice.open("rb") as fh:
            r = client.post(BASE + "/api/files", headers=headers, files={"file": ("练习题.txt", fh, "text/plain")})
        time.sleep(1.5)
        evs = [read_events(s["events"]) for s in students]
        file_ok = all(has_event(e, "file") for e in evs)
        saved = list(WORKDIR.glob("s*/课堂文件/练习题.txt"))
        chk.check("文件到达学生端并落盘", r.status_code == 200 and file_ok and len(saved) >= 3,
                  "保存 %s 份" % len(saved))

        cpp = WORKDIR / "hello.cpp"
        cpp.write_text("int main(){return 0;}\n", encoding="utf-8")
        with cpp.open("rb") as fh:
            r = client.post(BASE + "/api/files", headers=headers, files={"file": ("hello.cpp", fh, "text/plain")})
        time.sleep(1.5)
        evs = [read_events(s["events"]) for s in students]
        cpp_saved = list(WORKDIR.glob("s*/课堂文件/hello.cpp"))
        cpp_ok = all(
            any(e.get("event") == "file" and str(e.get("filename") or "").endswith(".cpp") for e in ev)
            for ev in evs
        )
        chk.check("C++ 代码文件发到学生机", r.status_code == 200 and cpp_ok and len(cpp_saved) >= 3,
                  "保存 %s 份" % len(cpp_saved))

        # 学生过滤代理：游戏站与安装包被拒，教师机下发仍成功
        evs = [read_events(s["events"]) for s in students]
        ports = []
        for ev in evs:
            for rec in ev:
                if rec.get("event") == "web_restrict_on" and rec.get("port"):
                    ports.append(int(rec["port"]))
        restrict_proxy_ok = False
        if ports:
            px = "http://127.0.0.1:%s" % ports[0]
            try:
                g = http_via_proxy("http://www.4399.com/", px)
                z = http_via_proxy("http://cdn.example.com/setup.exe", px)
                restrict_proxy_ok = g.status_code == 403 and z.status_code == 403
            except Exception:
                restrict_proxy_ok = False
        chk.check("学生端代理拦截游戏站和安装包", restrict_proxy_ok, "端口 %s" % (ports[:3],))

        r = client.post(BASE + "/api/restrict/web", headers=headers, json={"enabled": False})
        time.sleep(1.0)
        evs = [read_events(s["events"]) for s in students]
        off_ok = all(has_event(e, "web_restrict_off") for e in evs)
        chk.check("上课中关闭限制并恢复设置", r.status_code == 200 and off_ok
                  and r.json().get("web_restrict", {}).get("enabled") is False)

        r = client.post(BASE + "/api/restrict/web", headers=headers, json={"enabled": True})
        time.sleep(1.0)
        chk.check("重新开启上网限制", r.status_code == 200 and r.json().get("web_restrict", {}).get("enabled") is True)

        jpg = WORKDIR / "teacher.jpg"
        make_test_jpeg("TEACHER BROADCAST", jpg)
        r0 = client.post(BASE + "/api/broadcast/start", headers=headers, json={})
        with jpg.open("rb") as fh:
            r1 = client.post(BASE + "/api/broadcast/frame", headers=headers,
                             files={"file": ("teacher.jpg", fh, "image/jpeg")})
        time.sleep(1.5)
        evs = [read_events(s["events"]) for s in students]
        bc_ok = all(has_event(e, "broadcast_frame") for e in evs)
        chk.check("广播教师屏幕（测试图）到达学生端", r0.status_code == 200 and r1.status_code == 200 and bc_ok)

        big = Image.new("RGB", (1280, 720), (200, 30, 30))
        big_path = WORKDIR / "teacher_big.jpg"
        big.save(big_path, format="JPEG", quality=85)
        r_sh = client.post(BASE + "/api/broadcast/settings", headers=headers, json={"shrink": True})
        with big_path.open("rb") as fh:
            r_up = client.post(BASE + "/api/broadcast/frame", headers=headers,
                               files={"file": ("teacher_big.jpg", fh, "image/jpeg")})
        time.sleep(1.2)
        img = client.get(BASE + "/api/broadcast/image", headers=headers)
        # 控制台预览可能是原图接口；以学生收到的帧为准较难取字节，这里直接测 scale 与接口。
        shrink_flag = r_sh.status_code == 200 and r_sh.json().get("shrink") is True
        chk.check("勾选缩小屏幕", shrink_flag and r_up.status_code == 200)

        wall = WORKDIR / "lab_wallpaper.jpg"
        make_test_jpeg("LAB DESKTOP", wall)
        with wall.open("rb") as fh:
            r = client.post(
                BASE + "/api/desktop/wallpaper?lock=1",
                headers=headers,
                files={"file": ("lab_wallpaper.jpg", fh, "image/jpeg")},
            )
        deadline = time.time() + 8
        applied = False
        locked_ok = 0
        while time.time() < deadline:
            evs = [read_events(s["events"]) for s in students]
            applied = all(has_event(e, "desktop_applied") for e in evs)
            locked_ok = 0
            for path in WORKDIR.glob("s*/desktop/desktop_lock.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if payload.get("locked") and payload.get("intended_bmp"):
                    locked_ok += 1
            if applied and locked_ok >= 3:
                break
            time.sleep(0.3)
        st = client.get(BASE + "/api/state", headers=headers).json()
        desk = st.get("desktop") or {}
        preview = client.get(BASE + "/api/desktop/image", headers=headers)
        chk.check(
            "下发默认桌面并锁定",
            r.status_code == 200 and desk.get("locked") is True and applied and locked_ok >= 3 and preview.status_code == 200,
            "锁定 %s 台" % locked_ok,
        )

        # 记录下课前最后一帧时间
        evs_before = [read_events(s["events"]) for s in students]
        last_before = [last_ts(e, "frame_sent") for e in evs_before]
        r = client.post(BASE + "/api/class/end", headers=headers, json={})
        time.sleep(2.5)
        evs_after = [read_events(s["events"]) for s in students]
        stopped = all(has_event(e, "class_end") and has_event(e, "stopped_sending") for e in evs_after)
        no_new = True
        for i, ev in enumerate(evs_after):
            if last_ts(ev, "frame_sent") > last_before[i] + 0.05 and last_ts(ev, "frame_sent") > last_ts(ev, "class_end"):
                # 允许下课瞬间还有一帧在路上，但不能在 class_end 之后仍持续发送
                frames_after = [x for x in ev if x.get("event") == "frame_sent" and x.get("ts") > last_ts(ev, "class_end") + 0.8]
                if frames_after:
                    no_new = False
        st = client.get(BASE + "/api/state", headers=headers).json()
        chk.check("下课后停止传屏", r.status_code == 200 and (not st.get("class_active")) and stopped and no_new)
        evs_end = [read_events(s["events"]) for s in students]
        restrict_cleared = all(has_event(e, "web_restrict_off") for e in evs_end)
        chk.check("下课后关闭限制", restrict_cleared and (not (st.get("web_restrict") or {}).get("enabled")))

        # 下课后再取缩略图应已清空
        thumb_cleared = True
        for s in st["students"]:
            img = client.get(BASE + "/api/thumbs/" + s["device_id"], headers=headers)
            if img.status_code == 200:
                thumb_cleared = False
        chk.check("下课立即丢弃屏幕缓存", thumb_cleared)

        st = client.get(BASE + "/api/state", headers=headers).json()
        still = (st.get("desktop") or {}).get("locked") is True
        still_students = 0
        for path in WORKDIR.glob("s*/desktop/desktop_lock.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if payload.get("locked"):
                still_students += 1
        evs_end2 = [read_events(s["events"]) for s in students]
        unlocked_early = any(has_event(e, "desktop_unlocked") for e in evs_end2)
        chk.check("下课后桌面锁定仍保持", still and still_students >= 3 and not unlocked_early)

        # 重启一台学生机：同一数据目录应自动重新应用锁定
        s1 = students[0]
        try:
            s1["proc"].terminate()
            s1["proc"].wait(timeout=5)
        except Exception:
            try:
                s1["proc"].kill()
            except Exception:
                pass
        students[0] = start_student("s1", "学生甲", True)
        deadline = time.time() + 8
        reapplied = False
        st1_locked = False
        while time.time() < deadline:
            ev = read_events(students[0]["events"])
            reapplied = has_event(ev, "desktop_reapplied") or has_event(ev, "desktop_applied")
            lockp = WORKDIR / "s1" / "desktop" / "desktop_lock.json"
            if lockp.is_file():
                try:
                    st1_locked = bool(json.loads(lockp.read_text(encoding="utf-8")).get("locked"))
                except (OSError, ValueError):
                    st1_locked = False
            if reapplied and st1_locked:
                break
            time.sleep(0.3)
        chk.check("学生机重启后重新应用桌面锁定", reapplied and st1_locked)

        r = client.post(BASE + "/api/desktop/unlock", headers=headers, json={})
        deadline = time.time() + 8
        unlocked = False
        cleared = 0
        while time.time() < deadline:
            evs = [read_events(s["events"]) for s in students]
            unlocked = all(has_event(e, "desktop_unlocked") for e in evs)
            cleared = 0
            for path in WORKDIR.glob("s*/desktop/desktop_lock.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not payload.get("locked"):
                    cleared += 1
            if unlocked and cleared >= 3:
                break
            time.sleep(0.3)
        st = client.get(BASE + "/api/state", headers=headers).json()
        chk.check(
            "解除桌面锁定并恢复",
            r.status_code == 200 and not (st.get("desktop") or {}).get("locked") and unlocked and cleared >= 3,
            "已恢复 %s 台" % cleared,
        )

        client.close()
    except Exception as exc:
        chk.check("测试过程未异常中断", False, str(exc))
        import traceback
        traceback.print_exc()
    finally:
        for s in students:
            try:
                s["proc"].terminate()
            except Exception:
                pass
        try:
            server.terminate()
            server.wait(timeout=5)
        except Exception:
            try:
                server.kill()
            except Exception:
                pass
        logf.close()

    report = WORKDIR / "report.txt"
    report.write_text("\n".join(chk.rows) + "\n合计：通过 %s，失败 %s\n" % (chk.ok, chk.fail), encoding="utf-8")
    ok = chk.summary()
    if not ok:
        print("服务端日志：%s" % log_path, flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
