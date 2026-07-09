[Setup]
; NOTE: The value of AppId uniquely identifies this application.
AppId={{9F8A2D3C-4B1E-11EE-BE56-0242AC120002}
AppName=Trade Manager
AppVersion=1.0
AppPublisher=Trade Manager Inc.
DefaultDirName={pf}\TradeManager
DefaultGroupName=Trade Manager
OutputDir=.\Installer
OutputBaseFilename=Install_TradeManager_v1.0
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main Executable and all its dependencies
Source: "dist\TradeManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Additional configuration and manual
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "Panduan_Pengguna.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "TradeManager_Relay.mq5"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Trade Manager"; Filename: "{app}\TradeManager.exe"; IconFilename: "{app}\icon.ico"
Name: "{group}\Panduan Pengguna"; Filename: "{app}\Panduan_Pengguna.md"
Name: "{group}\{cm:UninstallProgram,Trade Manager}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Trade Manager"; Filename: "{app}\TradeManager.exe"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\Panduan_Pengguna.md"; Description: "Buka Panduan Pengguna"; Flags: shellexec postinstall skipifsilent
Filename: "{app}\TradeManager.exe"; Description: "Jalankan Trade Manager"; Flags: nowait postinstall skipifsilent
