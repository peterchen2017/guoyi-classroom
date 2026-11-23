# -*- coding: utf-8 -*-
"""上课期间网页游戏 / 随意下载的判断逻辑（按主机名与 URL，不做 HTTPS 解密）。"""

from urllib.parse import unquote, urlparse

# 常见中文小游戏门户及其常见子域后缀（匹配自身及所有子域）。
DEFAULT_GAME_DOMAINS = [
    "4399.com", "4399.cn", "4399ie.com", "4399api.com", "4399youpai.com",
    "4399pk.com", "i4399.com", "5054399.com", "box4399.com",
    "7k7k.com", "7k7k.cn",
    "3366.com", "3366img.com", "3366.cn",
    "2144.com", "2144.cn",
    "17yy.com",
    "7724.com",
    "3839.com",
    "2217.com",
    "4366.com",
    "5799.com",
    "265g.com",
    "07073.com",
    "52pk.com",
    "61.com",
    "51mole.com",
    "xiaoyouxi.com",
    "u7u9.com",
    "87g.com",
    "66rpg.com",
    "4355.com",
    "65111.com",
    "8090y.com",
    "8090.com",
    "9377.com",
    "966.com",
    "9665.com",
    "swjoy.com",
    "aoshitang.com",
    "kuaiwan.com",
    "6711.com",
    "91wan.com",
    "37.com",
    "37wan.com",
    "17173.com",
    "game.hao123.com",
    "game.2345.com",
    "minigame.qq.com",
    "game.qq.com",
    "qqgame.qq.com",
    "speed.qq.com",
    "kid.qq.com",
    "game.163.com",
    "minigame.163.com",
    "igame.163.com",
    "wan.360.cn",
    "game.360.cn",
    "game.bilibili.com",
    "biligame.com",
    "9game.cn",
]

# 常见网盘、下载站、种子站（按域名拦截，HTTPS 看不到路径）。
DEFAULT_DOWNLOAD_DOMAINS = [
    "pan.baidu.com", "yun.baidu.com", "baidupcs.com",
    "xunlei.com", "sandai.net",
    "123pan.com", "123684.com", "123652.com",
    "alipan.com", "aliyundrive.com",
    "lanzou.com", "lanzoui.com", "lanzoux.com", "lanzouy.com", "lanzouw.com",
    "weiyun.com",
    "115.com",
    "ctfile.com",
    "jianguoyun.com",
    "wenshushu.cn", "wss1.cn",
    "cowtransfer.com",
    "onlinedown.net", "crsky.com", "skycn.com", "xiazaiba.com",
    "downxia.com", "3987.com",
    "softonic.com",
    "mediafire.com",
    "mega.nz", "mega.co.nz",
    "1drv.ms",
    "cloud.189.cn",
]

DEFAULT_EXTENSIONS = [
    ".exe", ".msi", ".bat", ".cmd", ".scr",
    ".zip", ".rar", ".7z", ".iso", ".apk", ".torrent",
]

NOTICE = "上课期间已限制网页游戏和下载"


def default_game_domains():
    return list(DEFAULT_GAME_DOMAINS)


def default_download_domains():
    return list(DEFAULT_DOWNLOAD_DOMAINS)


def default_extensions():
    return list(DEFAULT_EXTENSIONS)


def normalize_domain(value):
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("http://", "").replace("https://", "")
    text = text.split("/")[0].split("?")[0].strip()
    if text.startswith("[") and "]" in text:
        text = text[1:text.index("]")]
    if text.startswith("*."):
        text = text[2:]
    text = text.lstrip(".")
    if ":" in text and text.count(":") == 1:
        host, port = text.split(":", 1)
        if port.isdigit():
            text = host
    if text.startswith("www.") and text.count(".") >= 2:
        # 名单里统一不带 www.，匹配时会覆盖子域。
        pass
    return text.rstrip(".")


def normalize_list(values):
    seen = set()
    out = []
    for item in values or []:
        d = normalize_domain(item) if not str(item).startswith(".") else ("." + normalize_domain(item.lstrip(".")))
        # extensions start with .
        raw = (item or "").strip().lower()
        if raw.startswith(".") and " " not in raw and "/" not in raw:
            d = raw if raw.startswith(".") else raw
            if not d.startswith("."):
                d = "." + d
        else:
            d = normalize_domain(item)
        if not d or d in seen:
            continue
        seen.add(d)
        out.append(d)
    return out


def normalize_exts(values):
    seen = set()
    out = []
    for item in values or []:
        e = (item or "").strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = "." + e
        e = e.split("/")[0].split("?")[0]
        if e in seen or len(e) < 2:
            continue
        seen.add(e)
        out.append(e)
    return out


def host_only(host):
    text = (host or "").strip().lower()
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")]
    if text.count(":") == 1:
        h, p = text.split(":", 1)
        if p.isdigit():
            return h
    return text.rstrip(".")


def host_matches(host, patterns):
    host = host_only(host)
    if not host:
        return False
    for raw in patterns or []:
        p = normalize_domain(raw)
        if not p:
            continue
        if host == p or host.endswith("." + p):
            return True
        # IPv4 精确匹配
        if host == p:
            return True
    return False


def url_has_blocked_extension(url, extensions):
    exts = normalize_exts(extensions)
    if not exts:
        return False
    text = unquote((url or "").replace("\\", "/")).lower()
    # 只检查路径和查询，不把主机名里的 .com 等当成文件。
    try:
        parsed = urlparse(text)
        path = parsed.path or ""
        query = parsed.query or ""
        fragment = parsed.fragment or ""
    except Exception:
        path, query, fragment = text, "", ""
    blob = path
    if query:
        blob = blob + "?" + query
    if fragment:
        blob = blob + "#" + fragment
    if not blob:
        return False
    for ext in exts:
        # .exe 出现在路径结尾或后面紧跟分隔符，避免误伤 exercise
        i = 0
        while True:
            i = blob.find(ext, i)
            if i < 0:
                break
            end = i + len(ext)
            if end == len(blob) or blob[end] in "/?#&":
                return True
            i = end
    return False


def host_from_url(url, fallback=""):
    try:
        parsed = urlparse(url or "")
        if parsed.hostname:
            return parsed.hostname.lower()
    except Exception:
        pass
    return host_only(fallback)


def is_bypass_host(host, teacher_ips, teacher_port, whitelist):
    host = host_only(host)
    if not host:
        return True
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if host_matches(host, teacher_ips or []):
        return True
    if host_matches(host, whitelist or []):
        return True
    return False


def decide(host, url, rules):
    """返回 (blocked: bool, reason: str)。rules 为字典。"""
    rules = rules or {}
    teacher_ips = rules.get("teacher_ips") or []
    whitelist = rules.get("whitelist_domains") or []
    teacher_port = rules.get("teacher_port")
    host = host_from_url(url, host)
    if is_bypass_host(host, teacher_ips, teacher_port, whitelist):
        return False, "whitelist"
    if host_matches(host, rules.get("game_domains") or []):
        return True, "game"
    if host_matches(host, rules.get("download_domains") or []):
        return True, "download-site"
    if url and url_has_blocked_extension(url, rules.get("extensions") or DEFAULT_EXTENSIONS):
        return True, "download-file"
    return False, "allow"


def block_page_html(reason=""):
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<title>%s</title>"
        "<style>body{font-family:'Microsoft YaHei',sans-serif;background:#1a365d;"
        "color:#fff;text-align:center;padding:12vh 24px;}h1{font-size:28px;}"
        "p{opacity:.9;}</style></head><body>"
        "<h1>%s</h1>"
        "<p>请认真听老师讲课。此提示由「课堂管理」客户端显示，下课或老师关闭限制后会自动恢复上网设置。</p>"
        "<p>课堂下发的资料不受影响。</p>"
        "</body></html>"
    ) % (NOTICE, NOTICE)
