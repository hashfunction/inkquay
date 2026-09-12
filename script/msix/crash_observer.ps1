# Copyright 2026 Trieflow LLC. MIT. Optional external diagnostic observer only.
function Add-InkObserverError($State,[string]$Message) {
    if ($State.observerErrors.Count -lt 12) { $State.observerErrors.Add($Message.Substring(0,[Math]::Min(1024,$Message.Length))) }
}

function Start-InkCrashObserver($State,[string]$SourceRoot) {
    if (-not $State.observerRequested) { return }
    try {
        if (-not $State.processOwned -or -not $State.processHandle -or $State.processHandle.IsInvalid -or
            $State.processHandle.IsClosed -or $State.process.HasExited -or $State.process.Id -ne $State.brokerProcessId) {
            throw 'Exact retained live broker ownership is unavailable for observer.'
        }
        if ([InkQuayQualification.NativePackageProbe]::GetFullName($State.process.Handle) -cne $State.ownedPackageFullName -or
            (Get-CanonicalPath $State.process.MainModule.FileName) -ine $State.verifiedExecutablePath) { throw 'Observer target identity changed.' }
        $hash=Assert-FileMatchesRecord $State.verifiedExecutablePath (Get-RecordPayloadEntry $State.record 'bin/inkquay.exe') 'Observer target'
        $preflight=Join-Path $SourceRoot 'build-evidence/crash-observer-preflight.json'
        Assert-NoReparsePath $preflight
        if ((Get-Item $preflight).Length -gt 1048576 -or (Get-Content $preflight -Raw|ConvertFrom-Json).passed -ne $true) {
            throw 'Live Windows observer fixture did not pass; attachment forbidden.'
        }
        $State.observerNonce=[guid]::NewGuid().ToString('N')
        $State.observerTarget=[ordered]@{process_id=$State.process.Id;start_filetime=$State.process.StartTime.ToUniversalTime().ToFileTimeUtc();
            executable=$State.verifiedExecutablePath;executable_sha256=$hash;package_full_name=$State.ownedPackageFullName}
        $request=Join-Path $State.temporary 'crash-observer-request.json'
        Write-NewUtf8Json $request ([ordered]@{nonce=$State.observerNonce;source_commit=$State.record.sourceCommit;
            target=$State.observerTarget;activation_utc=$State.activatedAtUtc.ToString('o');output=$State.output;preflight=$preflight})
        $python=$env:INKQUAY_QUALIFICATION_PYTHON
        Assert-NoReparsePath $python
        $info=[Diagnostics.ProcessStartInfo]::new($python)
        $info.UseShellExecute=$false;$info.CreateNoWindow=$true
        foreach ($arg in @((Join-Path $PSScriptRoot 'gdb_observer.py'),'--request',$request,'--request-sha256',(Get-FileHash $request).Hash.ToLowerInvariant())) { $info.ArgumentList.Add($arg) }
        $process=[Diagnostics.Process]::new();$process.StartInfo=$info
        try { if (-not $process.Start()) { throw 'Observer helper did not start.' } } catch { $process.Dispose();throw }
        $State.observerProcess=$process;$null=$process.Handle
        $ready=Join-Path $State.output 'crash-observer-ready.json'
        $deadline=[DateTime]::UtcNow.AddSeconds(25)
        while (-not (Test-Path $ready)) {
            if ($process.HasExited) { throw 'Observer helper exited before readiness.' }
            if ([DateTime]::UtcNow -gt $deadline) { throw 'Observer readiness deadline exceeded.' }
            Start-Sleep -Milliseconds 100
        }
        Assert-NoReparsePath $ready
        if ((Get-Item $ready).Length -gt 8192) { throw 'Observer readiness exceeds bound.' }
        $observed=Get-Content $ready -Raw|ConvertFrom-Json
        if ($observed.nonce -cne $State.observerNonce -or $observed.helper_process_id -ne $process.Id) { throw 'Observer readiness nonce/helper differs.' }
        foreach ($key in $State.observerTarget.Keys) {
            if ($observed.target.$key -cne $State.observerTarget[$key]) { throw 'Observer readiness target differs.' }
        }
        # This descriptor is emitted by our current-source helper only after
        # GDB independently verifies the target and resumes it.
        $debugger=[Diagnostics.Process]::GetProcessById([int]$observed.debugger_process_id)
        try {
            $null=$debugger.Handle
            $expected=Join-Path (Split-Path $python) 'gdb.exe'
            if ($debugger.HasExited -or $debugger.StartTime.ToUniversalTime() -lt $process.StartTime.ToUniversalTime() -or
                $debugger.StartTime.ToUniversalTime().ToFileTimeUtc() -ne $observed.debugger_start_filetime -or
                (Get-CanonicalPath $debugger.MainModule.FileName) -ine (Get-CanonicalPath $expected)) { throw 'Observer debugger ownership differs.' }
            $State.observerDebugger=$debugger
        } finally { if (-not $State.observerDebugger) { $debugger.Dispose() } }
        $State.observerAttached=$true
    } catch {
        Add-InkObserverError $State ('Start: '+$_.Exception.Message)
        Stop-InkCrashObserver $State
    }
}

function Stop-InkCrashObserver($State) {
    if (-not $State.observerRequested -or $State.observerStopped) { return }
    $State.observerStopped=$true
    try {
        if ($State.observerProcess) {
            if (-not $State.observerProcess.HasExited) {
                $stop=Join-Path $State.output 'crash-observer-stop.json'
                if (-not (Test-Path $stop)) { Write-NewUtf8Json $stop @{nonce=$State.observerNonce} }
                if (-not $State.observerProcess.WaitForExit(15000)) {
                    Add-InkObserverError $State 'Observer helper exceeded detach deadline.'
                    # The live native fixture must prove attached-target survival
                    # before this debugger is allowed to attach to the consumer.
                    if ($State.observerDebugger -and -not $State.observerDebugger.HasExited) {
                        $State.observerDebugger.Kill();$null=$State.observerDebugger.WaitForExit(5000)
                    }
                    if (-not $State.observerProcess.HasExited) { $State.observerProcess.Kill();$null=$State.observerProcess.WaitForExit(5000) }
                }
            }
            $path=Join-Path $State.output 'crash-observer.json'
            Assert-NoReparsePath $path
            if ((Get-Item $path).Length -gt 1048576) { throw 'Observer result exceeds bound.' }
            $value=Get-Content $path -Raw|ConvertFrom-Json
            if ($value.nonce -cne $State.observerNonce -or $value.source_commit -cne $State.record.sourceCommit -or
                $value.diagnostic_observer -isnot [bool] -or $value.diagnostic_observer -ne $true -or
                $value.consumer_acceptance -isnot [bool] -or $value.consumer_acceptance -ne $false) { throw 'Observer result identity/diagnostic mode differs.' }
            foreach ($key in $State.observerTarget.Keys) {
                if ($value.target.$key -cne $State.observerTarget[$key]) { throw 'Observer result target differs.' }
            }
            $State.observerEvidence=$value
            foreach ($error in $value.diagnostic_errors) { Add-InkObserverError $State ([string]$error) }
        }
    } catch { Add-InkObserverError $State ('Stop: '+$_.Exception.Message) }
    finally {
        if ($State.observerDebugger) {
            try {
                if (-not $State.observerDebugger.HasExited) {
                    $State.observerDebugger.Kill();$null=$State.observerDebugger.WaitForExit(5000)
                    Add-InkObserverError $State 'Retained debugger required fallback termination.'
                }
            } catch { Add-InkObserverError $State ('Debugger cleanup: '+$_.Exception.Message) }
            try { $State.observerDebugger.Dispose() } catch { Add-InkObserverError $State ('Debugger disposal: '+$_.Exception.Message) }
        }
        if ($State.observerProcess) {
            try {
                if (-not $State.observerProcess.HasExited) {
                    $State.observerProcess.Kill();$null=$State.observerProcess.WaitForExit(5000)
                    Add-InkObserverError $State 'Retained observer helper required fallback termination.'
                }
            } catch { Add-InkObserverError $State ('Observer cleanup: '+$_.Exception.Message) }
            try { $State.observerProcess.Dispose() } catch { Add-InkObserverError $State ('Observer disposal: '+$_.Exception.Message) }
        }
    }
}
