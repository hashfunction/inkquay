# Copyright 2026 Trieflow LLC. MIT. Disposable package qualification only.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
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
foreach ($fixture in @('test_qualify_msix_install.ps1','test_msix_evidence.ps1','test_registration_ownership.ps1','test_process_observation.ps1','test_module_collection.ps1','test_window_evidence.ps1','test_defender_module.ps1','test_temporary_ownership.ps1','test_workflow_helpers.ps1','test_workflow_crash.ps1')) {
    Invoke-Checked $powerShell @('-NoLogo','-NoProfile','-File',(Join-Path $PSScriptRoot $fixture))
}
$sourceCommit=(git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceCommit -cne $env:GITHUB_SHA) { throw 'Source differs from this qualification run.' }
$sdkVersion='10.0.26100.0'
$sdkDirectory=Join-Path ${env:ProgramFiles(x86)} "Windows Kits/10/bin/$sdkVersion/x64"
$packageOutput=Join-Path $env:RUNNER_TEMP ('inkquay-msix-'+[guid]::NewGuid().ToString('N'))
Invoke-Checked $python @('script/msix/msix_qualification.py','--release','build/dist',
    '--artwork','ui/pixmaps/com.trieflow.inkquay.png','--source-root','.','--source-commit',$sourceCommit,
    '--inventory','build-evidence/package-inventory.json','--startup','build-evidence/windows-startup.json',
    '--makeappx',(Join-Path $sdkDirectory 'makeappx.exe'),'--sdk-version',$sdkVersion,'--output',$packageOutput)
# Upload only the metadata copy. Unsigned/signed MSIX and certificates never enter artifact globs.
[IO.File]::Copy((Join-Path $packageOutput 'package-record.json'),(Join-Path (Get-Location) 'build-evidence/msix-package-record.json'),$false)
Invoke-Checked $powerShell @('-NoLogo','-NoProfile','-File','script/msix/qualify-msix-install.ps1',
    '-Package',(Join-Path $packageOutput 'InkQuay.Qualification_1.0.0.0_x64.msix'),
    '-PackageRecord',(Join-Path $packageOutput 'package-record.json'),
    '-SignTool',(Join-Path $sdkDirectory 'signtool.exe'),'-Output','build-evidence/msix-install')
