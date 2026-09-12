# Copyright 2026 Trieflow LLC. MIT. Separate real-product capture, never qualification.
param([Parameter(Mandatory)][string]$Inputs,[Parameter(Mandatory)][string]$QualifiedSource,[Parameter(Mandatory)][string]$CaptureOutput)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if(-not $IsWindows -or $env:CI -cne 'true' -or $env:GITHUB_REPOSITORY -cne 'hashfunction/inkquay'){throw 'Scriblark capture requires isolated Windows CI'}
$qualified=(Resolve-Path -LiteralPath $QualifiedSource).Path
. (Join-Path $qualified 'script/msix/qualify-msix-install.ps1') -LibraryOnly -IdentityMode store
. (Join-Path $qualified 'script/msix/qualify-workflow.ps1')
Add-InkWorkflowTypes
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type -Path (Join-Path $PSScriptRoot 'CaptureNative.cs')
. (Join-Path $PSScriptRoot 'capture_display.ps1')
. (Join-Path $PSScriptRoot 'capture_ui.ps1')
. (Join-Path $PSScriptRoot 'capture_operations.ps1')
Import-Module Appx -UseWindowsPowerShell -ErrorAction Stop
$root=(Resolve-Path -LiteralPath $Inputs).Path
Invoke-CheckedNative python @((Join-Path $PSScriptRoot 'capture_checks.py'),'--inputs',$root,'--qualified-source',$qualified)
$bound=(Get-Content (Join-Path $PSScriptRoot 'binding.json') -Raw|ConvertFrom-Json).qualified
$records=@(Get-ChildItem -LiteralPath (Join-Path $root 'metadata') -Recurse -File -Filter 'msix-store-package-record.json')
if($records.Count -ne 1){throw 'Original Store package record missing'}
$record=Get-Content $records[0].FullName -Raw|ConvertFrom-Json
Assert-InkQuayRecordIdentity $record 'store'
$output=[IO.Path]::GetFullPath($CaptureOutput)
if(Test-Path -LiteralPath $output){throw 'Existing capture output preserved'}
$state=@{package=(Join-Path $root 'store/Scriblark_1.0.1.0_x64.msix');record=$record;output=$output;statePath=(Join-Path $output 'capture-fixture-state.json');
    demo='C:\Scriblark Demo';profiles=@((Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'InkQuay'),(Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'InkQuay'));
    fixture=$null;fixtureRemoved=$false;sealed=$false;temporary=$null;certificate=$null;trustAttempted=$false;signed=$null;
    installed=$null;installedByUs=$false;installAttempted=$false;addCompleted=$false;ownedPackageFullName=$null;residual=@();
    process=$null;processOwned=$false;brokerPid=0;main=0;stopped=$true;normalClose=$false;exit=$null;cleanupExit=$null;uninstallVerified=$false;
    displayOriginalMode=$null;displayDevice=$null;displayRestoreRequired=$false;displayEvidence=$null;verified=$null;pdfReopened=$false;
    captures=[Collections.Generic.List[string]]::new();events=[Collections.Generic.List[object]]::new()}
$result=Invoke-ScribCaptureLifecycle (New-ScribCaptureOperations $state $bound $root $qualified)
$unchanged=$false
try{$null=Assert-FileMatchesRecord $state.package $bound.package 'Original unsigned after capture';$unchanged=$true}catch{$result.cleanup_errors+=('Original unsigned: '+$_.Exception.Message)}
$captured=(-not $result.primary_error -and $result.cleanup_errors.Count -eq 0 -and $state.captures.Count -eq 3 -and $state.pdfReopened -and
    $state.normalClose -and $state.uninstallVerified -and $state.fixtureRemoved -and $unchanged -and $state.displayEvidence.restore_verified)
if(Test-Path -LiteralPath $output){Write-NewUtf8Json (Join-Path $output 'capture-result.json') @{schema_version=1;purpose='real product screenshots only';captured=$captured;consumer_acceptance=$false;installation_qualification_claimed=$false;product_binary_changed=$false;certificate_private_key_exported=$false;
    capture_source_commit=$env:GITHUB_SHA;capture_run_id=$env:GITHUB_RUN_ID;capture_run_attempt=$env:GITHUB_RUN_ATTEMPT;qualified=$bound;package_full_name=$state.ownedPackageFullName;
    screenshots=@($state.captures);events=@($state.events);original_unsigned_unchanged=$unchanged;pdf_reopened=$state.pdfReopened;normal_close_verified=$state.normalClose;process_exit=$state.exit;cleanup_exit=$state.cleanupExit;
    uninstall_verified=$state.uninstallVerified;owned_demo_and_profiles_removed=$state.fixtureRemoved;display=$state.displayEvidence;residual_package_full_names=$state.residual;primary_error=$result.primary_error;cleanup_errors=$result.cleanup_errors}}
if($state.process){$state.process.Dispose()}
if(-not $captured){throw "Scriblark product capture incomplete: $($result.primary_error); cleanup: $($result.cleanup_errors -join '; ')"}
Write-Output 'Captured three original Scriblark Windows screenshots with unchanged Store MSIX and complete owned cleanup.'
