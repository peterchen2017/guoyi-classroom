# -*- coding: utf-8 -*-
"""准备并编译 Windows 7 SP1–11 安装包（NSIS）与免安装绿色版 zip。

会下载官方 Python 3.8.10 嵌入式发行版、Windows 轮子，以及微软官方的
VC++ 2015–2022 运行库和 Universal CRT 可再发行 DLL，打进 setup.exe / 绿色版，
老师安装后无需再单独安装 Python，也无需先打 KB2999226。

官方来源：
- https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-*.zip
- https://aka.ms/vs/17/release/vc_redist.x64.exe （及 x86）
- Visual Studio 频道清单中的 Microsoft.Windows.UniversalCRT.Redistributable.Msi
"""

from __future__ import print_function

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from shared.version import VERSION, TEACHER_WINDOW_TITLE, STUDENT_WINDOW_TITLE

PACK = ROOT / "packaging"
DIST = ROOT / "dist"
CACHE = PACK / "cache"
REDIST = CACHE / "redist"
UNPACKED = REDIST / "unpacked"

PY_VERSION = "3.8.10"
PY_URLS = {
    "amd64": "https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip",
    "win32": "https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-win32.zip",
}
PLAT_TAG = {"amd64": "win_amd64", "win32": "win32"}
VC_REDIST_URLS = {
    "amd64": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
    "win32": "https://aka.ms/vs/17/release/vc_redist.x86.exe",
}
VS_CHANNEL = "https://aka.ms/vs/17/release/channel"

RUNTIME_REQ = PACK / "runtime-py38.txt"

APP_FILES = [
    "launch_teacher.py",
    "launch_student.py",
    "requirements-py38.txt",
    "README.md",
    "乐昌国艺书院-机房课堂管理-使用说明.txt",
]
APP_DIRS = ["server", "student", "shared", "web", "teacher"]

TEACHER_KEEP = [
    "launch_teacher.py",
    "start_teacher.cmd",
    "README.md",
    "乐昌国艺书院-机房课堂管理-使用说明.txt",
    "打开说明.txt",
]
STUDENT_KEEP = [
    "launch_student.py",
    "start_student.cmd",
    "start_student_autostart.cmd",
    "更改连接设置.cmd",
    "README.md",
    "乐昌国艺书院-机房课堂管理-使用说明.txt",
    "打开说明.txt",
]


def log(msg):
    print(msg, flush=True)


def download(url, dest, sha256=None, min_size=10000):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= min_size:
        if sha256:
            got = hashlib.sha256(dest.read_bytes()).hexdigest()
            if got.lower() == sha256.lower():
                log("已缓存：%s" % dest.name)
                return dest
        else:
            log("已缓存：%s" % dest.name)
            return dest
    log("下载 %s ..." % url)
    req = Request(url, headers={"User-Agent": "GuoyiClassroomBuilder/%s" % VERSION})
    with urlopen(req, timeout=180) as resp:
        data = resp.read()
    if sha256:
        got = hashlib.sha256(data).hexdigest()
        if got.lower() != sha256.lower():
            raise RuntimeError("校验失败 %s：got %s" % (dest.name, got))
    dest.write_bytes(data)
    log("  保存 %s (%s 字节)" % (dest, len(data)))
    return dest


def write_runtime_req():
    lines = []
    for line in (ROOT / "requirements-py38.txt").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        name = s.split("==")[0].split(">=")[0].lower()
        if name in ("httpx", "httpcore", "certifi"):
            continue
        lines.append(s)
    RUNTIME_REQ.write_text("\n".join(lines) + "\n", encoding="utf-8")


def download_wheels(arch):
    wheel_dir = CACHE / ("wheels-" + arch)
    if wheel_dir.exists():
        shutil.rmtree(wheel_dir)
    wheel_dir.mkdir(parents=True)
    cmd = [
        sys.executable, "-m", "pip", "download",
        "-r", str(RUNTIME_REQ),
        "-d", str(wheel_dir),
        "--python-version", "38",
        "--platform", PLAT_TAG[arch],
        "--only-binary=:all:",
        "--abi", "cp38",
        "--implementation", "cp",
    ]
    log("下载 %s 轮子：%s" % (arch, " ".join(cmd)))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        cmd2 = [
            sys.executable, "-m", "pip", "download",
            "-r", str(RUNTIME_REQ),
            "-d", str(wheel_dir),
            "--python-version", "38",
            "--platform", PLAT_TAG[arch],
            "--only-binary=:all:",
        ]
        log("重试不加 abi ...")
        r = subprocess.run(cmd2)
    if r.returncode != 0:
        raise RuntimeError("无法下载 %s 的 Windows 轮子，请检查网络。" % arch)
    return wheel_dir



def ensure_win7_safe_wheels(wheel_dir):
    """去掉 pydantic-core，并改用 pydantic v1 的纯 Python 轮子。

    Win7 教师机 1.2.1 的失败原因是：
    ImportError: DLL load failed while importing _pydantic_core: 找不到指定的程序
    （WinError 127 ERROR_PROC_NOT_FOUND）。_pydantic_core 由较新的 Rust/MSVC 工具链
    编译，能被加载但缺少 Win7 上的导出函数。教师机与学生机共用同一套 site-packages。
    """
    wheel_dir = Path(wheel_dir)
    for p in list(wheel_dir.glob("pydantic_core-*.whl")) + list(wheel_dir.glob("pydantic-core-*.whl")):
        log("已移除 Win7 不兼容的轮子：%s" % p.name)
        p.unlink()
    native = []
    has_pure = False
    for p in wheel_dir.glob("pydantic-*.whl"):
        if p.name.startswith("pydantic_core"):
            continue
        if "py3-none-any" in p.name:
            has_pure = True
        else:
            native.append(p)
    for p in native:
        log("已移除带原生扩展的 pydantic 轮子：%s" % p.name)
        p.unlink()
    if not has_pure:
        cmd = [
            sys.executable, "-m", "pip", "download", "pydantic==1.10.18",
            "--only-binary=:all:",
            "--no-deps",
            "-d", str(wheel_dir),
            "--python-version", "38",
            "--abi", "none",
            "--platform", "any",
        ]
        log("下载 pydantic 1.10.18 纯 Python 轮子：%s" % " ".join(cmd))
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise RuntimeError("无法下载 pydantic-1.10.18-py3-none-any.whl")
        # 若仍下到了带扩展的轮子，再清一次
        for p in list(wheel_dir.glob("pydantic-*.whl")):
            if p.name.startswith("pydantic_core"):
                p.unlink()
                continue
            if "py3-none-any" not in p.name:
                p.unlink()
        if not any("py3-none-any" in p.name and p.name.startswith("pydantic-1.") for p in wheel_dir.glob("pydantic-*.whl")):
            raise RuntimeError("缺少 pydantic 1.x 纯 Python 轮子")
    missing = []
    if not any(wheel_dir.glob("exceptiongroup-*.whl")):
        missing.append("exceptiongroup==1.2.2")
    if missing:
        cmd = [
            sys.executable, "-m", "pip", "download",
            *missing,
            "--only-binary=:all:",
            "-d", str(wheel_dir),
            "--python-version", "38",
        ]
        log("补下 Python 3.8 需要的纯 Python 依赖：%s" % " ".join(missing))
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise RuntimeError("无法下载：%s" % ", ".join(missing))


def assert_no_pydantic_core(site):
    site = Path(site)
    hits = [p for p in site.rglob("*") if "pydantic_core" in p.name.lower() or "pydantic-core" in p.name.lower()]
    if hits:
        raise RuntimeError("site-packages 中不得包含 pydantic_core：%s" % ", ".join(str(p.relative_to(site)) for p in hits[:8]))
    ver = None
    for cand in (site / "pydantic" / "version.py", site / "pydantic" / "__init__.py"):
        if cand.is_file():
            for line in cand.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith("VERSION") or line.strip().startswith("__version__"):
                    ver = line
                    break
        if ver:
            break
    log("已确认无 pydantic_core；pydantic 版本信息：%s" % (ver or "未读取到"))
    if ver and ("2." in ver and "1.10" not in ver):
        raise RuntimeError("期望打包 Pydantic v1，实际：%s" % ver)


def unpack_wheels(wheel_dir, site):
    site.mkdir(parents=True, exist_ok=True)
    for whl in sorted(wheel_dir.glob("*.whl")):
        log("  解包 %s" % whl.name)
        with zipfile.ZipFile(whl) as zf:
            zf.extractall(site)


def extract_python(arch, dest_python):
    url = PY_URLS[arch]
    zpath = CACHE / Path(url).name
    if not download(url, zpath):
        raise RuntimeError("无法下载嵌入式 Python 3.8.10（%s）" % arch)
    if dest_python.exists():
        shutil.rmtree(dest_python)
    dest_python.mkdir(parents=True)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest_python)
    pth = list(dest_python.glob("python*._pth"))
    if not pth:
        raise RuntimeError("嵌入式 Python 中没有 ._pth 文件")
    pth[0].write_text("python38.zip\n.\nLib\\site-packages\nimport site\n", encoding="utf-8")
    return dest_python


def _which(name):
    return shutil.which(name)


def _cabextract(cab, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    exe = _which("cabextract") or _which("7z")
    if not exe:
        raise RuntimeError("需要 cabextract 或 7z 来解开运行库安装包")
    if Path(exe).name.startswith("cabextract"):
        r = subprocess.run([exe, "-d", str(dest), str(cab)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    else:
        r = subprocess.run([exe, "x", "-y", "-o%s" % dest, str(cab)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise RuntimeError("解开 %s 失败：%s" % (cab, r.stdout.decode("utf-8", "replace")[-400:]))


def _extract_burn_payloads(bundle_exe, dest):
    """从 WiX Burn 的 vc_redist.exe 中取出附属 CAB，并按清单还原文件名。"""
    data = Path(bundle_exe).read_bytes()
    first = data.find(b"MSCF")
    if first < 0:
        raise RuntimeError("vc_redist 中找不到 CAB 标记：%s" % bundle_exe)
    ux = dest / "_ux.cab"
    ux.write_bytes(data[first:])
    uxdir = dest / "_ux"
    _cabextract(ux, uxdir)
    manifest = None
    for p in uxdir.iterdir():
        raw = p.read_bytes()
        if b"BurnManifest" in raw[:2000] or b"vcRuntimeMinimum" in raw:
            manifest = raw
            break
    if not manifest:
        raise RuntimeError("vc_redist 中找不到 Burn 清单")
    text = manifest.decode("utf-8-sig", "replace")
    text = text.replace('xmlns="http://schemas.microsoft.com/wix/2008/Burn"', "")
    root = ET.fromstring(text)

    second = data.find(b"MSCF", first + 4)
    if second < 0:
        raise RuntimeError("vc_redist 中找不到附属容器")
    container = dest / "_attached.cab"
    container.write_bytes(data[second:])
    contdir = dest / "_attached"
    _cabextract(container, contdir)

    mapping = {}
    for el in root.findall(".//Payload"):
        src = el.attrib.get("SourcePath") or ""
        name = el.attrib.get("FilePath") or ""
        if src and name:
            mapping[src] = name.replace("\\", "/")

    out = dest / "payloads"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for src, rel in mapping.items():
        srcp = contdir / src
        if not srcp.is_file():
            srcp = uxdir / src
        if not srcp.is_file():
            continue
        destp = out / rel
        destp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(srcp, destp)
    return out


def _find_ucrt_payloads():
    """从官方 VS 频道清单定位 Universal CRT Redistributable MSI 与 CAB。"""
    log("查询官方 Universal CRT 可再发行包地址…")
    raw = urlopen(Request(VS_CHANNEL, headers={"User-Agent": "GuoyiClassroomBuilder/%s" % VERSION}), timeout=120).read()
    channel = json.loads(raw)
    vsman_url = None
    for item in channel.get("channelItems") or []:
        for pl in item.get("payloads") or []:
            fn = (pl.get("fileName") or "")
            if fn.endswith(".vsman") or "VisualStudio.vsman" in fn:
                vsman_url = pl.get("url")
                break
        if vsman_url:
            break
    if not vsman_url:
        raise RuntimeError("无法在 VS 频道清单中找到 vsman")
    man = json.loads(urlopen(Request(vsman_url, headers={"User-Agent": "GuoyiClassroomBuilder/%s" % VERSION}), timeout=180).read())
    for pkg in man.get("packages") or []:
        if pkg.get("id") == "Microsoft.Windows.UniversalCRT.Redistributable.Msi":
            files = []
            for pl in pkg.get("payloads") or []:
                files.append({
                    "name": Path(pl["fileName"]).name,
                    "url": pl["url"],
                    "sha256": pl.get("sha256"),
                    "size": pl.get("size") or 0,
                })
            if files:
                return files
    raise RuntimeError("频道清单中没有 Microsoft.Windows.UniversalCRT.Redistributable.Msi")


def ensure_win_runtimes():
    """下载并解开官方 VC 运行库与 UCRT，缓存到 packaging/cache/redist/unpacked。"""
    UNPACKED.mkdir(parents=True, exist_ok=True)
    for arch, url in VC_REDIST_URLS.items():
        marker = UNPACKED / ("vcmin-%s" % arch)
        need = (not marker.exists()) or (not any(marker.glob("msvcp140*.dll")))
        if not need:
            log("已缓存 VC 运行库 DLL：%s" % marker)
            continue
        exe_name = "vc_redist.x64.exe" if arch == "amd64" else "vc_redist.x86.exe"
        bundle = download(url, REDIST / exe_name, min_size=1000000)
        work = Path(tempfile.mkdtemp(prefix="vcredist-%s-" % arch))
        try:
            payloads = _extract_burn_payloads(bundle, work)
            cabs = list(payloads.glob("**/vcRuntimeMinimum_*/cab1.cab"))
            if not cabs:
                cabs = [p for p in payloads.rglob("*.cab") if "RuntimeMinimum" in str(p) or "runtimeMinimum" in str(p)]
            if not cabs:
                raise RuntimeError("未在 vc_redist（%s）中找到 vcRuntimeMinimum cab" % arch)
            rawdir = work / "mincab"
            _cabextract(cabs[0], rawdir)
            if marker.exists():
                shutil.rmtree(marker)
            marker.mkdir(parents=True)
            for src in rawdir.iterdir():
                if not src.is_file():
                    continue
                name = src.name
                # cab 内为 msvcp140.dll_amd64 / msvcp140.dll_x86
                if ".dll_" in name:
                    name = name.split(".dll_", 1)[0] + ".dll"
                if not name.lower().endswith(".dll"):
                    continue
                shutil.copy2(src, marker / name)
            log("已展开 VC 运行库 %s：%s 个 DLL" % (arch, len(list(marker.glob("*.dll")))))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    ucrt_x64 = UNPACKED / "ucrt-amd64"
    ucrt_x86 = UNPACKED / "ucrt-win32"
    if (ucrt_x64 / "ucrtbase.dll").is_file() and (ucrt_x86 / "ucrtbase.dll").is_file():
        log("已缓存 UCRT 可再发行 DLL")
        return
    files = _find_ucrt_payloads()
    msi_dir = REDIST / "ucrt-msi"
    msi_dir.mkdir(parents=True, exist_ok=True)
    msi_path = None
    for item in files:
        min_size = 1000 if item["name"].endswith(".msi") else 10000
        dest = download(item["url"], msi_dir / item["name"], sha256=item.get("sha256"), min_size=min_size)
        if item["name"].lower().endswith(".msi"):
            msi_path = dest
    if not msi_path:
        raise RuntimeError("未下载到 Universal CRT Redistributable MSI")
    msiextract = _which("msiextract")
    if not msiextract:
        raise RuntimeError("需要 msitools 的 msiextract 来解开 Universal CRT MSI")
    work = Path(tempfile.mkdtemp(prefix="ucrt-msi-"))
    try:
        for src in msi_dir.iterdir():
            shutil.copy2(src, work / src.name)
        r = subprocess.run(
            [msiextract, msi_path.name],
            cwd=str(work),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if r.returncode != 0:
            raise RuntimeError("msiextract 失败：%s" % r.stdout.decode("utf-8", "replace")[-400:])
        found = list(work.rglob("Redist/ucrt/DLLs"))
        if not found:
            found = list(work.rglob("ucrt/DLLs"))
        if not found:
            raise RuntimeError("MSI 中没有 Redist/ucrt/DLLs")
        root_dlls = found[0]
        for src_arch, dest_dir in (("x64", ucrt_x64), ("x86", ucrt_x86)):
            src = root_dlls / src_arch
            if not src.is_dir():
                raise RuntimeError("UCRT 缺少 %s 目录" % src_arch)
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            dest_dir.mkdir(parents=True)
            for dll in src.glob("*.dll"):
                shutil.copy2(dll, dest_dir / dll.name)
            if not (dest_dir / "ucrtbase.dll").is_file():
                raise RuntimeError("UCRT %s 缺少 ucrtbase.dll" % src_arch)
            log("已展开 UCRT %s：%s 个 DLL" % (src_arch, len(list(dest_dir.glob("*.dll")))))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def bundle_win_runtimes(arch, dest_python):
    """把官方 UCRT 与 VC 运行库 DLL 复制到嵌入式 Python 目录（与 python.exe 同级）。"""
    dest_python = Path(dest_python)
    dest_python.mkdir(parents=True, exist_ok=True)
    copied = 0
    for folder in (UNPACKED / ("ucrt-%s" % arch), UNPACKED / ("vcmin-%s" % arch)):
        if not folder.is_dir():
            raise RuntimeError("缺少运行库缓存：%s" % folder)
        for dll in folder.glob("*.dll"):
            shutil.copy2(dll, dest_python / dll.name)
            copied += 1
    must = ["ucrtbase.dll", "api-ms-win-crt-runtime-l1-1-0.dll", "msvcp140.dll", "vcruntime140.dll"]
    missing = [n for n in must if not (dest_python / n).is_file()]
    if missing:
        raise RuntimeError("运行库不完整，缺少：%s" % ", ".join(missing))
    log("已向 %s 写入 %s 个运行库 DLL" % (dest_python, copied))


def write_cmd(path, lines):
    """用 GBK 写 .cmd，避免 Win7 上 chcp 65001 导致乱码或失败。"""
    text = "\r\n".join(lines) + "\r\n"
    Path(path).write_bytes(text.encode("gbk"))


def fail_help_lines(log_name):
    return [
        "echo.",
        "echo 启动失败。请打开下面的日志文件（记事本即可），并把它发给开发者：",
        "echo %LOG%",
        "echo.",
        "echo 请同时逐条检查：",
        "echo 1. 打开“计算机”右键 - 属性，查看“系统类型”。",
        "echo    32 位操作系统必须用 x86 软件包，不要用 64 位（x64）包。",
        "echo 2. 教师机默认安装目录：",
        "echo    C:\\Users\\用户名\\AppData\\Local\\GuoyiClassroom\\Teacher",
        "echo    学生机默认安装目录：",
        "echo    C:\\Users\\用户名\\AppData\\Local\\GuoyiClassroom\\Student",
        "echo 3. 本软件需要 Windows 7 SP1 或更高版本（也支持 Windows 8.1 / 10 / 11）。",
        "echo 4. 请把绿色版解压到较短路径后再试，例如 C:\\GuoyiTeacher 或 C:\\GuoyiStudent。",
        "echo.",
        "pause",
    ]


def write_launch_scripts(dest, arch_label):
    dest = Path(dest)
    teacher_head = [
        "@echo off",
        "setlocal",
        "cd /d \"%~dp0\"",
        "rem Win7 上 chcp 65001 可能失败，这里只用系统中文代码页，失败也不退出",
        "chcp 936 >nul 2>&1",
        "set \"LOG=%~dp0start_teacher.log\"",
        "title " + TEACHER_WINDOW_TITLE,
        "echo.>>\"%LOG%\"",
        "echo ===== %date% %time% 启动教师机 =====>>\"%LOG%\"",
        "echo VERSION=" + VERSION + ">>\"%LOG%\"",
        "echo INSTDIR=%CD%>>\"%LOG%\"",
        "echo ========================================",
        "echo  乐昌国艺书院  机房课堂管理（教师机） " + VERSION,
        "echo  " + TEACHER_WINDOW_TITLE,
        "echo  版权所有  乐昌国艺书院    开发者：陈老师",
        "echo ========================================",
        "echo.",
        "echo 日志文件：%LOG%",
        "echo.",
        "if not exist \"%~dp0python\\python.exe\" (",
        "  echo [错误] 未找到内置 Python。请确认已完整安装，或完整解压绿色版。",
        "  echo [错误] 未找到内置 Python。>>\"%LOG%\"",
        "  goto :fail",
        ")",
        "echo 正在检测 python.exe ...>>\"%LOG%\"",
        "\"%~dp0python\\python.exe\" -c \"import sys; print(sys.version)\" >>\"%LOG%\" 2>&1",
        "if errorlevel 1 (",
        "  echo [错误] python.exe 无法启动。可能是运行库无法加载，或 32/64 位软件包选错。>>\"%LOG%\"",
        "  echo [错误] python.exe 无法启动。可能是运行库无法加载，或 32/64 位软件包选错。",
        "  goto :fail",
        ")",
        "echo 正在启动课堂服务 ...>>\"%LOG%\"",
        "rem 主程序自己把输出写入 start_teacher.log，这里不重定向，以便黑窗口仍显示本机地址",
        "\"%~dp0python\\python.exe\" launch_teacher.py",
        "set ERR=%ERRORLEVEL%",
        "if not \"%ERR%\"==\"0\" (",
        "  echo [错误] launch_teacher.py 退出码 %ERR%>>\"%LOG%\"",
        "  goto :fail",
        ")",
        "goto :eof",
        ":fail",
    ]
    write_cmd(dest / "start_teacher.cmd", teacher_head + fail_help_lines("start_teacher.log"))

    student_head = [
        "@echo off",
        "setlocal",
        "cd /d \"%~dp0\"",
        "chcp 936 >nul 2>&1",
        "set \"LOG=%~dp0start_student.log\"",
        "title " + STUDENT_WINDOW_TITLE,
        "echo.>>\"%LOG%\"",
        "echo ===== %date% %time% 启动学生机 =====>>\"%LOG%\"",
        "echo VERSION=" + VERSION + ">>\"%LOG%\"",
        "echo INSTDIR=%CD%>>\"%LOG%\"",
        "echo ========================================",
        "echo  乐昌国艺书院  机房课堂管理（学生机） " + VERSION,
        "echo  " + STUDENT_WINDOW_TITLE,
        "echo  版权所有  乐昌国艺书院    开发者：陈老师",
        "echo ========================================",
        "echo.",
        "if not exist \"%~dp0python\\python.exe\" (",
        "  echo [错误] 未找到内置 Python。请确认已完整安装，或完整解压绿色版。",
        "  echo [错误] 未找到内置 Python。>>\"%LOG%\"",
        "  goto :fail",
        ")",
        "echo 正在检测 python.exe ...>>\"%LOG%\"",
        "\"%~dp0python\\python.exe\" -c \"import sys; print(sys.version)\" >>\"%LOG%\" 2>&1",
        "if errorlevel 1 (",
        "  echo [错误] python.exe 无法启动。可能是运行库无法加载，或 32/64 位软件包选错。>>\"%LOG%\"",
        "  echo [错误] python.exe 无法启动。可能是运行库无法加载，或 32/64 位软件包选错。",
        "  goto :fail",
        ")",
        "if exist \"%~dp0python\\pythonw.exe\" (",
        "  start \"课堂管理运行中\" \"%~dp0python\\pythonw.exe\" launch_student.py",
        ") else (",
        "  \"%~dp0python\\python.exe\" launch_student.py",
        "  set ERR=%ERRORLEVEL%",
        "  if not \"%ERR%\"==\"0\" (",
        "    echo [错误] launch_student.py 退出码 %ERR%>>\"%LOG%\"",
        "    goto :fail",
        "  )",
        ")",
        "goto :eof",
        ":fail",
    ]
    write_cmd(dest / "start_student.cmd", student_head + fail_help_lines("start_student.log"))

    write_cmd(dest / "start_student_autostart.cmd", [
        "@echo off",
        "setlocal",
        "cd /d \"%~dp0\"",
        "chcp 936 >nul 2>&1",
        "set \"LOG=%~dp0start_student.log\"",
        "echo.>>\"%LOG%\"",
        "echo ===== %date% %time% 开机启动学生机 =====>>\"%LOG%\"",
        "echo VERSION=" + VERSION + ">>\"%LOG%\"",
        "if not exist \"%~dp0python\\python.exe\" goto :fail",
        "\"%~dp0python\\python.exe\" -c \"import sys\" >>\"%LOG%\" 2>&1",
        "if errorlevel 1 goto :fail",
        "if exist \"%~dp0python\\pythonw.exe\" (",
        "  start \"\" \"%~dp0python\\pythonw.exe\" launch_student.py",
        ") else (",
        "  start \"\" \"%~dp0python\\python.exe\" launch_student.py",
        ")",
        "goto :eof",
        ":fail",
        "echo 课堂管理学生端启动失败。32 位系统请使用 x86 包；并请改用最新安装包或绿色版。>>\"%LOG%\"",
        "echo 课堂管理学生端启动失败。32 位系统请使用 x86 包；并请改用最新安装包或绿色版。",
        "echo 请把安装目录下的 start_student.log 发给开发者。",
        "pause",
    ])

    write_cmd(dest / "更改连接设置.cmd", [
        "@echo off",
        "setlocal",
        "cd /d \"%~dp0\"",
        "chcp 936 >nul 2>&1",
        "set \"LOG=%~dp0start_student.log\"",
        "if not exist \"%~dp0python\\python.exe\" goto :fail",
        "\"%~dp0python\\python.exe\" -c \"import sys\" >nul 2>&1",
        "if errorlevel 1 goto :fail",
        "if exist \"%~dp0python\\pythonw.exe\" (",
        "  start \"\" \"%~dp0python\\pythonw.exe\" launch_student.py --config-ui",
        ") else (",
        "  \"%~dp0python\\python.exe\" launch_student.py --config-ui",
        "  if errorlevel 1 goto :fail",
        ")",
        "goto :eof",
        ":fail",
    ] + fail_help_lines("start_student.log"))

    # 给绿色版看的简短说明（UTF-8 BOM，记事本可打开）
    tip = (
        "乐昌国艺书院 机房课堂管理 - 绿色版 %s\r\n"
        "版权所有 © 乐昌国艺书院    开发者：陈老师\r\n"
        "\r\n"
        "本压缩包解压后即可运行，不必管理员，也不必先安装 Python。\r\n"
        "请解压到较短路径，例如 C:\\GuoyiTeacher 或 C:\\GuoyiStudent。\r\n"
        "\r\n"
        "教师机：双击 start_teacher.cmd\r\n"
        "学生机：双击 start_student.cmd\r\n"
        "\r\n"
        "若启动失败，请用记事本打开同目录下的 start_teacher.log 或 start_student.log，\r\n"
        "把该文件发给开发者。安装包默认目录：\r\n"
        "  C:\\Users\\用户名\\AppData\\Local\\GuoyiClassroom\\Teacher\r\n"
        "  C:\\Users\\用户名\\AppData\\Local\\GuoyiClassroom\\Student\r\n"
        "\r\n"
        "本包架构：%s\r\n"
        "32 位 Windows 7 必须使用 x86 包；64 位系统优先使用 x64 包。\r\n"
        "查看方法：打开“计算机”右键 - 属性，看“系统类型”。\r\n"
        "需要 Windows 7 SP1 或更高版本。\r\n"
        % (VERSION, arch_label)
    )
    (dest / "打开说明.txt").write_bytes(b"\xef\xbb\xbf" + tip.encode("utf-8"))


def copy_app(dest, arch):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for name in APP_FILES:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, dest / name)
    for d in APP_DIRS:
        src = ROOT / d
        target = dest / d
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    arch_label = "64 位（x64）" if arch == "amd64" else "32 位（x86）"
    write_launch_scripts(dest, arch_label)


def stage(arch, role):
    name = "staging-%s-%s" % (role, arch)
    dest = PACK / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    log("==== 组装 %s / %s ====" % (role, arch))
    extract_python(arch, dest / "python")
    bundle_win_runtimes(arch, dest / "python")
    wheels = download_wheels(arch)
    ensure_win7_safe_wheels(wheels)
    site = dest / "python" / "Lib" / "site-packages"
    unpack_wheels(wheels, site)
    assert_no_pydantic_core(site)
    copy_app(dest, arch)
    return dest


def patch_nsi(src_nsi, arch, role):
    text = src_nsi.read_text(encoding="utf-8")
    if arch == "win32":
        text = text.replace("staging-%s-amd64" % role, "staging-%s-win32" % role)
        text = text.replace("安装包-x64.exe", "安装包-x86.exe")
        text = text.replace("-x64.exe", "-x86.exe")
        out = PACK / ("%s-win32.nsi" % role)
        out.write_text(text, encoding="utf-8")
        return out
    return src_nsi


def run_makensis(nsi):
    DIST.mkdir(parents=True, exist_ok=True)
    exe = shutil.which("makensis")
    if not exe:
        log("未找到 makensis，跳过编译。请在本机安装 NSIS 后运行：makensis %s" % nsi)
        return None
    log("编译 %s ..." % nsi.name)
    r = subprocess.run([exe, "-V2", str(nsi)], cwd=str(PACK))
    if r.returncode != 0:
        raise RuntimeError("makensis 失败：%s" % nsi)
    return True


def _zip_dir(src, zip_path, inner_root):
    src = Path(src)
    zip_path = Path(zip_path)
    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    # compresslevel 需要 Python 3.7+
    kwargs = {"compression": zipfile.ZIP_DEFLATED}
    if sys.version_info >= (3, 7):
        kwargs["compresslevel"] = 9
    with zipfile.ZipFile(zip_path, "w", **kwargs) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_dir():
                continue
            if path.name.endswith((".pyc", ".pyo")) or "__pycache__" in path.parts:
                continue
            rel = Path(inner_root) / path.relative_to(src)
            zf.write(path, str(rel).replace("\\", "/"))
    return zip_path


def slim_portable(src_stage, dest, role):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    keep_files = TEACHER_KEEP if role == "teacher" else STUDENT_KEEP
    keep_dirs = ["python", "shared"]
    if role == "teacher":
        keep_dirs += ["server", "web", "teacher"]
    else:
        keep_dirs += ["student"]
    for name in keep_files:
        src = src_stage / name
        if src.exists():
            shutil.copy2(src, dest / name)
    for name in keep_dirs:
        src = src_stage / name
        if src.is_dir():
            shutil.copytree(src, dest / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    return dest


def build_portable_zips(built_archs):
    """按角色裁剪后打包绿色版：中文名 + 英文短文件名各一份。"""
    names = {
        ("teacher", "amd64"): (
            "乐昌国艺书院-机房课堂管理-教师机-绿色版-Win7-x64.zip",
            "Guoyi-Teacher-Win7-x64.zip",
            "GuoyiTeacher",
        ),
        ("teacher", "win32"): (
            "乐昌国艺书院-机房课堂管理-教师机-绿色版-Win7-x86.zip",
            "Guoyi-Teacher-Win7-x86.zip",
            "GuoyiTeacher",
        ),
        ("student", "amd64"): (
            "乐昌国艺书院-机房课堂管理-学生机-绿色版-Win7-x64.zip",
            "Guoyi-Student-Win7-x64.zip",
            "GuoyiStudent",
        ),
        ("student", "win32"): (
            "乐昌国艺书院-机房课堂管理-学生机-绿色版-Win7-x86.zip",
            "Guoyi-Student-Win7-x86.zip",
            "GuoyiStudent",
        ),
    }
    made = []
    work = PACK / "portable-tmp"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    try:
        for arch in built_archs:
            for role in ("teacher", "student"):
                key = (role, arch)
                if key not in names:
                    continue
                cn, en, folder = names[key]
                src = PACK / ("staging-%s-%s" % (role, arch))
                if not src.is_dir():
                    log("跳过绿色版（没有 staging）：%s" % src)
                    continue
                slim = slim_portable(src, work / ("%s-%s" % (role, arch)), role)
                zpath = DIST / cn
                _zip_dir(slim, zpath, folder)
                enpath = DIST / en
                shutil.copy2(zpath, enpath)
                size = zpath.stat().st_size
                log("绿色版：%s （%.2f MB）" % (zpath.name, size / (1024 * 1024.0)))
                log("  英文名备份：%s" % enpath.name)
                if size >= 25 * 1024 * 1024:
                    raise RuntimeError("绿色版超过 25MB：%s" % zpath)
                made.append(zpath)
                made.append(enpath)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return made



def _zip_write_kwargs():
    kwargs = {"compression": zipfile.ZIP_DEFLATED}
    if sys.version_info >= (3, 7):
        kwargs["compresslevel"] = 9
    return kwargs


def build_email_zips():
    """邮件附件包：每个 zip 含对应安装 exe 与使用说明。"""
    email_dir = DIST / "email"
    email_dir.mkdir(parents=True, exist_ok=True)
    guide = ROOT / "乐昌国艺书院-机房课堂管理-使用说明.txt"
    pairs = [
        ("乐昌国艺书院-机房课堂管理-教师机-安装包-x64.exe", "Guoyi-Teacher-x64-setup.zip"),
        ("乐昌国艺书院-机房课堂管理-教师机-安装包-x86.exe", "Guoyi-Teacher-x86-setup.zip"),
        ("乐昌国艺书院-机房课堂管理-学生机-安装包-x64.exe", "Guoyi-Student-x64-setup.zip"),
        ("乐昌国艺书院-机房课堂管理-学生机-安装包-x86.exe", "Guoyi-Student-x86-setup.zip"),
    ]
    made = []
    for exe_name, zip_name in pairs:
        exe = DIST / exe_name
        if not exe.is_file():
            log("跳过邮件包（缺少 exe）：%s" % exe_name)
            continue
        zpath = email_dir / zip_name
        if zpath.exists():
            zpath.unlink()
        with zipfile.ZipFile(zpath, "w", **_zip_write_kwargs()) as zf:
            zf.write(exe, exe_name)
            if guide.is_file():
                zf.write(guide, guide.name)
        made.append(zpath)
        log("邮件包：%s （%.2f MB）" % (zpath.name, zpath.stat().st_size / (1024 * 1024.0)))
    return made


def build_source_zip():
    """把源码打进 delivery，不含构建缓存、虚拟环境和已生成安装包。"""
    delivery = DIST / "delivery"
    delivery.mkdir(parents=True, exist_ok=True)
    zpath = delivery / ("guoyi-classroom-source-%s.zip" % VERSION)
    if zpath.exists():
        zpath.unlink()
    skip_dir_names = {
        ".git", ".venv", "__pycache__", "dist", "cache", "redist", "unpacked",
        "portable-tmp", "wheels-amd64", "wheels-win32",
    }
    skip_suffixes = (".zip", ".exe", ".pyc", ".pyo", ".b64")
    include_top_dirs = {"packaging", "scripts", "server", "shared", "student", "teacher", "tests", "web"}
    with zipfile.ZipFile(zpath, "w", **_zip_write_kwargs()) as zf:
        for path in sorted(ROOT.iterdir()):
            if path.name.startswith(".") and path.name not in (".gitignore",):
                continue
            if path.is_file():
                if path.suffix.lower() in skip_suffixes:
                    continue
                if path.stat().st_size > 1024 * 1024:
                    continue
                zf.write(path, "guoyi-classroom-%s/%s" % (VERSION, path.name))
                continue
            if path.name not in include_top_dirs:
                continue
            for sub in sorted(path.rglob("*")):
                if sub.is_dir():
                    continue
                parts = sub.relative_to(ROOT).parts
                if any(part in skip_dir_names or part.startswith("staging-") for part in parts):
                    continue
                if sub.suffix.lower() in skip_suffixes:
                    continue
                rel_s = str(sub.relative_to(ROOT)).replace("\\", "/")
                zf.write(sub, "guoyi-classroom-%s/%s" % (VERSION, rel_s))
    log("源码包：%s （%.2f MB）" % (zpath.name, zpath.stat().st_size / (1024 * 1024.0)))
    return zpath


def write_delivery_sums(extra_paths):
    delivery = DIST / "delivery"
    delivery.mkdir(parents=True, exist_ok=True)
    paths = []
    for p in sorted(DIST.iterdir()):
        if p.is_file() and p.suffix.lower() in (".exe", ".zip"):
            paths.append(p)
    for p in extra_paths:
        p = Path(p)
        if p.is_file():
            paths.append(p)
    # unique, keep order
    seen = set()
    uniq = []
    for p in paths:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    lines = []
    for p in uniq:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        size = p.stat().st_size / (1024 * 1024.0)
        lines.append("%s  %s  (%.2f MB)" % (digest, str(p), size))
        log("  交付校验：%s  %.2f MB  %s" % (p.name, size, digest))
    out = delivery / ("RELEASE-SHA256SUMS-%s.txt" % VERSION)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("已写入 %s" % out)
    return out


def write_sha256sums():
    rows = []
    for p in sorted(DIST.iterdir()):
        if p.suffix.lower() not in (".exe", ".zip"):
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        rows.append("%s  %s" % (digest, p.name))
        log("  %s  %.2f MB  %s" % (p.name, p.stat().st_size / (1024 * 1024.0), digest))
    (DIST / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main():
    write_runtime_req()
    CACHE.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)
    ensure_win_runtimes()
    built = []
    errors = []
    for arch in ("amd64", "win32"):
        try:
            stage(arch, "teacher")
            src = PACK / ("staging-teacher-" + arch)
            dst = PACK / ("staging-student-" + arch)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            nsi_t = patch_nsi(PACK / "teacher.nsi", arch, "teacher")
            nsi_s = patch_nsi(PACK / "student.nsi", arch, "student")
            run_makensis(nsi_t)
            run_makensis(nsi_s)
            built.append(arch)
        except Exception as exc:
            errors.append("%s: %s" % (arch, exc))
            log("构建 %s 失败：%s" % (arch, exc))
    log("完成的架构：%s" % (", ".join(built) if built else "无"))
    for e in errors:
        log("错误：%s" % e)
    try:
        build_portable_zips(built)
    except Exception as exc:
        errors.append("portable: %s" % exc)
        log("绿色版打包失败：%s" % exc)
    write_sha256sums()
    try:
        email_zips = build_email_zips()
        src_zip = build_source_zip()
        write_delivery_sums(list(email_zips) + [src_zip])
    except Exception as exc:
        errors.append("email/delivery: %s" % exc)
        log("邮件包或交付校验失败：%s" % exc)
    for p in sorted(DIST.glob("*.exe")) + sorted(DIST.glob("*.zip")):
        log("交付：%s (%s 字节)" % (p, p.stat().st_size))
    if not built:
        sys.exit(1)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
