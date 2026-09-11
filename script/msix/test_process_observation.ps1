# Copyright 2026 Trieflow LLC. MIT. Actual process/handle fixtures, no native GUI claim.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
foreach ($code in @(0,7)) {
    $start=[Diagnostics.ProcessStartInfo]::new((Get-Process -Id $PID).Path)
    $start.UseShellExecute=$false
    $start.RedirectStandardOutput=$true
    foreach ($arg in @('-NoLogo','-NoProfile','-Command',('[Console]::WriteLine("ready"); Start-Sleep -Milliseconds 600; exit '+$code))) { $start.ArgumentList.Add($arg) }
    $started=[Diagnostics.Process]::Start($start)
    $attached=$null
    try {
        if ($started.StandardOutput.ReadLine() -cne 'ready') { throw 'Fixture failed to start' }
        $attached=[Diagnostics.Process]::GetProcessById($started.Id)
        $handle=$attached.SafeHandle
        if ($handle.IsInvalid -or $handle.IsClosed) { throw 'Did not retain live attached handle' }
        $timeout=Get-InkQuayProcessExitEvidence $attached 1
        if ($timeout.wait_completed -or $null -ne $timeout.exit_code -or $timeout.normal_exit -or $timeout.observation_error) { throw 'Timeout was confused with observed exit' }
        $exit=Get-InkQuayProcessExitEvidence $attached 10000
        if (-not $exit.wait_completed -or $exit.exit_code -ne $code -or $exit.normal_exit -ne ($code -eq 0) -or $exit.observation_error) { throw 'Attached process exit evidence was incorrect' }
        Write-Output "PASS retained attached handle: exit $code and timeout remain distinct"
    } finally {
        if (-not $started.HasExited) { $started.Kill();$started.WaitForExit() }
        if ($attached) { $attached.Dispose() };$started.Dispose()
    }
}
$unattached=[Diagnostics.Process]::new()
try {
    $observed=Get-InkQuayProcessExitEvidence $unattached 1
    if (-not $observed.observation_error -or $observed.normal_exit -or $null -ne $observed.exit_code) { throw 'Unattached observation must not claim a normal exit' }
} finally { $unattached.Dispose() }
Write-Output 'PASS observation error remains separate from timeout and nonzero exit'

# Exercise the real StopOwnedProcess closure against live children. A broker PID
# is not cleanup ownership until executable and package identity were verified.
$script:ProcessFixture=$null
function Invoke-InkQuayQualificationCore([Collections.IDictionary]$Operations) {
    $fixture=$script:ProcessFixture
    $state=$Operations.Preflight.Module.SessionState.PSVariable.GetValue('state')
    $state.output=$fixture.directory
    $state.package=Join-Path $fixture.directory 'unsigned.msix'
    [IO.File]::WriteAllText($state.package,'unsigned fixture')
    $state.unsignedPackageSha256=(Get-FileHash $state.package -Algorithm SHA256).Hash.ToLowerInvariant()
    $state.process=[Diagnostics.Process]::GetProcessById($fixture.child.Id)
    $state.processHandle=$state.process.SafeHandle
    $state['processOwned']=$fixture.owned
    & $Operations.StopOwnedProcess
    return [pscustomobject]@{installation_qualification_passed=$false;primary_error='controlled test';cleanup_errors=@()}
}
foreach ($owned in @($false,$true)) {
    $directory=Join-Path ([IO.Path]::GetTempPath()) ('inkquay-process-ownership-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory $directory | Out-Null
    $start=[Diagnostics.ProcessStartInfo]::new((Get-Process -Id $PID).Path)
    $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true
    foreach ($arg in @('-NoLogo','-NoProfile','-Command','[Console]::WriteLine("ready"); Start-Sleep -Seconds 30')) { $start.ArgumentList.Add($arg) }
    $child=[Diagnostics.Process]::Start($start)
    try {
        if ($child.StandardOutput.ReadLine() -cne 'ready') { throw 'Fixture did not start' }
        $script:ProcessFixture=@{directory=$directory;child=$child;owned=$owned}
        try { Invoke-InkQuayInstallQualification unused unused unused $directory | Out-Null } catch {
            if ($_.Exception.Message -notmatch 'controlled test') { throw }
        }
        if ($owned -and -not $child.WaitForExit(5000)) { throw 'Exact verified owned process was not stopped' }
        if (-not $owned -and $child.HasExited) { throw 'Unverified broker process was incorrectly killed' }
        $record=Get-Content (Join-Path $directory 'installation-qualification.json') -Raw | ConvertFrom-Json
        if ($owned -and (-not $record.cleanup_process_exit.wait_completed -or $record.cleanup_process_exit.process_id -ne $child.Id)) { throw 'Owned cleanup exit observation was not retained' }
        if (-not $owned -and $null -ne $record.cleanup_process_exit) { throw 'Unowned process cleanup observation was fabricated' }
        Write-Output "PASS actual cleanup closure: process identity ownership $owned"
    } finally {
        if (-not $child.HasExited) { $child.Kill();$child.WaitForExit() }
        $child.Dispose();Remove-Item $directory -Recurse -Force
    }
}
