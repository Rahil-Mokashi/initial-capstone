; Short default install folder (per-user): keeps the installed path far from Windows' 260-character limit.
; Only applied when there is no previous install; an existing install keeps its folder, and the user
; can still pick another folder on the folder page.
!macro preInit
  SetRegView 64
  ReadRegStr $R0 HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation
  StrCmp $R0 "" 0 +2
  WriteRegExpandStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "$LOCALAPPDATA\PPERP"
!macroend
