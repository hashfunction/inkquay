# Copyright 2026 Trieflow LLC. MIT. Real retained process and production diagnostic boundaries.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-workflow.ps1')
function Check($Value,[string]$Message) { if (-not $Value) { throw $Message } }
function Reject($Action,[string]$Pattern) {
    $failure=$null
    try { & $Action | Out-Null } catch { $failure=$_.Exception.Message }
    Check ($failure -match $Pattern) "Expected $Pattern, observed $failure"
}
$script:now=[DateTime]::UtcNow
$script:identity=@{process_id=42;executable=[IO.Path]::GetFullPath('owned/inkquay.exe');package_full_name='owned-package';activation_utc=$script:now.AddMinutes(-1)}
function Event($Changes=@{}) {
    $fields=[ordered]@{AppPath=$script:identity.executable;ProcessId=('0x{0:x}' -f $script:identity.process_id);ModuleName='libgtk-3-0.dll';ModulePath='C:\owned\libgtk-3-0.dll';ExceptionCode='c0000005';FaultingOffset='0000000000012345';PackageFullName='owned-package'}
    foreach ($key in $Changes.Keys) { if ($fields.Contains($key)) { $fields[$key]=$Changes[$key] } }
    $data=($fields.Keys | ForEach-Object { '<Data Name="'+$_+'">'+[Security.SecurityElement]::Escape([string]$fields[$_])+'</Data>' }) -join ''
    $event=[pscustomobject]@{Id=1000;ProviderName='Application Error';TimeCreated=$script:now;RecordId=17;Xml='<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><EventData>'+$data+'</EventData></Event>'}
    foreach ($key in $Changes.Keys) { if ($event.PSObject.Properties[$key]) { $event.$key=$Changes[$key] } }
    $event | Add-Member ScriptMethod ToXml { return $this.Xml }
    return $event
}
$valid=Event
$record=ConvertTo-InkWorkflowApplicationError $valid $script:identity $script:now
Check ($record.process_id -eq 42 -and $record.exception_code -ceq 'c0000005' -and
    $record.faulting_offset -ceq '0000000000012345' -and $record.module_name -ceq 'libgtk-3-0.dll') 'Exact matching crash metadata lost.'
foreach ($change in @(
    @{ProcessId='43'},@{AppPath=($script:identity.executable+'.other')},@{TimeCreated=$script:identity.activation_utc.AddSeconds(-1)},
    @{TimeCreated=$script:now.AddSeconds(1)},@{ProviderName='Other'},@{Id=1001},@{PackageFullName='other-package'}
)) {
    Check ($null -eq (ConvertTo-InkWorkflowApplicationError (Event $change) $script:identity $script:now)) 'Unowned event was retained.'
}
Check ((ConvertTo-InkWorkflowApplicationError (Event @{ProcessId='42';PackageFullName=''}) $script:identity $script:now).process_id -eq 42) 'Decimal PID or absent optional package identity rejected.'
Reject { ConvertTo-InkWorkflowApplicationError (Event @{Xml=('x'*32769)}) $script:identity $script:now } 'bound'
Reject { ConvertTo-InkWorkflowApplicationError (Event @{Xml='<Event><EventData><Data Name="AppPath">one</Data><Data Name="AppPath">two</Data></EventData></Event>'}) $script:identity $script:now } 'duplicate'
Reject { ConvertTo-InkWorkflowApplicationError (Event @{ModuleName=('x'*1025)}) $script:identity $script:now } 'bound'
Reject { ConvertTo-InkWorkflowApplicationError (Event @{Xml='<!DOCTYPE Event [<!ENTITY value "external">]><Event>&value;</Event>'}) $script:identity $script:now } 'malformed'
Write-Output 'PASS: exact PID/executable/time/package matching excludes unrelated events; XML and field bounds enforced.'

# The real child/attached handle proves exit observation without reopening by PID
# after exit. Only Get-WinEvent, an unavailable platform boundary, is adapted.
function Get-WinEvent($FilterHashtable,$MaxEvents,$ErrorAction) {
    $script:queries++
    Check ($FilterHashtable.LogName -ceq 'Application' -and $FilterHashtable.ProviderName -ceq 'Application Error' -and
        $FilterHashtable.Id -eq 1000 -and $FilterHashtable.StartTime -eq $script:identity.activation_utc -and $MaxEvents -eq 33) 'Unbounded or unrelated event query.'
    if ($script:queryMode -ceq 'failure') { throw 'controlled event query failure' }
    if ($script:queryMode -ceq 'overflow') { return @(1..33 | ForEach-Object { Event }) }
    if ($script:queryMode -ceq 'matches-overflow') { return @(1..5 | ForEach-Object { Event }) }
    if ($script:queryMode -ceq 'empty') { return @() }
    return @((Event @{ProcessId='999999'}),(Event @{ProcessId=[string]$script:identity.process_id}))
}
$info=[Diagnostics.ProcessStartInfo]::new((Get-Process -Id $PID).Path)
$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardInput=$true
foreach ($arg in @('-NoProfile','-Command','[Console]::WriteLine("ready"); [void][Console]::ReadLine(); exit 7')) { $info.ArgumentList.Add($arg) }
$started=[Diagnostics.Process]::Start($info)
$attached=$null
try {
    Check ($started.StandardOutput.ReadLine() -ceq 'ready') 'Child did not start.'
    $attached=[Diagnostics.Process]::GetProcessById($started.Id)
    $state=@{process=$attached;processHandle=$attached.SafeHandle;processOwned=$true;brokerProcessId=$attached.Id;
        activatedAtUtc=$script:now.AddMinutes(-1);verifiedExecutablePath=$attached.MainModule.FileName;ownedPackageFullName='owned-package'}
    $script:identity=@{process_id=$attached.Id;executable=$state.verifiedExecutablePath;package_full_name='owned-package';activation_utc=$state.activatedAtUtc}
    $script:queries=0;$script:queryMode='valid'
    $live=Get-InkWorkflowCrashDiagnostics $state
    Check (-not $live.process_exit.wait_completed -and $null -eq $live.process_exit.exit_code -and $script:queries -eq 0) 'Live process was called crashed or queried for crash events.'
    $started.StandardInput.WriteLine('exit');$started.StandardInput.Flush()
    Check ($attached.WaitForExit(10000)) 'Child did not exit.'
    foreach ($script:queryMode in @('valid','empty','failure','overflow','matches-overflow')) {
        $script:queries=0
        $result=[ordered]@{passed=$false;error=$null;active_operation=@{kind='observe';title='Save File';dialog=$true};failed_operation=$null;diagnostic_errors=@();crash_diagnostics=$null}
        $primary=[Management.Automation.ErrorRecord]::new([InvalidOperationException]::new('original workflow failure'),'fixture',[Management.Automation.ErrorCategory]::NotSpecified,$null)
        Add-InkWorkflowFailureEvidence $result $state $primary
        Check (-not $result.passed -and $result.error -ceq $primary.Exception.ToString() -and $result.failed_operation.title -ceq 'Save File') 'Diagnostics displaced original failure or failed observation.'
        $crash=$result.crash_diagnostics
        Check ($crash.process_exit.wait_completed -and $crash.process_exit.exit_code -eq 7 -and
            $crash.process_exit.exit_code_hex -ceq '0x00000007') 'Exact retained process exit lost.'
        if ($script:queryMode -ceq 'valid') {
            Check ($crash.application_errors.Count -eq 1 -and $result.diagnostic_errors.Count -eq 0 -and $script:queries -eq 1) 'Exact owned crash event lost.'
        } elseif ($script:queryMode -ceq 'empty') {
            Check ($crash.application_errors.Count -eq 0 -and $result.diagnostic_errors.Count -eq 0 -and $script:queries -eq 3) 'No-match result was fabricated or polling unbounded.'
        } else {
            Check ($crash.application_errors.Count -eq 0 -and $result.diagnostic_errors.Count -eq 1 -and $script:queries -eq 1) 'Query/collection failure escaped secondary diagnostics or published partial evidence.'
        }
    }
    $state.processOwned=$false;$script:queries=0
    $unowned=Get-InkWorkflowCrashDiagnostics $state
    Check ($null -eq $unowned.process_exit -and $unowned.diagnostic_errors.Count -eq 1 -and $script:queries -eq 0) 'Unowned process was observed or queried.'
    $state.processOwned=$true;$state.brokerProcessId++
    $wrongProcess=Get-InkWorkflowCrashDiagnostics $state
    Check ($null -eq $wrongProcess.process_exit -and $wrongProcess.diagnostic_errors.Count -eq 1 -and $script:queries -eq 0) 'Mismatched retained PID was observed or queried.'
    $state.brokerProcessId=$attached.Id;$state.activatedAtUtc=[DateTime]::UtcNow.AddMinutes(-31)
    $old=Get-InkWorkflowCrashDiagnostics $state
    Check ($null -eq $old.process_exit -and $old.diagnostic_errors.Count -eq 1 -and $script:queries -eq 0) 'Crash query exceeded its activation interval bound.'
    $state.activatedAtUtc=$script:identity.activation_utc;$script:queryMode='valid'
    # Windows exposes a signed 32-bit access-violation exit. Model only that
    # platform getter value while exercising the real diagnostic formatter.
    $exitGetter=[pscustomobject]@{Id=$attached.Id}
    $exitGetter | Add-Member ScriptMethod get_Id { return $this.Id }
    $exitGetter | Add-Member ScriptMethod WaitForExit { param($Timeout);Check ($Timeout -eq 0) 'Diagnostic waited for a process.';return $true }
    $exitGetter | Add-Member ScriptMethod get_ExitCode { return -1073741819 }
    $state.process=$exitGetter
    $accessViolation=Get-InkWorkflowCrashDiagnostics $state
    Check ($accessViolation.process_exit.exit_code -eq -1073741819 -and $accessViolation.process_exit.exit_code_hex -ceq '0xC0000005') 'Signed native crash code was not retained exactly.'
    $state.process=$attached
    $state.processHandle.Dispose();$script:queries=0
    $closed=Get-InkWorkflowCrashDiagnostics $state
    Check ($null -eq $closed.process_exit -and $closed.diagnostic_errors.Count -eq 1 -and $script:queries -eq 0) 'Closed retained handle was observed or queried.'
} finally {
    if (-not $started.HasExited) { $started.Kill();$started.WaitForExit() }
    if ($attached) { $attached.Dispose() };$started.Dispose()
}
Write-Output 'PASS: actual retained exit/hex, bounded event query, no-match/error separation, and original failure/operation retention.'
$originalDiagnostics=${function:Get-InkWorkflowCrashDiagnostics}
try {
    function Get-InkWorkflowCrashDiagnostics($State) { throw ('unexpected diagnostic failure '+('x'*5000)) }
    $result=[ordered]@{passed=$false;error=$null;active_operation=@{kind='input';action='save-new-note'};failed_operation=$null;diagnostic_errors=@();crash_diagnostics=$null}
    Add-InkWorkflowFailureEvidence $result @{} $primary
    Check ($result.error -ceq $primary.Exception.ToString() -and -not $result.passed -and
        $result.failed_operation.action -ceq 'save-new-note' -and $result.diagnostic_errors.Count -eq 1 -and
        $result.diagnostic_errors[0].Length -lt 256) 'Unexpected diagnostic failure displaced primary evidence or exceeded its bound.'
} finally { Set-Item Function:Get-InkWorkflowCrashDiagnostics $originalDiagnostics }
Write-Output 'PASS: unexpected diagnostic failure retains original input failure and bounded secondary error.'
