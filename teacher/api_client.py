# -*- coding: utf-8 -*-
"""教师控制台 HTTP 客户端。只使用标准库，安装包里不带 httpx。

可在 Linux 上对着本机 FastAPI 服务做测试。鉴权方式与 web/app.js 一致：
Authorization: Bearer <token>
"""

from __future__ import print_function

import json
import mimetypes
import os
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class TeacherApiError(Exception):
    def __init__(self, message, status=None, payload=None):
        Exception.__init__(self, message)
        self.status = status
        self.payload = payload


class AuthExpired(TeacherApiError):
    pass


def _detail(data, default="请求失败"):
    if data is None:
        return default
    if not isinstance(data, dict):
        text = str(data).strip()
        return text or default
    detail = data.get("detail", default)
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict):
                parts.append(str(item.get("msg") or item))
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else default
    return str(detail) if detail is not None else default


def _guess_mime(filename, fallback="application/octet-stream"):
    name = filename or ""
    ext = os.path.splitext(name)[1].lower()
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".bmp": "image/bmp",
        ".gif": "image/gif",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".cpp": "text/x-c++src",
        ".cc": "text/x-c++src",
        ".cxx": "text/x-c++src",
        ".h": "text/x-c++hdr",
        ".hpp": "text/x-c++hdr",
        ".c": "text/x-csrc",
        ".in": "text/plain",
        ".out": "text/plain",
    }
    if ext in mapping:
        return mapping[ext]
    guessed, _enc = mimetypes.guess_type(name)
    return guessed or fallback


def encode_multipart(fields=None, files=None):
    """fields: [(name, value)], files: [(field, filename, content, content_type)]."""
    boundary = "----GuoyiForm" + secrets.token_hex(16)
    body = bytearray()
    marker = ("--%s\r\n" % boundary).encode("ascii")

    for name, value in fields or ():
        body.extend(marker)
        body.extend(
            ('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode("utf-8")
        )
        if not isinstance(value, bytes):
            value = str(value).encode("utf-8")
        body.extend(value)
        body.extend(b"\r\n")

    for item in files or ():
        if len(item) == 3:
            field, filename, content = item
            ctype = None
        else:
            field, filename, content, ctype = item
        if content is None:
            content = b""
        if not isinstance(content, bytes):
            content = bytes(content)
        filename = filename or "file"
        ctype = ctype or _guess_mime(filename)
        body.extend(marker)
        header = (
            'Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
            "Content-Type: %s\r\n\r\n" % (field, filename, ctype)
        )
        body.extend(header.encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")

    body.extend(("--%s--\r\n" % boundary).encode("ascii"))
    return "multipart/form-data; boundary=%s" % boundary, bytes(body)


class TeacherClient(object):
    """调用 http://127.0.0.1:8765 上现有教师 API。"""

    def __init__(self, base_url="http://127.0.0.1:8765", timeout=15):
        self.base_url = (base_url or "http://127.0.0.1:8765").rstrip("/")
        self.timeout = timeout
        self.token = ""
        self.username = ""
        self.state = None

    def url(self, path, query=None):
        if not path.startswith("/"):
            path = "/" + path
        result = self.base_url + path
        if query:
            items = []
            for key, value in query.items():
                if value is None:
                    continue
                items.append((key, value))
            if items:
                result += "?" + urlencode(items)
        return result

    def _headers(self, extra=None, with_auth=True):
        headers = {}
        if with_auth and self.token:
            headers["Authorization"] = "Bearer " + self.token
        if extra:
            headers.update(extra)
        return headers

    def _auth_was_sent(self, with_auth):
        return bool(with_auth and self.token)

    def _raise_status(self, status, message, payload, with_auth):
        if status == 401 and self._auth_was_sent(with_auth):
            raise AuthExpired(message or "登录已过期，请重新登录", status=401, payload=payload)
        raise TeacherApiError(message or "请求失败", status=status, payload=payload)

    def request(self, method, path, json_body=None, files=None, query=None,
                raw=False, timeout=None, with_auth=True):
        headers = self._headers(with_auth=with_auth)
        data = None
        if files is not None:
            ctype, data = encode_multipart(files=files)
            headers["Content-Type"] = ctype
        elif json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(self.url(path, query), data=data, headers=headers, method=method)
        try:
            resp = urlopen(req, timeout=timeout if timeout is not None else self.timeout)
            body = resp.read()
            status = getattr(resp, "status", None) or resp.getcode()
            ctype = resp.headers.get("Content-Type") or ""
        except HTTPError as exc:
            body = exc.read() if exc.fp is not None else b""
            status = exc.code
            ctype = ""
            try:
                ctype = exc.headers.get("Content-Type") if exc.headers else ""
            except Exception:
                ctype = ""
            if raw:
                if status == 401 and self._auth_was_sent(with_auth):
                    raise AuthExpired("登录已过期，请重新登录", status=401)
                return body, status, ctype
            payload = None
            if body and "json" in (ctype or "").lower():
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    payload = None
            elif body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    payload = None
            message = _detail(payload, "请求失败")
            if not payload and body:
                try:
                    text = body.decode("utf-8", "replace").strip()
                    if text:
                        message = text[:300]
                except Exception:
                    pass
            self._raise_status(status, message, payload, with_auth)
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise TeacherApiError("无法连接课堂服务：%s" % reason)

        if raw:
            return body, status, ctype

        if status == 204 or not body:
            return None
        if "json" in (ctype or "").lower() or body[:1] in (b"{", b"["):
            try:
                payload = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise TeacherApiError("服务返回了无法解析的数据", status=status)
            if status >= 400:
                self._raise_status(status, _detail(payload), payload, with_auth)
            return payload
        if status >= 400:
            self._raise_status(status, "请求失败", None, with_auth)
        return body

    def info(self):
        return self.request("GET", "/api/info", with_auth=False)

    def login(self, username, password):
        data = self.request(
            "POST",
            "/api/login",
            json_body={"username": username, "password": password},
            with_auth=False,
        )
        token = (data or {}).get("token") or ""
        if not token:
            raise TeacherApiError("登录失败：未返回令牌")
        self.token = token
        self.username = (data or {}).get("username") or username
        self.state = (data or {}).get("state")
        return data

    def logout(self):
        self.token = ""
        self.username = ""
        self.state = None

    def get_state(self):
        self.state = self.request("GET", "/api/state")
        return self.state

    def change_password(self, old_password, new_password):
        return self.request(
            "POST",
            "/api/password",
            json_body={"old_password": old_password, "new_password": new_password},
        )

    def class_start(self):
        self.state = self.request("POST", "/api/class/start", json_body={})
        return self.state

    def class_end(self):
        self.state = self.request("POST", "/api/class/end", json_body={})
        return self.state

    def refresh_code(self):
        data = self.request("POST", "/api/class/code", json_body={})
        if self.state is not None and data and "class_code" in data:
            self.state["class_code"] = data["class_code"]
        return data

    def approve(self, device_id, name=None):
        body = {}
        if name:
            body["name"] = name
        return self.request(
            "POST",
            "/api/students/%s/approve" % quote(device_id, safe=""),
            json_body=body,
        )

    def revoke(self, device_id):
        return self.request(
            "POST",
            "/api/students/%s/revoke" % quote(device_id, safe=""),
            json_body={},
        )

    def set_focus(self, student_id):
        return self.request("POST", "/api/focus", json_body={"student_id": student_id})

    def lock(self, student_ids=None):
        body = {}
        if student_ids is not None:
            body["student_ids"] = list(student_ids)
        return self.request("POST", "/api/lock", json_body=body)

    def unlock(self, student_ids=None):
        body = {}
        if student_ids is not None:
            body["student_ids"] = list(student_ids)
        return self.request("POST", "/api/unlock", json_body=body)

    def announce(self, text, kind="announce"):
        return self.request("POST", "/api/announce", json_body={"text": text, "kind": kind})

    def restrict_web(self, enabled):
        self.state = self.request(
            "POST", "/api/restrict/web", json_body={"enabled": bool(enabled)}
        )
        return self.state

    def restrict_lists(self, game_domains=None, download_domains=None,
                       whitelist_domains=None, extensions=None, reset_defaults=False):
        body = {}
        if reset_defaults:
            body["reset_defaults"] = True
        if game_domains is not None:
            body["game_domains"] = list(game_domains)
        if download_domains is not None:
            body["download_domains"] = list(download_domains)
        if whitelist_domains is not None:
            body["whitelist_domains"] = list(whitelist_domains)
        if extensions is not None:
            body["extensions"] = list(extensions)
        self.state = self.request("POST", "/api/restrict/lists", json_body=body)
        return self.state

    def upload_file(self, path, filename=None, student_ids=None, timeout=45):
        path = os.fspath(path)
        filename = filename or os.path.basename(path)
        with open(path, "rb") as fp:
            content = fp.read()
        return self.upload_file_bytes(filename, content, student_ids=student_ids, timeout=timeout)

    def upload_file_bytes(self, filename, content, student_ids=None, timeout=45):
        query = None
        if student_ids:
            query = {"student_ids": ",".join(student_ids)}
        return self.request(
            "POST",
            "/api/files",
            files=[("file", filename, content)],
            query=query,
            timeout=timeout,
        )

    def broadcast_start(self, shrink=None):
        body = {}
        if shrink is not None:
            body["shrink"] = bool(shrink)
        return self.request("POST", "/api/broadcast/start", json_body=body)

    def broadcast_end(self):
        return self.request("POST", "/api/broadcast/end", json_body={})

    def broadcast_settings(self, shrink):
        return self.request(
            "POST", "/api/broadcast/settings", json_body={"shrink": bool(shrink)}
        )

    def broadcast_frame(self, path, filename=None, timeout=45):
        path = os.fspath(path)
        filename = filename or os.path.basename(path)
        with open(path, "rb") as fp:
            content = fp.read()
        return self.broadcast_frame_bytes(filename, content, timeout=timeout)

    def broadcast_frame_bytes(self, filename, content, timeout=45):
        return self.request(
            "POST",
            "/api/broadcast/frame",
            files=[("file", filename, content)],
            timeout=timeout,
        )

    def set_desktop_wallpaper(self, path, lock=True, filename=None, timeout=45):
        path = os.fspath(path)
        filename = filename or os.path.basename(path)
        with open(path, "rb") as fp:
            content = fp.read()
        return self.set_desktop_wallpaper_bytes(filename, content, lock=lock, timeout=timeout)

    def set_desktop_wallpaper_bytes(self, filename, content, lock=True, timeout=45):
        self.state = self.request(
            "POST",
            "/api/desktop/wallpaper",
            files=[("file", filename, content)],
            query={"lock": "1" if lock else "0"},
            timeout=timeout,
        )
        return self.state

    def desktop_unlock(self):
        self.state = self.request("POST", "/api/desktop/unlock", json_body={})
        return self.state

    def desktop_image(self):
        body, status, ctype = self.request("GET", "/api/desktop/image", raw=True)
        return body, status, ctype

    def thumb(self, device_id, at=None):
        query = {"t": at} if at is not None else None
        body, status, ctype = self.request(
            "GET",
            "/api/thumbs/%s" % quote(device_id, safe=""),
            query=query,
            raw=True,
        )
        return body, status, ctype

    def focus_frame(self, device_id):
        body, status, ctype = self.request(
            "GET",
            "/api/focus/%s" % quote(device_id, safe=""),
            raw=True,
        )
        return body, status, ctype

    def remote_start(self, device_id):
        return self.request("POST", "/api/remote/start", json_body={"student_id": device_id})

    def remote_stop(self, device_id=None):
        return self.request("POST", "/api/remote/stop", json_body={"student_id": device_id or ""})

    def remote_input(self, device_id, events):
        return self.request(
            "POST",
            "/api/remote/input",
            json_body={"student_id": device_id, "events": events or []},
        )
