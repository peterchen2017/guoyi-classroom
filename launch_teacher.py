# -*- coding: utf-8 -*-
"""教师机启动器：启动课堂服务并打开本机控制台。"""

from __future__ import print_function

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(str(ROOT))


def _open_browser():
    time.sleep(1.2)
    try:
        webbrowser.open("http://127.0.0.1:8765")
    except Exception:
        pass


def main():
    from server.app import main as server_main
    threading.Thread(target=_open_browser, daemon=True).start()
    server_main([])


if __name__ == "__main__":
    main()
