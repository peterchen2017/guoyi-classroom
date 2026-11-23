#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi
export CLASSROOM_PYTHON="$(pwd)/.venv/bin/python"
echo "开始验证 Win7 依赖、wintypes 兼容、登录凭据、教师 API 客户端、默认桌面锁定、上网限制与核心流程…"
.venv/bin/python tests/test_win7_deps.py
.venv/bin/python tests/test_win_types.py
.venv/bin/python tests/test_credentials.py
.venv/bin/python tests/test_teacher_client.py
.venv/bin/python tests/test_desktop.py
.venv/bin/python tests/test_web_filter.py
exec .venv/bin/python tests/test_flow.py
