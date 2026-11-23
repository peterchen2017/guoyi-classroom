# -*- coding: utf-8 -*-
"""把 /api/state 映射成窗口上要用的文案。不含 Win32，可在 Linux 测试。"""

from __future__ import print_function


def status_label(student):
    student = student or {}
    if (not student.get("approved")) and student.get("online"):
        return "待批准"
    if student.get("online") and student.get("locked"):
        return "在线 · 已锁屏"
    if student.get("online"):
        return "在线"
    if student.get("approved"):
        return "离线"
    return "未加入"


def student_line(student):
    student = student or {}
    name = student.get("name") or "学生"
    bits = [status_label(student)]
    if student.get("hostname"):
        bits.append(student.get("hostname"))
    if student.get("ip"):
        bits.append(student.get("ip"))
    return "%s  %s" % (name, " · ".join(bits))


def student_summary(state):
    students = (state or {}).get("students") or []
    online = 0
    pending = 0
    for s in students:
        if s.get("online"):
            online += 1
        if (not s.get("approved")) and s.get("online"):
            pending += 1
    text = "在线 %s" % online
    if pending:
        text += " · 待批准 %s" % pending
    text += " · 共 %s" % len(students)
    return text


def class_pill_text(state):
    state = state or {}
    if not state.get("class_active"):
        return "未上课"
    if state.get("broadcast_active"):
        return "上课中 · 正在广播"
    return "上课中"


def toolbar_captions(state):
    state = state or {}
    wr = state.get("web_restrict") or {}
    desk = state.get("desktop") or {}
    return {
        "class": "下课" if state.get("class_active") else "开始上课",
        "broadcast": "停止广播" if state.get("broadcast_active") else "广播教师屏幕",
        "restrict": "关闭网页/下载限制" if wr.get("enabled") else "限制网页游戏和下载",
        "desktop": "更换默认桌面（已锁定）" if desk.get("locked") else "设置默认桌面",
        "desktop_unlock_enabled": bool(desk.get("locked")),
        "shrink": bool(state.get("broadcast_shrink")),
    }


def wall_students(state):
    state = state or {}
    if not state.get("class_active"):
        return []
    rows = []
    for s in state.get("students") or []:
        if s.get("approved") and s.get("online") and s.get("thumb_at"):
            rows.append(s)
    return rows


def find_student(state, device_id):
    for s in (state or {}).get("students") or []:
        if s.get("device_id") == device_id:
            return s
    return None


def format_lan_banner(ips, port=8765):
    ips = [ip for ip in (ips or []) if ip and not str(ip).startswith("127.")]
    if not ips:
        return "本机局域网 IP 未能自动识别，请运行 ipconfig 查看。手机请打开 http://教师机IP:%s" % port
    if len(ips) == 1:
        return "本机 IP %s    手机请打开 http://%s:%s" % (ips[0], ips[0], port)
    shown = "  /  ".join(ips)
    first = ips[0]
    return "本机 IP %s    手机请打开 http://%s:%s" % (shown, first, port)


def split_lines(text):
    rows = []
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        item = line.strip()
        if item:
            rows.append(item)
    return rows
