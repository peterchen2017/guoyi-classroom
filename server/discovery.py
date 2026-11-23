# -*- coding: utf-8 -*-
"""局域网 UDP 发现：教师机应答探测并周期性广播自身地址。"""

from __future__ import print_function

import asyncio
import json
import socket
from typing import Callable, Optional

from server import config


def _packet(ip_hint):
    # type: (str) -> bytes
    body = {
        "v": 1,
        "magic": "GUOYI_CLASSROOM",
        "school": config.SCHOOL_NAME,
        "app": config.APP_NAME,
        "port": config.PORT,
        "ip": ip_hint,
    }
    return config.DISCOVERY_MAGIC + b'\n' + json.dumps(body, ensure_ascii=False).encode('utf-8')


class DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, ip_hint, on_log=None):
        # type: (str, Optional[Callable[[str], None]]) -> None
        self.ip_hint = ip_hint
        self.on_log = on_log or (lambda _msg: None)
        self.transport = None  # type: Optional[asyncio.DatagramTransport]

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if not data:
            return
        if data.startswith(config.DISCOVERY_PROBE) or data.startswith(config.DISCOVERY_MAGIC + b"_PROBE"):
            if self.transport is not None:
                self.transport.sendto(_packet(self.ip_hint), addr)

    def error_received(self, exc):
        self.on_log("UDP 发现出错：%s" % (exc,))


async def run_discovery(ip_hint, on_log=None):
    loop = asyncio.get_running_loop()
    on_log = on_log or (lambda _msg: None)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except OSError:
        pass
    sock.bind(("0.0.0.0", config.DISCOVERY_PORT))
    sock.setblocking(False)
    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: DiscoveryProtocol(ip_hint, on_log),
        sock=sock,
    )
    on_log("UDP 发现已在端口 %s 监听" % config.DISCOVERY_PORT)
    try:
        packet = _packet(ip_hint)
        while True:
            try:
                transport.sendto(packet, ("255.255.255.255", config.DISCOVERY_PORT))
            except OSError:
                pass
            await asyncio.sleep(3)
    finally:
        transport.close()
