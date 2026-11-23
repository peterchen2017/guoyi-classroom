# -*- coding: utf-8 -*-
"""本机 HTTP/HTTPS 过滤代理：按主机名（CONNECT/SNI）和 HTTP URL 拦截，不解密 HTTPS。"""

import select
import socket
import threading

from shared.web_filter import NOTICE, block_page_html, decide, host_only

DEFAULT_PORT = 18780


class FilterProxy(object):
    def __init__(self):
        self._sock = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.rules = {}
        self.port = None
        self.last_blocks = []

    def update_rules(self, rules):
        with self._lock:
            self.rules = dict(rules or {})

    def _get_rules(self):
        with self._lock:
            return dict(self.rules)

    def start(self, rules=None, preferred_port=DEFAULT_PORT):
        self.stop()
        self._stop.clear()
        if rules is not None:
            self.update_rules(rules)
        last_err = None
        sock = None
        port = None
        candidates = [preferred_port] + list(range(preferred_port + 1, preferred_port + 10)) + [0]
        for cand in candidates:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", cand))
                s.listen(50)
                s.settimeout(0.5)
                sock = s
                port = s.getsockname()[1]
                break
            except OSError as exc:
                last_err = exc
                try:
                    s.close()
                except Exception:
                    pass
        if sock is None:
            raise RuntimeError("无法绑定本地过滤代理端口：%s" % last_err)
        self._sock = sock
        self.port = port
        self._thread = threading.Thread(target=self._accept_loop, name="classroom-filter-proxy", daemon=True)
        self._thread.start()
        return port

    def stop(self):
        self._stop.set()
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self.port = None

    def running(self):
        return self._sock is not None and not self._stop.is_set()

    def _accept_loop(self):
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    break
                continue
            t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
            t.start()

    def _handle(self, conn):
        conn.settimeout(20)
        try:
            data = _recv_headers(conn)
            if not data:
                return
            first, headers, rest = _parse_head(data)
            if not first:
                return
            parts = first.split(" ")
            method = parts[0].upper() if parts else ""
            target = parts[1] if len(parts) > 1 else ""
            if method == "CONNECT":
                self._handle_connect(conn, target)
                return
            host = _header(headers, "Host") or ""
            url = target
            if url.startswith("/"):
                url = "http://%s%s" % (host, url)
            blocked, reason = decide(host, url, self._get_rules())
            if blocked:
                _log_block(self, reason, host, url)
                _send_block(conn)
                return
            self._forward_http(conn, first, headers, rest, host)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _handle_connect(self, conn, target):
        hostport = target.strip()
        host = host_only(hostport)
        # CONNECT 只能看到主机名/端口，不能看路径（不解密）。
        url = "https://%s/" % host
        blocked, reason = decide(host, url, self._get_rules())
        if blocked:
            _log_block(self, reason, host, url)
            try:
                body = block_page_html(reason).encode("utf-8")
                conn.sendall(
                    b"HTTP/1.1 403 Forbidden\r\n"
                    b"Content-Type: text/html; charset=utf-8\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
                )
            except Exception:
                pass
            return
        port = 443
        if ":" in hostport and not hostport.startswith("["):
            try:
                host, port_s = hostport.rsplit(":", 1)
                port = int(port_s)
                host = host_only(host)
            except ValueError:
                host = host_only(hostport)
        try:
            remote = socket.create_connection((host, port), timeout=10)
        except Exception:
            try:
                conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            except Exception:
                pass
            return
        try:
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            _tunnel(conn, remote)
        finally:
            try:
                remote.close()
            except Exception:
                pass

    def _forward_http(self, conn, first, headers, rest, host):
        parts = first.split(" ")
        target = parts[1] if len(parts) > 1 else "/"
        port = 80
        hostname = host_only(host)
        if ":" in (host or "") and host.count(":") == 1:
            hostname, port_s = host.split(":", 1)
            try:
                port = int(port_s)
            except ValueError:
                port = 80
        path = target
        if target.startswith("http://") or target.startswith("https://"):
            # 绝对 URL：改为路径
            from urllib.parse import urlparse
            parsed = urlparse(target)
            path = parsed.path or "/"
            if parsed.query:
                path = path + "?" + parsed.query
            if parsed.hostname:
                hostname = parsed.hostname
            if parsed.port:
                port = parsed.port
        req = " ".join([parts[0], path] + parts[2:]) if len(parts) >= 2 else first
        lines = [req]
        have_close = False
        for k, v in headers:
            if k.lower() == "proxy-connection":
                continue
            if k.lower() == "connection":
                lines.append("Connection: close")
                have_close = True
                continue
            lines.append("%s: %s" % (k, v))
        if not have_close:
            lines.append("Connection: close")
        head = "\r\n".join(lines) + "\r\n\r\n"
        try:
            remote = socket.create_connection((hostname, port), timeout=10)
        except Exception:
            try:
                conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            except Exception:
                pass
            return
        try:
            remote.sendall(head.encode("utf-8", "replace") + rest)
            _tunnel(conn, remote)
        finally:
            try:
                remote.close()
            except Exception:
                pass


def _log_block(proxy, reason, host, url):
    rec = {"reason": reason, "host": host, "url": (url or "")[:200]}
    with proxy._lock:
        proxy.last_blocks.append(rec)
        if len(proxy.last_blocks) > 50:
            proxy.last_blocks = proxy.last_blocks[-50:]


def _send_block(conn):
    body = block_page_html().encode("utf-8")
    conn.sendall(
        b"HTTP/1.1 403 Forbidden\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"Cache-Control: no-store\r\n"
        b"Connection: close\r\n"
        b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
    )


def _recv_headers(conn, limit=65536):
    buf = b""
    while b"\r\n\r\n" not in buf and len(buf) < limit:
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf


def _parse_head(data):
    if b"\r\n\r\n" in data:
        head, rest = data.split(b"\r\n\r\n", 1)
    else:
        head, rest = data, b""
    try:
        text = head.decode("iso-8859-1")
    except Exception:
        text = head.decode("utf-8", "replace")
    lines = text.split("\r\n")
    if not lines:
        return "", [], rest
    headers = []
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers.append((k.strip(), v.strip()))
    return lines[0], headers, rest


def _header(headers, name):
    name = name.lower()
    for k, v in headers:
        if k.lower() == name:
            return v
    return ""


def _tunnel(a, b, timeout=20):
    sockets = [a, b]
    try:
        a.settimeout(timeout)
        b.settimeout(timeout)
    except Exception:
        pass
    while True:
        try:
            r, _w, _x = select.select(sockets, [], sockets, timeout)
        except Exception:
            break
        if not r:
            break
        for src in r:
            dst = b if src is a else a
            try:
                data = src.recv(16384)
            except Exception:
                return
            if not data:
                return
            try:
                dst.sendall(data)
            except Exception:
                return
