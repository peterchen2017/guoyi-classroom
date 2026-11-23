@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist python\python.exe (
  python\python.exe launch_teacher.py
  goto :eof
)
if exist runtime\python.exe (
  runtime\python.exe launch_teacher.py
  goto :eof
)
where py >nul 2>&1
if %errorlevel%==0 (
  py -3.8 -c "import sys" >nul 2>&1
  if %errorlevel%==0 (
    py -3.8 launch_teacher.py
    goto :eof
  )
  py -3 launch_teacher.py
  goto :eof
)
python launch_teacher.py
