# Copyright 2026 Trieflow LLC. MIT. Disposable package qualification only.
[CmdletBinding()]
param([switch]$CaptureCrashStack,[switch]$LibraryOnly)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Invoke-InkQuayPackageSequence([scriptblock]$Build,[scriptblock]$Install,[scriptblock]$Export,[bool]$Diagnostic) {
    & $Build 'qualification'
    & $Install 'qualification'
    if (-not $Diagnostic) {
        & $Build 'store'
        & $Install 'store'
        & $Export
    }
}
if ($LibraryOnly) { return }
if (-not $IsWindows -or $env:CI -ne 'true' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'Requires disposable Windows CI and PowerShell 7.' }
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '../..'))
function Invoke-Checked([string]$Program,[string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit $LASTEXITCODE" }
}
[string]$python=(Get-Content -LiteralPath 'build-evidence/python-executable.txt' -Raw).Trim()
if (-not [IO.Path]::IsPathFullyQualified($python) -or -not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Exact same-run MSYS2 Python path is required.' }
$env:INKQUAY_QUALIFICATION_PYTHON=$python
$env:LANG='C'; $env:LANGUAGE='C'
$powerShell=(Get-Process -Id $PID).Path
Invoke-Checked $python @('script/msix/test_msix_qualification.py','-v')
Invoke-Checked $python @('script/msix/test_workflow_files.py','-v')
Invoke-Checked $python @('script/msix/test_gdb_observer.py','-v')
Invoke-Checked $python @('script/msix/test_observer_gdb_build.py','-v')
Invoke-Checked $python @('script/msix/test_gdb_preflight_reporting.py','-v')
foreach($fixture in @('test_store_identity.py','test_source_publication.py','test_store_workflow_evidence.py','test_store_export.py')) { Invoke-Checked $python @((Join-Path $PSScriptRoot $fixture),'-v') }
foreach ($fixture in @('test_qualify_msix_install.ps1','test_msix_evidence.ps1','test_registration_ownership.ps1','test_process_observation.ps1','test_module_collection.ps1','test_window_evidence.ps1','test_defender_module.ps1','test_temporary_ownership.ps1','test_workflow_helpers.ps1','test_export_menu_observation.ps1','test_workflow_crash.ps1','test_crash_observer.ps1','test_store_identity.ps1','test_store_orchestration.ps1')) {
    Invoke-Checked $powerShell @('-NoLogo','-NoProfile','-File',(Join-Path $PSScriptRoot $fixture))
}
Invoke-Checked $powerShell @('-NoLogo','-NoProfile','-File',(Join-Path $PSScriptRoot 'test_registration_ownership.ps1'),'-IdentityMode','store')
$sourceCommit=(git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceCommit -cne $env:GITHUB_SHA) { throw 'Source differs from this qualification run.' }
if ($CaptureCrashStack) {
    # Failure is recorded and prohibits production attachment. It never replaces
    # a later consumer failure, or permits debugger-only consumer acceptance.
    & $python script/msix/test_gdb_observer_windows.py --output build-evidence/crash-observer-preflight.json
    if ($LASTEXITCODE -ne 0) { Write-Host 'Diagnostic observer preflight failed; actual consumer workflow will retain that secondary failure.' }
}
$sdkVersion='10.0.26100.0'
$sdkDirectory=Join-Path ${env:ProgramFiles(x86)} "Windows Kits/10/bin/$sdkVersion/x64"
$packageOutputs=@{}
foreach($mode in @('qualification','store')) { $packageOutputs[$mode]=Join-Path $env:RUNNER_TEMP ('inkquay-msix-'+$mode+'-'+[guid]::NewGuid().ToString('N')) }
$build={param([string]$Mode)
    Invoke-Checked $python @('script/msix/msix_qualification.py','--release','build/dist',
        '--artwork','ui/pixmaps/com.trieflow.inkquay.png','--source-root','.','--source-commit',$sourceCommit,
        '--inventory','build-evidence/package-inventory.json','--startup','build-evidence/windows-startup.json',
        '--makeappx',(Join-Path $sdkDirectory 'makeappx.exe'),'--sdk-version',$sdkVersion,'--output',$packageOutputs[$Mode],'--identity-mode',$Mode)
    $recordName=if($Mode -ceq 'store'){'msix-store-package-record.json'}else{'msix-package-record.json'}
    [IO.File]::Copy((Join-Path $packageOutputs[$Mode] 'package-record.json'),(Join-Path (Get-Location) ('build-evidence/'+$recordName)),$false)
}
$install={param([string]$Mode)
    $name=if($Mode -ceq 'store'){'Scriblark_1.0.1.0_x64.msix'}else{'Scriblark.Qualification_1.0.1.0_x64.msix'}
    $output=if($Mode -ceq 'store'){'build-evidence/msix-store-install'}else{'build-evidence/msix-install'}
    $arguments=@('-NoLogo','-NoProfile','-File','script/msix/qualify-msix-install.ps1',
        '-Package',(Join-Path $packageOutputs[$Mode] $name),'-PackageRecord',(Join-Path $packageOutputs[$Mode] 'package-record.json'),
        '-SignTool',(Join-Path $sdkDirectory 'signtool.exe'),'-Output',$output,'-IdentityMode',$Mode)
    if($CaptureCrashStack){$arguments+='-CaptureCrashStack'}
    # Each identity gets a separate PowerShell process, package and owned temporary tree.
    Invoke-Checked $powerShell $arguments
}
$export={
    Invoke-Checked $python @('script/msix/store_export.py','--qualification',$packageOutputs.qualification,'--store',$packageOutputs.store,'--output','build-evidence/store-ready')
}
Invoke-InkQuayPackageSequence $build $install $export ([bool]$CaptureCrashStack)
