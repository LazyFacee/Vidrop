; Installer Vidrop (Inno Setup 6). Dibuat otomatis oleh GitHub Actions.
; AppId yang SAMA di setiap versi membuat installer baru menimpa versi lama
; (upgrade di tempat) tanpa perlu uninstall dulu. Jangan diubah-ubah.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "Vidrop"

[Setup]
AppId={{8ACFB21E-EAC8-421E-A11A-3163893D533C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Vidrop
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\Vidrop.exe
SetupIconFile=assets\vidrop.ico
OutputDir=installer
OutputBaseFilename=Vidrop-Setup-v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Pasang untuk pengguna saat ini saja: tidak perlu hak admin / jendela UAC
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Tutup Vidrop yang sedang terbuka saat update, lalu jalankan lagi
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
#if FileExists(SourcePath + "Indonesian.isl")
Name: "indonesian"; MessagesFile: "Indonesian.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "Buat ikon Vidrop di Desktop / Create a Desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\Vidrop.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\Vidrop.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Vidrop.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Vidrop.exe"; Description: "Jalankan Vidrop / Launch Vidrop"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Hapus data aplikasi (pengaturan + komponen YouTube). File unduhanmu TIDAK disentuh.
Type: filesandordirs; Name: "{localappdata}\Vidrop"
