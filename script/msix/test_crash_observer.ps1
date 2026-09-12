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

# Replay the actual post-readiness ownership block from Start-InkCrashObserver.
# Only its Process property adapter is a fixture; path reads/hashes/reparse checks
# and the production native-payload/start-time predicates execute unchanged.
$observerSource=Get-Content (Join-Path $PSScriptRoot 'crash_observer.ps1') -Raw
$boundaryStart=$observerSource.IndexOf('            $expected=')
$boundaryEnd=$observerSource.IndexOf('        } finally { if (-not $State.observerDebugger)', $boundaryStart)
Check ($boundaryStart -ge 0 -and $boundaryEnd -gt $boundaryStart) 'Actual debugger ownership boundary was not found.'
$ownershipBoundary=[scriptblock]::Create($observerSource.Substring($boundaryStart,$boundaryEnd-$boundaryStart))
function Invoke-DebuggerOwnershipFixture($SourceRoot,$preflight,$debugger,$process,$observed) {
    $State=@{observerDebugger=$null}
    . $ownershipBoundary
    return $State.observerDebugger
}
$ownershipChecks=0
foreach ($leaf in @('gdb.exe','lt-gdb.exe')) {
    $root=Join-Path $(if ($IsWindows) { [IO.Path]::GetTempPath() } else { '/private/tmp' }) ('ink-debugger-path-'+[guid]::NewGuid().ToString('N'))
    $nativeRoot=Join-Path $root 'build-observer-gdb/build/gdb/.libs'
    New-Item -ItemType Directory $nativeRoot | Out-Null
    try {
        $native=Join-Path $nativeRoot $leaf
        $wrapper=Join-Path (Split-Path $nativeRoot -Parent) 'gdb.exe'
        [IO.File]::WriteAllText($native,'fixture native payload, never executed')
        [IO.File]::WriteAllText($wrapper,'fixture Libtool launcher, never executed')
        $preflight=Join-Path $root 'preflight.json'
        $fingerprint=@{gdb=$native;gdb_sha256=(Get-FileHash $native).Hash.ToLowerInvariant()}
        Write-NewUtf8Json $preflight @{fingerprint=$fingerprint}
        $time=[DateTime]::UtcNow
        $debugger=@{HasExited=$false;StartTime=$time;MainModule=@{FileName=$native}}
        $process=@{StartTime=$time.AddSeconds(-1)}
        $observed=@{debugger_start_filetime=$time.ToFileTimeUtc()}
        $actual=Invoke-DebuggerOwnershipFixture $root $preflight $debugger $process $observed
        Check ([object]::ReferenceEquals($actual,$debugger)) ('Actual native Libtool payload refused: '+$leaf)
        $ownershipChecks++
        foreach ($mode in @('wrapper','foreign','wrong-hash','missing','ambiguous','reparse','process-path','process-start','process-exited','preexisting-process')) {
            $other=Join-Path $nativeRoot $(if ($leaf -ceq 'gdb.exe') {'lt-gdb.exe'} else {'gdb.exe'})
            $row=$fingerprint.Clone();$candidate=@{HasExited=$false;StartTime=$time;MainModule=@{FileName=$native}}
            switch ($mode) {
                'wrapper' {$row.gdb=$wrapper;$row.gdb_sha256=(Get-FileHash $wrapper).Hash.ToLowerInvariant();$candidate.MainModule.FileName=$wrapper}
                'foreign' {$row.gdb=Join-Path $root 'foreign.exe';Copy-Item $native $row.gdb;$candidate.MainModule.FileName=$row.gdb}
                'wrong-hash' {$row.gdb_sha256='0'*64}
                'missing' {[IO.File]::Move($native,$native+'.held')}
                'ambiguous' {Copy-Item $native $other}
                'reparse' {[IO.Directory]::Move($nativeRoot,$nativeRoot+'.held');$linkType=if ($IsWindows) {'Junction'} else {'SymbolicLink'};New-Item -ItemType $linkType -Path $nativeRoot -Target ($nativeRoot+'.held') | Out-Null}
                'process-path' {$candidate.MainModule.FileName=$wrapper}
                'process-start' {$candidate.StartTime=$time.AddSeconds(1)}
                'process-exited' {$candidate.HasExited=$true}
                'preexisting-process' {$candidate.StartTime=$time.AddSeconds(-2)}
            }
            [IO.File]::WriteAllText($preflight,(@{fingerprint=$row}|ConvertTo-Json -Depth 4))
            $failure=$null
            try {$null=Invoke-DebuggerOwnershipFixture $root $preflight $candidate $process $observed}
            catch {$failure=$_.Exception.Message}
            Check ($null -ne $failure) ('Accepted unbound debugger '+$leaf+'/'+$mode)
            $ownershipChecks++
            if ($mode -ceq 'reparse') {[IO.Directory]::Delete($nativeRoot);[IO.Directory]::Move($nativeRoot+'.held',$nativeRoot)}
            if ($mode -ceq 'missing') {[IO.File]::Move($native+'.held',$native)}
            if (Test-Path $other) {[IO.File]::Delete($other)}
        }
    } finally {Remove-Item -LiteralPath $root -Recurse -Force}
}
Write-Output "PASS: actual post-readiness debugger ownership boundary: $ownershipChecks native Libtool, wrapper/foreign/hash/reparse and process-lifetime checks."

Write-Output 'PASS: default off, unowned attachment refusal, bounded secondary errors, and exact observer result identity/types with real retained helper exits.'
