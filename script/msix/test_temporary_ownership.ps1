# Real preparation/cleanup closures. Simulate a colliding, unowned temporary path.
# Copyright 2026 Trieflow LLC. MIT.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
$script:ActualCore=${function:Invoke-InkQuayQualificationCore}
$script:probeRoot=Join-Path ([IO.Path]::GetTempPath()) ('inkquay-temporary-test-'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($script:probeRoot) | Out-Null
$script:collision=$null
$previousRunnerTemp=$env:RUNNER_TEMP
$env:RUNNER_TEMP=$script:probeRoot
function New-Item {
    [CmdletBinding()] param([string]$ItemType,[string]$Path)
    $script:collision=$Path
    [IO.Directory]::CreateDirectory($Path) | Out-Null
    [IO.File]::WriteAllText((Join-Path $Path 'unowned.txt'),'preserve other owner')
    throw 'Temporary directory creation collided with another owner'
}
function Invoke-InkQuayQualificationCore([Collections.IDictionary]$Operations) {
    $state=$Operations.Preflight.Module.SessionState.PSVariable.GetValue('state')
    $state.output=$script:probeRoot
    $state.package=Join-Path $script:probeRoot 'original.msix'
    [IO.File]::WriteAllText($state.package,'original unsigned fixture')
    $state.unsignedPackageSha256=(Get-FileHash $state.package -Algorithm SHA256).Hash.ToLowerInvariant()
    $Operations.Preflight={}
    # The collision occurs before certificate creation. Run the real owned cleanup.
    return & $script:ActualCore $Operations
}
try {
    $failure=$null
    try { Invoke-InkQuayInstallQualification unused unused unused $script:probeRoot | Out-Null }
    catch { $failure=$_.Exception.Message }
    if ($failure -notmatch 'collided with another owner') { throw 'Original preparation failure was lost' }
    if (-not (Test-Path -LiteralPath (Join-Path $script:collision 'unowned.txt'))) { throw 'Unowned colliding temporary directory was deleted' }
    if ((Get-Content -LiteralPath (Join-Path $script:collision 'unowned.txt') -Raw) -cne 'preserve other owner') { throw 'Unowned bytes changed' }
    Write-Output 'PASS real preparation failure preserves an unowned colliding temporary directory'
} finally {
    $env:RUNNER_TEMP=$previousRunnerTemp
    Remove-Item -LiteralPath $script:probeRoot -Recurse -Force
}
