# -*- coding: utf-8 -*-
"""教师机启动器：启动课堂服务、写启动日志，并打开原生教师主窗口。"""

from __future__ import print_function

import datetime
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(str(ROOT))

from shared.version import VERSION, TEACHER_WINDOW_TITLE

LOG_NAME = "start_teacher.log"


def log_path():
    raw = os.environ.get("CLASSROOM_LAUNCH_LOG")
    if raw:
        return Path(raw)
    return ROOT / LOG_NAME


def open_log(append=True):
    """打开日志。使用 UTF-8 BOM，方便 Windows 记事本打开。"""
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.is_file() and path.stat().st_size > 0
    fp = open(str(path), "a" if append else "w", encoding="utf-8")
    if not existed:
        fp.write("\ufeff")
    return fp


class _Tee(object):
    def __init__(self, stream, log_fp):
        self._stream = stream
        self._log = log_fp

    def write(self, data):
        if data is None:
            return
        try:
            self._stream.write(data)
            self._stream.flush()
        except Exception:
            pass
        try:
            self._log.write(data)
            if not str(data).endswith("\n"):
                pass
            self._log.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass
        try:
            self._log.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return self._stream.isatty()
        except Exception:
            return False


def message_box(title, text, icon=0x10):
    """弹出中文错误框，避免窗口一闪就关。非 Windows 上只打印。"""
    if sys.platform != "win32":
        try:
            sys.stderr.write("%s\n%s\n" % (title, text))
        except Exception:
            pass
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), icon | 0x00040000)
    except Exception:
        pass


def set_console_title(title):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(str(title))
    except Exception:
        pass


def write_header(fp):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fp.write("===== %s 启动教师机 =====\n" % now)
    fp.write("VERSION=%s\n" % VERSION)
    fp.write("ROOT=%s\n" % ROOT)
    fp.write("python=%s\n" % sys.version.replace("\n", " "))
    fp.write("executable=%s\n" % sys.executable)
    fp.write("platform=%s\n" % sys.platform)
    try:
        fp.write("cwd=%s\n" % os.getcwd())
    except Exception:
        pass
    fp.flush()


def failure_text(prefix="教师机启动失败"):
    tb = traceback.format_exc()
    logp = str(log_path())
    detail = tb.strip() or "未知错误（无 traceback）。"
    return (
        "%s。\n\n"
        "请把下面的日志文件发给开发者（可用记事本打开）：\n"
        "%s\n\n"
        "默认安装目录：\n"
        "C:\\Users\\用户名\\AppData\\Local\\GuoyiClassroom\\Teacher\n\n"
        "错误信息：\n%s\n"
        % (prefix, logp, detail)
    )


def report_failure(prefix="教师机启动失败"):
    text = failure_text(prefix)
    try:
        with open_log(append=True) as fp:
            fp.write("\n----- 启动失败 -----\n")
            fp.write(text)
            if not text.endswith("\n"):
                fp.write("\n")
            fp.flush()
    except Exception:
        pass
    try:
        sys.stderr.write(text)
        sys.stderr.flush()
    except Exception:
        pass
    message_box("课堂管理启动失败", text, 0x10)


def wait_port(host, port, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(0.4)
            sock.connect((host, int(port)))
            return True
        except Exception:
            time.sleep(0.25)
        finally:
            try:
                sock.close()
            except Exception:
                pass
    return False


def open_browser(url):
    if sys.platform == "win32":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except Exception:
            pass
        try:
            import subprocess
            subprocess.Popen(["cmd.exe", "/c", "start", "", url], close_fds=True)
            return True
        except Exception:
            pass
    try:
        import webbrowser
        webbrowser.open(url)
        return True
    except Exception:
        return False



def start_uvicorn_thread(host, port):
    """在后台线程运行课堂服务，主线程用来跑原生窗口。"""
    import uvicorn
    from server.app import app, _print_banner

    class _Server(uvicorn.Server):
        def install_signal_handlers(self):
            pass

    cfg = uvicorn.Config(app, host=host, port=port, log_level="info", loop="asyncio")
    server = _Server(cfg)

    def _run():
        _print_banner()
        server.run()

    thread = threading.Thread(target=_run, name="classroom-teacher-http", daemon=True)
    thread.start()
    return server, thread


def shutdown_server(server, timeout=2):
    if server is None:
        return
    try:
        server.should_exit = True
    except Exception:
        pass
    time.sleep(min(0.4, timeout))


def main():
    from server import config
    url = "http://127.0.0.1:%s" % config.PORT
    set_console_title(TEACHER_WINDOW_TITLE)
    if sys.platform != "win32":
        # Linux 开发机没有 Win32 主窗口，只启动服务（测试通过 python -m server）。
        from server.app import main as server_main
        server_main([])
        return

    server, _thread = start_uvicorn_thread(config.HOST, config.PORT)
    if not wait_port("127.0.0.1", config.PORT, timeout=45):
        report_failure("教师机服务未能在 45 秒内就绪")
        shutdown_server(server)
        sys.exit(1)
    print("服务已就绪，正在打开教师主窗口（不必使用浏览器）…", flush=True)
    print("本机控制台备用地址：%s" % url, flush=True)
    try:
        from teacher.win_console import run_main_window
        run_main_window(
            url,
            open_browser_fn=open_browser,
            lan_ips=config.lan_ips(),
            port=config.PORT,
        )
    except Exception:
        report_failure("无法打开教师主窗口")
        shutdown_server(server)
        sys.exit(1)
    print("教师主窗口已关闭，正在退出。", flush=True)
    shutdown_server(server)
    os._exit(0)


def run():
    fp = None
    try:
        fp = open_log(append=True)
        write_header(fp)
        sys.stdout = _Tee(sys.__stdout__ or sys.stdout, fp)
        sys.stderr = _Tee(sys.__stderr__ or sys.stderr, fp)
        main()
    except SystemExit as exc:
        code = exc.code
        if code not in (0, None):
            report_failure("教师机启动失败（退出码 %s）" % code)
        if fp:
            try:
                fp.close()
            except Exception:
                pass
        raise
    except Exception:
        report_failure("教师机启动失败")
        if fp:
            try:
                fp.close()
            except Exception:
                pass
        sys.exit(1)
    if fp:
        try:
            fp.close()
        except Exception:
            pass


if __name__ == "__main__":
    run()
