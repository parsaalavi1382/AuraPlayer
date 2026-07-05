; Inno Setup Script for AuraPlayer
; Compatible with Inno Setup 6.0+

#define MyAppName "AuraPlayer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Parsa Alavi"
#define MyAppURL "https://github.com/parsaalavi1382/AuraPlayer"
#define MyAppExeName "AuraPlayer.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
AppId={{9F9676EA-6363-4C3D-88AF-0AA331EFE1FF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
; Setup Icon File must exist. Since we generated assets\logo.ico, this will compile successfully!
SetupIconFile=assets\logo.ico
OutputDir=dist
OutputBaseFilename=AuraPlayer_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy the main executable and all bundled files from the PyInstaller dist directory
Source: "dist\auraplayer\AuraPlayer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\auraplayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
