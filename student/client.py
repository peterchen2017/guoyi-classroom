# -*- coding: utf-8 -*-
"""学生机客户端：连接教师机、上课后传屏、接收锁屏/公告/文件/广播。"""

from __future__ import print_function

import argparse
import asyncio
import base64
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path

# 保证以 python launch 或 -m student 都能找到包
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import config as server_config
from student.screen import capture_jpeg
from student.ui import create_ui
from student.web_restrict import WebRestrictor
from student.wallpaper import DesktopManager

if sys.version_info < (3, 8):
    sys.stderr.write("需要 Python 3.8 或更高版本。Windows 7 请安装官方 Python 3.8.10。\n")
    sys.exit(1)


def _ws_connect(url):
    """兼容 websockets 10–17 的连接入口。"""
    max_size = 8 * 1024 * 1024
    try:
        import websockets
        if hasattr(websockets, "connect"):
            return websockets.connect(url, max_size=max_size, ping_interval=20, ping_timeout=20)
    except Exception:
        pass
    try:
        from websockets.legacy.client import connect as legacy_connect
        return legacy_connect(url, max_size=max_size, ping_interval=20, ping_timeout=20)
    except Exception:
        from websockets.asyncio.client import connect as aio_connect
        return aio_connect(url, max_size=max_size)


def discover_teacher(timeout=3.0, port=None):
    """UDP 探测教师机，返回 (ip, port) 或 None。"""
    port = port or server_config.DISCOVERY_PORT
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    try:
        sock.bind(("", 0))
        sock.sendto(server_config.DISCOVERY_PROBE, ("255.255.255.255", port))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                sock.settimeout(max(0.1, deadline - time.time()))
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                break
            if not data.startswith(server_config.DISCOVERY_MAGIC):
                continue
            ip, http_port = addr[0], server_config.PORT
            try:
                text = data.split(b"\n", 1)[1].decode("utf-8")
                body = json.loads(text)
                http_port = int(body.get("port") or http_port)
                if body.get("ip"):
                    ip = body.get("ip")
            except Exception:
                pass
            if ip and not str(ip).startswith("127."):
                return ip, http_port
            return addr[0], http_port
    except OSError:
        return None
    finally:
        sock.close()
    return None


def load_or_create_device_id(data_dir):
    path = data_dir / "device.json"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("device_id"):
                return raw["device_id"]
        except (OSError, ValueError):
            pass
    device_id = str(uuid.uuid4())
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"device_id": device_id}, ensure_ascii=False, indent=2), encoding="utf-8")
    return device_id


def load_saved_config(data_dir):
    path = data_dir / "config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(data_dir, cfg):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class EventLog(object):
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event, **kwargs):
        rec = {"ts": time.time(), "event": event}
        rec.update(kwargs)
        line = json.dumps(rec, ensure_ascii=False)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return rec


class StudentClient(object):
    def __init__(self, args):
        self.args = args
        self.data_dir = Path(args.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.device_id = load_or_create_device_id(self.data_dir)
        self.name = args.name
        self.server = args.server
        self.port = args.port
        self.class_code = (args.code or "").strip().upper()
        self.sim = bool(args.sim)
        self.ui = create_ui(sim=self.sim, no_ui=bool(args.no_ui))
        self.log = EventLog(args.event_log)
        self.token = ""
        self.approved = False
        self.class_active = False
        self.locked = False
        self.broadcast_active = False
        self.focus_on = False
        self.remote_active = False
        self._stop_send = asyncio.Event()
        self._sender_task = None
        self._running = True
        self._frames_sent = 0
        self._stopped_sending = False
        self.web_restrict_on = False
        self.restrictor = WebRestrictor(self.data_dir, log=self.log, ui=self.ui)
        self.restrictor.restore_leftover()
        # 默认桌面锁定与上课无关：启动时若本地仍锁定，立即重新应用。
        self.desktop = DesktopManager(self.data_dir, log=self.log, ui=self.ui)

    def _status_text(self):
        parts = [
            "课堂管理运行中",
            "乐昌国艺书院  学生机  v%s" % server_config.VERSION,
            "学生：%s" % self.name,
            "教师机：%s:%s" % (self.server or "未连接", self.port),
            "登记：%s" % ("已加入" if self.approved else "等待教师允许"),
            "课堂：%s" % ("上课中" if self.class_active else "未上课（不传屏）"),
            "锁屏：%s" % ("是" if self.locked else "否"),
            "远程控制：%s" % ("老师正在控制本机" if self.remote_active else "否"),
            "上网限制：%s" % ("已限制网页游戏和下载" if self.web_restrict_on else "未开启"),
            "默认桌面：%s" % self.desktop.status_label(),
            server_config.COPYRIGHT,
        ]
        return "\n".join(parts)

    def _refresh_ui(self):
        self.ui.set_status(self._status_text())

    def _start_remote(self):
        if not (self.approved and self.class_active):
            return
        if self.remote_active:
            return
        self.remote_active = True
        try:
            self.ui.show_remote_control()
        except Exception:
            pass
        self.log.write("remote_start")
        self._refresh_ui()

    def _stop_remote(self, reason=""):
        if not self.remote_active:
            return
        self.remote_active = False
        try:
            self.ui.hide_remote_control()
        except Exception:
            pass
        self.log.write("remote_stop", reason=reason)
        self._refresh_ui()

    def _apply_restrict(self, msg):
        msg = msg or {}
        enabled = bool(msg.get("enabled"))
        if enabled:
            self.restrictor.apply(msg, teacher_server=self.server, teacher_port=self.port)
            self.web_restrict_on = True
        else:
            self.restrictor.disable()
            self.web_restrict_on = False

    def _recv_dir(self):
        path = self.data_dir / "课堂文件"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def _handle(self, msg):
        typ = msg.get("type")
        if typ == "welcome":
            self.approved = bool(msg.get("approved"))
            self.class_active = bool(msg.get("class_active"))
            self.token = msg.get("token") or ""
            self.locked = bool(msg.get("locked"))
            self.broadcast_active = bool(msg.get("broadcast_active"))
            self.log.write("welcome", approved=self.approved, class_active=self.class_active)
            if self.approved and self.class_active:
                self._start_sending()
            if self.locked:
                self.ui.show_lock("请看老师")
            wr = msg.get("web_restrict")
            if wr:
                self._apply_restrict(wr)
            desk = msg.get("desktop")
            if desk:
                await self._apply_desktop(desk)
            if msg.get("remote_active"):
                self._start_remote()
            self._refresh_ui()
        elif typ == "approved":
            self.approved = True
            if msg.get("class_active"):
                self.class_active = True
                self._start_sending()
            self.log.write("approved")
            self.ui.show_announce("课堂管理", "教师已允许本机加入课堂")
            self._refresh_ui()
        elif typ == "revoked":
            self.approved = False
            await self._stop_sending(reason="revoked")
            self.locked = False
            self._apply_restrict({"enabled": False})
            self.ui.hide_lock()
            self.ui.clear_broadcast()
            self._stop_remote("revoked")
            self.log.write("revoked")
            self._refresh_ui()
        elif typ == "class_start":
            self.class_active = True
            self._stopped_sending = False
            self.log.write("class_start")
            if self.approved:
                self._start_sending()
            wr = msg.get("web_restrict")
            if wr:
                self._apply_restrict(wr)
            self._refresh_ui()
        elif typ == "class_end":
            self.class_active = False
            self.locked = False
            self.broadcast_active = False
            self.focus_on = False
            await self._stop_sending(reason="class_end")
            self._apply_restrict({"enabled": False})
            self.ui.hide_lock()
            self.ui.clear_broadcast()
            self._stop_remote("class_end")
            self.log.write("class_end")
            self._refresh_ui()
        elif typ == "web_restrict":
            self._apply_restrict(msg)
            self._refresh_ui()
        elif typ in ("desktop_lock", "desktop_unlock"):
            await self._apply_desktop(msg)
        elif typ == "lock":
            self.locked = True
            self.ui.show_lock(msg.get("message") or "请看老师")
            self.log.write("lock")
            self._refresh_ui()
        elif typ == "unlock":
            self.locked = False
            self.ui.hide_lock()
            self.log.write("unlock")
            self._refresh_ui()
        elif typ in ("announce", "question"):
            title = msg.get("title") or ("课堂题目" if typ == "question" else "课堂公告")
            text = msg.get("text") or ""
            self.ui.show_announce(title, text)
            self.log.write(typ, text=text, title=title)
        elif typ == "file":
            await self._download_file(msg)
        elif typ == "broadcast_start":
            self.broadcast_active = True
            self.log.write("broadcast_start")
        elif typ == "broadcast_end":
            self.broadcast_active = False
            self.ui.clear_broadcast()
            self.log.write("broadcast_end")
        elif typ == "broadcast_frame":
            raw = msg.get("data") or ""
            try:
                data = base64.b64decode(raw)
            except Exception:
                data = b""
            if data:
                self.ui.show_broadcast_frame(data)
                self.log.write("broadcast_frame", bytes=len(data))
        elif typ == "focus":
            self.focus_on = bool(msg.get("on"))
            self.log.write("focus", on=self.focus_on)
        elif typ == "remote_start":
            self._start_remote()
        elif typ == "remote_stop":
            self._stop_remote("teacher")
        elif typ == "remote_input":
            if self.remote_active and self.class_active and self.approved:
                try:
                    from student.remote_input import apply_events
                    apply_events(msg.get("events") or [])
                except Exception as exc:
                    self.log.write("remote_input_error", error=str(exc))
        elif typ == "error":
            self.ui.show_announce("连接提示", msg.get("message") or "发生错误")
            self.log.write("error", message=msg.get("message"))

    async def _apply_desktop(self, msg):
        msg = msg or {}
        typ = msg.get("type") or ""
        locked = bool(msg.get("locked")) if "locked" in msg else (typ == "desktop_lock")
        if typ == "desktop_unlock" or not locked:
            if self.desktop.is_locked():
                self.desktop.unlock()
            self._refresh_ui()
            return
        url = msg.get("url") or ""
        if not url:
            self._refresh_ui()
            return
        if url.startswith("/"):
            url = "http://%s:%s%s" % (self.server, self.port, url)
        try:
            import urllib.request
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            filename = Path(msg.get("filename") or "wallpaper.jpg").name
            self.desktop.apply_image(data, filename=filename, lock=True)
        except Exception as exc:
            self.log.write("desktop_error", error=str(exc))
        self._refresh_ui()

    async def _download_file(self, msg):
        url = msg.get("url") or ""
        filename = Path(msg.get("filename") or "课堂文件").name
        dest = self._recv_dir() / filename
        if not url:
            self.log.write("file_error", reason="missing url")
            return
        if url.startswith("/"):
            url = "http://%s:%s%s" % (self.server, self.port, url)
        try:
            import urllib.request
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            dest.write_bytes(data)
            self.ui.show_announce("收到文件", "已保存：%s" % dest)
            self.log.write("file", filename=filename, path=str(dest), size=len(data))
        except Exception as exc:
            self.log.write("file_error", filename=filename, error=str(exc))
            self.ui.show_announce("文件接收失败", str(exc))

    def _start_sending(self):
        if not (self.approved and self.class_active):
            return
        self._stop_send.clear()
        self._stopped_sending = False
        if self._sender_task is None or self._sender_task.done():
            self._sender_task = asyncio.create_task(self._send_loop())

    async def _stop_sending(self, reason=""):
        self._stop_send.set()
        task = self._sender_task
        self._sender_task = None
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2)
            except Exception:
                task.cancel()
        if not self._stopped_sending:
            self._stopped_sending = True
            self.log.write("stopped_sending", reason=reason)

    async def _send_loop(self):
        try:
            while not self._stop_send.is_set() and self.class_active and self.approved:
                kind = "focus" if self.focus_on else "thumb"
                quality = 70 if self.focus_on else 55
                max_width = 960 if self.focus_on else 480
                try:
                    loop = asyncio.get_running_loop()
                    jpeg = await loop.run_in_executor(
                        None,
                        lambda: capture_jpeg(
                            self.name,
                            max_width=max_width,
                            quality=quality,
                            sim=self.sim,
                            extra_lines=["上课中"] + (["已锁屏"] if self.locked else []),
                        ),
                    )
                except Exception:
                    jpeg = None
                if jpeg and self.ws is not None and not self._stop_send.is_set() and self.class_active:
                    payload = {
                        "type": "frame",
                        "kind": kind,
                        "mime": "image/jpeg",
                        "data": base64.b64encode(jpeg).decode("ascii"),
                    }
                    try:
                        await self.ws.send(json.dumps(payload))
                        self._frames_sent += 1
                        self.log.write("frame_sent", kind=kind, bytes=len(jpeg), n=self._frames_sent)
                    except Exception:
                        break
                interval = server_config.FOCUS_INTERVAL if self.focus_on else server_config.THUMB_INTERVAL
                try:
                    await asyncio.wait_for(self._stop_send.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            if not self._stopped_sending and not self.class_active:
                self._stopped_sending = True
                self.log.write("stopped_sending", reason="loop_exit")

    async def _session(self):
        url = "ws://%s:%s/ws/student" % (self.server, self.port)
        self.ui.set_status(self._status_text() + "\n正在连接…")
        async with _ws_connect(url) as ws:
            self.ws = ws
            hello = {
                "type": "hello",
                "device_id": self.device_id,
                "name": self.name,
                "hostname": socket.gethostname(),
                "platform": "linux-sim" if (self.sim or sys.platform != "win32") else sys.platform,
                "class_code": self.class_code,
            }
            await ws.send(json.dumps(hello, ensure_ascii=False))
            self.log.write("connected", server=self.server, port=self.port)
            self._refresh_ui()
            while self._running:
                raw = await ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                await self._handle(msg)

    async def run(self):
        self.ui.start()
        self._refresh_ui()
        backoff = 1
        try:
            while self._running:
                self.ws = None
                try:
                    await self._session()
                    backoff = 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.log.write("disconnect", error=str(exc))
                    self.approved = False
                    self.class_active = False
                    self._stop_remote("disconnect")
                    await self._stop_sending(reason="disconnect")
                    self.ui.set_status(self._status_text() + "\n连接中断，%s 秒后重试\n%s" % (backoff, exc))
                    await asyncio.sleep(backoff)
                    backoff = min(10, backoff * 2)
        finally:
            await self._stop_sending(reason="exit")
            try:
                self.restrictor.disable()
            except Exception:
                pass
            try:
                # 只停止检测线程，不解除桌面锁定（重启后仍保持）。
                self.desktop.stop()
            except Exception:
                pass
            self.ui.stop()


def parse_args(argv=None):
    default_data = os.environ.get("CLASSROOM_STUDENT_DATA")
    if not default_data:
        if os.name == "nt":
            base = os.environ.get("APPDATA") or str(Path.home())
            default_data = str(Path(base) / "GuoyiClassroom" / "student")
        else:
            default_data = str(ROOT / "student_data")
    parser = argparse.ArgumentParser(description="乐昌国艺书院 机房课堂管理 - 学生端")
    parser.add_argument("--server", default="", help="教师机 IP，如 192.168.1.10")
    parser.add_argument("--port", type=int, default=server_config.PORT)
    parser.add_argument("--name", default="", help="学生姓名或机位号")
    parser.add_argument("--code", default="", help="课堂加入码（有码可自动加入）")
    parser.add_argument("--discover", action="store_true", help="UDP 自动发现教师机")
    parser.add_argument("--sim", action="store_true", help="强制使用模拟画面（Linux 验证用）")
    parser.add_argument("--no-ui", action="store_true", help="不创建图形窗口，只打印状态")
    parser.add_argument("--event-log", default="", help="将事件写入 JSONL，供测试检查")
    parser.add_argument("--data-dir", default=default_data)
    parser.add_argument("--config-ui", action="store_true", help="启动前弹出连接设置窗口（Windows）")
    return parser.parse_args(argv)


def resolve_connection(args):
    data_dir = Path(args.data_dir)
    saved = load_saved_config(data_dir)
    if not args.server:
        args.server = saved.get("server") or ""
    if not args.name:
        args.name = saved.get("name") or ""
    if not args.code:
        args.code = saved.get("code") or ""
    if not args.port:
        args.port = saved.get("port") or server_config.PORT

    want_ui = args.config_ui or (sys.platform == "win32" and not args.no_ui and (not args.server or not args.name))
    if want_ui and sys.platform == "win32" and not args.no_ui:
        try:
            from student.win_config import ask_connection
            result = ask_connection(
                server=args.server,
                port=args.port,
                name=args.name,
                code=args.code,
            )
            if not result:
                return False
            args.server, args.port, args.name, args.code = result
        except Exception as exc:
            print("无法打开设置窗口：%s" % exc, flush=True)

    if args.discover or not args.server:
        found = discover_teacher()
        if found:
            args.server, args.port = found
            print("已发现教师机 %s:%s" % (args.server, args.port), flush=True)

    if not args.server:
        print("未找到教师机。请用 --server 填写教师机 IP，或在同一 WiFi 下使用 --discover。", flush=True)
        return False
    if not args.name:
        args.name = socket.gethostname()
    save_config(data_dir, {
        "server": args.server,
        "port": args.port,
        "name": args.name,
        "code": args.code,
    })
    return True


def main(argv=None):
    args = parse_args(argv)
    if not resolve_connection(args):
        sys.exit(2)
    client = StudentClient(args)
    import atexit
    atexit.register(client.restrictor.disable)
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("已退出", flush=True)
    finally:
        try:
            client.restrictor.disable()
        except Exception:
            pass


if __name__ == "__main__":
    main()
