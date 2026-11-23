#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi
# Linux 使用模拟画面 + 控制台状态
exec .venv/bin/python launch_student.py --sim --no-ui --discover "$@"
