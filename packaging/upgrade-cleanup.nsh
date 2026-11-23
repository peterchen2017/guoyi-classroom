; 升级安装前清理旧程序文件，避免覆盖失败后仍运行旧版。
; 保留：安装目录下的 *.log，以及 data\（若有人把课堂数据放在安装目录内）。
; 不触碰安装目录以外的位置（例如 %APPDATA%\GuoyiClassroom、学生「课堂文件」作业目录）。

!include "WordFunc.nsh"
!insertmacro WordReplace

!macro GuoyiStopInstallDirProcesses
  ; 先按窗口标题结束本软件，再按可执行文件路径结束本安装目录里的 python/pythonw。
  ClearErrors
  nsExec::ExecToLog 'taskkill /F /FI "WINDOWTITLE eq 机房课堂管理-教师机*"'
  Pop $0
  nsExec::ExecToLog 'taskkill /F /FI "WINDOWTITLE eq 机房课堂管理-学生机*"'
  Pop $0
  nsExec::ExecToLog 'taskkill /F /FI "WINDOWTITLE eq 课堂管理运行中*"'
  Pop $0
  ; WMI LIKE 中反斜杠需要再转义一次
  Push $R1
  ${WordReplace} "$INSTDIR\" "\" "\\" "+" $R1
  nsExec::ExecToLog `wmic process where "ExecutablePath like '$R1%'" call terminate`
  Pop $0
  Pop $R1
  Sleep 800
  ClearErrors
!macroend

!macro GuoyiCleanupOldProgramFiles
  IfFileExists "$INSTDIR\*.*" 0 guoyi_cleanup_done
  DetailPrint "正在清理旧版程序文件（保留日志和课堂数据）..."
  !insertmacro GuoyiStopInstallDirProcesses

  Delete "$INSTDIR\launch_teacher.py"
  Delete "$INSTDIR\launch_student.py"
  Delete "$INSTDIR\launch_teacher.pyc"
  Delete "$INSTDIR\launch_student.pyc"
  Delete "$INSTDIR\start_teacher.cmd"
  Delete "$INSTDIR\start_student.cmd"
  Delete "$INSTDIR\start_student_autostart.cmd"
  Delete "$INSTDIR\更改连接设置.cmd"

  RMDir /r "$INSTDIR\__pycache__"
  RMDir /r "$INSTDIR\server"
  RMDir /r "$INSTDIR\student"
  RMDir /r "$INSTDIR\shared"
  RMDir /r "$INSTDIR\web"
  RMDir /r "$INSTDIR\teacher"
  ; 整棵内置 Python（含 site-packages 里残留的 pydantic / pydantic_core）
  RMDir /r "$INSTDIR\python"

  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\乐昌国艺书院-机房课堂管理-使用说明.txt"
  Delete "$INSTDIR\打开说明.txt"
  Delete "$INSTDIR\requirements.txt"
  Delete "$INSTDIR\requirements-py38.txt"

  ; 旧的无版本号快捷方式，避免点到旧图标却看不出是否已升级
  Delete "$DESKTOP\机房课堂管理-教师机.lnk"
  Delete "$DESKTOP\机房课堂管理-学生机.lnk"
  Delete "$SMPROGRAMS\乐昌国艺书院\机房课堂管理-教师机.lnk"
  Delete "$SMPROGRAMS\乐昌国艺书院\机房课堂管理-学生机.lnk"

  ClearErrors
  guoyi_cleanup_done:
!macroend
