[Setup]
AppId={{70E68F53-B09E-46C9-ACF6-ECE84F5861C8}
AppName=ORBIT Desktop
AppVersion={#OrbitVersion}
VersionInfoVersion={#WindowsVersion}
VersionInfoProductTextVersion={#OrbitVersion}
AppPublisher=Liltaz6xx
AppPublisherURL=https://github.com/Liltaz6xx/orbit-desktop
AppUpdatesURL=https://github.com/Liltaz6xx/orbit-desktop/releases
DefaultDirName={localappdata}\Programs\ORBIT Desktop
DisableDirPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
WizardStyle=modern
SetupIconFile=..\assets\orbit.ico
UninstallDisplayIcon={app}\assets\orbit.ico
SetupLogging=yes
SetupMutex=OrbitDesktop.Installer
AppMutex=OrbitDesktop.Application
CloseApplications=no
RestartApplications=no
OutputBaseFilename=ORBIT-Desktop-{#OrbitVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=no
ExtraDiskSpaceRequired=450000000
InfoBeforeFile=before-install.txt

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#UvExe}"; DestName: "uv.exe"; Flags: dontcopy
Source: "requirements-win-x64.txt"; Flags: dontcopy
Source: "..\main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\orbit\*.py"; DestDir: "{app}\orbit"; Flags: ignoreversion
Source: "..\assets\orbit_core.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\orbit_halo.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\orbit.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\scripts\download_voice_models.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "remove_runtime.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\MODEL_SOURCES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#UvNotices}"; DestName: "uv-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\ORBIT Desktop\ORBIT Desktop"; Filename: "{code:EnvironmentPath}\Scripts\pythonw.exe"; Parameters: "-E -s -B ""{app}\main.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\orbit.ico"
Name: "{userdesktop}\ORBIT Desktop"; Filename: "{code:EnvironmentPath}\Scripts\pythonw.exe"; Parameters: "-E -s -B ""{app}\main.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\orbit.ico"; Tasks: desktopicon
Name: "{userprograms}\ORBIT Desktop\Download Kokoro voice"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NoExit -ExecutionPolicy Bypass -File ""{app}\scripts\download_voice_models.ps1"" -AssetsDirectory ""{localappdata}\ORBIT Desktop\voice"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\orbit.ico"

[Run]
Filename: "{code:EnvironmentPath}\Scripts\pythonw.exe"; Parameters: "-E -s -B ""{app}\main.py"""; WorkingDir: "{app}"; Description: "Launch ORBIT Desktop"; Flags: postinstall nowait skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\ORBIT Desktop"; ValueType: string; ValueName: "InstallerVersion"; ValueData: "{#WindowsVersion}"; Flags: uninsdeletekeyifempty uninsdeletevalue

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Code]
const
  PythonArchive = 'cpython-3.12.16-windows-x64.tar.gz';
  PythonUrl = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261110/' +
    'cpython-3.12.16%2B20261110-x86_64-pc-windows-msvc-install_only_stripped.tar.gz';
  PythonHash = '355ee61b8207b91574491b1c6dc9b0ebb4408fc56bfafe498f3ef439314b52dc';
  RegistryKey = 'Software\ORBIT Desktop';

var
  Progress: TOutputMarqueeProgressWizardPage;

function InitializeSetup(): Boolean;
var
  Installed: String;
  InstalledVersion, SetupVersion: Int64;
begin
  Result := True;
  if RegQueryStringValue(HKCU, RegistryKey, 'InstallerVersion', Installed) and
     StrToVersion(Installed, InstalledVersion) and
     StrToVersion('{#WindowsVersion}', SetupVersion) and
     (ComparePackedVersion(InstalledVersion, SetupVersion) > 0) then
  begin
    SuppressibleMsgBox('A newer version of ORBIT Desktop is installed. Download its installer to repair it.', mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

procedure InitializeWizard();
begin
  Progress := CreateOutputMarqueeProgressPage('Preparing ORBIT Desktop',
    'Setting up the private Python runtime. The first installation downloads its dependencies.');
end;

function EnvironmentPath(Param: String): String;
begin
  Result := ExpandConstant('{app}\runtime\env-{#RuntimeId}');
end;

function RunTool(Exe, Arguments: String): Boolean;
var
  Code: Integer;
begin
  Result := ExecAndLogOutput(Exe, Arguments, ExpandConstant('{tmp}'), SW_SHOWNORMAL,
    ewWaitUntilTerminated, Code, nil) and (Code = 0);
  if not Result then
    Log(Format('Dependency command failed with status %d.', [Code]));
end;

function RuntimeHealthy(Python: String): Boolean;
begin
  Result := FileExists(Python) and
    FileExists(AddBackslash(ExtractFileDir(Python)) + 'pythonw.exe') and
    RunTool(Python, '-I -B -c "import sqlite3, numpy, psutil, sounddevice, kokoro_onnx; from PySide6 import QtWidgets"');
end;

function PreparePython(InstallPython: String): Boolean;
begin
  Result := True;
  if FileExists(InstallPython + '\python\python.exe') and
     FileExists(InstallPython + '\archive.ready') then
    exit;
  try
    DownloadTemporaryFile(PythonUrl, PythonArchive, PythonHash, nil);
    Result := ForceDirectories(InstallPython) and
      RunTool(ExpandConstant('{sys}\tar.exe'), '-xzf "' + ExpandConstant('{tmp}\') + PythonArchive +
        '" -C "' + InstallPython + '"') and
      FileExists(InstallPython + '\python\python.exe') and
      SaveStringToFile(InstallPython + '\archive.ready', PythonHash, False);
  except
    Log(GetExceptionMessage);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  UV, Lock, InstallPython, Interpreter, Env, Python: String;
begin
  Result := '';
  Env := EnvironmentPath('');
  Python := Env + '\Scripts\python.exe';
  if FileExists(Env + '\orbit-runtime.ready') and RuntimeHealthy(Python) then
  begin
    Log('Reusing the verified ORBIT runtime.');
    exit;
  end;

  Progress.Show;
  try
    Progress.Animate;
    ExtractTemporaryFile('uv.exe');
    ExtractTemporaryFile('requirements-win-x64.txt');
    UV := ExpandConstant('{tmp}\uv.exe');
    Lock := ExpandConstant('{tmp}\requirements-win-x64.txt');
    InstallPython := ExpandConstant('{app}\runtime\python-3.12.16');
    Interpreter := InstallPython + '\python\python.exe';

    if not PreparePython(InstallPython) then
      Result := 'Setup could not install ORBIT''s private Python runtime. Check your Internet connection and run Setup again.'
    else if not RunTool(UV,
      '--no-config --no-progress venv --clear --no-python-downloads --python "' +
      Interpreter + '" "' + Env + '"') then
      Result := 'Setup could not create ORBIT''s private environment.'
    else if not RunTool(UV,
      '--no-config --no-progress pip sync --only-binary :all: --require-hashes --link-mode copy ' +
      '--index-url https://pypi.org/simple --python "' + Python + '" "' + Lock + '"') then
      Result := 'Setup could not download or verify the Python dependencies. Check your Internet connection and run Setup again.'
    else if not RuntimeHealthy(Python) then
      Result := 'The Python environment did not pass its dependency check. See the Setup log for details.'
    else if not SaveStringToFile(Env + '\orbit-runtime.ready', '{#RuntimeId}', False) then
      Result := 'Setup could not record the verified runtime. Check the installation folder permissions.';
  finally
    Progress.Hide;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PowerShell, AppDir: String;
begin
  if CurUninstallStep <> usUninstall then
    exit;
  AppDir := ExpandConstant('{app}');
  PowerShell := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  { The cleanup script handles paths beyond MAX_PATH in the provisioned wheels. }
  if not RunTool(PowerShell, '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    AppDir + '\scripts\remove_runtime.ps1" -AppDirectory "' + AppDir + '"') then
    Log('Could not remove all ORBIT runtime files.');
end;
