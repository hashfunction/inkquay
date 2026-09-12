# Copyright 2026 Trieflow LLC. MIT. Original helper loader and capture lifecycle.
param([string]$QualifiedSource=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $QualifiedSource 'script/msix/qualify-msix-install.ps1') -LibraryOnly -IdentityMode store
. (Join-Path $PSScriptRoot 'capture_operations.ps1')
function Check($Value,$Message){if(-not $Value){throw $Message}}
Check ((Get-InkQuayIdentity 'store').packageName -ceq '1659hashfunction.InkQuay') 'Qualified original helper loader differs'
$names=@('Preflight','Prepare','Sign','Install','Activate','Workflow','Close','Uninstall','ObserveFailure','Stop','RestoreDisplay','RemovePackage','RemoveDemoAndProfiles','RemoveTrust','RemoveKey','RemoveTemporary')
foreach($failure in @('none','Preflight','Sign','Activate','Workflow','Close','Uninstall')){
    $script:calls=[Collections.Generic.List[string]]::new();$ops=[ordered]@{}
    foreach($name in $names){$ops[$name]={ $script:calls.Add($name);if($name -ceq $failure){throw ('original '+$name)} }.GetNewClosure()}
    $result=Invoke-ScribCaptureLifecycle $ops
    if($failure -ceq 'none'){Check (-not $result.primary_error -and $result.cleanup_errors.Count -eq 0) 'Normal capture failed'}
    else{Check ($result.primary_error -match ('original '+$failure)) 'Original failure lost';Check ($script:calls.Contains('ObserveFailure')) 'Original failure not observed'}
    $tail=@($script:calls|Select-Object -Last 7)
    Check (($tail -join ',') -ceq 'Stop,RestoreDisplay,RemovePackage,RemoveDemoAndProfiles,RemoveTrust,RemoveKey,RemoveTemporary') 'Owned cleanup order changed'
    Check (@($script:calls|Where-Object {$_ -ceq 'Workflow'}).Count -le 1) 'Capture UI replayed'
}
$script:calls=[Collections.Generic.List[string]]::new();$ops=[ordered]@{}
foreach($name in $names){$ops[$name]={ $script:calls.Add($name);if($name -cin @('Workflow','RestoreDisplay','RemoveTrust')){throw ('original '+$name)} }.GetNewClosure()}
$r=Invoke-ScribCaptureLifecycle $ops
Check ($r.primary_error -match 'original Workflow' -and $r.cleanup_errors.Count -eq 2 -and $script:calls[-1] -ceq 'RemoveTemporary') 'Cleanup failure hid original or skipped later cleanup'
'PASS original helper loading, normal capture, six phase failures and continued cleanup after multiple failures.'

# Compile the unchanged qualified broker solely to inspect its real contract;
# substitute only its COM activation leaf when invoking the actual capture caller.
Add-InkQuayActivationTypes
$method=[InkQuayQualification.ActivationBroker].GetMethod('Activate',[type[]]@([string],[string]))
Check ($null -ne $method -and $method.ReturnType -eq [uint32]) 'Qualified activation contract changed'
Add-Type -TypeDefinition @'
namespace ScribCaptureActivationReplay {
 public static class Broker {
  public static int Calls;
  public static string Aumid, Arguments;
  public static uint Activate(string appUserModelId,string arguments) {
   Calls++;Aumid=appUserModelId;Arguments=arguments;
   throw new System.InvalidOperationException("activation-leaf-test-stop");
  }
 }
}
'@
$production=Get-Content (Join-Path $PSScriptRoot 'capture_operations.ps1') -Raw
. ([scriptblock]::Create($production.Replace('[InkQuayQualification.ActivationBroker]','[ScribCaptureActivationReplay.Broker]')))
$state=@{stopped=$true;processOwned=$false};$ops=New-ScribCaptureOperations $state @{} 'unused-inputs' $QualifiedSource
$failure=''
try{& $ops.Activate}catch{$failure=$_.Exception.ToString()}
Check ($failure -match 'activation-leaf-test-stop') 'Actual capture caller did not bind the qualified two-argument broker contract'
Check ([ScribCaptureActivationReplay.Broker]::Calls -eq 1 -and
    [ScribCaptureActivationReplay.Broker]::Aumid -ceq '1659hashfunction.InkQuay_r3hxytd7jt6c4!InkQuay' -and
    [string]::IsNullOrEmpty([ScribCaptureActivationReplay.Broker]::Arguments)) 'Unexpected activation identity, arguments or replay'
Check (-not $state.stopped -and -not $state.processOwned -and -not $state.ContainsKey('process')) 'Failed activation fabricated process ownership'
'PASS actual capture activation caller, exact qualified broker signature, one normal activation attempt and failure ownership preservation.'

# Replay actual observed HWND590310/PID5592 ownership with a transient Process title.
# Only the read-only query and sleep leaves are substituted; the production
# waiter and unchanged qualified native selector execute for every scenario.
. (Join-Path $QualifiedSource 'script/msix/qualify-workflow.ps1')
. (Join-Path $PSScriptRoot 'capture_operations.ps1')
function StartupWindow {
    [pscustomobject]@{Handle=590310L;Owner=0L;ProcessId=5592;Title='Unsaved Document - Scriblark';ClassName='gdkWindowToplevel';Visible=$true;Enabled=$true;X=78;Y=78;Width=816;Height=639}
}
function Get-ScribCaptureStartupObservation($State) {
    $script:reads++
    if($script:startupCase -ceq 'lost-process'){throw 'original retained process ownership lost'}
    $w=StartupWindow;$title=$w.Title;$handle=$w.Handle;$windows=@($w)
    switch($script:startupCase){
        'title-converges'{if($script:reads -eq 1){$title=''}}
        'handle-converges'{if($script:reads -eq 1){$handle=0L}}
        'wrong-title'{$title='Wrong';$w.Title='Wrong'}
        'foreign'{$w.ProcessId=6000}
        'duplicate'{$windows=@($w,(StartupWindow))}
        'hidden'{$w.Visible=$false}
        'disabled'{$w.Enabled=$false}
        'wrong-class'{$w.ClassName='foreign'}
        'zero'{$handle=0L}
        'late-valid'{[Threading.Thread]::Sleep(225)}
    }
    return @{process_id=5592;main_window_handle=$handle;main_window_title=$title;native_windows=$windows}
}
function Start-Sleep {param([int]$Milliseconds) [Threading.Thread]::Sleep(1)}
foreach($case in @('ready','title-converges','handle-converges','wrong-title','foreign','duplicate','hidden','disabled','wrong-class','zero','late-valid','lost-process')){
    $script:startupCase=$case;$script:reads=0;$state=@{main=0L};$errorText=''
    try{$null=Wait-ScribCaptureMain $state -TimeoutMilliseconds 200}catch{$errorText=$_.Exception.ToString()}
    if($case -cin @('ready','title-converges','handle-converges')){
        Check (-not $errorText -and $state.main -eq 590310 -and $state.startupWindowObservation.accepted) ('Startup convergence failed: '+$case)
        if($case -ne 'ready'){Check ($script:reads -ge 2) 'Waiter prematurely accepted or rejected a transient sample'}
    }else{
        Check ($errorText -and $state.main -eq 0 -and -not $state.startupWindowObservation.accepted) ('Invalid startup accepted: '+$case)
        if($case -ceq 'lost-process'){Check ($errorText -match 'original retained process ownership lost' -and $script:reads -eq 1) 'Lost process ownership was retried or hidden'}
    }
    Check ($state.startupWindowObservation.observations.Count -le 301) 'Startup observations exceeded bound'
    if($case -ceq 'title-converges'){
        $script:successfulStartup=$state
        $first=$state.startupWindowObservation.observations[0]
        Check ($first.main_window_title -ceq '' -and $first.native_windows[0].Title -ceq 'Unsaved Document - Scriblark') 'Original rejected getter/native values were not preserved'
    }
}
'PASS12actual startup waiter scenarios: convergence, unchanged native selector refusals, deadline and original ownership failure.'

$receiptDirectory=Join-Path ([IO.Path]::GetTempPath()) ('scrib-startup-replay-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $receiptDirectory -ErrorAction Stop|Out-Null
try{
    $state=$script:successfulStartup;$state.output=$receiptDirectory
    Write-ScribCaptureStartupObservation $state
    Write-ScribCaptureStartupObservation $state
    $record=Get-Content -LiteralPath (Join-Path $receiptDirectory 'startup-window-observations.json') -Raw|ConvertFrom-Json
    Check ($record.accepted -and $record.observations.Count -eq 2 -and $record.observations[0].main_window_title -ceq '' -and
        $record.observations[0].native_windows[0].Handle -eq 590310) 'Actual exclusive JSON writer lost rejected/accepted startup samples'
    Check ($state.startupWindowObservationWritten) 'Written startup record was not marked'
}finally{Remove-Item -LiteralPath $receiptDirectory -Recurse -Force}
'PASS actual qualified exclusive JSON writer, rejected/accepted native records and one-write preservation.'
