# -*- coding: utf-8 -*-
"""上课限制网页游戏和随意下载：启动本机过滤代理，Windows 上设置并在结束后还原系统代理。"""

import sys
from pathlib import Path

from student.filter_proxy import DEFAULT_PORT, FilterProxy

PROXY_FLAG = "proxy_backup.json"


class WebRestrictor(object):
    def __init__(self, data_dir, log=None, ui=None):
        self.data_dir = Path(data_dir)
        self.log = log
        self.ui = ui
        self.proxy = FilterProxy()
        self.enabled = False
        self.port = None
        self._applied_win = False

    def _flag_path(self):
        return self.data_dir / PROXY_FLAG

    def _write(self, event, **kwargs):
        if self.log is not None:
            self.log.write(event, **kwargs)

    def restore_leftover(self):
        """客户端启动时：若上次异常退出留下了系统代理，先还原。"""
        if sys.platform != "win32":
            return
        try:
            from student import win_proxy
        except Exception:
            return
        payload = win_proxy.load_file(self._flag_path())
        if not payload or not payload.get("applied"):
            return
        try:
            win_proxy.apply_saved(payload.get("original") or {})
            self._write("proxy_restored_leftover")
        except Exception as exc:
            self._write("proxy_restore_error", error=str(exc))
        win_proxy.clear_file(self._flag_path())

    def apply(self, msg, teacher_server="", teacher_port=8765):
        enabled = bool(msg.get("enabled"))
        if not enabled:
            self.disable()
            return
        teacher_ips = list(msg.get("teacher_ips") or [])
        if teacher_server and teacher_server not in teacher_ips:
            teacher_ips.append(teacher_server)
        rules = {
            "teacher_ips": teacher_ips,
            "teacher_port": msg.get("teacher_port") or teacher_port,
            "game_domains": msg.get("game_domains") or [],
            "download_domains": msg.get("download_domains") or [],
            "whitelist_domains": msg.get("whitelist_domains") or [],
            "extensions": msg.get("extensions") or [],
        }
        port = self.proxy.start(rules=rules, preferred_port=DEFAULT_PORT)
        self.port = port
        if sys.platform == "win32":
            self._set_win_proxy(port, teacher_ips)
        self.enabled = True
        notice = msg.get("notice") or "上课期间已限制网页游戏和下载"
        if self.ui is not None:
            try:
                self.ui.show_announce("课堂管理", notice)
            except Exception:
                pass
        self._write("web_restrict_on", port=port, games=len(rules["game_domains"]))

    def disable(self):
        was = self.enabled or self._applied_win
        self._restore_win_proxy()
        self.proxy.stop()
        self.port = None
        if was or self.enabled:
            self._write("web_restrict_off")
            if self.ui is not None and self.enabled:
                try:
                    self.ui.show_announce("课堂管理", "已恢复原来的网络设置，网页游戏和下载限制已关闭")
                except Exception:
                    pass
        self.enabled = False

    def _set_win_proxy(self, port, teacher_ips):
        try:
            from student import win_proxy
        except Exception as exc:
            self._write("proxy_win_skip", error=str(exc))
            return
        try:
            flag = win_proxy.load_file(self._flag_path())
            if flag and flag.get("applied") and flag.get("original") is not None:
                original = flag.get("original")
            else:
                original = win_proxy.get_proxy()
            win_proxy.set_classroom_proxy(port, extra_bypass=teacher_ips)
            win_proxy.save_file(self._flag_path(), {"applied": True, "original": original, "port": port})
            self._applied_win = True
        except Exception as exc:
            self._write("proxy_win_error", error=str(exc))

    def _restore_win_proxy(self):
        if sys.platform != "win32":
            self._applied_win = False
            return
        try:
            from student import win_proxy
        except Exception:
            self._applied_win = False
            return
        payload = win_proxy.load_file(self._flag_path())
        if payload and payload.get("applied"):
            try:
                win_proxy.apply_saved(payload.get("original") or {})
            except Exception as exc:
                self._write("proxy_restore_error", error=str(exc))
            win_proxy.clear_file(self._flag_path())
        self._applied_win = False
