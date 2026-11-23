# -*- coding: utf-8 -*-
"""教师机启动器：启动课堂服务、写启动日志，并打开本机控制台。"""

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


def start_running_indicator(url):
    """控制台标题 + 一个很小的常驻窗口，避免只剩浏览器时被误以为没启动。"""
    set_console_title("课堂管理运行中 - 乐昌国艺书院教师机")
    if sys.platform != "win32":
        return

    def _run():
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            IS_64 = ctypes.sizeof(ctypes.c_void_p) == 8
            WNDPROCTYPE = ctypes.WINFUNCTYPE(
                ctypes.c_longlong if IS_64 else ctypes.c_long,
                wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            )

            class WNDCLASSW(ctypes.Structure):
                _fields_ = [
                    ("style", wintypes.UINT),
                    ("lpfnWndProc", WNDPROCTYPE),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HCURSOR),
                    ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR),
                ]

            class PAINTSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("hdc", wintypes.HDC),
                    ("fErase", wintypes.BOOL),
                    ("rcPaint", wintypes.RECT),
                    ("fRestore", wintypes.BOOL),
                    ("fIncUpdate", wintypes.BOOL),
                    ("rgbReserved", wintypes.BYTE * 32),
                ]

            WM_DESTROY = 0x0002
            WM_CLOSE = 0x0010
            WM_PAINT = 0x000F
            WM_COMMAND = 0x0111
            WS_OVERLAPPED = 0x00000000
            WS_CAPTION = 0x00C00000
            WS_SYSMENU = 0x00080000
            WS_MINIMIZEBOX = 0x00020000
            WS_VISIBLE = 0x10000000
            ID_OPEN = 1001
            class_name = "GuoyiTeacherStatus"
            lines = [
                "课堂管理运行中",
                "乐昌国艺书院  教师机",
                url,
                "关闭本窗口不会退出课堂管理。",
                "请关闭黑色控制台窗口来退出。",
            ]

            def _proc(hwnd, msg, wparam, lparam):
                if msg == WM_PAINT:
                    ps = PAINTSTRUCT()
                    hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
                    rect = wintypes.RECT(12, 10, 420, 150)
                    text = "\r\n".join(lines)
                    user32.DrawTextW(hdc, text, -1, ctypes.byref(rect), 0x00000010)
                    user32.EndPaint(hwnd, ctypes.byref(ps))
                    return 0
                if msg == WM_COMMAND and (wparam & 0xFFFF) == ID_OPEN:
                    open_browser(url)
                    return 0
                if msg == WM_CLOSE:
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            wndproc = WNDPROCTYPE(_proc)
            wc = WNDCLASSW()
            wc.lpfnWndProc = wndproc
            wc.hInstance = kernel32.GetModuleHandleW(None)
            wc.hbrBackground = 5 + 1
            wc.lpszClassName = class_name
            wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
            if not user32.RegisterClassW(ctypes.byref(wc)):
                # 重复注册时仍可继续创建窗口
                pass
            style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_VISIBLE
            hwnd = user32.CreateWindowExW(
                0, class_name, "课堂管理运行中", style,
                80, 80, 440, 220,
                None, None, wc.hInstance, None,
            )
            if not hwnd:
                return
            user32.CreateWindowExW(
                0, "BUTTON", "打开控制台", 0x50000000,
                140, 150, 140, 28,
                hwnd, ctypes.c_void_p(ID_OPEN), wc.hInstance, None,
            )
            user32.ShowWindow(hwnd, 1)
            user32.UpdateWindow(hwnd)
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            # 保持 wndproc 引用到循环结束，防止被回收
            _ = wndproc
        except Exception:
            return

    threading.Thread(target=_run, daemon=True).start()


def _open_when_ready(url, port):
    if wait_port("127.0.0.1", port, timeout=45):
        ok = open_browser(url)
        print("已打开浏览器：%s（成功=%s）" % (url, ok), flush=True)
    else:
        print("等待服务端口 %s 超时，仍尝试打开浏览器。" % port, flush=True)
        open_browser(url)


def main():
    from server import config
    url = "http://127.0.0.1:%s" % config.PORT
    set_console_title("课堂管理运行中 - 乐昌国艺书院教师机")
    start_running_indicator(url)
    threading.Thread(target=_open_when_ready, args=(url, config.PORT), daemon=True).start()
    from server.app import main as server_main
    server_main([])


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
