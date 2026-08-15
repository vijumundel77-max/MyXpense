; Expenzo 1.0.0 — Inno Setup installer (per-user, no admin).
; Compiled with ISCC from packaging/build_release.ps1:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
;
; User data (database + exports) lives in %APPDATA%\Expenzo and is NEVER
; installed, uninstalled, or overwritten. Reinstalls/updates only overlay the
; program files, so existing user data is always preserved.

#define MyAppName "Expenzo"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Expenzo"
#define MyAppExeName "Expenzo.exe"

[Setup]
AppId={{6C2F9E4A-3B7D-4A1E-9F2B-Expenzo1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Expenzo
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ExpenzoSetup-{#MyAppVersion}
SetupIconFile=..\assets\expenzo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Expenzo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only program files are removed; %APPDATA%\Expenzo user data is preserved.
