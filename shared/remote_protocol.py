# -*- coding: utf-8 -*-
"""远程控制协议与状态机（纯逻辑，可在 Linux 测试）。

消息类型 remote_start / remote_stop / remote_input。旧版学生端不认识这些
type 时应忽略且不崩溃。一次只控制一台学生机。
"""
from __future__ import print_function

MSG_START = "remote_start"
MSG_STOP = "remote_stop"
MSG_INPUT = "remote_input"

KINDS = ("move", "down", "up", "wheel", "keydown", "keyup")
BUTTONS = ("left", "right", "middle")
MAX_EVENTS = 40


def is_remote_message(typ):
    return typ in (MSG_START, MSG_STOP, MSG_INPUT)


def clamp01(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def sanitize_event(raw):
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind") or raw.get("t")
    if kind not in KINDS:
        return None
    ev = {"kind": kind}
    if kind in ("move", "down", "up", "wheel"):
        ev["x"] = clamp01(raw.get("x", 0))
        ev["y"] = clamp01(raw.get("y", 0))
    if kind in ("down", "up"):
        btn = raw.get("btn") or raw.get("button") or "left"
        if btn not in BUTTONS:
            btn = "left"
        ev["btn"] = btn
    if kind == "wheel":
        try:
            ev["delta"] = int(raw.get("delta") or 0)
        except (TypeError, ValueError):
            ev["delta"] = 0
        if ev["delta"] > 360:
            ev["delta"] = 360
        if ev["delta"] < -360:
            ev["delta"] = -360
    if kind in ("keydown", "keyup"):
        try:
            vk = int(raw.get("vk") or 0)
        except (TypeError, ValueError):
            return None
        if vk < 1 or vk > 254:
            return None
        ev["vk"] = vk
    return ev


def sanitize_events(events):
    out = []
    for item in events or []:
        ev = sanitize_event(item)
        if ev is not None:
            out.append(ev)
        if len(out) >= MAX_EVENTS:
            break
    return out


def start_message():
    return {"type": MSG_START}


def stop_message():
    return {"type": MSG_STOP}


def input_message(events):
    return {"type": MSG_INPUT, "events": sanitize_events(events)}


class RemoteHub(object):
    """教师机一侧的会话：一次只控制一台。"""

    def __init__(self):
        self.target_id = None

    def start(self, student_id, class_active, approved, online):
        if not class_active:
            return False, "请先开始上课", None
        if not student_id:
            return False, "请先选择一名学生", None
        if not approved or not online:
            return False, "只能控制已加入且在线的学生机", None
        prev = self.target_id
        if prev == student_id:
            return True, "already", prev
        self.target_id = student_id
        return True, "started", prev

    def stop(self, student_id=None):
        if student_id is not None and self.target_id != student_id:
            return None
        prev = self.target_id
        self.target_id = None
        return prev

    def stop_if_class_ended(self, class_active):
        if class_active:
            return None
        return self.stop()

    def accept_input(self, student_id, events, class_active):
        if not class_active:
            return False, "请先开始上课", []
        if not self.target_id or self.target_id != student_id:
            return False, "当前没有控制这台学生机", []
        cleaned = sanitize_events(events)
        return True, "ok", cleaned


def old_client_ignore(handler, typ, payload=None):
    """模拟 1.2.6 学生端：不认识的 type 直接忽略。"""
    known = set(handler or ())
    if typ in known:
        return "handled"
    if is_remote_message(typ):
        return "ignored"
    return "ignored"
