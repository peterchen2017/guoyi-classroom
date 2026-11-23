# -*- coding: utf-8 -*-
"""课堂状态：学生登记、上课开关、会话。持久化到 data/state.json。"""

import json
import time
from pathlib import Path

from server import auth, config
from shared.web_filter import (
    default_download_domains,
    default_extensions,
    default_game_domains,
    normalize_exts,
    normalize_list,
)


class Student(object):
    def __init__(
        self,
        device_id,
        name,
        hostname="",
        platform="",
        approved=False,
        online=False,
        locked=False,
        last_seen=0.0,
        thumb_at=0.0,
        focus_at=0.0,
        ip="",
        focus_requested=False,
    ):
        self.device_id = device_id
        self.name = name
        self.hostname = hostname
        self.platform = platform
        self.approved = approved
        self.online = online
        self.locked = locked
        self.last_seen = last_seen
        self.thumb_at = thumb_at
        self.focus_at = focus_at
        self.ip = ip
        self.focus_requested = focus_requested

    def public(self):
        return {
            "device_id": self.device_id,
            "name": self.name,
            "hostname": self.hostname,
            "platform": self.platform,
            "approved": self.approved,
            "online": self.online,
            "locked": self.locked,
            "last_seen": self.last_seen,
            "thumb_at": self.thumb_at,
            "focus_at": self.focus_at,
            "ip": self.ip,
        }


class Store(object):
    def __init__(self, path=None):
        self.path = path or config.state_path()
        self.teacher_username = config.DEFAULT_TEACHER_USER
        self.password_hash = ""
        self.class_code = auth.new_class_code()
        self.class_active = False
        self.broadcast_active = False
        self.broadcast_shrink = False
        self.students = {}
        self.sessions = {}
        self.student_tokens = {}  # token -> device_id
        self.device_tokens = {}  # device_id -> token
        self.thumbs = {}
        self.focus_frames = {}
        self.broadcast_frame = None
        self.broadcast_frame_at = 0.0
        self.remote_device_id = None
        self.announcement = ""
        self.announcement_at = 0.0
        self.web_restrict_enabled = False
        self.game_domains = default_game_domains()
        self.download_domains = default_download_domains()
        self.whitelist_domains = []
        self.blocked_extensions = default_extensions()
        self.desktop_locked = False
        self.desktop_filename = ""
        self.remote_device_id = None
        self._load_or_init()

    def _load_or_init(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            self.teacher_username = raw.get("teacher_username") or config.DEFAULT_TEACHER_USER
            self.password_hash = raw.get("password_hash") or ""
            self.class_code = raw.get("class_code") or auth.new_class_code()
            for item in raw.get("students", []):
                student = Student(
                    device_id=item["device_id"],
                    name=item.get("name") or "学生",
                    hostname=item.get("hostname") or "",
                    platform=item.get("platform") or "",
                    approved=bool(item.get("approved")),
                    online=False,
                    locked=False,
                    ip=item.get("ip") or "",
                )
                self.students[student.device_id] = student
            if "game_domains" in raw:
                self.game_domains = normalize_list(raw.get("game_domains") or [])
            if "download_domains" in raw:
                self.download_domains = normalize_list(raw.get("download_domains") or [])
            if "whitelist_domains" in raw:
                self.whitelist_domains = normalize_list(raw.get("whitelist_domains") or [])
            if "blocked_extensions" in raw:
                self.blocked_extensions = normalize_exts(raw.get("blocked_extensions") or [])
            self.desktop_locked = bool(raw.get("desktop_locked"))
            self.desktop_filename = raw.get("desktop_filename") or ""
        if not self.password_hash:
            self.password_hash = auth.hash_password(config.DEFAULT_TEACHER_PASSWORD)
            self.save()

    def save(self):
        payload = {
            "teacher_username": self.teacher_username,
            "password_hash": self.password_hash,
            "class_code": self.class_code,
            "game_domains": self.game_domains,
            "download_domains": self.download_domains,
            "whitelist_domains": self.whitelist_domains,
            "blocked_extensions": self.blocked_extensions,
            "desktop_locked": bool(self.desktop_locked),
            "desktop_filename": self.desktop_filename,
            "students": [
                {
                    "device_id": s.device_id,
                    "name": s.name,
                    "hostname": s.hostname,
                    "platform": s.platform,
                    "approved": s.approved,
                    "ip": s.ip,
                }
                for s in self.students.values()
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def public_state(self):
        return {
            "school": config.SCHOOL_NAME,
            "app": config.APP_NAME,
            "version": config.VERSION,
            "class_code": self.class_code,
            "class_active": self.class_active,
            "broadcast_active": self.broadcast_active,
            "broadcast_shrink": bool(self.broadcast_shrink),
            "announcement": self.announcement,
            "announcement_at": self.announcement_at,
            "web_restrict": self.web_restrict_public(),
            "desktop": self.desktop_public(),
            "students": [s.public() for s in self.sorted_students()],
            "remote_device_id": self.remote_device_id,
        }

    def desktop_public(self):
        has_file = False
        folder = config.wallpapers_dir()
        for ext in (".jpg", ".jpeg", ".png", ".bmp"):
            if (folder / ("current" + ext)).is_file():
                has_file = True
                break
        return {
            "locked": bool(self.desktop_locked),
            "has_wallpaper": has_file,
            "filename": self.desktop_filename or "",
        }

    def desktop_message(self, token=None):
        data = self.desktop_public()
        if self.desktop_locked and token:
            data["type"] = "desktop_lock"
            data["url"] = "/api/student/desktop?token=%s" % token
        elif not self.desktop_locked:
            data["type"] = "desktop_unlock"
        else:
            data["type"] = "desktop_lock"
        data["notice"] = "已设置机房默认桌面，学生不能更改壁纸" if self.desktop_locked else "已解除桌面锁定"
        return data

    def web_restrict_public(self):
        enabled = bool(self.class_active and self.web_restrict_enabled)
        return {
            "enabled": enabled,
            "game_domains": list(self.game_domains),
            "download_domains": list(self.download_domains),
            "whitelist_domains": list(self.whitelist_domains),
            "extensions": list(self.blocked_extensions),
        }

    def restrict_message(self, teacher_ips=None, teacher_port=None):
        data = self.web_restrict_public()
        data["type"] = "web_restrict"
        data["teacher_ips"] = list(teacher_ips or [])
        data["teacher_port"] = teacher_port
        data["notice"] = "上课期间已限制网页游戏和下载"
        return data

    def sorted_students(self):
        def key(s):
            pending = 0 if (not s.approved and s.online) else 1
            online = 0 if s.online else 1
            return (pending, online, s.name, s.device_id)

        return sorted(self.students.values(), key=key)

    def reset_password_to_default(self):
        """把教师密码恢复为默认，并作废已有教师登录会话。"""
        self.password_hash = auth.hash_password(config.DEFAULT_TEACHER_PASSWORD)
        self.sessions = {}
        self.save()

    def create_session(self, username):
        token = auth.new_token()
        self.sessions[token] = {
            "username": username,
            "expires": auth.session_expiry(),
        }
        return token

    def check_session(self, token):
        if not token:
            return False
        session = self.sessions.get(token)
        if not session:
            return False
        if not auth.session_valid(session["expires"]):
            self.sessions.pop(token, None)
            return False
        return True

    def bind_student_token(self, device_id):
        old = self.device_tokens.pop(device_id, None)
        if old:
            self.student_tokens.pop(old, None)
        token = auth.new_token()
        self.student_tokens[token] = device_id
        self.device_tokens[device_id] = token
        return token

    def student_by_token(self, token):
        if not token:
            return None
        device_id = self.student_tokens.get(token)
        if not device_id:
            return None
        return self.students.get(device_id)

    def touch(self, device_id):
        student = self.students.get(device_id)
        if student:
            student.last_seen = time.time()
            student.online = True

    def mark_offline_stale(self, now=None):
        if now is None:
            now = time.time()
        changed = []
        for student in self.students.values():
            if student.online and now - student.last_seen > config.OFFLINE_AFTER:
                student.online = False
                student.focus_requested = False
                changed.append(student.device_id)
        return changed

    def end_class_cleanup(self):
        self.class_active = False
        self.broadcast_active = False
        self.broadcast_shrink = False
        self.web_restrict_enabled = False
        for student in self.students.values():
            student.locked = False
            student.focus_requested = False
        # 下课立即丢弃画面，避免课后仍展示抓屏。
        self.thumbs.clear()
        self.focus_frames.clear()
        self.broadcast_frame = None
        self.broadcast_frame_at = 0.0
        self.remote_device_id = None
