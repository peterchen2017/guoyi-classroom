# -*- coding: utf-8 -*-
"""检查 Windows 安装依赖已去掉 pydantic-core，并验证启动器失败时能写日志。"""

from __future__ import print_function

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def _pin(text, name):
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or not s:
            continue
        if s.split("==")[0].strip().lower() == name.lower():
            return s.split("==", 1)[1].strip()
    return None


def main():
    c = Checker()
    req = (ROOT / "requirements-py38.txt").read_text(encoding="utf-8")
    pins = []
    for line in req.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        pins.append(s.lower())
    pin_text = "\n".join(pins)
    c.check("requirements-py38 不含 pydantic-core", "pydantic-core" not in pin_text and "pydantic_core" not in pin_text)
    ver = _pin(req, "pydantic")
    c.check("pydantic 锁定为 1.x", bool(ver) and ver.startswith("1."), ver or "未找到")
    fa = _pin(req, "fastapi")
    c.check("FastAPI 锁定为 0.99.x（不依赖 pydantic-core）", bool(fa) and fa.startswith("0.99."), fa or "未找到")
    c.check("显式包含 exceptiongroup（Python 3.8 需要，避免在 3.13 构建机上漏下）", _pin(req, "exceptiongroup") is not None)

    # 启动器失败日志（不启动真实服务）
    import launch_teacher
    import launch_student

    for label, mod, needle in (
        ("教师机", launch_teacher, "GuoyiClassroom\\Teacher"),
        ("学生机", launch_student, "GuoyiClassroom\\Student"),
    ):
        td = tempfile.mkdtemp(prefix="guoyi-launch-")
        logp = Path(td) / ("start_%s.log" % ("teacher" if "教师" in label else "student"))
        os.environ["CLASSROOM_LAUNCH_LOG"] = str(logp)
        try:
            try:
                raise RuntimeError("模拟 %s 导入失败" % label)
            except RuntimeError:
                if hasattr(mod, "report_failure"):
                    mod.report_failure("%s启动失败" % label)
        finally:
            os.environ.pop("CLASSROOM_LAUNCH_LOG", None)
        raw = logp.read_bytes() if logp.is_file() else b""
        text = raw.decode("utf-8-sig", "replace") if raw else ""
        c.check("%s 失败日志存在" % label, logp.is_file() and logp.stat().st_size > 0, str(logp))
        c.check("%s 日志含 UTF-8 BOM，记事本可打开" % label, raw.startswith(bytes([0xEF, 0xBB, 0xBF])))
        c.check("%s 日志含 traceback" % label, "RuntimeError" in text and "模拟" in text)
        c.check("%s 日志写出默认安装目录提示" % label, "GuoyiClassroom" in text)

    # 源码侧不应再直接引用 pydantic_core
    hits = []
    for folder in ("server", "student", "shared", "teacher", "launch_teacher.py", "launch_student.py"):
        path = ROOT / folder
        files = [path] if path.is_file() else list(path.rglob("*.py"))
        for f in files:
            if "__pycache__" in str(f):
                continue
            body = f.read_text(encoding="utf-8", errors="replace")
            if re.search(r"pydantic_core|pydantic-core", body):
                hits.append(str(f.relative_to(ROOT)))
    c.check("应用源码不引用 pydantic_core", not hits, ", ".join(hits))

    from shared.version import VERSION
    from server import config as server_config
    import launch_teacher
    import launch_student

    c.check("应用版本为 1.2.4", VERSION == "1.2.4", VERSION)
    c.check("server.config.VERSION 与 shared.version 一致", server_config.VERSION == VERSION)

    # 启动日志写明 VERSION，便于从日志判断是否跑到新版
    for label, mod in (("教师机", launch_teacher), ("学生机", launch_student)):
        td = tempfile.mkdtemp(prefix="guoyi-ver-")
        logp = Path(td) / "start.log"
        os.environ["CLASSROOM_LAUNCH_LOG"] = str(logp)
        try:
            with launch_teacher.open_log(append=False) if False else open(str(logp), "w", encoding="utf-8") as fp:
                pass
            with mod.open_log(append=False) as fp:
                mod.write_header(fp)
        finally:
            os.environ.pop("CLASSROOM_LAUNCH_LOG", None)
        text = logp.read_text(encoding="utf-8-sig") if logp.is_file() else ""
        c.check("%s 启动日志含 VERSION=%s" % (label, VERSION), ("VERSION=%s" % VERSION) in text, text[:200].replace("\n", " / "))

    # 1.2.1 的 launch_teacher.py 里 main() 约在第 29 行；新版应远在其后
    src = (ROOT / "launch_teacher.py").read_text(encoding="utf-8").splitlines()
    main_lines = [i + 1 for i, line in enumerate(src) if line.startswith("def main(")]
    c.check("launch_teacher.py 的 main() 不在旧版行号附近", bool(main_lines) and min(main_lines) >= 100, str(main_lines))

    teacher_nsi = (ROOT / "packaging" / "teacher.nsi").read_text(encoding="utf-8")
    student_nsi = (ROOT / "packaging" / "student.nsi").read_text(encoding="utf-8")
    cleanup = (ROOT / "packaging" / "upgrade-cleanup.nsh").read_text(encoding="utf-8")
    c.check("存在升级清理脚本 upgrade-cleanup.nsh", (ROOT / "packaging" / "upgrade-cleanup.nsh").is_file())
    for role, nsi in (("教师机", teacher_nsi), ("学生机", student_nsi)):
        c.check("%s NSIS 安装前调用升级清理" % role, "!insertmacro GuoyiCleanupOldProgramFiles" in nsi and nsi.find("!insertmacro GuoyiCleanupOldProgramFiles") < nsi.find("File /r"))
        c.check("%s NSIS 版本为 1.2.4" % role, '!define APP_VERSION "1.2.4"' in nsi and "${APP_VERSION}" in nsi)
    c.check("升级清理会删除旧 launch 脚本", "launch_teacher.py" in cleanup and "launch_student.py" in cleanup and "start_teacher.cmd" in cleanup)
    c.check("升级清理会移除整棵内置 Python/site-packages", 'RMDir /r "$INSTDIR\\python"' in cleanup)
    c.check("升级清理说明保留日志和 data", "data" in cleanup and "*.log" in cleanup)

    guide = (ROOT / "乐昌国艺书院-机房课堂管理-使用说明.txt").read_text(encoding="utf-8")
    c.check("使用说明提示升级前可先卸载旧版", "升级前可先卸载旧版" in guide or "建议先卸载旧版再安装本版" in guide)
    c.check("使用说明提示旧行号/_pydantic_core 仍是旧程序", "_pydantic_core" in guide and "30 行" in guide)


    build_src = (ROOT / "scripts" / "build_windows_installers.py").read_text(encoding="utf-8")
    c.check("安装包会复制 teacher/ 目录", '"teacher"' in build_src and "APP_DIRS" in build_src)
    c.check("绿色版教师机保留 teacher/", 'keep_dirs += ["server", "web", "teacher"]' in build_src)
    c.check("升级清理会删除旧 teacher 目录", 'RMDir /r "$INSTDIR\\teacher"' in cleanup)

    launch_src = (ROOT / "launch_teacher.py").read_text(encoding="utf-8")
    c.check("教师机启动后打开原生主窗口", "run_main_window" in launch_src and "teacher.win_console" in launch_src)
    c.check("默认不再自动打开浏览器", "_open_when_ready" not in launch_src)
    c.check("使用说明以软件主窗口为主", "教师主窗口" in guide and "不必预先安装 Chrome" in guide)
    c.check("使用说明版本写 1.2.4", "1.2.4" in guide)

    if not c.summary():
        sys.exit(1)


if __name__ == "__main__":
    main()
