# Copyright 2026 Trieflow LLC. MIT. Actual observer orchestration/reporting boundaries.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
. (Join-Path $PSScriptRoot 'crash_observer.ps1')
function Check($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
function State {
    return @{observerRequested=$false;observerStopped=$false;observerProcess=$null;observerDebugger=$null;
        observerErrors=[Collections.Generic.List[string]]::new();observerEvidence=$null;processOwned=$false;
        primary_error='preserve original workflow failure';observerNonce=('a'*32);record=@{sourceCommit=('b'*40)};
        observerTarget=@{process_id=42;start_filetime=123;executable='owned';executable_sha256=('c'*64);package_full_name='fixture'}}
}
$state=State
Start-InkCrashObserver $state 'must-not-be-read'
Check ($state.observerErrors.Count -eq 0 -and -not $state.observerStopped) 'Default observer mode performed work.'
$state.observerRequested=$true
Start-InkCrashObserver $state 'must-not-be-read'
Check ($state.observerErrors.Count -eq 1 -and $state.observerErrors[0] -match 'ownership' -and -not $state.observerProcess) 'Unowned target started a debugger.'
Check ($state.primary_error -ceq 'preserve original workflow failure') 'Observer failure displaced original error.'
1..50 | ForEach-Object { Add-InkObserverError $state ('x'*4096) }
Check ($state.observerErrors.Count -eq 12 -and @($state.observerErrors|Where-Object Length -gt 1024).Count -eq 0) 'Observer diagnostics exceeded their bounds.'

foreach ($mode in @('valid','wrong-nonce','wrong-target','false-mode-type')) {
    $temporaryRoot=if ($IsWindows) { [IO.Path]::GetTempPath() } else { '/private/tmp' }
    $root=Join-Path $temporaryRoot ('ink-observer-report-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory $root | Out-Null
    $child=$null
    try {
        $state=State;$state.observerRequested=$true;$state.output=$root
        $info=[Diagnostics.ProcessStartInfo]::new((Get-Process -Id $PID).Path);$info.UseShellExecute=$false
        foreach ($arg in @('-NoLogo','-NoProfile','-Command','exit 0')) { $info.ArgumentList.Add($arg) }
        $child=[Diagnostics.Process]::Start($info);$null=$child.Handle
        Check ($child.WaitForExit(10000)) 'Owned helper fixture did not exit.'
        $state.observerProcess=$child
        $record=@{nonce=$state.observerNonce;source_commit=$state.record.sourceCommit;target=$state.observerTarget.Clone();
            diagnostic_observer=$true;consumer_acceptance=$false;diagnostic_errors=@('fixture diagnostic failure')}
        if ($mode -ceq 'wrong-nonce') { $record.nonce='other' }
        if ($mode -ceq 'wrong-target') { $record.target.process_id=43 }
        if ($mode -ceq 'false-mode-type') { $record.consumer_acceptance=0 }
        Write-NewUtf8Json (Join-Path $root 'crash-observer.json') $record
        Stop-InkCrashObserver $state
        Check ($state.primary_error -ceq 'preserve original workflow failure') 'Observer report displaced original failure.'
        if ($mode -ceq 'valid') {
            Check ($null -ne $state.observerEvidence -and $state.observerErrors[0] -ceq 'fixture diagnostic failure') ('Owned observer report/secondary failure was lost: '+($state.observerErrors -join '; '))
        } else { Check ($null -eq $state.observerEvidence -and $state.observerErrors.Count -eq 1) 'Unbound observer report was accepted.' }
    } finally {
        if ($child) { $child.Dispose() }
        Remove-Item $root -Recurse -Force
    }
}
$root=Join-Path $(if ($IsWindows) { [IO.Path]::GetTempPath() } else { '/private/tmp' }) ('ink-observer-stop-failure-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $root | Out-Null
$child=$null
try {
    $state=State;$state.observerRequested=$true;$state.output=Join-Path $root 'missing-parent'
    $info=[Diagnostics.ProcessStartInfo]::new((Get-Process -Id $PID).Path);$info.UseShellExecute=$false
    foreach ($arg in @('-NoLogo','-NoProfile','-Command','Start-Sleep -Seconds 30')) { $info.ArgumentList.Add($arg) }
    $child=[Diagnostics.Process]::Start($info);$null=$child.Handle
    $state.observerProcess=$child
    # Keep a separate original handle for observing exit after the production
    # cleanup disposes its own retained Process wrapper.
    $retained=[Diagnostics.Process]::GetProcessById($child.Id);$null=$retained.Handle
    try {
        Stop-InkCrashObserver $state
        Check ($retained.WaitForExit(5000)) 'Stop-file failure left the owned observer helper running.'
        Check ($state.observerErrors.Count -ge 2 -and $state.primary_error -ceq 'preserve original workflow failure') 'Stop-file failure lost secondary cleanup or original failure.'
    } finally {
        if (-not $retained.HasExited) { $retained.Kill();$null=$retained.WaitForExit(5000) }
        $retained.Dispose()
    }
} finally {
    if ($child) { $child.Dispose() }
    Remove-Item $root -Recurse -Force
}
Write-Output 'PASS: default off, unowned attachment refusal, bounded secondary errors, and exact observer result identity/types with real retained helper exits.'
