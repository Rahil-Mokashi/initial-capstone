; Inno Setup script for Petrol Pump ERP.
;
; Builds a proper Windows installer around the standalone dist\PetrolPumpERP.exe
; produced by `pyinstaller petrol_pump_erp.spec` - Start Menu entry, optional
; desktop shortcut, an uninstaller registered with Windows, and the three
; docs\*.md guides made available from the Start Menu alongside the app.
;
; Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php) on the machine
; that builds the installer - not a runtime dependency for end users. Build
; the exe first, then compile this script:
;   pyinstaller petrol_pump_erp.spec
;   iscc installer\petrol_pump_erp.iss
; Output: installer\output\PetrolPumpERP-Setup-<version>.exe

#define MyAppName "Petrol Pump ERP"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Petrol Pump ERP"
#define MyAppExeName "PetrolPumpERP.exe"

[Setup]
AppId={{B6C1E1B4-6B5B-4C7E-9C6E-6C6F7E7B2A3D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=output
OutputBaseFilename=PetrolPumpERP-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; The app is entirely offline and stores its own data under
; %LOCALAPPDATA%\PetrolPumpERP (see app/database/connection.py) rather than
; under Program Files, so this installer never needs elevated per-machine
; write access to anywhere but the install directory itself.
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\PetrolPumpERP.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\first-shift-runbook.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\user-guide.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\administrator-guide.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\recovery-guide.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\First Shift Runbook"; Filename: "{app}\docs\first-shift-runbook.md"
Name: "{group}\User Guide"; Filename: "{app}\docs\user-guide.md"
Name: "{group}\Administrator Guide"; Filename: "{app}\docs\administrator-guide.md"
Name: "{group}\Backup & Recovery Guide"; Filename: "{app}\docs\recovery-guide.md"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The database, backups, logs, and reports under %LOCALAPPDATA%\PetrolPumpERP
; are deliberately NOT removed by uninstall - CLAUDE.md: "Never remove
; historical financial data". Uninstalling only removes the application
; files this installer placed in {app}; a reinstall picks the existing
; database back up automatically.
Type: files; Name: "{app}\*.pyc"
