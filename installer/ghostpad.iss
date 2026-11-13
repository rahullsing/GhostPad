; Inno Setup script for the Ghostpad installer wizard.
;
; Build the app first (dist\Ghostpad must exist), then compile this script:
;   tools\build.ps1                                   (recommended, does everything)
;   ISCC.exe /DAppVersion=1.0.0 installer\ghostpad.iss  (manual)
;
; Output: dist\installer\Ghostpad-Setup-<version>.exe

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName      "Ghostpad"
#define AppExe       "Ghostpad.exe"
#define AppPublisher "The Ghostpad authors"
#define SourceDir    "..\dist\Ghostpad"

[Setup]
; AppId identifies the app across upgrades. Never change it after the first release.
AppId={{6F1C7E2A-4B8D-4E3F-9A51-2D7C0B9E8F14}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}

; Install per user by default (no administrator rights needed); the wizard
; offers "Install for all users" for people who have admin rights.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes

; Ghostpad's capture protection needs Windows 10 version 2004 (build 19041).
MinVersion=10.0.19041
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Ask the user to close a running Ghostpad before upgrading or uninstalling.
AppMutex=Local\Ghostpad.Instance
CloseApplications=yes

LicenseFile=..\LICENSE
SetupIconFile=..\assets\ghostpad.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardSmallImageFile=..\assets\ghostpad.png
Compression=lzma2/max
SolidCompression=yes
OutputDir=..\dist\installer
OutputBaseFilename=Ghostpad-Setup-{#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Start {#AppName} when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked

[InstallDelete]
; Remove files from a previous version so stale libraries never linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{autostartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// Notes and settings live in %APPDATA%\Ghostpad. Keep them by default (so a
// reinstall restores everything) but offer to remove them on uninstall.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#AppName}');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox('Also delete your Ghostpad notes and settings?' + #13#10 + #13#10 + DataDir,
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
