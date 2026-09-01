#define AppName "Work Todo"
#define AppVersion "2.3.0"
#define AppPublisher "Work Todo"
#define AppExeName "WorkTodo.exe"

[Setup]
AppId={{B0BBAB27-0C46-42CD-98CD-D2F2EF906776}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Work Todo
DefaultGroupName=Work Todo
OutputDir=..\release
OutputBaseFilename=WorkTodo-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Work Todo"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Work Todo"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动 Work Todo"; Flags: nowait postinstall skipifsilent
