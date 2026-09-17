#define AppName "大可桌边"
#define AppVersion "4.7.0"
#define AppPublisher "大可"
#define AppExeName "DaKeDesk.exe"
#define AppAUMID "DaKe.DaKeDesk"

[Setup]
AppId={{B0BBAB27-0C46-42CD-98CD-D2F2EF906776}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
SetupIconFile=..\assets\dake-desk-icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
DefaultDirName={code:SuggestedInstallDir}
UsePreviousAppDir=yes
DisableDirPage=auto
DefaultGroupName={#AppName}
OutputDir=..\release
OutputBaseFilename=DaKeDesk-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Do not show Inno Setup's generic "cannot close applications" dialog.  The
; upgrade flow below only deals with DaKeDesk.exe and explains the choice in
; product language before any program file is replaced.
CloseApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Files]
; If a security scanner briefly keeps the executable open after the app has
; exited, defer this one replacement until Windows restarts instead of asking
; the user to skip the program file.
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion restartreplace

[InstallDelete]
Type: files; Name: "{app}\WorkTodo.exe"
; The AppId stays the same so an upgrade retains its program location and
; local data. Remove only the obsolete shortcut files from the old name.
Type: files; Name: "{autodesktop}\Work Todo.lnk"
Type: files; Name: "{autodesktop}\WorkTodo.lnk"
Type: files; Name: "{autoprograms}\Work Todo.lnk"
Type: files; Name: "{autoprograms}\WorkTodo.lnk"

[Icons]
; Windows uses this stable identity to associate system reminders with 大可桌边,
; including the app name/icon shown in Notification Center.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppAUMID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppAUMID}"; Tasks: desktopicon

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

function IsDaKeDeskRunning: Boolean;
var
  ResultCode: Integer;
begin
  { tasklist itself returns success even when it finds no matching process.
    find changes the result to 0 only when DaKeDesk.exe is actually running. }
  Result := Exec(
    ExpandConstant('{sys}\cmd.exe'),
    '/C tasklist /FI "IMAGENAME eq {#AppExeName}" /NH | find /I "{#AppExeName}" > NUL',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  ) and (ResultCode = 0);
end;

function StopDaKeDeskForUpgrade: Boolean;
var
  ResultCode: Integer;
  Attempt: Integer;
begin
  { Older releases hide when their main window is closed, so an update cannot
    rely on the normal window-close action. This command targets only the app
    and its child process tree, after the user has explicitly approved it. }
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/IM "{#AppExeName}" /T /F',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  );

  for Attempt := 1 to 20 do begin
    Sleep(250);
    if not IsDaKeDeskRunning then begin
      Result := True;
      exit;
    end;
  end;

  Result := False;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not IsDaKeDeskRunning then
    exit;

  if MsgBox(
    '检测到大可桌边仍在后台运行。'#13#10#13#10 +
    '关闭主页面不会退出软件。选择“是”后，安装程序会自动退出大可桌边并继续升级。'#13#10#13#10 +
    '已保存的待办和设置不会受影响；当前尚未保存的编辑内容将不会保留。',
    mbConfirmation, MB_YESNO
  ) <> IDYES then begin
    Result := '已取消本次升级。请在方便时重新运行安装包。';
    exit;
  end;

  if not StopDaKeDeskForUpgrade then
    Result :=
      '安装程序暂时无法退出大可桌边。请重启电脑后重新运行安装包；' +
      '若仍然失败，请右键安装包并选择“以管理员身份运行”。';
end;

procedure InitializeWizard;
var
  GuidePage: TOutputMsgMemoWizardPage;
begin
  GuidePage := CreateOutputMsgMemoPage(
    wpWelcome,
    '大可桌边｜Windows 桌面工作待办工具',
    '让要紧的事，在桌边等你。',
    '安装位置说明',
    '推荐安装到 D:、E: 等非系统磁盘。无需提前创建文件夹。'#13#10#13#10 +
    '首次安装时，选择磁盘后，安装程序会自动建立“大可桌边”专用文件夹。'#13#10#13#10 +
    '待办内容和个人设置会独立保存在当前 Windows 用户数据中；后续升级会保留已有内容。'#13#10#13#10 +
    '如需自行整理文件夹，可在下一步点击“浏览”更改安装位置。'
  );
end;
