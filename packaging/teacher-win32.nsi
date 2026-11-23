Unicode true
SetCompressor /SOLID lzma
!include "MUI2.nsh"

!define APP_VERSION "1.2.6"
Name "乐昌国艺书院 机房课堂管理（教师机） ${APP_VERSION}"
OutFile "..\dist\乐昌国艺书院-机房课堂管理-教师机-安装包-x86.exe"
; 默认装到当前用户目录，无需管理员（机房 Win7 常见无管理员权限）
InstallDir "$LOCALAPPDATA\GuoyiClassroom\Teacher"
InstallDirRegKey HKCU "Software\GuoyiClassroom\Teacher" "InstallDir"
RequestExecutionLevel user
BrandingText "版权所有 © 乐昌国艺书院    开发者：陈老师"

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\orange-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\orange-uninstall.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "teacher-license.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "安装完成后立即启动教师机"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchTeacher
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!include "upgrade-cleanup.nsh"

Section "Teacher" SecMain
  !insertmacro GuoyiCleanupOldProgramFiles
  SetOverwrite on
  SetOutPath "$INSTDIR"
  File /r "staging-teacher-win32\*.*"

  CreateDirectory "$SMPROGRAMS\乐昌国艺书院"
  ; CreateShortCut 的工作目录取当前 $OUTDIR，必须先回到安装目录
  SetOutPath "$INSTDIR"
  CreateShortCut "$SMPROGRAMS\乐昌国艺书院\机房课堂管理-教师机 ${APP_VERSION}.lnk" "$INSTDIR\start_teacher.cmd" "" "$INSTDIR\python\python.exe" 0 SW_SHOWNORMAL
  CreateShortCut "$SMPROGRAMS\乐昌国艺书院\卸载教师机.lnk" "$INSTDIR\卸载教师机.exe"
  CreateShortCut "$DESKTOP\机房课堂管理-教师机 ${APP_VERSION}.lnk" "$INSTDIR\start_teacher.cmd" "" "$INSTDIR\python\python.exe" 0 SW_SHOWNORMAL

  ; 无管理员权限时防火墙规则会失败，不能因此中止安装
  ClearErrors
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="GuoyiClassroom-TCP-8765"'
  Pop $0
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="GuoyiClassroom-UDP-8766"'
  Pop $0
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="GuoyiClassroom-TCP-8765" dir=in action=allow protocol=TCP localport=8765'
  Pop $0
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="GuoyiClassroom-UDP-8766" dir=in action=allow protocol=UDP localport=8766'
  Pop $0
  ClearErrors

  WriteRegStr HKCU "Software\GuoyiClassroom\Teacher" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\卸载教师机.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomTeacher" "DisplayName" "乐昌国艺书院 机房课堂管理（教师机） ${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomTeacher" "UninstallString" "$INSTDIR\卸载教师机.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomTeacher" "Publisher" "乐昌国艺书院"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomTeacher" "DisplayVersion" "${APP_VERSION}"
SectionEnd

Section "Uninstall"
  ClearErrors
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="GuoyiClassroom-TCP-8765"'
  Pop $0
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="GuoyiClassroom-UDP-8766"'
  Pop $0
  ClearErrors
  Delete "$DESKTOP\机房课堂管理-教师机.lnk"
  Delete "$DESKTOP\机房课堂管理-教师机 *.lnk"
  Delete "$SMPROGRAMS\乐昌国艺书院\机房课堂管理-教师机.lnk"
  Delete "$SMPROGRAMS\乐昌国艺书院\机房课堂管理-教师机 *.lnk"
  Delete "$SMPROGRAMS\乐昌国艺书院\卸载教师机.lnk"
  RMDir "$SMPROGRAMS\乐昌国艺书院"
  DeleteRegKey HKCU "Software\GuoyiClassroom\Teacher"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomTeacher"
  RMDir /r "$INSTDIR"
SectionEnd

Function LaunchTeacher
  ; Win7 上 MUI_FINISHPAGE_RUN 直接 Exec .cmd 常失败，改用 ShellExecute
  SetOutPath "$INSTDIR"
  ExecShell "open" "$INSTDIR\start_teacher.cmd"
FunctionEnd
