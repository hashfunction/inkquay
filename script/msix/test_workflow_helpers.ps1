# Copyright 2026 Trieflow LLC. MIT. Portable boundary tests, plus a real Windows HWND check.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$helper=Join-Path $PSScriptRoot 'qualify-workflow.ps1'
if (-not (Test-Path $helper)) { throw 'Installed consumer workflow driver is missing.' }
. $helper
function Check($value,$message) { if (-not $value) { throw $message } }
function Reject($action) { try { & $action; throw 'accepted invalid fixture' } catch { if ($_.Exception.Message -eq 'accepted invalid fixture') { throw } } }
function Window($id,$handle,$title,$owner=0) { [pscustomobject]@{ProcessId=$id;Handle=$handle;Title=$title;Owner=$owner;Visible=$true;Enabled=$true;ClassName='gdkWindowToplevel';Width=600;Height=500} }
$main=Window 44 100 'source.xopp - InkQuay'
$dialog=Window 44 101 'Configure new page template' 100
Check ((Select-InkWorkflowWindow @($main,$dialog) 44 100 'Configure new page template' $true).Handle -eq 101) 'owned dialog omitted'
Reject { Select-InkWorkflowWindow @($main,(Window 45 102 'Configure new page template' 100)) 44 100 'Configure new page template' $true }
Reject { Select-InkWorkflowWindow @($main,(Window 44 102 'Configure new page template' 999)) 44 100 'Configure new page template' $true }
Reject { Select-InkWorkflowWindow @($main,$dialog,$dialog) 44 100 'Configure new page template' $true }
Reject { Select-InkWorkflowWindow @($main,(Window 44 0 'Configure new page template' 100)) 44 100 'Configure new page template' $true }
Reject { Select-InkWorkflowWindow @($main,(Window 44 102 'Error' 100)) 44 100 'source.xopp - InkQuay' $false }
$contract=Get-InkWorkflowContract (Resolve-Path (Join-Path $PSScriptRoot '../..'))
Check ($contract.configureMenuDown -eq 5) 'source journal menu operation differs'
Check ($contract.cornellConfig -ceq 'iq=2,m1=166,r1=24') 'source Cornell configuration differs'
Check ($contract.templateTitle -ceq 'Configure new page template') 'source dialog contract differs'
Add-InkWorkflowTypes
if ($IsWindows) {
    Add-Type -AssemblyName System.Windows.Forms
    $form=[Windows.Forms.Form]::new();$form.Text='InkQuay qualification native fixture';$form.Width=600;$form.Height=500
    try {
        $form.Show();[Windows.Forms.Application]::DoEvents()
        $items=@([InkQuayWorkflow.Native]::Windows($PID))
        $match=@($items|Where-Object Title -CEQ $form.Text)
        Check ($match.Count -eq 1 -and $match[0].Handle -eq $form.Handle.ToInt64()) 'real native window was not discovered exactly'
        [InkQuayWorkflow.Native]::Focus($form.Handle,$PID)
        Reject { [InkQuayWorkflow.Native]::Focus($form.Handle,($PID+1)) }
    } finally { $form.Close();$form.Dispose() }
} else { Write-Output 'Native Windows HWND fixture not executed on this host.' }
Write-Output 'PASS: exact workflow window ownership, ambiguity/error rejection and source-backed action contract.'
