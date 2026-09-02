#define AppName "大可桌边"
#define AppVersion "3.1"
#define AppPublisher "大可"
#define AppExeName "DaKeDesk.exe"

[Setup]
AppId={{B0BBAB27-0C46-42CD-98CD-D2F2EF906776}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={code:SuggestedInstallDir}
UsePreviousAppDir=yes
DisableDirPage=auto
DefaultGroupName={#AppName}
OutputDir=..\release
OutputBaseFilename=DaKeDesk-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DefaultLanguageName=chinesesimp

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{app}\WorkTodo.exe"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动大可桌边"; Flags: nowait postinstall skipifsilent

[Code]
function SuggestedInstallDir(Param: String): String;
begin
  { 首次安装优先选择常见的非系统盘；后续升级由 UsePreviousAppDir 自动沿用旧位置。 }
  if DirExists('D:\') then
    Result := 'D:\大可桌边'
  else if DirExists('E:\') then
    Result := 'E:\大可桌边'
  else
    Result := ExpandConstant('{autopf}\大可桌边');
end;

procedure InitializeWizard;
var
  GuidePage: TOutputMsgMemoWizardPage;
begin
  GuidePage := CreateOutputMsgMemoPage(
    wpWelcome,
    '安装位置说明',
    '推荐安装到 D:、E: 等非系统磁盘',
    '无需提前创建文件夹',
    '首次安装时，选择磁盘后，安装程序会自动建立“大可桌边”专用文件夹。'#13#10#13#10 +
    '待办内容和个人设置会独立保存在当前 Windows 用户数据中；后续升级会保留已有内容。'#13#10#13#10 +
    '如需自行整理文件夹，可在下一步点击“浏览”更改安装位置。'
  );
end;
