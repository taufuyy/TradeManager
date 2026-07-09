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
SetupIconFile=..\Source_Code\icon.ico
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName=Trade Manager

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main Executable and all its dependencies
Source: "dist\TradeManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Additional configuration and manual
Source: "..\Source_Code\config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "Panduan_Pengguna.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Source_Code\TradeManager_Relay.mq5"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Source_Code\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Trade Manager"; Filename: "{app}\TradeManager.exe"; IconFilename: "{app}\icon.ico"
Name: "{group}\Panduan Pengguna"; Filename: "{app}\Panduan_Pengguna.txt"
Name: "{group}\{cm:UninstallProgram,Trade Manager}"; Filename: "{uninstallexe}"; IconFilename: "{app}\icon.ico"
Name: "{app}\Uninstall Trade Manager"; Filename: "{uninstallexe}"; IconFilename: "{app}\icon.ico"
Name: "{commondesktop}\Trade Manager"; Filename: "{app}\TradeManager.exe"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\Panduan_Pengguna.txt"; Description: "Buka Panduan Pengguna"; Flags: shellexec postinstall skipifsilent
Filename: "{app}\TradeManager.exe"; Description: "Jalankan Trade Manager"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
