; ─────────────────────────────────────────────────────────────────────────────
; HazariTrackerFacio.iss  —  Inno Setup 6 installer script
;
; Builds:  HazariTrackerFacio-vX.Y.Z-Setup.exe
; ─────────────────────────────────────────────────────────────────────────────

#define MyAppName      "HazariTracker Facio"
; MyAppVersion is injected by publish.ps1 via:  ISCC /DMyAppVersion=X.Y.Z
#ifndef MyAppVersion
  #define MyAppVersion  "1.0.0"
#endif
#define MyAppPublisher "Themehakcodes"
#define MyAppURL       "https://github.com/Themehakcodes/HazariTrackerFacio"
#define MyAppExeName   "HazariTrackerFacio.exe"
#define MyDistFolder   "dist\HazariTrackerFacio-v" + MyAppVersion
#define MyOutputDir    "dist"

[Setup]
AppId={{B4C3D2E1-0A5B-4C8E-A3F7-2D9E4E5F6A7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Output
OutputDir={#MyOutputDir}
OutputBaseFilename=HazariTrackerFacio-v{#MyAppVersion}-Setup
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
; Architecture — 64-bit installer
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
; UI
WizardStyle=modern
MinVersion=10.0
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
SetupIconFile=icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "{cm:CreateDesktopIcon}";     GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon";  Description: "Launch at Windows startup";   GroupDescription: "Startup:";             Flags: unchecked

[Files]
Source: "{#MyDistFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";               Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";         Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}";         Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Registry]
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nClick Next to continue.
