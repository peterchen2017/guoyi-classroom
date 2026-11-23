# -*- coding: utf-8 -*-
"""上网限制逻辑与本机过滤代理验证（Linux 可跑，不改系统代理）。"""

from __future__ import print_function

import io
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from PIL import Image

from shared.web_filter import decide, host_matches, url_has_blocked_extension
from student.filter_proxy import FilterProxy
from server import capture

def http_via_proxy(url, proxy, timeout=5.0):
    """兼容 httpx 0.27（proxies=）与 0.28+（proxy=）。"""
    try:
        return httpx.get(url, proxy=proxy, timeout=timeout, follow_redirects=False)
    except TypeError:
        return httpx.get(url, proxies={"http://": proxy, "https://": proxy}, timeout=timeout, follow_redirects=False)


class Checker(object):
    def __init__(self):
        self.ok = 0
        self.fail = 0

    def check(self, name, cond, detail=""):
        status = "通过" if cond else "失败"
        if cond:
            self.ok += 1
        else:
            self.fail += 1
        print("[%s] %s%s" % (status, name, (" — " + detail) if detail else ""), flush=True)
        return cond

    def summary(self):
        print("上网限制合计：通过 %s，失败 %s" % (self.ok, self.fail), flush=True)
        return self.fail == 0


def default_rules(teacher_ip="127.0.0.1"):
    from shared.web_filter import default_download_domains, default_extensions, default_game_domains
    return {
        "teacher_ips": [teacher_ip, "localhost"],
        "teacher_port": 8765,
        "game_domains": default_game_domains(),
        "download_domains": default_download_domains(),
        "whitelist_domains": ["luogu.com.cn"],
        "extensions": default_extensions(),
    }


def main():
    chk = Checker()
    rules = default_rules()

    chk.check("拦截 4399", decide("www.4399.com", "http://www.4399.com/flash/1.htm", rules)[0])
    chk.check("拦截 7k7k 子域", decide("new.7k7k.com", "https://new.7k7k.com/", rules)[0])
    chk.check("拦截 3366", decide("www.3366.com", "http://www.3366.com/", rules)[0])
    chk.check("拦截 2144", decide("www.2144.cn", "http://www.2144.cn/", rules)[0])
    chk.check("放行普通教学站", not decide("www.example.com", "http://www.example.com/lesson.html", rules)[0])
    chk.check("拦截 HTTP 安装包", decide("cdn.example.com", "http://cdn.example.com/setup.exe", rules)[0])
    chk.check("拦截压缩包 zip", decide("cdn.example.com", "http://files.example.com/a.zip?x=1", rules)[0])
    chk.check("不把 exercise 当成 exe", not url_has_blocked_extension("/homework/exercise.html", [".exe"]))
    chk.check("拦截网盘域名", decide("pan.baidu.com", "https://pan.baidu.com/s/1", rules)[0])
    chk.check("白名单教学站放行", not decide("www.luogu.com.cn", "https://www.luogu.com.cn/problem/P1001", rules)[0])
    chk.check("教师机 IP 放行（含 .exe 下发）", not decide("127.0.0.1", "http://127.0.0.1:8765/api/student/download/x/demo.exe", rules)[0])
    chk.check("C++ 源码扩展名不被当下载拦截", not url_has_blocked_extension("/a.cpp", [".exe", ".zip"]))
    chk.check("host_matches 子域", host_matches("img.4399.com", ["4399.com"]))

    # 缩小画面
    img = Image.new("RGB", (1280, 720), (20, 80, 160))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    raw = buf.getvalue()
    small = capture.scale_jpeg(raw, max_width=800, quality=50)
    out = Image.open(io.BytesIO(small))
    chk.check("缩小画面宽度不超过 800", out.width <= 800, "宽=%s" % out.width)

    # 过滤代理
    origin_port = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            body = b"hello-ok"
            if self.path.endswith(".cpp"):
                body = b"int main(){return 0;}"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    origin = HTTPServer(("127.0.0.1", 0), Handler)
    origin_port = origin.server_address[1]
    th = threading.Thread(target=origin.serve_forever, daemon=True)
    th.start()

    proxy = FilterProxy()
    pport = proxy.start(rules=rules, preferred_port=18780)
    proxy_url = "http://127.0.0.1:%s" % pport
    try:
        r = http_via_proxy("http://www.4399.com/flash/1.htm", proxy_url)
        chk.check("代理拒绝游戏站", r.status_code == 403 and "限制" in r.text)

        r = http_via_proxy("http://cdn.example.com/game.zip", proxy_url)
        chk.check("代理拒绝压缩包下载", r.status_code == 403)

        r = http_via_proxy("http://127.0.0.1:%s/hello.txt" % origin_port, proxy_url)
        chk.check("白名单/教师机地址仍可访问", r.status_code == 200 and r.text == "hello-ok")

        r = http_via_proxy("http://127.0.0.1:%s/hello.cpp" % origin_port, proxy_url)
        chk.check("教师机下发 .cpp 不被拦截", r.status_code == 200 and b"int main" in r.content)

        # CONNECT 游戏站应 403
        sock = socket.create_connection(("127.0.0.1", pport), timeout=5)
        sock.sendall(b"CONNECT www.7k7k.com:443 HTTP/1.1\r\nHost: www.7k7k.com:443\r\n\r\n")
        got = sock.recv(1024).decode("utf-8", "replace")
        sock.close()
        chk.check("CONNECT 拒绝游戏站（按主机名，不解密）", got.startswith("HTTP/1.1 403"))
    finally:
        proxy.stop()
        origin.shutdown()

    chk.check("关闭后代理不再监听", not proxy.running())
    ok = chk.summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
