# Copyright 2026 Trieflow LLC. MIT. Temporary capture lifecycle only.
function Invoke-ScribCaptureFiles([string]$Mode,$State,[string[]]$Extra=@()){
    $raw=& python (Join-Path $PSScriptRoot 'capture_files.py') $Mode --state $State.statePath @Extra
    if($LASTEXITCODE -ne 0){throw "Owned capture files failed: $Mode"}
    return ($raw -join "`n")|ConvertFrom-Json
}
function Invoke-ScribCaptureLifecycle($Operations){
    $primary=$null;$cleanup=[Collections.Generic.List[string]]::new()
    try{foreach($name in @('Preflight','Prepare','Sign','Install','Activate','Workflow','Close','Uninstall')){& $Operations[$name]|Out-Host}}
    catch{$primary=$_.Exception.ToString();try{& $Operations.ObserveFailure|Out-Host}catch{$cleanup.Add('Failure observation: '+$_.Exception.Message)}}
    finally{foreach($name in @('Stop','RestoreDisplay','RemovePackage','RemoveDemoAndProfiles','RemoveTrust','RemoveKey','RemoveTemporary')){try{& $Operations[$name]|Out-Host}catch{$cleanup.Add($name+': '+$_.Exception.Message)}}}
    return @{primary_error=$primary;cleanup_errors=@($cleanup)}
}
function Get-ScribCaptureStartupObservation($State){
    Assert-ScribCaptureProcess $State
    return @{process_id=$State.process.Id;main_window_handle=[long]$State.process.MainWindowHandle;
        main_window_title=[string]$State.process.MainWindowTitle;native_windows=@([InkQuayWorkflow.Native]::Windows($State.process.Id))}
}
function Wait-ScribCaptureMain($State,[ValidateRange(1,30000)][int]$TimeoutMilliseconds=30000){
    $watch=[Diagnostics.Stopwatch]::StartNew();$samples=[Collections.Generic.List[object]]::new()
    $receipt=@{schema_version=1;timeout_ms=$TimeoutMilliseconds;accepted=$false;observations=$samples;omitted_observations=0;elapsed_ms=0;last_rejection=$null}
    $State.startupWindowObservation=$receipt
    try{
        do{
            # Ownership failures are terminal; only incomplete window readiness
            # converges. This never repeats activation or sends input.
            $sample=Get-ScribCaptureStartupObservation $State
            $sample.elapsed_ms=$watch.ElapsedMilliseconds
            if($sample.native_windows.Count -gt 64){throw 'Capture startup native window inventory exceeds bound'}
            if($samples.Count -lt 301){$samples.Add($sample)}else{$receipt.omitted_observations++}
            if($watch.ElapsedMilliseconds -ge $TimeoutMilliseconds){break}
            $window=$null
            if($sample.main_window_handle -ne 0 -and $sample.main_window_title -ceq 'Unsaved Document - Scriblark'){
                try{$window=Select-InkWorkflowWindow $sample.native_windows $sample.process_id $sample.main_window_handle 'Unsaved Document - Scriblark' $false}
                catch{$receipt.last_rejection=$_.Exception.Message}
            }else{$receipt.last_rejection='Process main HWND/title is not yet the exact startup window'}
            if($window -and $watch.ElapsedMilliseconds -lt $TimeoutMilliseconds){
                $State.main=[long]$window.Handle;$receipt.accepted=$true;return
            }
            Start-Sleep -Milliseconds ([Math]::Max(1,[Math]::Min(100,$TimeoutMilliseconds-$watch.ElapsedMilliseconds)))
        }while($watch.ElapsedMilliseconds -lt $TimeoutMilliseconds)
        throw ('Actual capture main window unavailable within bound: '+$receipt.last_rejection)
    }finally{$receipt.elapsed_ms=$watch.ElapsedMilliseconds;$watch.Stop()}
}
function Write-ScribCaptureStartupObservation($State){
    if($State.ContainsKey('startupWindowObservation') -and -not $State['startupWindowObservationWritten']){
        Write-NewUtf8Json (Join-Path $State.output 'startup-window-observations.json') $State.startupWindowObservation
        $State.startupWindowObservationWritten=$true
    }
}
function New-ScribCaptureOperations($State,$Bound,[string]$InputRoot,[string]$QualifiedSource){
    $full='1659hashfunction.InkQuay_1.0.1.0_x64__r3hxytd7jt6c4';$packageName='1659hashfunction.InkQuay'
    return [ordered]@{
        Preflight={
            foreach($path in @($State.demo)+$State.profiles){if(Test-Path -LiteralPath $path){throw 'Existing capture content/profile preserved'}}
            if(@(Get-AppxPackage -Name $packageName -ErrorAction Stop).Count){throw 'Existing Store registration preserved'}
            New-Item -ItemType Directory -Path $State.output -ErrorAction Stop|Out-Null
            [IO.File]::Copy((Join-Path $InputRoot 'capture-inputs.json'),(Join-Path $State.output 'capture-inputs.json'),$false)
        }.GetNewClosure()
        Prepare={
            $State.fixture=Invoke-ScribCaptureFiles 'create' $State @('--root',$State.demo,'--profile',$State.profiles[0],'--profile',$State.profiles[1])
            Start-ScriblarkMarketingConsumerDisplay $State
            $State.temporary=Join-Path $env:RUNNER_TEMP ('.scriblark-capture-'+[guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $State.temporary -ErrorAction Stop|Out-Null
        }.GetNewClosure()
        Sign={
            $State.signed=Join-Path $State.temporary 'Scriblark.capture.signed.msix';[IO.File]::Copy($State.package,$State.signed,$false)
            $State.certificate=New-SelfSignedCertificate -Type Custom -KeyUsage DigitalSignature -KeyExportPolicy NonExportable -KeySpec Signature -CertStoreLocation 'Cert:\CurrentUser\My' -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3','2.5.29.19={text}') -Subject 'CN=B6A2631A-FD32-45CC-AE12-82466975F528' -FriendlyName 'Scriblark temporary marketing capture' -NotAfter (Get-Date).AddHours(2)
            $public=Join-Path $State.temporary 'capture-public.cer';Export-Certificate -Cert $State.certificate -FilePath $public|Out-Null
            $State.trustAttempted=$true;Import-Certificate -FilePath $public -CertStoreLocation 'Cert:\LocalMachine\TrustedPeople'|Out-Null
            $tool=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin/10.0.26100.0/x64/signtool.exe';$hash=(Get-FileHash $tool).Hash
            Invoke-CheckedNative $tool @('sign','/fd','SHA256','/sha1',$State.certificate.Thumbprint,'/s','My',$State.signed)
            Invoke-CheckedNative $tool @('verify','/pa','/all','/v',$State.signed)
            $sig=Get-AuthenticodeSignature -LiteralPath $State.signed
            if($sig.Status -ne [Management.Automation.SignatureStatus]::Valid -or $sig.SignerCertificate.Thumbprint -cne $State.certificate.Thumbprint -or (Get-FileHash $tool).Hash -cne $hash){throw 'Capture signature or signing tool changed'}
            $null=Assert-FileMatchesRecord $State.package $Bound.package 'Unchanged original Store package'
        }.GetNewClosure()
        Install={
            $State.installAttempted=$true;Add-AppxPackage -Path $State.signed -ErrorAction Stop;$State.addCompleted=$true
            $matches=@(Get-AppxPackage -Name $packageName -ErrorAction Stop)
            if($matches.Count -ne 1 -or $matches[0].Name -cne $packageName -or $matches[0].PackageFullName -cne $full -or $matches[0].Publisher -cne 'CN=B6A2631A-FD32-45CC-AE12-82466975F528' -or [string]$matches[0].Version -cne '1.0.1.0' -or [string]$matches[0].Architecture -cne 'X64' -or $matches[0].PackageFamilyName -cne '1659hashfunction.InkQuay_r3hxytd7jt6c4'){throw 'Installed capture identity differs'}
            $State.installed=$matches[0];$State.ownedPackageFullName=$full;$State.installedByUs=$true
            foreach($entry in $State.record.payload.PSObject.Properties){$null=Assert-FileMatchesRecord (Join-Path $State.installed.InstallLocation $entry.Name) $entry.Value 'Installed original payload'}
        }.GetNewClosure()
        Activate={
            Add-InkQuayActivationTypes;$State.stopped=$false
            $State.brokerPid=[int][InkQuayQualification.ActivationBroker]::Activate('1659hashfunction.InkQuay_r3hxytd7jt6c4!InkQuay',$null)
            $State.process=[Diagnostics.Process]::GetProcessById($State.brokerPid);$null=$State.process.SafeHandle
            Assert-ScribCaptureProcess $State;$State.processOwned=$true
            Wait-ScribCaptureMain $State
            Write-ScribCaptureStartupObservation $State
            Write-NewUtf8Json (Join-Path $State.output 'loaded-modules.json') (Get-ScribCaptureModules $State)
        }.GetNewClosure()
        Workflow={Invoke-ScribCaptureUi $State $QualifiedSource;Write-NewUtf8Json (Join-Path $State.output 'loaded-modules-after-capture.json') (Get-ScribCaptureModules $State)}.GetNewClosure()
        ObserveFailure={
            if($State.processOwned -and -not $State.process.HasExited){Write-NewUtf8Json (Join-Path $State.output 'failure-windows.json') ([InkQuayWorkflow.Native]::Windows($State.process.Id))}
            Write-ScribCaptureStartupObservation $State
        }.GetNewClosure()
        Close={
            Assert-ScribCaptureProcess $State
            if(-not $State.process.CloseMainWindow()){throw 'Capture app refused normal close'}
            $State.exit=Get-InkQuayProcessExitEvidence $State.process 15000
            if(-not $State.exit.normal_exit){throw 'Capture process did not exit normally with zero'}
            $State.normalClose=$true;$State.stopped=$true
            $State.verified=Invoke-ScribCaptureFiles 'verify' $State @('--stopped');$State.sealed=$true
            Write-NewUtf8Json (Join-Path $State.output 'capture-verified-files.json') $State.verified
        }.GetNewClosure()
        Uninstall={
            if(-not $State.installedByUs -or $State.ownedPackageFullName -cne $full){throw 'Capture registration ownership unavailable'}
            Remove-AppxPackage -Package $full -ErrorAction Stop
            if(@(Get-AppxPackage -Name $packageName -ErrorAction Stop).Count){throw 'Capture registration remains'}
            $State.uninstallVerified=$true
        }.GetNewClosure()
        Stop={
            if(-not $State.stopped){
                if(-not $State.processOwned){throw 'Unproven process preserved'}
                $exit=Get-InkQuayProcessExitEvidence $State.process 0
                if(-not $exit.wait_completed){$State.process.Kill();$exit=Get-InkQuayProcessExitEvidence $State.process 10000}
                if(-not $exit.wait_completed -or $exit.observation_error){throw 'Owned process shutdown unproven'}
                $State.cleanupExit=$exit;$State.stopped=$true
            }
        }.GetNewClosure()
        RestoreDisplay={Restore-ScriblarkMarketingConsumerDisplay $State}.GetNewClosure()
        RemovePackage={
            if($State.installAttempted){
                $remaining=@(Get-AppxPackage -Name $packageName -ErrorAction Stop)
                if($State.installedByUs){$owned=@($remaining|Where-Object PackageFullName -CEQ $full);if($owned.Count -gt 1){throw 'Ambiguous registration preserved'};if($owned.Count -eq 1){Remove-AppxPackage -Package $full -ErrorAction Stop}}
                $State.residual=@(Get-AppxPackage -Name $packageName -ErrorAction Stop|ForEach-Object PackageFullName)
                if($State.residual.Count -or ($State.addCompleted -and -not $State.installedByUs)){throw 'Unresolved capture registration preserved'}
            }
        }.GetNewClosure()
        RemoveDemoAndProfiles={
            if($State.fixture){
                if(-not $State.stopped){throw 'Unstopped capture content preserved'}
                if(-not $State.sealed){$null=Invoke-ScribCaptureFiles 'seal' $State @('--stopped');$State.sealed=$true}
                $removed=Invoke-ScribCaptureFiles 'cleanup' $State @('--stopped');$State.fixtureRemoved=$removed.removed -eq $true
            }
        }.GetNewClosure()
        RemoveTrust={if($State.trustAttempted -and $State.certificate){$path='Cert:\LocalMachine\TrustedPeople\'+$State.certificate.Thumbprint;if(Test-Path $path){Remove-Item $path -Force -ErrorAction Stop};if(Test-Path $path){throw 'Owned trust certificate remains'}}}.GetNewClosure()
        RemoveKey={if($State.certificate){$path='Cert:\CurrentUser\My\'+$State.certificate.Thumbprint;if(Test-Path $path){Remove-Item $path -DeleteKey -Force -ErrorAction Stop};if(Test-Path $path){throw 'Owned certificate/key remains'}}}.GetNewClosure()
        RemoveTemporary={if($State.temporary){Remove-Item -LiteralPath $State.temporary -Recurse -Force -ErrorAction Stop;if(Test-Path -LiteralPath $State.temporary){throw 'Owned signing directory remains'}}}.GetNewClosure()
    }
}
