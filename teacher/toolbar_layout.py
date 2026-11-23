# -*- coding: utf-8 -*-
"""教师工具栏换行布局（纯计算，可在 Linux 测试）。

窗口不够宽时折到下一行，绝不把按钮丢在 (0,0) 或裁掉。
"""
from __future__ import print_function

DEFAULT_GROUPS = (
    ("课堂", ("class", "refresh_code")),
    ("控制", ("lock_all", "unlock_all", "remote")),
    ("屏幕", ("broadcast", "shrink", "broadcast_image")),
    ("教学", ("announce", "question", "file")),
    ("限制", ("restrict", "restrict_lists", "desktop", "desktop_unlock")),
)

DEFAULT_WIDTHS = {
    "class": 120,
    "refresh_code": 64,
    "lock_all": 90,
    "unlock_all": 90,
    "remote": 90,
    "broadcast": 120,
    "shrink": 90,
    "broadcast_image": 90,
    "announce": 80,
    "question": 80,
    "file": 80,
    "restrict": 170,
    "restrict_lists": 120,
    "desktop": 150,
    "desktop_unlock": 120,
}

# 「开始上课」更显眼
DEFAULT_SPECIAL = {
    "class": {"w": 120, "h": 32},
}


def layout_toolbar(
    area_width,
    groups=None,
    widths=None,
    special=None,
    pad=8,
    gap=6,
    group_gap=14,
    row_h=26,
    label_w=36,
    start_y=0,
):
    """计算每个按钮和分组标签的位置。

    返回 (items, total_height)。items 为 dict 列表：
    name/label/x/y/w/h；分组标签的 name 以 'label:' 开头。
    """
    groups = groups if groups is not None else DEFAULT_GROUPS
    widths = widths or DEFAULT_WIDTHS
    special = special if special is not None else DEFAULT_SPECIAL
    area_width = max(int(area_width or 0), 1)
    inner = max(area_width - pad * 2, 40)

    items = []
    x = pad
    y = int(start_y)
    row_height = row_h

    # Use a simple state list so this is Python 3.8 friendly without nonlocal confusion
    state = [x, y, row_height]

    def ensure_space(w, h):
        cx, cy, rh = state
        if cx > pad and cx + w > area_width - pad:
            cx = pad
            cy += rh + 6
            rh = row_h
        if w > inner:
            w = inner
        # 即使第一列也很窄，也从 pad 开始放，绝不用 (0,0) 当「放不下」的垃圾坐标
        if cx < pad:
            cx = pad
        state[0], state[1], state[2] = cx, cy, max(rh, h)
        return w

    for group_label, names in groups:
        names = list(names)
        # 估算本组宽度，整组尽量放在同一行；放不下则整组换行（单个仍可再拆）
        group_w = (label_w + 4 if group_label else 0)
        for i, name in enumerate(names):
            spec = (special or {}).get(name) or {}
            group_w += int(spec.get("w", widths.get(name, 90)))
            if i < len(names) - 1:
                group_w += gap
        if state[0] > pad and state[0] + group_w > area_width - pad:
            state[0], state[1], state[2] = pad, state[1] + state[2] + 6, row_h

        if group_label:
            lw = label_w
            lw = ensure_space(lw, 18)
            cx, cy, rh = state
            items.append({
                "name": "label:%s" % group_label,
                "label": group_label,
                "x": cx,
                "y": cy + max(0, (rh - 18) // 2),
                "w": lw,
                "h": 18,
            })
            state[0] = cx + lw + 4

        for name in names:
            spec = (special or {}).get(name) or {}
            w = int(spec.get("w", widths.get(name, 90)))
            h = int(spec.get("h", row_h))
            w = ensure_space(w, h)
            cx, cy, rh = state
            items.append({
                "name": name,
                "label": "",
                "x": cx,
                "y": cy,
                "w": w,
                "h": h,
            })
            state[0] = cx + w + gap
        state[0] = state[0] + max(group_gap - gap, 0)

    total_h = (state[1] + state[2]) - int(start_y) + 8
    return items, max(total_h, row_h + 8)


