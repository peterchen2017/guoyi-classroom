# -*- coding: utf-8 -*-
"""1.2.7：屏幕墙卡片/缓存、工具栏换行、远程控制协议（Linux 可跑，不打开 Win32 窗口）。"""

from __future__ import print_function

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from teacher.toolbar_layout import layout_toolbar
from teacher.wall_logic import (
    ThumbCache,
    build_wall_entries,
    tile_status_text,
    wall_empty_message,
    WALL_EMPTY_BEFORE_CLASS,
    WALL_WAITING,
)
from teacher import state_view
from shared.remote_protocol import (
    RemoteHub,
    is_remote_message,
    old_client_ignore,
    sanitize_event,
    sanitize_events,
    start_message,
    stop_message,
    input_message,
)
from student.remote_input import apply_events
from shared.jpeg_decode import decode_jpeg_bgrx, _decode_gdiplus
from shared.version import VERSION


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


def test_wall(chk):
    chk.check("版本为 1.2.7", VERSION == "1.2.7", VERSION)
    idle = {"class_active": False, "students": [
        {"device_id": "a", "approved": True, "online": True},
    ]}
    chk.check("未上课屏幕墙为空", state_view.wall_students(idle) == [])
    chk.check("未上课空状态提示显眼", wall_empty_message(idle) == WALL_EMPTY_BEFORE_CLASS)
    chk.check("提示含开始上课", "开始上课" in WALL_EMPTY_BEFORE_CLASS)

    active = {
        "class_active": True,
        "students": [
            {"device_id": "ok", "name": "甲", "approved": True, "online": True},
            {"device_id": "off", "name": "乙", "approved": True, "online": False},
            {"device_id": "pend", "name": "丙", "approved": False, "online": True},
        ],
    }
    wall = state_view.wall_students(active)
    chk.check("上课后已批准在线即上墙（不要 thumb_at）", [s["device_id"] for s in wall] == ["ok"])
    entries = build_wall_entries(active)
    chk.check("新卡片先显示等待画面", entries[0]["status_text"] == WALL_WAITING)
    chk.check("等待文案", tile_status_text(False, None, True) == WALL_WAITING)
    chk.check("失败文案明确", "取屏失败" in tile_status_text(False, "取屏失败：HTTP 500", False))

    cache = ThumbCache(retry_waiting=2.0, retry_error=5.0)
    chk.check("尚无画面时应拉取", cache.should_fetch("ok", None, 10.0) is True)
    cache.mark_waiting("ok", None, 10.0)
    chk.check("等待期内不重复狂拉", cache.should_fetch("ok", None, 11.0) is False)
    chk.check("等待期满再拉", cache.should_fetch("ok", None, 13.0) is True)

    # 缩略图先到、格子未建：先缓存
    cache.mark_fetched("late", 3.14, b"JPEGDATA")
    pending = {"class_active": True, "students": [
        {"device_id": "late", "name": "丁", "approved": True, "online": True, "thumb_at": 3.14},
    ]}
    filled = build_wall_entries(pending, cache)
    chk.check("先到的画面会填进后建的格子", filled[0]["image_bytes"] == b"JPEGDATA")
    chk.check("已有该帧则不再拉", cache.should_fetch("late", 3.14, 100.0) is False)
    chk.check("新时间戳会再拉", cache.should_fetch("late", 3.15, 100.0) is True)

    cache.mark_error("err", None, "取屏失败：无法连接教师机服务", 20.0)
    chk.check("失败后有退避", cache.should_fetch("err", None, 21.0) is False)
    chk.check("失败后到期再试（不会因记过时间戳而永远不拉）", cache.should_fetch("err", None, 26.0) is True)
    bad = {"class_active": True, "students": [
        {"device_id": "err", "name": "戊", "approved": True, "online": True},
    ]}
    err_entries = build_wall_entries(bad, cache)
    chk.check("失败格子有明确文字", "取屏失败" in (err_entries[0]["status_text"] or ""))


def test_toolbar(chk):
    items, height = layout_toolbar(1400)
    buttons = [i for i in items if not i["name"].startswith("label:")]
    labels = [i for i in items if i["name"].startswith("label:")]
    names = [i["name"] for i in buttons]
    chk.check("宽窗口包含全部分组标签", {"课堂", "控制", "屏幕", "教学", "限制"} <= set(i["label"] for i in labels))
    chk.check("开始上课按钮在布局中", "class" in names)
    chk.check("远程控制按钮在布局中", "remote" in names)
    chk.check("宽窗口没有按钮落在 (0,0)", all(i["x"] > 0 and i["y"] >= 0 for i in items))
    chk.check("开始上课按钮更大", any(i["name"] == "class" and i["h"] >= 32 for i in items))

    mid, h2 = layout_toolbar(480)
    chk.check("窄窗口会换行", h2 > height)
    chk.check("换行后仍没有 (0,0)", all(i["x"] > 0 and i["y"] >= 0 for i in mid))
    mid_names = [i["name"] for i in mid if not i["name"].startswith("label:")]
    chk.check("换行不丢按钮", set(names) == set(mid_names), str(set(names) ^ set(mid_names)))

    tiny, h3 = layout_toolbar(160)
    chk.check("极窄窗口也全部放下", len([i for i in tiny if not i["name"].startswith("label:")]) == len(names))
    chk.check("极窄窗口也不用 (0,0)", all(i["x"] > 0 for i in tiny), str([(i["name"], i["x"], i["y"]) for i in tiny if i["x"] <= 0]))


def test_remote_protocol(chk):
    hub = RemoteHub()
    ok, reason, prev = hub.start("s1", False, True, True)
    chk.check("未上课不能开始远程控制", ok is False and "上课" in reason)
    ok, reason, prev = hub.start("s1", True, False, True)
    chk.check("未批准不能控制", ok is False)
    ok, reason, prev = hub.start("s1", True, True, True)
    chk.check("上课后可开始控制", ok is True and hub.target_id == "s1")
    ok, reason, prev = hub.start("s2", True, True, True)
    chk.check("换学生时交还上一台", ok is True and prev == "s1" and hub.target_id == "s2")
    chk.check("一次只控制一台", hub.target_id == "s2")

    ok, reason, evs = hub.accept_input("s1", [{"kind": "move", "x": 0.2, "y": 0.3}], True)
    chk.check("不能向未作为目标的学生发输入", ok is False)
    ok, reason, evs = hub.accept_input("s2", [
        {"kind": "move", "x": 1.5, "y": -1},
        {"kind": "down", "btn": "left", "x": 0.4, "y": 0.5},
        {"kind": "keydown", "vk": 13},
        {"kind": "spy"},
        {"kind": "keydown", "vk": 0},
        "bad",
    ], True)
    chk.check("合法事件被保留", ok is True and len(evs) == 3)
    chk.check("坐标被限制在 0–1", evs[0]["x"] == 1.0 and evs[0]["y"] == 0.0)
    chk.check("非法事件被丢掉", sanitize_event({"kind": "keydown", "vk": 999}) is None)

    stopped = hub.stop_if_class_ended(False)
    chk.check("下课立即停止控制", stopped == "s2" and hub.target_id is None)
    ok, reason, evs = hub.accept_input("s2", [{"kind": "move", "x": 0.1, "y": 0.1}], False)
    chk.check("课后不再接受输入", ok is False)

    chk.check("start 消息类型", start_message()["type"] == "remote_start")
    chk.check("stop 消息类型", stop_message()["type"] == "remote_stop")
    chk.check("input 消息清洗", input_message([{"kind": "move", "x": 2, "y": 0}])["events"][0]["x"] == 1.0)

    # 1.2.6 学生端忽略未知类型
    old_known = ("welcome", "approved", "revoked", "class_start", "class_end", "lock", "unlock",
                 "announce", "question", "file", "broadcast_start", "broadcast_end", "broadcast_frame",
                 "focus", "error", "web_restrict", "desktop_lock", "desktop_unlock")
    for typ in ("remote_start", "remote_stop", "remote_input"):
        chk.check("旧客户端忽略 %s 且不崩溃" % typ, old_client_ignore(old_known, typ) == "ignored")
        chk.check("%s 属于远程消息" % typ, is_remote_message(typ) is True)

    recorded = []
    applied = apply_events(
        [{"kind": "move", "x": 0.2, "y": 0.8}, {"kind": "keydown", "vk": 65}, {"kind": "unknown"}],
        injector=recorded.append,
    )
    chk.check("模拟注入不走 Win32 SendInput", len(applied) == 2 and recorded == applied)
    chk.check("Linux 导入 remote_input 不要求 SendInput", True)

    # jpeg 解码：Linux 不得因导入 GDI+ 塌掉
    chk.check("Linux 上 GDI+ 回退函数可引用但未在导入时调用", callable(_decode_gdiplus))
    try:
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.new("RGB", (8, 6), (10, 20, 30)).save(buf, format="JPEG", quality=80)
        data = buf.getvalue()
        got = decode_jpeg_bgrx(data)
        chk.check("Pillow 路径能解码 JPEG", got is not None and got[0] == 8 and got[1] == 6)
    except Exception as exc:
        chk.check("Pillow 路径能解码 JPEG", False, str(exc))
    chk.check("空数据返回 None", decode_jpeg_bgrx(b"") is None)
    chk.check("坏数据返回 None 而不抛", decode_jpeg_bgrx(b"not-a-jpeg") is None)


def main():
    chk = Checker()
    test_wall(chk)
    test_toolbar(chk)
    test_remote_protocol(chk)
    ok = chk.summary()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
