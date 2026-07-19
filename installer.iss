; Inno Setup 腳本：把 PyInstaller onedir 產出包成 setup.exe
; 先 `pyinstaller gui.spec`，再用 Inno Setup 編譯此檔（iscc installer.iss）。

#define AppName "Whisper Dictate TW"
#define AppVersion "0.1.0"
#define AppExe "whisper-dictate-tw.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
; per-user 安裝：免系統管理員、裝到使用者目錄，{userstartup} 開機項才會落在正確使用者
PrivilegesRequired=lowest
DefaultDirName={autopf}\WhisperDictateTW
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputBaseFilename=whisper-dictate-tw-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "cht"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\whisper-dictate-tw\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Tasks]
Name: "startup"; Description: "開機自動啟動"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即執行"; Flags: nowait postinstall skipifsilent
