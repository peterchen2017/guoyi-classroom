# -*- coding: utf-8 -*-
"""教师机服务：HTTP + WebSocket 控制台，局域网内给学生机和手机使用。"""

from __future__ import print_function

import argparse
import asyncio
import getpass
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server import auth, capture, config
from server.discovery import run_discovery
from server.store import Store, Student

if sys.version_info < (3, 8):
    sys.stderr.write("需要 Python 3.8 或更高版本。Windows 7 请安装官方 Python 3.8.10。\n")
    sys.exit(1)

store = Store()
teacher_sockets = set()  # type: set
student_sockets = {}  # type: Dict[str, WebSocket]
broadcast_lock = asyncio.Lock()

app = FastAPI(title=config.SCHOOL_NAME + " " + config.APP_NAME, version=config.VERSION)


# ---------- 请求体 ----------

class LoginBody(BaseModel):
    username: str
    password: str


class IdsBody(BaseModel):
    student_ids: Optional[List[str]] = None


class AnnounceBody(BaseModel):
    text: str
    kind: str = "announce"


class PasswordBody(BaseModel):
    old_password: str
    new_password: str


class FocusBody(BaseModel):
    student_id: Optional[str] = None


class NameBody(BaseModel):
    name: Optional[str] = None


class RestrictToggleBody(BaseModel):
    enabled: bool


class RestrictListsBody(BaseModel):
    game_domains: Optional[List[str]] = None
    download_domains: Optional[List[str]] = None
    whitelist_domains: Optional[List[str]] = None
    extensions: Optional[List[str]] = None
    reset_defaults: Optional[bool] = None


class BroadcastStartBody(BaseModel):
    shrink: Optional[bool] = None


class BroadcastSettingsBody(BaseModel):
    shrink: bool


class DesktopLockBody(BaseModel):
    lock: Optional[bool] = True


# ---------- 鉴权 ----------

def _bearer(authorization=None):
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return authorization.strip()


def require_teacher(authorization=Header(None)):
    token = _bearer(authorization)
    if not store.check_session(token):
        raise HTTPException(status_code=401, detail="请先登录")
    return token


def teacher_ips_for_students():
    ips = list(config.lan_ips())
    if "127.0.0.1" not in ips:
        ips.append("127.0.0.1")
    return ips


def restrict_payload():
    return store.restrict_message(
        teacher_ips=teacher_ips_for_students(),
        teacher_port=config.PORT,
    )


def wallpaper_file():
    folder = config.wallpapers_dir()
    for ext in (".jpg", ".jpeg", ".png", ".bmp"):
        path = folder / ("current" + ext)
        if path.is_file():
            return path
    return None


async def push_desktop(device_ids=None):
    ids = device_ids or approved_online_ids()
    for device_id in ids:
        student = store.students.get(device_id)
        if not student or not student.approved:
            continue
        token = store.device_tokens.get(device_id)
        msg = store.desktop_message(token)
        await send_student(device_id, msg)


def outgoing_broadcast_frame():
    frame = store.broadcast_frame
    if frame and store.broadcast_shrink:
        return capture.scale_jpeg(frame, max_width=capture.SHRINK_WIDTH, quality=capture.SHRINK_QUALITY)
    return frame


# ---------- 推送 ----------

async def push_teachers(payload):
    dead = []
    text = json.dumps(payload, ensure_ascii=False)
    for ws in list(teacher_sockets):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        teacher_sockets.discard(ws)


async def push_state():
    await push_teachers({"type": "state", "data": store.public_state()})


async def send_student(device_id, payload):
    ws = student_sockets.get(device_id)
    if ws is None:
        return False
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
        return True
    except Exception:
        student_sockets.pop(device_id, None)
        student = store.students.get(device_id)
        if student:
            student.online = False
        return False


async def send_students(device_ids, payload):
    for device_id in device_ids:
        await send_student(device_id, payload)


def approved_online_ids():
    return [
        s.device_id
        for s in store.students.values()
        if s.approved and s.online
    ]


def target_ids(student_ids):
    if student_ids:
        return [sid for sid in student_ids if sid in store.students]
    return approved_online_ids()


# ---------- 公开信息 / 登录 ----------

@app.get("/api/info")
async def api_info():
    return {
        "school": config.SCHOOL_NAME,
        "app": config.APP_NAME,
        "version": config.VERSION,
        "developer": config.DEVELOPER,
        "copyright": config.COPYRIGHT,
        "class_active": store.class_active,
    }


@app.post("/api/login")
async def api_login(body: LoginBody):
    if body.username != store.teacher_username:
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    if not auth.verify_password(body.password, store.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    token = store.create_session(body.username)
    return {"token": token, "username": body.username, "state": store.public_state()}


@app.get("/api/state")
async def api_state(_token=Depends(require_teacher)):
    return store.public_state()


@app.post("/api/password")
async def api_password(body: PasswordBody, _token=Depends(require_teacher)):
    if not auth.verify_password(body.old_password, store.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码至少 8 位")
    store.password_hash = auth.hash_password(body.new_password)
    store.save()
    return {"ok": True}


# ---------- 课堂 ----------

@app.post("/api/class/start")
async def api_class_start(_token=Depends(require_teacher)):
    store.class_active = True
    store.web_restrict_enabled = True
    payload = restrict_payload()
    await send_students(approved_online_ids(), {"type": "class_start", "web_restrict": payload})
    await send_students(approved_online_ids(), payload)
    await push_state()
    return store.public_state()


@app.post("/api/class/end")
async def api_class_end(_token=Depends(require_teacher)):
    ids = approved_online_ids()
    off = restrict_payload()
    store.end_class_cleanup()
    off["enabled"] = False
    await send_students(ids, {"type": "class_end"})
    await send_students(ids, off)
    await push_state()
    return store.public_state()


@app.post("/api/class/code")
async def api_class_code(_token=Depends(require_teacher)):
    store.class_code = auth.new_class_code()
    store.save()
    await push_state()
    return {"class_code": store.class_code}


# ---------- 学生管理 ----------

@app.post("/api/students/{device_id}/approve")
async def api_approve(device_id: str, body: NameBody = NameBody(), _token=Depends(require_teacher)):
    student = store.students.get(device_id)
    if not student:
        raise HTTPException(status_code=404, detail="未找到该学生机")
    student.approved = True
    if body and body.name:
        student.name = body.name.strip() or student.name
    store.save()
    await send_student(device_id, {"type": "approved", "class_active": store.class_active})
    if store.class_active:
        payload = restrict_payload()
        await send_student(device_id, {"type": "class_start", "web_restrict": payload})
        await send_student(device_id, payload)
    await push_desktop([device_id])
    await push_state()
    return student.public()


@app.post("/api/students/{device_id}/revoke")
async def api_revoke(device_id: str, _token=Depends(require_teacher)):
    student = store.students.get(device_id)
    if not student:
        raise HTTPException(status_code=404, detail="未找到该学生机")
    student.approved = False
    student.locked = False
    student.focus_requested = False
    store.thumbs.pop(device_id, None)
    store.focus_frames.pop(device_id, None)
    store.save()
    await send_student(device_id, {"type": "revoked"})
    await push_state()
    return student.public()


@app.post("/api/focus")
async def api_focus(body: FocusBody, _token=Depends(require_teacher)):
    for student in store.students.values():
        want = bool(body.student_id and student.device_id == body.student_id)
        if student.focus_requested != want:
            student.focus_requested = want
            await send_student(student.device_id, {"type": "focus", "on": want})
    await push_state()
    return {"ok": True, "student_id": body.student_id}


# ---------- 锁屏 / 公告 / 文件 / 广播 ----------

@app.post("/api/lock")
async def api_lock(body: IdsBody = IdsBody(), _token=Depends(require_teacher)):
    ids = target_ids(body.student_ids)
    for device_id in ids:
        student = store.students.get(device_id)
        if student and student.approved:
            student.locked = True
            await send_student(device_id, {"type": "lock", "message": "请看老师"})
    await push_state()
    return {"ok": True, "count": len(ids)}


@app.post("/api/unlock")
async def api_unlock(body: IdsBody = IdsBody(), _token=Depends(require_teacher)):
    ids = target_ids(body.student_ids)
    for device_id in ids:
        student = store.students.get(device_id)
        if student:
            student.locked = False
            await send_student(device_id, {"type": "unlock"})
    await push_state()
    return {"ok": True, "count": len(ids)}


@app.post("/api/announce")
async def api_announce(body: AnnounceBody, _token=Depends(require_teacher)):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="公告内容不能为空")
    kind = body.kind if body.kind in ("announce", "question") else "announce"
    store.announcement = text
    store.announcement_at = time.time()
    payload = {
        "type": "question" if kind == "question" else "announce",
        "title": "课堂题目" if kind == "question" else "课堂公告",
        "text": text,
    }
    await send_students(approved_online_ids(), payload)
    await push_state()
    return {"ok": True}


@app.post("/api/restrict/web")
async def api_restrict_web(body: RestrictToggleBody, _token=Depends(require_teacher)):
    if body.enabled and not store.class_active:
        raise HTTPException(status_code=400, detail="请先开始上课")
    store.web_restrict_enabled = bool(body.enabled)
    await send_students(approved_online_ids(), restrict_payload())
    await push_state()
    return store.public_state()


@app.post("/api/restrict/lists")
async def api_restrict_lists(body: RestrictListsBody, _token=Depends(require_teacher)):
    from shared.web_filter import (
        default_download_domains,
        default_extensions,
        default_game_domains,
        normalize_exts,
        normalize_list,
    )
    if body.reset_defaults:
        store.game_domains = default_game_domains()
        store.download_domains = default_download_domains()
        store.blocked_extensions = default_extensions()
        store.whitelist_domains = []
    if body.game_domains is not None:
        store.game_domains = normalize_list(body.game_domains)
    if body.download_domains is not None:
        store.download_domains = normalize_list(body.download_domains)
    if body.whitelist_domains is not None:
        store.whitelist_domains = normalize_list(body.whitelist_domains)
    if body.extensions is not None:
        store.blocked_extensions = normalize_exts(body.extensions)
    store.save()
    if store.class_active and store.web_restrict_enabled:
        await send_students(approved_online_ids(), restrict_payload())
    await push_state()
    return store.public_state()


@app.post("/api/desktop/wallpaper")
async def api_desktop_wallpaper(
    file: UploadFile = File(...),
    lock: str = Query("1"),
    _token=Depends(require_teacher),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="请选择一张壁纸图片")
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="壁纸不能超过 12MB")
    filename = Path(file.filename or "wallpaper.jpg").name
    ext = Path(filename).suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in (".jpg", ".png", ".bmp"):
        # 仍尝试按内容识别
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif raw[:2] == b"BM":
            ext = ".bmp"
        else:
            ext = ".jpg"
    try:
        from PIL import Image
        import io
        Image.open(io.BytesIO(raw)).verify()
    except Exception:
        raise HTTPException(status_code=400, detail="无法识别图片，请使用 jpg / png / bmp")
    folder = config.wallpapers_dir()
    for oldp in folder.glob("current.*"):
        try:
            oldp.unlink()
        except OSError:
            pass
    dest = folder / ("current" + ext)
    dest.write_bytes(raw)
    store.desktop_filename = filename
    store.desktop_locked = (str(lock) not in ("0", "false", "False", "no"))
    store.save()
    await push_desktop()
    await push_state()
    return store.public_state()


@app.post("/api/desktop/unlock")
async def api_desktop_unlock(_token=Depends(require_teacher)):
    store.desktop_locked = False
    store.save()
    await push_desktop()
    await push_state()
    return store.public_state()


@app.get("/api/desktop/image")
async def api_desktop_image(_token=Depends(require_teacher)):
    path = wallpaper_file()
    if not path:
        return Response(status_code=404)
    mime = "image/jpeg"
    if path.suffix.lower() == ".png":
        mime = "image/png"
    elif path.suffix.lower() == ".bmp":
        mime = "image/bmp"
    return Response(content=path.read_bytes(), media_type=mime)


@app.get("/api/student/desktop")
async def api_student_desktop(token: str = Query("")):
    student = store.student_by_token(token)
    if student is None or not student.approved:
        raise HTTPException(status_code=401, detail="无效的学生令牌")
    if not store.desktop_locked:
        raise HTTPException(status_code=404, detail="当前未锁定默认桌面")
    path = wallpaper_file()
    if not path:
        raise HTTPException(status_code=404, detail="尚未设置壁纸")
    return FileResponse(path, filename=store.desktop_filename or path.name)


@app.post("/api/files")
async def api_files(
    file: UploadFile = File(...),
    student_ids: Optional[str] = Query(None),
    _token=Depends(require_teacher),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 25MB")
    filename = Path(file.filename or "课堂文件").name
    # 明确放行 C++ 与常见文本，且不对课堂下发做扩展名拦截。
    _suffix = Path(filename).suffix.lower()
    if _suffix == ".h++":
        pass
    file_id = auth.new_token()[:16]
    dest = config.uploads_dir() / (file_id + "_" + filename)
    dest.write_bytes(raw)
    ids = target_ids(student_ids.split(",") if student_ids else None)
    for device_id in ids:
        token = store.device_tokens.get(device_id)
        if not token:
            continue
        await send_student(
            device_id,
            {
                "type": "file",
                "file_id": file_id,
                "filename": filename,
                "size": len(raw),
                "url": "/api/student/download/%s?token=%s" % (file_id, token),
            },
        )
    return {"ok": True, "filename": filename, "size": len(raw), "count": len(ids)}


@app.get("/api/student/download/{file_id}")
async def api_student_download(file_id: str, token: str = Query("")):
    student = store.student_by_token(token)
    if student is None or not student.approved:
        raise HTTPException(status_code=401, detail="无效的学生令牌")
    matches = list(config.uploads_dir().glob(file_id + "_*"))
    if not matches:
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    path = matches[0]
    filename = path.name.split("_", 1)[-1]
    return FileResponse(path, filename=filename)


@app.post("/api/broadcast/start")
async def api_broadcast_start(body: Optional[BroadcastStartBody] = None, _token=Depends(require_teacher)):
    if not store.class_active:
        raise HTTPException(status_code=400, detail="请先开始上课")
    store.broadcast_active = True
    if body is not None and body.shrink is not None:
        store.broadcast_shrink = bool(body.shrink)
    if store.broadcast_frame is None:
        store.broadcast_frame = capture.placeholder_jpeg()
        store.broadcast_frame_at = time.time()
    await send_students(approved_online_ids(), {"type": "broadcast_start", "shrink": store.broadcast_shrink})
    if store.broadcast_frame is not None:
        await _push_broadcast_frame()
    await push_state()
    return {"ok": True, "capture": capture.can_grab_screen(), "shrink": store.broadcast_shrink}


@app.post("/api/broadcast/settings")
async def api_broadcast_settings(body: BroadcastSettingsBody, _token=Depends(require_teacher)):
    store.broadcast_shrink = bool(body.shrink)
    if store.broadcast_active and store.class_active and store.broadcast_frame:
        await _push_broadcast_frame()
    await push_state()
    return {"ok": True, "shrink": store.broadcast_shrink}


@app.post("/api/broadcast/end")
async def api_broadcast_end(_token=Depends(require_teacher)):
    store.broadcast_active = False
    await send_students(approved_online_ids(), {"type": "broadcast_end"})
    await push_state()
    return {"ok": True}


@app.post("/api/broadcast/frame")
async def api_broadcast_frame(file: UploadFile = File(...), _token=Depends(require_teacher)):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="画面为空")
    store.broadcast_frame = raw
    store.broadcast_frame_at = time.time()
    if store.broadcast_active and store.class_active:
        await _push_broadcast_frame()
    return {"ok": True, "size": len(raw)}


# ---------- 画面 ----------

@app.get("/api/thumbs/{device_id}")
async def api_thumb(device_id: str, _token=Depends(require_teacher)):
    data = store.thumbs.get(device_id)
    if not data:
        return Response(status_code=404)
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/focus/{device_id}")
async def api_focus_frame(device_id: str, _token=Depends(require_teacher)):
    data = store.focus_frames.get(device_id) or store.thumbs.get(device_id)
    if not data:
        return Response(status_code=404)
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/broadcast/image")
async def api_broadcast_image(_token=Depends(require_teacher)):
    data = store.broadcast_frame
    if not data:
        return Response(status_code=404)
    return Response(content=data, media_type="image/jpeg")


# ---------- WebSocket ----------

@app.websocket("/ws/teacher")
async def ws_teacher(ws: WebSocket, token: str = Query("")):
    if not store.check_session(token):
        await ws.close(code=4401)
        return
    await ws.accept()
    teacher_sockets.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "state", "data": store.public_state()}, ensure_ascii=False))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        teacher_sockets.discard(ws)


@app.websocket("/ws/student")
async def ws_student(ws: WebSocket):
    await ws.accept()
    device_id = None
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=20)
        hello = json.loads(first)
        if hello.get("type") != "hello":
            await ws.send_text(json.dumps({"type": "error", "message": "请先发送 hello"}, ensure_ascii=False))
            await ws.close()
            return
        device_id = (hello.get("device_id") or "").strip()
        name = (hello.get("name") or "").strip() or "学生"
        hostname = (hello.get("hostname") or "").strip()
        platform = (hello.get("platform") or "").strip()
        class_code = (hello.get("class_code") or "").strip().upper()
        ip = ""
        if ws.client:
            ip = ws.client.host or ""
        if not device_id:
            await ws.send_text(json.dumps({"type": "error", "message": "缺少 device_id"}, ensure_ascii=False))
            await ws.close()
            return

        student = store.students.get(device_id)
        auto = bool(class_code and class_code == store.class_code)
        if student is None:
            student = Student(
                device_id=device_id,
                name=name,
                hostname=hostname,
                platform=platform,
                approved=auto,
                ip=ip,
            )
            store.students[device_id] = student
        else:
            student.name = name or student.name
            student.hostname = hostname or student.hostname
            student.platform = platform or student.platform
            student.ip = ip or student.ip
            if auto:
                student.approved = True
        student.online = True
        student.last_seen = time.time()
        store.save()

        token = store.bind_student_token(device_id)
        old = student_sockets.get(device_id)
        if old is not None and old is not ws:
            try:
                await old.close()
            except Exception:
                pass
        student_sockets[device_id] = ws

        await ws.send_text(
            json.dumps(
                {
                    "type": "welcome",
                    "approved": student.approved,
                    "class_active": store.class_active,
                    "student_id": device_id,
                    "token": token,
                    "locked": student.locked if store.class_active else False,
                    "broadcast_active": store.broadcast_active and store.class_active,
                    "broadcast_shrink": store.broadcast_shrink,
                    "school": config.SCHOOL_NAME,
                    "copyright": config.COPYRIGHT,
                    "web_restrict": restrict_payload(),
                    "desktop": store.desktop_public(),
                },
                ensure_ascii=False,
            )
        )
        await push_state()

        if student.approved and store.class_active:
            payload = restrict_payload()
            await ws.send_text(json.dumps({"type": "class_start", "web_restrict": payload}, ensure_ascii=False))
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
            if student.locked:
                await ws.send_text(json.dumps({"type": "lock", "message": "请看老师"}, ensure_ascii=False))
            if store.broadcast_active:
                await ws.send_text(json.dumps({"type": "broadcast_start", "shrink": store.broadcast_shrink}))

        # 默认桌面锁定与上课无关，学生连上或重启后仍要应用，直到老师解除。
        if student.approved:
            token = store.device_tokens.get(device_id)
            await ws.send_text(json.dumps(store.desktop_message(token), ensure_ascii=False))

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            await _handle_student_message(student, msg)
    except asyncio.TimeoutError:
        try:
            await ws.close()
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass
    finally:
        if device_id and student_sockets.get(device_id) is ws:
            student_sockets.pop(device_id, None)
            student = store.students.get(device_id)
            if student:
                student.online = False
                student.focus_requested = False
            try:
                await push_state()
            except Exception:
                pass


async def _handle_student_message(student, msg):
    typ = msg.get("type")
    store.touch(student.device_id)
    if typ == "ping":
        ws = student_sockets.get(student.device_id)
        if ws is not None:
            await ws.send_text(json.dumps({"type": "pong"}))
        return
    if typ != "frame":
        return
    if not student.approved or not store.class_active:
        return
    kind = msg.get("kind") or "thumb"
    data_b64 = msg.get("data") or ""
    if not data_b64:
        return
    try:
        import base64
        data = base64.b64decode(data_b64)
    except Exception:
        return
    if len(data) > 2 * 1024 * 1024:
        return
    if kind == "focus":
        store.focus_frames[student.device_id] = data
        student.focus_at = time.time()
        await push_teachers({"type": "focus", "student_id": student.device_id, "at": student.focus_at})
    else:
        store.thumbs[student.device_id] = data
        student.thumb_at = time.time()
        await push_teachers({"type": "thumb", "student_id": student.device_id, "at": student.thumb_at})


async def _push_broadcast_frame():
    frame = outgoing_broadcast_frame()
    if not frame or not store.broadcast_active or not store.class_active:
        return
    import base64
    payload = {
        "type": "broadcast_frame",
        "mime": "image/jpeg",
        "data": base64.b64encode(frame).decode("ascii"),
    }
    await send_students(approved_online_ids(), payload)
    await push_teachers({"type": "broadcast", "at": store.broadcast_frame_at})


async def _heartbeat_loop():
    while True:
        await asyncio.sleep(5)
        changed = store.mark_offline_stale()
        if changed:
            await push_state()


async def _broadcast_capture_loop():
    while True:
        await asyncio.sleep(config.BROADCAST_INTERVAL)
        if not (store.broadcast_active and store.class_active):
            continue
        # 若教师网页刚刚上传过画面，则优先用上传帧，避免覆盖。
        if time.time() - store.broadcast_frame_at < 0.8 and store.broadcast_frame:
            await _push_broadcast_frame()
            continue
        grabbed = None
        try:
            loop = asyncio.get_running_loop()
            grabbed = await loop.run_in_executor(
                None, lambda: capture.grab_teacher_screen(max_width=capture.NORMAL_WIDTH, quality=capture.NORMAL_QUALITY)
            )
        except Exception:
            grabbed = None
        if grabbed:
            store.broadcast_frame = grabbed
            store.broadcast_frame_at = time.time()
        elif store.broadcast_frame is None:
            store.broadcast_frame = capture.placeholder_jpeg()
            store.broadcast_frame_at = time.time()
        await _push_broadcast_frame()


@app.on_event("startup")
async def on_startup():
    ips = config.lan_ips()
    ip_hint = ips[0] if ips else "127.0.0.1"
    asyncio.create_task(_heartbeat_loop())
    asyncio.create_task(_broadcast_capture_loop())
    asyncio.create_task(run_discovery(ip_hint, on_log=_safe_log))


def _safe_log(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass


# 静态控制台（放在 API 之后）
if config.WEB_DIR.exists():
    @app.get("/")
    async def index_page():
        return FileResponse(config.WEB_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")


def _print_banner():
    ips = config.lan_ips()
    print("")
    print("=" * 60)
    print("  %s · %s  v%s" % (config.SCHOOL_NAME, config.APP_NAME, config.VERSION))
    print("=" * 60)
    print("  本机控制台:  http://127.0.0.1:%s" % config.PORT)
    if ips:
        for ip in ips:
            print("  手机/学生请打开: http://%s:%s" % (ip, config.PORT))
    else:
        print("  未能自动识别局域网 IP，请在教师机上运行 ipconfig 查看。")
    print("  UDP 发现端口: %s" % config.DISCOVERY_PORT)
    print("  请放行防火墙 TCP %s 与 UDP %s" % (config.PORT, config.DISCOVERY_PORT))
    print("  请使用 Chrome 或新版 Edge 打开控制台（不要用 IE）。")
    print("  默认教师账号见 README，首次使用请立即修改密码。")
    print("  %s" % config.COPYRIGHT)
    print("=" * 60)
    print("")


def main(argv=None):
    parser = argparse.ArgumentParser(description=config.SCHOOL_NAME + " " + config.APP_NAME)
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--set-password", action="store_true", help="交互式重设教师密码后退出")
    args = parser.parse_args(argv)
    if args.set_password:
        p1 = getpass.getpass("新密码: ")
        p2 = getpass.getpass("再输入一次: ")
        if p1 != p2:
            print("两次输入不一致")
            sys.exit(1)
        if len(p1) < 8:
            print("密码至少 8 位")
            sys.exit(1)
        store.password_hash = auth.hash_password(p1)
        store.save()
        print("密码已更新。")
        return
    config.HOST = args.host
    config.PORT = args.port
    _print_banner()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
