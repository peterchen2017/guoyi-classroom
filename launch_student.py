# -*- coding: utf-8 -*-
"""学生机启动器：显示连接设置并启动可见的课堂管理客户端。失败时写日志并弹窗。"""

from __future__ import print_function

import datetime
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(str(ROOT))

from shared.version import VERSION, STUDENT_WINDOW_TITLE

LOG_NAME = "start_student.log"


def log_path():
    raw = os.environ.get("CLASSROOM_LAUNCH_LOG")
    if raw:
        return Path(raw)
    return ROOT / LOG_NAME


def open_log(append=True):
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


def write_header(fp):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fp.write("===== %s 启动学生机 =====\n" % now)
    fp.write("VERSION=%s\n" % VERSION)
    fp.write("ROOT=%s\n" % ROOT)
    fp.write("python=%s\n" % sys.version.replace("\n", " "))
    fp.write("executable=%s\n" % sys.executable)
    fp.write("argv=%s\n" % " ".join(sys.argv))
    fp.flush()


def report_failure(prefix="学生机启动失败"):
    tb = traceback.format_exc()
    logp = str(log_path())
    detail = tb.strip() or "未知错误（无 traceback）。"
    text = (
        "%s。\n\n"
        "请把下面的日志文件发给开发者（可用记事本打开）：\n"
        "%s\n\n"
        "默认安装目录：\n"
        "C:\\Users\\用户名\\AppData\\Local\\GuoyiClassroom\\Student\n\n"
        "错误信息：\n%s\n"
        % (prefix, logp, detail)
    )
    try:
        with open_log(append=True) as fp:
            fp.write("\n----- 启动失败 -----\n")
            fp.write(text)
            fp.flush()
    except Exception:
        pass
    try:
        sys.stderr.write(text)
        sys.stderr.flush()
    except Exception:
        pass
    message_box("课堂管理启动失败", text, 0x10)


def main():
    from student.client import main as student_main
    student_main(list(sys.argv[1:]))


def run():
    fp = None
    try:
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleTitleW(STUDENT_WINDOW_TITLE)
            except Exception:
                pass
        fp = open_log(append=True)
        write_header(fp)
        sys.stdout = _Tee(sys.__stdout__ or sys.stdout, fp)
        sys.stderr = _Tee(sys.__stderr__ or sys.stderr, fp)
        main()
    except SystemExit as exc:
        code = exc.code
        if code not in (0, None):
            report_failure("学生机启动失败（退出码 %s）" % code)
        if fp:
            try:
                fp.close()
            except Exception:
                pass
        raise
    except Exception:
        report_failure("学生机启动失败")
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
