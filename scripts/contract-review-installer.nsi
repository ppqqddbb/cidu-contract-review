Unicode True
RequestExecutionLevel user
Name "合同智审"
OutFile "合同智审-0.1.0-x64-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\合同智审"
InstallDirRegKey HKCU "Software\合同智审" "InstallDir"
SetCompressor /SOLID lzma

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "合同智审"
  SetOutPath "$INSTDIR"
  File "..\apps\desktop\src-tauri\target\release\contract-review-desktop.exe"
  File "..\services\api\dist\contract-backend.exe"
  SetOutPath "$INSTDIR\libreoffice"
  File /r "..\.build\libreoffice\*"
  WriteRegStr HKCU "Software\合同智审" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateDirectory "$SMPROGRAMS\合同智审"
  CreateShortcut "$DESKTOP\合同智审.lnk" "$INSTDIR\contract-review-desktop.exe"
  CreateShortcut "$SMPROGRAMS\合同智审\合同智审.lnk" "$INSTDIR\contract-review-desktop.exe"
  CreateShortcut "$SMPROGRAMS\合同智审\卸载合同智审.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\合同智审.lnk"
  Delete "$SMPROGRAMS\合同智审\合同智审.lnk"
  Delete "$SMPROGRAMS\合同智审\卸载合同智审.lnk"
  RMDir "$SMPROGRAMS\合同智审"
  Delete "$INSTDIR\contract-review-desktop.exe"
  Delete "$INSTDIR\contract-backend.exe"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR\libreoffice"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\合同智审"
SectionEnd

