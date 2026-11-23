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
    for folder in ("server", "student", "shared", "launch_teacher.py", "launch_student.py"):
        path = ROOT / folder
        files = [path] if path.is_file() else list(path.rglob("*.py"))
        for f in files:
            if "__pycache__" in str(f):
                continue
            body = f.read_text(encoding="utf-8", errors="replace")
            if re.search(r"pydantic_core|pydantic-core", body):
                hits.append(str(f.relative_to(ROOT)))
    c.check("应用源码不引用 pydantic_core", not hits, ", ".join(hits))

    if not c.summary():
        sys.exit(1)


if __name__ == "__main__":
    main()
