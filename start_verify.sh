#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi
export CLASSROOM_PYTHON="$(pwd)/.venv/bin/python"
echo "开始验证默认桌面锁定、上网限制与核心流程…"
.venv/bin/python tests/test_desktop.py
.venv/bin/python tests/test_web_filter.py
exec .venv/bin/python tests/test_flow.py
