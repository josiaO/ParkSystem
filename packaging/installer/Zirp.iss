; Zirp — Windows installer (Inno Setup 6.3+).
; Built by packaging\installer\build.ps1, which stages the release and passes:
;   /DAppVersion=1.4.0 /DAppVersionNumeric=1.4.0.0 /DStageDir=... /DBinDir=... /DOutputDir=...
;   optionally /DSignTool=zirpsign together with /Szirpsign=... (Authenticode signing)
;
; Layout on the target PC
;   C:\Program Files\Zirp\versions\<version>\   this release (files from StageDir)
;   C:\Program Files\Zirp\current               junction to the active version (made by zirpctl)
;   C:\Program Files\Zirp\bin\                  zirpctl.ps1, Zirp-Kiosk.ps1, icon
;   C:\ProgramData\SmartParkEdge\               site data, settings, logs, backups (kept on uninstall)

#ifndef AppVersion
  #error AppVersion is required (build with packaging\installer\build.ps1)
#endif
#ifndef AppVersionNumeric
  #define AppVersionNumeric "0.0.0.0"
#endif

[Setup]
AppId={{6F2B8C4E-3D1A-4B7E-9F05-2A8C7D1E4B93}
AppName=Zirp
AppVersion={#AppVersion}
AppVerName=Zirp {#AppVersion}
AppPublisher=Zirp
AppSupportURL=https://zirp.app
VersionInfoVersion={#AppVersionNumeric}
VersionInfoProductName=Zirp
DefaultDirName={autopf}\Zirp
UsePreviousAppDir=yes
; An update/repair reuses the existing folder; the folder page only shows on a first install.
DisableDirPage=auto
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=Zirp-Setup-{#AppVersion}
SetupIconFile={#StageDir}\app\assets\zirp.ico
UninstallDisplayIcon={app}\bin\zirp.ico
UninstallDisplayName=Zirp
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
SetupLogging=yes
CloseApplications=no
RestartIfNeededByRun=no
#ifdef SignTool
SignTool={#SignTool}
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Check: not IsKiosk

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}\versions\{#AppVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BinDir}\*"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#StageDir}\app\assets\zirp.ico"; DestDir: "{app}\bin"; Flags: ignoreversion
; A Site Server keeps this installer so other LAN computers can download it
; from http://<server>:8760/downloads/zirp-setup.exe (no USB, no internet).
Source: "{srcexe}"; DestDir: "{app}\installers"; DestName: "Zirp-Setup-{#AppVersion}.exe"; Flags: external ignoreversion; Check: IsSiteServer

[Dirs]
Name: "{commonappdata}\SmartParkEdge"; Flags: uninsneveruninstall
Name: "{commonappdata}\SmartParkEdge\config"; Flags: uninsneveruninstall

[Registry]
; The installer owns its registry state (zirpctl also keeps install\state.json).
Root: HKLM64; Subkey: "SOFTWARE\Zirp"; Flags: uninsdeletekey
Root: HKLM64; Subkey: "SOFTWARE\Zirp"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"
Root: HKLM64; Subkey: "SOFTWARE\Zirp"; ValueType: string; ValueName: "Role"; ValueData: "{code:SelectedRoleParam}"
Root: HKLM64; Subkey: "SOFTWARE\Zirp"; ValueType: string; ValueName: "KioskUser"; ValueData: "{code:KioskUserValue}"; Check: IsKiosk
Root: HKLM64; Subkey: "SOFTWARE\Zirp"; ValueType: string; ValueName: "HvxAsService"; ValueData: "{code:HvxValue}"; Check: HasCameras

[Icons]
Name: "{autoprograms}\Zirp\Zirp"; Filename: "{app}\current\python64\pythonw.exe"; Parameters: "-m app.desktop.launch"; WorkingDir: "{app}\current"; IconFilename: "{app}\bin\zirp.ico"; Check: not IsKiosk
Name: "{autoprograms}\Zirp\Zirp Kiosk"; Filename: "powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\bin\Zirp-Kiosk.ps1"""; WorkingDir: "{app}\bin"; IconFilename: "{app}\bin\zirp.ico"; Check: IsKiosk
Name: "{autoprograms}\Zirp\Zirp Web"; Filename: "http://127.0.0.1:8760/"; Check: IsServerRole
Name: "{autoprograms}\Zirp\Zirp Portal"; Filename: "http://127.0.0.1:3000/"; Check: IsSiteServer
Name: "{autoprograms}\Zirp\Zirp startup check"; Filename: "{app}\current\python64\python.exe"; Parameters: "tools\startup_check.py"; WorkingDir: "{app}\current"; IconFilename: "{app}\bin\zirp.ico"; Check: IsServerRole
Name: "{autoprograms}\Zirp\Zirp status and versions"; Filename: "powershell.exe"; Parameters: "-NoExit -NoProfile -ExecutionPolicy Bypass -File ""{app}\bin\zirpctl.ps1"" status"; WorkingDir: "{app}\bin"
Name: "{autoprograms}\Zirp\Zirp logs"; Filename: "{commonappdata}\SmartParkEdge\logs"
Name: "{autodesktop}\Zirp"; Filename: "{app}\current\python64\pythonw.exe"; Parameters: "-m app.desktop.launch"; WorkingDir: "{app}\current"; IconFilename: "{app}\bin\zirp.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\current\python64\pythonw.exe"; Parameters: "-m app.desktop.launch"; WorkingDir: "{app}\current"; Description: "Start Zirp now"; Flags: postinstall nowait skipifsilent; Check: ActivationOk and (not IsKiosk)

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\bin\zirpctl.ps1"" uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "ZirpUninstallServices"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\versions"
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\installers"
Type: dirifempty; Name: "{app}"

[Code]
const
  RoleKeys = 'COMBINED,SERVER,EDGE,OPERATOR,KIOSK';

var
  MaintenancePage: TInputOptionWizardPage;
  RolePage: TInputOptionWizardPage;
  KioskPage: TInputQueryWizardPage;
  OptionsPage: TInputOptionWizardPage;
  PreviousRole, PreviousKioskUser, PreviousHvx, InstalledVersion: String;
  IsUpgrade, Reconfigure, ActivationSucceeded, HeldForReinstall: Boolean;

function RoleKey(Index: Integer): String;
begin
  case Index of
    0: Result := 'COMBINED';
    1: Result := 'SERVER';
    2: Result := 'EDGE';
    3: Result := 'OPERATOR';
    4: Result := 'KIOSK';
  else
    Result := 'COMBINED';
  end;
end;

function RoleIndex(Key: String): Integer;
begin
  Key := Uppercase(Key);
  if Key = 'SERVER' then Result := 1
  else if Key = 'EDGE' then Result := 2
  else if Key = 'OPERATOR' then Result := 3
  else if Key = 'KIOSK' then Result := 4
  else Result := 0;
end;

function SelectedRole: String;
var
  FromCmd: String;
begin
  FromCmd := Uppercase(ExpandConstant('{param:ROLE|}'));
  if (FromCmd <> '') and (Pos(FromCmd, RoleKeys) > 0) then
    Result := FromCmd
  else if (RolePage <> nil) and (not IsUpgrade or Reconfigure) then
    Result := RoleKey(RolePage.SelectedValueIndex)
  else if PreviousRole <> '' then
    Result := PreviousRole
  else
    Result := 'COMBINED';
end;

function SelectedRoleParam(Param: String): String;
begin
  Result := SelectedRole;
end;

function IsKiosk: Boolean;
begin
  Result := SelectedRole = 'KIOSK';
end;

function IsServerRole: Boolean;
begin
  Result := (SelectedRole = 'COMBINED') or (SelectedRole = 'SERVER') or (SelectedRole = 'EDGE');
end;

function IsSiteServer: Boolean;
begin
  Result := (SelectedRole = 'COMBINED') or (SelectedRole = 'SERVER');
end;

function HasCameras: Boolean;
begin
  Result := (SelectedRole = 'COMBINED') or (SelectedRole = 'EDGE');
end;

function ActivationOk: Boolean;
begin
  Result := ActivationSucceeded;
end;

function KioskUserValue(Param: String): String;
begin
  Result := Trim(KioskPage.Values[0]);
end;

function HvxValue(Param: String): String;
begin
  if OptionsPage.Values[0] then Result := '1' else Result := '0';
end;

procedure InitializeWizard;
begin
  IsUpgrade := RegQueryStringValue(HKLM64, 'SOFTWARE\Zirp', 'Role', PreviousRole);
  RegQueryStringValue(HKLM64, 'SOFTWARE\Zirp', 'KioskUser', PreviousKioskUser);
  RegQueryStringValue(HKLM64, 'SOFTWARE\Zirp', 'HvxAsService', PreviousHvx);
  Reconfigure := ExpandConstant('{param:RECONFIGURE|0}') = '1';
  RegQueryStringValue(HKLM64,
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{6F2B8C4E-3D1A-4B7E-9F05-2A8C7D1E4B93}_is1',
    'DisplayVersion', InstalledVersion);

  // Running the installer on a computer that already has Zirp: offer
  // update/repair (keep everything) or changing the role/options first.
  if IsUpgrade then
  begin
    if InstalledVersion = '' then InstalledVersion := 'An earlier version';
    if InstalledVersion = '{#AppVersion}' then
      MaintenancePage := CreateInputOptionPage(wpWelcome,
        'Zirp {#AppVersion} is already installed', 'What do you want to do?',
        'This computer is set up as: ' + PreviousRole + '. ' +
        'Settings, database, photos and payment keys in C:\ProgramData\SmartParkEdge are always kept, ' +
        'and the database is backed up before anything changes.',
        True, False)
    else
      MaintenancePage := CreateInputOptionPage(wpWelcome,
        'Zirp ' + InstalledVersion + ' is installed on this computer', 'What do you want to do?',
        'This computer is set up as: ' + PreviousRole + '. ' +
        'Settings, database, photos and payment keys in C:\ProgramData\SmartParkEdge are always kept, ' +
        'the database is backed up before anything changes, and the previous version stays available for rollback.',
        True, False);
    if InstalledVersion = '{#AppVersion}' then
      MaintenancePage.Add('Repair Zirp {#AppVersion}: reinstall the program files, keep role and settings (recommended)')
    else
      MaintenancePage.Add('Update to Zirp {#AppVersion}: keep role and settings (recommended)');
    MaintenancePage.Add('Change the role or options of this computer, then update/repair');
    if Reconfigure then
      MaintenancePage.SelectedValueIndex := 1
    else
      MaintenancePage.SelectedValueIndex := 0;
  end;

  RolePage := CreateInputOptionPage(wpSelectDir,
    'Role of this computer', 'What will this computer do on the parking site?',
    'Choose one. Settings, database and photos are kept in C:\ProgramData\SmartParkEdge and survive upgrades.',
    True, False);
  RolePage.Add('Site Server with cameras and gates (single-computer site)');
  RolePage.Add('Site Server only (cameras and gates are on Edge Nodes)');
  RolePage.Add('Edge Node (lane computer with cameras and barriers)');
  RolePage.Add('Operator Workstation (desk application only)');
  RolePage.Add('Payment Kiosk (driver-facing, full screen)');
  RolePage.SelectedValueIndex := RoleIndex(PreviousRole);

  KioskPage := CreateInputQueryPage(RolePage.ID,
    'Payment kiosk', 'Which Windows account runs the kiosk?',
    'Zirp starts full screen when this account signs in and restarts if it is closed. ' +
    'Use a dedicated standard (non-administrator) account set to sign in automatically.');
  KioskPage.Add('Windows account (e.g. KIOSK01\kiosk):', False);
  if PreviousKioskUser <> '' then
    KioskPage.Values[0] := PreviousKioskUser
  else
    KioskPage.Values[0] := GetComputerNameString + '\' + GetUserNameString;

  OptionsPage := CreateInputOptionPage(KioskPage.ID,
    'Camera SDK host', 'How should the 32-bit camera SDK host run?',
    'As a Windows service it works with nobody signed in. Choose it only after the camera model was verified as a service on site; otherwise it runs when a user signs in.',
    False, False);
  OptionsPage.Add('Run the camera SDK host as a Windows service');
  OptionsPage.Values[0] := (PreviousHvx = '1') or (ExpandConstant('{param:HVXSERVICE|0}') = '1');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = RolePage.ID) then
    Result := (IsUpgrade and not Reconfigure) or (ExpandConstant('{param:ROLE|}') <> '');
  if (PageID = KioskPage.ID) then
    Result := (not IsKiosk) or (IsUpgrade and not Reconfigure and (PreviousKioskUser <> ''));
  if (PageID = OptionsPage.ID) then
    Result := (not HasCameras) or (IsUpgrade and not Reconfigure);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (MaintenancePage <> nil) and (CurPageID = MaintenancePage.ID) then
    Reconfigure := MaintenancePage.SelectedValueIndex = 1;
  if (CurPageID = KioskPage.ID) and (Trim(KioskPage.Values[0]) = '') then
  begin
    MsgBox('Enter the Windows account that runs the kiosk.', mbError, MB_OK);
    Result := False;
  end;
end;

function ZirpCtl(Arguments: String; var ResultCode: Integer): Boolean;
begin
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\bin\zirpctl.ps1') + '" ' + Arguments,
    ExpandConstant('{app}\bin'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  // Reinstalling (repairing) the version that is running: stop it and keep
  // it stopped so its files can be replaced. Without the hold, the Site
  // Service watchdog or an open desktop started Zirp again mid-copy and
  // setup failed with "DeleteFile failed; code 5" on python32 files.
  // This runs the new zirpctl from this installer: the installed copy may
  // be older and not know -Hold.
  if DirExists(ExpandConstant('{app}\versions\{#AppVersion}')) then
  begin
    ExtractTemporaryFile('zirpctl.ps1');
    Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\zirpctl.ps1') +
      '" services stop -Hold -Root "' + ExpandConstant('{app}') + '"',
      ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    HeldForReinstall := True;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Args: String;
  Reason: AnsiString;
begin
  if CurStep <> ssPostInstall then Exit;
  DeleteFile(ExpandConstant('{commonappdata}\SmartParkEdge\logs\install\last-error.txt'));
  DeleteFile(ExpandConstant('{commonappdata}\SmartParkEdge\logs\install\last-warnings.txt'));
  WizardForm.StatusLabel.Caption := 'Configuring Zirp services and checking health (this can take a few minutes)...';
  Args := 'activate -Version "{#AppVersion}" -Role ' + SelectedRole;
  if IsKiosk then
    Args := Args + ' -KioskUser "' + Trim(KioskPage.Values[0]) + '"';
  if HasCameras then
  begin
    if OptionsPage.Values[0] then Args := Args + ' -HvxHost service'
    else Args := Args + ' -HvxHost task';
  end;
  if ZirpCtl(Args, ResultCode) and (ResultCode = 0) then
  begin
    ActivationSucceeded := True;
    Reason := '';
    if LoadStringFromFile(ExpandConstant('{commonappdata}\SmartParkEdge\logs\install\last-warnings.txt'), Reason)
       and (Length(Reason) > 0) and not WizardSilent then
      MsgBox('Zirp {#AppVersion} is installed and running. Please note:' + #13#10#13#10 + String(Reason), mbInformation, MB_OK);
  end
  else
  begin
    ActivationSucceeded := False;
    Reason := '';
    LoadStringFromFile(ExpandConstant('{commonappdata}\SmartParkEdge\logs\install\last-error.txt'), Reason);
    if Length(Reason) > 900 then Reason := Copy(Reason, 1, 900) + '...';
    if not WizardSilent then
      MsgBox('Zirp {#AppVersion} was copied, but it could not be activated (code ' + IntToStr(ResultCode) + ').' + #13#10 +
        'If an earlier version was installed, it was switched back and is running.' + #13#10#13#10 +
        'Reason: ' + String(Reason) + #13#10#13#10 +
        'Details: C:\ProgramData\SmartParkEdge\logs\install', mbError, MB_OK);
  end;
end;

procedure DeinitializeSetup();
var
  ResultCode: Integer;
begin
  // Setup cancelled or failed after holding the services: put them back.
  if HeldForReinstall and not ActivationSucceeded then
    Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -Command "Get-Service SmartPark* | Set-Service -StartupType Automatic; ' +
      'if (Test-Path ''' + ExpandConstant('{app}\bin\zirpctl.ps1') + ''') { & ''' +
      ExpandConstant('{app}\bin\zirpctl.ps1') + ''' services start }"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

var
  UninstallRole: String;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  // Read the role before zirpctl uninstall removes HKLM\SOFTWARE\Zirp.
  if CurUninstallStep = usUninstall then
    RegQueryStringValue(HKLM64, 'SOFTWARE\Zirp', 'Role', UninstallRole);
  if CurUninstallStep <> usPostUninstall then Exit;
  DataDir := ExpandConstant('{commonappdata}\SmartParkEdge');
  if UninstallSilent or not DirExists(DataDir) then Exit;
  if (UninstallRole <> 'OPERATOR') and (UninstallRole <> 'KIOSK') then
  begin
    // Servers and Edge Nodes: photos here are referenced by the site database.
    // Deleting only the files would orphan those records, so never offer it here.
    MsgBox('Zirp is removed. The site data is kept in ' + DataDir + '.' + #13#10#13#10 +
      'For a complete factory reset, run "zirpctl purge-data -Force" (it also resets the site database) ' +
      'before uninstalling, or delete the folder yourself once the site database is no longer needed.',
      mbInformation, MB_OK);
    Exit;
  end;
  if MsgBox('Zirp is removed. The site data is still on this computer:' + #13#10 + DataDir + #13#10#13#10 +
     '(database, settings, photos, backups and logs)' + #13#10#13#10 +
     'Delete the site data too? This cannot be undone.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    DelTree(DataDir, True, True, True);
end;
