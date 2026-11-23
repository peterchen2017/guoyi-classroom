# -*- coding: utf-8 -*-
"""屏幕墙条目与缩略图缓存（纯逻辑，可在 Linux 测试）。

修正：缩略图先到、格子未建时先缓存；不要因记过 _thumb_at 而永远不再拉。
"""
from __future__ import print_function

WALL_EMPTY_BEFORE_CLASS = "请先点左上角「开始上课」，学生机才会传来画面"
WALL_EMPTY_NO_STUDENT = "还没有已加入且在线的学生机。请在左侧允许学生加入课堂。"
WALL_WAITING = "等待画面…"
WALL_NO_FRAME = "暂无画面"


def wall_empty_message(state):
    state = state or {}
    if not state.get("class_active"):
        return WALL_EMPTY_BEFORE_CLASS
    return WALL_EMPTY_NO_STUDENT


def tile_status_text(has_image, error=None, waiting=False):
    if has_image:
        return ""
    if error:
        return error
    if waiting:
        return WALL_WAITING
    return WALL_NO_FRAME


def tile_caption(student, controlling=False):
    student = student or {}
    name = student.get("name") or "学生"
    bits = []
    if student.get("locked"):
        bits.append("已锁屏")
    if controlling:
        bits.append("远程控制中")
    if student.get("online"):
        if not bits:
            bits.append("在线")
    else:
        bits.append("离线")
    return "%s  %s" % (name, " · ".join(bits))


class ThumbCache(object):
    """按学生缓存最近一次成功的 JPEG，以及失败/等待信息。"""

    def __init__(self, retry_waiting=1.0, retry_error=2.0):
        self.images = {}  # sid -> {at, bytes}
        self.errors = {}  # sid -> message
        self._retry_after = {}  # (sid, at) -> timestamp
        self.retry_waiting = retry_waiting
        self.retry_error = retry_error

    def get(self, sid):
        return self.images.get(sid)

    def error(self, sid):
        if sid in self.images and self.images[sid].get("bytes"):
            return None
        return self.errors.get(sid)

    def should_fetch(self, sid, at, now):
        if not sid:
            return False
        cached = self.images.get(sid)
        if at and cached and cached.get("at") == at and cached.get("bytes"):
            return False
        due = self._retry_after.get((sid, at), 0)
        if now < due:
            return False
        return True

    def mark_fetched(self, sid, at, data):
        if not sid or not data:
            return
        self.images[sid] = {"at": at, "bytes": data}
        self.errors.pop(sid, None)
        self._retry_after.pop((sid, at), None)

    def mark_waiting(self, sid, at, now):
        self._retry_after[(sid, at)] = now + self.retry_waiting
        if sid not in self.images or not self.images[sid].get("bytes"):
            self.errors.pop(sid, None)

    def mark_error(self, sid, at, message, now):
        if sid not in self.images or not self.images[sid].get("bytes"):
            self.errors[sid] = message or "取屏失败"
        self._retry_after[(sid, at)] = now + self.retry_error

    def evict_missing(self, live_ids):
        live = set(live_ids or [])
        for sid in list(self.images.keys()):
            if sid not in live:
                self.images.pop(sid, None)
                self.errors.pop(sid, None)
        for key in list(self._retry_after.keys()):
            if key[0] not in live:
                self._retry_after.pop(key, None)

    def apply_to_entries(self, entries):
        """把缓存画面填进格子。即使 set_tiles 时尚无格子，缓存仍保留。"""
        filled = []
        for item in entries:
            item = dict(item)
            sid = item.get("id")
            cached = self.images.get(sid)
            if cached and cached.get("bytes"):
                if item.get("image_bytes") is None:
                    item["image_bytes"] = cached["bytes"]
                if item.get("at") is None:
                    item["at"] = cached.get("at")
            err = self.error(sid)
            has = bool(item.get("image_bytes"))
            waiting = (not has) and (not err)
            item["error"] = err
            item["waiting"] = waiting
            item["status_text"] = tile_status_text(has, err, waiting)
            filled.append(item)
        return filled


def build_wall_entries(state, cache=None, remote_device_id=None):
    from teacher import state_view

    entries = []
    for s in state_view.wall_students(state):
        sid = s.get("device_id")
        entries.append({
            "id": sid,
            "name": s.get("name") or "学生",
            "locked": bool(s.get("locked")),
            "online": bool(s.get("online")),
            "at": s.get("thumb_at"),
            "image_bytes": None,
            "caption": tile_caption(s, controlling=(sid == remote_device_id)),
        })
    if cache is not None:
        live = [e["id"] for e in entries]
        cache.evict_missing(live)
        entries = cache.apply_to_entries(entries)
    else:
        for item in entries:
            item["waiting"] = not item.get("image_bytes")
            item["error"] = None
            item["status_text"] = tile_status_text(False, None, True)
    return entries
