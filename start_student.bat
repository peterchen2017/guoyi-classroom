@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist python\pythonw.exe (
  start "" python\pythonw.exe launch_student.py --config-ui
  goto :eof
)
if exist python\python.exe (
  python\python.exe launch_student.py --config-ui
  goto :eof
)
if exist runtime\python.exe (
  runtime\python.exe launch_student.py --config-ui
  goto :eof
)
where py >nul 2>&1
if %errorlevel%==0 (
  py -3.8 launch_student.py --config-ui
  goto :eof
)
python launch_student.py --config-ui
