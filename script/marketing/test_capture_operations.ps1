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
