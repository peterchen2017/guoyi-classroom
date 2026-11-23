Unicode true
SetCompressor /SOLID lzma
!include "MUI2.nsh"

Name "乐昌国艺书院 机房课堂管理（学生机）"
OutFile "..\dist\乐昌国艺书院-机房课堂管理-学生机-安装包-x64.exe"
; 默认装到当前用户目录，无需管理员
InstallDir "$LOCALAPPDATA\GuoyiClassroom\Student"
InstallDirRegKey HKCU "Software\GuoyiClassroom\Student" "InstallDir"
RequestExecutionLevel user
BrandingText "版权所有 © 乐昌国艺书院    开发者：陈老师"

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\orange-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\orange-uninstall.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "student-license.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\start_student.cmd"
!define MUI_FINISHPAGE_RUN_TEXT "安装完成后立即启动学生端"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "学生端程序" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "staging-student-amd64\*.*"

  CreateDirectory "$SMPROGRAMS\乐昌国艺书院"
  CreateShortCut "$SMPROGRAMS\乐昌国艺书院\机房课堂管理-学生机.lnk" "$INSTDIR\start_student.cmd" "" "$INSTDIR\python\pythonw.exe" 0
  CreateShortCut "$SMPROGRAMS\乐昌国艺书院\更改连接设置.lnk" "$INSTDIR\更改连接设置.cmd" "" "$INSTDIR\python\pythonw.exe" 0
  CreateShortCut "$SMPROGRAMS\乐昌国艺书院\卸载学生机.lnk" "$INSTDIR\卸载学生机.exe"
  CreateShortCut "$DESKTOP\机房课堂管理-学生机.lnk" "$INSTDIR\start_student.cmd" "" "$INSTDIR\python\pythonw.exe" 0

  WriteRegStr HKCU "Software\GuoyiClassroom\Student" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\卸载学生机.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomStudent" "DisplayName" "乐昌国艺书院 机房课堂管理（学生机）"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomStudent" "UninstallString" "$INSTDIR\卸载学生机.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomStudent" "Publisher" "乐昌国艺书院"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomStudent" "DisplayVersion" "1.2.1"
SectionEnd

Section "开机自动启动（可选）" SecAuto
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GuoyiClassroomStudent" '"$INSTDIR\start_student_autostart.cmd"'
SectionEnd

Section "Uninstall"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GuoyiClassroomStudent"
  Delete "$DESKTOP\机房课堂管理-学生机.lnk"
  Delete "$SMPROGRAMS\乐昌国艺书院\机房课堂管理-学生机.lnk"
  Delete "$SMPROGRAMS\乐昌国艺书院\更改连接设置.lnk"
  Delete "$SMPROGRAMS\乐昌国艺书院\卸载学生机.lnk"
  RMDir "$SMPROGRAMS\乐昌国艺书院"
  DeleteRegKey HKCU "Software\GuoyiClassroom\Student"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GuoyiClassroomStudent"
  RMDir /r "$INSTDIR"
SectionEnd
