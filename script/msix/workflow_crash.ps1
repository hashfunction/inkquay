# Copyright 2026 Trieflow LLC. MIT. Read-only diagnostics; never workflow acceptance.
function ConvertTo-InkWorkflowApplicationError($Event,$Identity,[DateTime]$EndUtc) {
    if ($Event.Id -ne 1000 -or $Event.ProviderName -cne 'Application Error' -or $null -eq $Event.TimeCreated -or
        $Event.TimeCreated.ToUniversalTime() -lt $Identity.activation_utc -or $Event.TimeCreated.ToUniversalTime() -gt $EndUtc) { return $null }
    $text=$Event.ToXml()
    if ($text.Length -gt 32768) { throw 'Application Error XML exceeds its diagnostic bound.' }
    $settings=[Xml.XmlReaderSettings]::new()
    $settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver=$null;$settings.MaxCharactersInDocument=32768
    $reader=[Xml.XmlReader]::Create([IO.StringReader]::new($text),$settings)
    try { $xml=[Xml.XmlDocument]::new();$xml.XmlResolver=$null;$xml.Load($reader) }
    catch { throw 'Application Error XML is malformed.' }
    finally { $reader.Dispose() }
    $fields=@{}
    foreach ($item in $xml.SelectNodes('/*[local-name()="Event"]/*[local-name()="EventData"]/*[local-name()="Data"]')) {
        $name=$item.GetAttribute('Name')
        if ($fields.ContainsKey($name)) { throw 'Application Error has duplicate metadata fields.' }
        $fields[$name]=$item.InnerText
    }
    if (-not $fields.ContainsKey('AppPath') -or -not $fields.ContainsKey('ProcessId')) { return $null }
    # Do not normalize an event's path into a different target or read its files.
    if (-not [string]::Equals($fields.AppPath,$Identity.executable,[StringComparison]::OrdinalIgnoreCase)) { return $null }
    $processId=[uint32]0
    if ($fields.ProcessId -cmatch '^0x([0-9a-fA-F]{1,8})$') {
        $processId=[Convert]::ToUInt32($Matches[1],16)
    } elseif (-not [uint32]::TryParse($fields.ProcessId,[ref]$processId)) { return $null }
    if ($processId -ne $Identity.process_id) { return $null }
    if ($fields.ContainsKey('PackageFullName') -and $fields.PackageFullName -and
        $fields.PackageFullName -cne $Identity.package_full_name) { return $null }
    foreach ($name in @('ModuleName','ModulePath','ExceptionCode','FaultingOffset')) {
        if (-not $fields.ContainsKey($name)) { throw 'Owned Application Error lacks required fault metadata.' }
        if ($fields[$name].Length -gt 1024) { throw 'Owned Application Error field exceeds its diagnostic bound.' }
    }
    return [ordered]@{record_id=$Event.RecordId;time_utc=$Event.TimeCreated.ToUniversalTime().ToString('o');
        process_id=$processId;executable=$Identity.executable;module_name=$fields.ModuleName;module_path=$fields.ModulePath;
        exception_code=$fields.ExceptionCode;faulting_offset=$fields.FaultingOffset}
}

function Get-InkWorkflowCrashDiagnostics($State) {
    $result=[ordered]@{process_exit=$null;activation_utc=$null;query_end_utc=$null;query_attempts=0;application_errors=@();diagnostic_errors=@()}
    try {
        if (-not $State.processOwned -or -not $State.processHandle -or $State.processHandle.IsInvalid -or $State.processHandle.IsClosed -or
            $State.process.get_Id() -ne $State.brokerProcessId) { throw 'Exact retained workflow process ownership is unavailable.' }
        if ($State.activatedAtUtc -isnot [DateTime] -or -not [IO.Path]::IsPathFullyQualified($State.verifiedExecutablePath) -or
            -not $State.ownedPackageFullName) { throw 'Verified activation identity is unavailable for crash diagnostics.' }
        $end=[DateTime]::UtcNow
        if ($State.activatedAtUtc -gt $end -or ($end-$State.activatedAtUtc).TotalMinutes -gt 30) { throw 'Activation time exceeds the crash diagnostic query bound.' }
        $identity=@{process_id=$State.process.get_Id();executable=$State.verifiedExecutablePath;
            package_full_name=$State.ownedPackageFullName;activation_utc=$State.activatedAtUtc}
        $result.activation_utc=$State.activatedAtUtc.ToString('o')
        # This is the same retained Process/SafeHandle, never a fresh PID lookup.
        $exited=$State.process.WaitForExit(0)
        $exit=[ordered]@{process_id=$identity.process_id;wait_completed=$exited;exit_code=$null;exit_code_hex=$null}
        if ($exited) {
            $exit.exit_code=$State.process.get_ExitCode()
            $exit.exit_code_hex='0x{0:X8}' -f ([long]$exit.exit_code -band 0xffffffffL)
        }
        $result.process_exit=$exit
        if (-not $exited) { return $result }
        # Event publication can lag process exit. Three read-only attempts span
        # at most one second of deliberate waiting; each query returns at most 33.
        for ($attempt=0;$attempt -lt 3;$attempt++) {
            $end=[DateTime]::UtcNow
            $result.query_end_utc=$end.ToString('o');$result.query_attempts++
            $events=@()
            try {
                $events=@(Get-WinEvent -FilterHashtable @{LogName='Application';ProviderName='Application Error';Id=1000;
                    StartTime=$identity.activation_utc;EndTime=$end} -MaxEvents 33 -ErrorAction Stop)
            } catch {
                if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw 'Application Error query failed.' }
            }
            if ($events.Count -gt 32) { throw 'Application Error event count exceeds its diagnostic bound.' }
            $matches=[Collections.Generic.List[object]]::new()
            foreach ($event in $events) {
                $match=ConvertTo-InkWorkflowApplicationError $event $identity $end
                if ($null -ne $match) { $matches.Add($match) }
                if ($matches.Count -gt 4) { throw 'Owned Application Error count exceeds its diagnostic bound.' }
            }
            # Publish only a fully checked collection, never partial event data.
            if ($matches.Count) { $result.application_errors=@($matches);break }
            if ($attempt -lt 2) { Start-Sleep -Milliseconds 500 }
        }
    } catch {
        $message=$_.Exception.Message
        $result.diagnostic_errors+=('Crash observation: '+$message.Substring(0,[Math]::Min(1024,$message.Length)))
    }
    return $result
}

function Add-InkWorkflowFailureEvidence($Result,$State,$Failure) {
    $Result.error=$Failure.Exception.ToString()
    $Result.failed_operation=$Result.active_operation
    try {
        $Result.crash_diagnostics=Get-InkWorkflowCrashDiagnostics $State
        $Result.diagnostic_errors+=@($Result.crash_diagnostics.diagnostic_errors)
    } catch {
        # Even an unexpected diagnostic bug must preserve the original failure.
        $Result.diagnostic_errors+='Crash diagnostic collection failed: '+$_.Exception.GetType().FullName
    }
}
