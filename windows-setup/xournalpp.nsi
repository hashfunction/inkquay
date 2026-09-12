; Scriblark NSIS installation script for Windows
; Author: The Xournal++ Team
; Scriblark changes copyright 2026 Trieflow LLC.

;--------------------------------
; NSIS setup

Unicode true

;--------------------------------
; Includes

!include "MUI2.nsh"
!include x64.nsh
!include "${SCRIPT_DIR}\FileAssociation.nsh"
!include nsDialogs.nsh

; Options for MultiUser plugin
!define MULTIUSER_INSTALLMODE_INSTDIR "InkQuay"
!define MULTIUSER_INSTALLMODE_INSTDIR_REGISTRY_KEY "Software\InkQuay"

!define MULTIUSER_EXECUTIONLEVEL Highest ; Mixed-mode installer that can both be per-machine or per-user
!define MULTIUSER_MUI
!define MULTIUSER_INSTALLMODE_COMMANDLINE
!define MULTIUSER_USE_PROGRAMFILES64
!include MultiUser.nsh


;--------------------------------
; Initialization

Function .onInit
	${If} ${RunningX64}
		# 64 bit code
		SetRegView 64
	${Else}
		# 32 bit code
		MessageBox MB_OK "Scriblark requires 64-bit Windows. Sorry!"
		Abort
	${EndIf}

	!insertmacro MULTIUSER_INIT
FunctionEnd

Function un.onInit
	${If} ${RunningX64}
		# 64 bit code
		SetRegView 64
	${Else}
		# 32 bit code
		MessageBox MB_OK "Scriblark requires 64-bit Windows. Sorry!"
		Abort
	${EndIf}

    !insertmacro MULTIUSER_UNINIT
FunctionEnd

; Name and file
Name "Scriblark ${XOURNALPP_VERSION}"
OutFile "${OUTPUT_INSTALLER_FILE}"

;--------------------------------
; Global Variables

Var StartMenuFolder

;--------------------------------
; Interface Settings

!define MUI_ABORTWARNING

;--------------------------------
; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${SCRIPT_DIR}\..\LICENSE"
!insertmacro MULTIUSER_PAGE_INSTALLMODE
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY

;Start Menu Folder Page Configuration
!define MUI_STARTMENUPAGE_REGISTRY_ROOT "SHCTX"
!define MUI_STARTMENUPAGE_REGISTRY_KEY "Software\InkQuay"
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "StartMenuEntry"
!define MUI_STARTMENUPAGE_DEFAULTFOLDER "Scriblark"

!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder

!insertmacro MUI_PAGE_INSTFILES

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; Languages

!insertmacro MUI_LANGUAGE "English"

;-------------------------------
; Uninstall previous version

Var IsLegacyInstall
Section "" SecUninstallPrevious
	ReadRegStr $R0 SHCTX "Software\InkQuay" ""
	${If} $R0 == ""
		; check for legacy installation
		ReadRegStr $R0 HKCU "Software\Xournalpp" ""
		${If} $R0 != ""
			StrCpy $IsLegacyInstall 1
		${EndIf}
		SetRegView 64
	${ENDIF}
	${If} $R0 != ""
        DetailPrint "Removing previous version located at $R0"
		ExecWait '"$R0\Uninstall.exe /S"'

		${If} $IsLegacyInstall == 1
			DetailPrint "Detected legacy installation (version 1.0.20 and below), cleaning up old files."
			RMDir /r "$R0\bin"
			RMDir /r "$R0\lib"
			RMDir /r "$R0\share"
			RMDir /r "$R0\ui"
			RMDir "$R0"

			; delete old start menu entry
			DetailPrint "Removing old start menu entries"

			!insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
			Delete "$SMPROGRAMS\$StartMenuFolder\InkQuay.lnk"
			Delete "$SMPROGRAMS\$StartMenuFolder\Uninstall.lnk"
			RMDir "$SMPROGRAMS\$StartMenuFolder"

			DetailPrint "Removing old registry keys"
			DeleteRegKey HKLM "Software\Classes\InkQuay file"
			DeleteRegKey HKLM "Software\Classes\InkQuay Template Files"
			DeleteRegKey HKLM "Software\Classes\Xournal file"
			DeleteRegKey HKCU "Software\Xournalpp"
		${EndIf}
    ${EndIf}
SectionEnd

;-------------------------------
; File association macros
; see https://docs.microsoft.com/en-us/windows/win32/shell/fa-file-types#registering-a-file-type

!macro SetDefaultExt EXT PROGID
	WriteRegStr SHCTX "Software\Classes\${EXT}" "" "${PROGID}"
!macroend

!macro RegisterExt EXT PROGID
	WriteRegStr SHCTX "Software\Classes\${EXT}\OpenWithProgIds" "${PROGID}" ""
	WriteRegStr SHCTX "Software\Classes\Applications\inkquay.exe\SupportedTypes" "${EXT}" ""
!macroend

!macro AddProgId PROGID CMD DESC
	; Define ProgId. See https://docs.microsoft.com/en-us/windows/win32/shell/fa-progids
	WriteRegStr SHCTX "Software\Classes\${PROGID}" "" "${DESC}"
	WriteRegStr SHCTX "Software\Classes\${PROGID}\DefaultIcon" "" '"${CMD}",0'
	WriteRegStr SHCTX "Software\Classes\${PROGID}\shell" "" "open"
	WriteRegStr SHCTX "Software\Classes\${PROGID}\shell\open\command" "" '"${CMD}" "%1"'
	WriteRegStr SHCTX "Software\Classes\${PROGID}\shell\edit" "" "Edit with Scriblark"
	WriteRegStr SHCTX "Software\Classes\${PROGID}\shell\edit\command" "" '"${CMD}" "%1"'
!macroend

!macro DeleteProgId PROGID
	; See https://docs.microsoft.com/en-us/windows/win32/shell/fa-file-types#deleting-registry-information-during-uninstallation
	DeleteRegKey SHCTX "Software\Classes\${PROGID}"
!macroend

!define SHCNE_ASSOCCHANGED 0x08000000
!define SHCNE_CREATE 0x2
!define SHCNE_DELETE 0x4

!define SHCNF_IDLIST 0x0
!define SHCNF_PATH 0x1
!define SHCNF_FLUSH 0x1000

!macro RefreshShellIconCreate FILEPATH
	DetailPrint "Refreshing shell icon create ${FILEPATH}"
	System::Call 'shell32::SHChangeNotify(i ${SHCNE_CREATE}, i ${SHCNF_FLUSH} | ${SHCNF_PATH}, w "${FILEPATH}", i 0)'
!macroend

!macro RefreshShellIconDelete FILEPATH
	DetailPrint "Refreshing shell icon delete ${FILEPATH}"
	System::Call 'shell32::SHChangeNotify(i ${SHCNE_DELETE}, i ${SHCNF_FLUSH} | ${SHCNF_PATH}, w "${FILEPATH}", i 0)'
!macroend

;-------------------------------
; Installer Sections

Section /o "Associate .xopp files with Scriblark" SecFileXopp
	!insertmacro SetDefaultExt ".xopp" "InkQuay.File"
SectionEnd

Section /o "Associate .xopt files with Scriblark" SecFileXopt
	!insertmacro SetDefaultExt ".xopt" "InkQuay.Template"
SectionEnd

Section /o "Associate .xoj files with Scriblark" SecFileXoj
	!insertmacro SetDefaultExt ".xoj" "InkQuay.Xournal"
SectionEnd

Section "Scriblark" SecXournalpp
	; Required
	SectionIn RO

	SetOutPath "$INSTDIR"

	; Files to put into the setup
	File /r ${SETUP_DIR}\*

	; Set install information
	WriteRegStr SHCTX "Software\InkQuay" "" '"$INSTDIR"'

	; Set program information
	WriteRegStr SHCTX "Software\Classes\Applications\inkquay.exe" "" '"$INSTDIR\bin\Scriblark-wrapper.exe"'
	WriteRegStr SHCTX "Software\Classes\Applications\inkquay.exe" "FriendlyAppName" "Scriblark"
	WriteRegExpandStr SHCTX "Software\Classes\Applications\inkquay.exe" "DefaultIcon" '"$INSTDIR\bin\Scriblark-wrapper.exe",0'
	WriteRegStr SHCTX "Software\Microsoft\Windows\CurrentVersion\App Paths\inkquay.exe" "" '"$INSTDIR\bin\Scriblark-wrapper.exe"'

	; Add file type information
	!insertmacro RegisterExt ".xopp" "InkQuay.File"
	!insertmacro RegisterExt ".xopt" "InkQuay.Template"
	!insertmacro RegisterExt ".xoj" "InkQuay.Xournal"
	!insertmacro RegisterExt ".pdf" "InkQuay.AnnotatePdf"
	push $R0
	StrCpy $R0 "$INSTDIR\bin\Scriblark-wrapper.exe"
	!insertmacro AddProgId "InkQuay.File" "$R0" "Scriblark file"
	!insertmacro AddProgId "InkQuay.Template" "$R0" "Scriblark template file"
	!insertmacro AddProgId "InkQuay.Xournal" "$R0" "Xournal file"
	!insertmacro AddProgId "InkQuay.AnnotatePdf" "$R0" "PDF file"
	pop $R0

	; Create uninstaller
	WriteUninstaller "$INSTDIR\Uninstall.exe"
	; Add uninstall entry. See https://docs.microsoft.com/en-us/windows/win32/msi/uninstall-registry-key
	WriteRegStr SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "DisplayIcon" '"$INSTDIR\bin\Scriblark-wrapper.exe"'
	WriteRegStr SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "DisplayName" "Scriblark"
	WriteRegStr SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "DisplayVersion" "${XOURNALPP_VERSION}"
	WriteRegStr SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "Publisher" "Trieflow LLC"
	WriteRegStr SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "URLInfoAbout" "https://scriblark.trieflow.com"
	WriteRegStr SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "InstallLocation" '"$INSTDIR"'
	WriteRegStr SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "UninstallString" '"$INSTDIR\Uninstall.exe"'
	WriteRegDWORD SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "NoModify" 1
	WriteRegDWORD SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay" "NoRepair" 1

	!insertmacro MUI_STARTMENU_WRITE_BEGIN Application
		;Create shortcuts
		CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
		CreateShortcut "$SMPROGRAMS\$StartMenuFolder\Scriblark.lnk" '"$INSTDIR\bin\Scriblark-wrapper.exe"'
		CreateShortcut "$SMPROGRAMS\$StartMenuFolder\Uninstall.lnk" '"$INSTDIR\Uninstall.exe"'

		!insertmacro RefreshShellIconCreate "$SMPROGRAMS\$StartMenuFolder\Scriblark.lnk"
	!insertmacro MUI_STARTMENU_WRITE_END

	!insertmacro RefreshShellIcons
SectionEnd

;--------------------------------
; Descriptions

; Language strings
LangString DESC_SecXournalpp ${LANG_ENGLISH} "Scriblark executable"
LangString DESC_SecFileXopp ${LANG_ENGLISH} "Open .xopp files with Scriblark"
LangString DESC_SecFileXopt ${LANG_ENGLISH} "Open .xopt files with Scriblark"
LangString DESC_SecFileXoj ${LANG_ENGLISH} "Open .xoj files with Scriblark"

; Assign language strings to sections
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
	!insertmacro MUI_DESCRIPTION_TEXT ${SecXournalpp} $(DESC_SecXournalpp)
	!insertmacro MUI_DESCRIPTION_TEXT ${SecFileXopp} $(DESC_SecFileXopp)
	!insertmacro MUI_DESCRIPTION_TEXT ${SecFileXopt} $(DESC_SecFileXopt)
	!insertmacro MUI_DESCRIPTION_TEXT ${SecFileXoj} $(DESC_SecFileXoj)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; Uninstaller

Section "Uninstall"

	SetRegView 64

	; FIXME: ask if the user wants to uninstall the user or system wide install
	ReadRegStr $0 HKCU "Software\InkQuay" ""
	${IF} $0 == ""
		SetShellVarContext all
	${ELSE}
		SetShellVarContext current
	${ENDIF}

	; Remove registry keys
	DeleteRegKey SHCTX "Software\InkQuay"
	DeleteRegKey SHCTX "Software\Classes\Applications\inkquay.exe"
	DeleteRegKey SHCTX "Software\Microsoft\Windows\CurrentVersion\App Paths\inkquay.exe"
	DeleteRegKey SHCTX "Software\Microsoft\Windows\CurrentVersion\Uninstall\InkQuay"

	!insertmacro DeleteProgId "InkQuay.File"
	!insertmacro DeleteProgId "InkQuay.Template"
	!insertmacro DeleteProgId "InkQuay.Xournal"
	!insertmacro DeleteProgId "InkQuay.AnnotatePdf"

	; Clean up start menu
	!insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
	Delete "$SMPROGRAMS\$StartMenuFolder\Scriblark.lnk"
	Delete "$SMPROGRAMS\$StartMenuFolder\Uninstall.lnk"
	RMDir "$SMPROGRAMS\$StartMenuFolder"

	; Remove files
	RMDir /r "$INSTDIR\bin"
	RMDir /r "$INSTDIR\lib"
	RMDir /r "$INSTDIR\share"
	RMDir /r "$INSTDIR\ui"
	Delete "$INSTDIR\Uninstall.exe"
	RMDir "$INSTDIR"

	!insertmacro RefreshShellIconDelete "$SMPROGRAMS\$StartMenuFolder\Scriblark.lnk"
	!insertmacro RefreshShellIcons
SectionEnd
