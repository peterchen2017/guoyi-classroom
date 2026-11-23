#define MyAppName "乐昌国艺书院 机房课堂管理（学生机）"
#define MyAppVersion "1.2.5"
[Setup]
AppId={{A7C3E4D1-0B25-4A1E-9C11-GUOYISTUD01}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=乐昌国艺书院
AppCopyright=版权所有 © 乐昌国艺书院    开发者：陈老师
DefaultDirName={localappdata}\GuoyiClassroom\Student
DefaultGroupName=乐昌国艺书院
OutputDir=..\dist
OutputBaseFilename=乐昌国艺书院-机房课堂管理-学生机-安装包-inno-x64
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
MinVersion=6.1
[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
[Files]
Source: "staging-student-amd64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
[Icons]
Name: "{group}\机房课堂管理-学生机"; Filename: "{app}\start_student.cmd"; WorkingDir: "{app}"
Name: "{userdesktop}\机房课堂管理-学生机"; Filename: "{app}\start_student.cmd"; WorkingDir: "{app}"
[Run]
Filename: "{cmd}"; Parameters: "/c ""{app}\start_student.cmd"""; WorkingDir: "{app}"; Description: "启动学生机"; Flags: nowait postinstall skipifsilent
