; Expenzo — Inno Setup installer (per-user, no admin).
; Compiled with ISCC from packaging/build_release.ps1, which sets
; EXPENZO_BUILD_VERSION so the installer always carries the same version
; that the app reports (version_service.py at the repo root).
;
; User data (database + exports) lives in %APPDATA%\Expenzo and is NEVER
; installed, uninstalled, or overwritten. Reinstalls/updates only overlay the
; program files, so existing user data is always preserved.

#ifndef EXPENZO_BUILD_VERSION
  #define EXPENZO_BUILD_VERSION "1.0.0"
#endif

#define MyAppName "Expenzo"
#define MyAppVersion EXPENZO_BUILD_VERSION
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
