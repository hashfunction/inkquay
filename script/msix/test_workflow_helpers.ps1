# Copyright 2026 Trieflow LLC. MIT. Portable boundary tests, plus a real Windows HWND check.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$helper=Join-Path $PSScriptRoot 'qualify-workflow.ps1'
if (-not (Test-Path $helper)) { throw 'Installed consumer workflow driver is missing.' }
. $helper
function Check($value,$message) { if (-not $value) { throw $message } }
function Reject($action) { try { & $action; throw 'accepted invalid fixture' } catch { if ($_.Exception.Message -eq 'accepted invalid fixture') { throw } } }
function Window($id,$handle,$title,$owner=0) { [pscustomobject]@{ProcessId=$id;Handle=$handle;Title=$title;Owner=$owner;Visible=$true;Enabled=$true;ClassName='gdkWindowToplevel';Width=600;Height=500} }
$main=Window 44 100 'source.xopp - Scriblark'
$dialog=Window 44 101 'Configure new page template' 100
Check ((Select-InkWorkflowWindow @($main,$dialog) 44 100 'Configure new page template' $true).Handle -eq 101) 'owned dialog omitted'
Reject { Select-InkWorkflowWindow @($main,(Window 45 102 'Configure new page template' 100)) 44 100 'Configure new page template' $true }
Reject { Select-InkWorkflowWindow @($main,(Window 44 102 'Configure new page template' 999)) 44 100 'Configure new page template' $true }
Reject { Select-InkWorkflowWindow @($main,$dialog,$dialog) 44 100 'Configure new page template' $true }
Reject { Select-InkWorkflowWindow @($main,(Window 44 0 'Configure new page template' 100)) 44 100 'Configure new page template' $true }
Reject { Select-InkWorkflowWindow @($main,(Window 44 102 'Error' 100)) 44 100 'source.xopp - Scriblark' $false }
$contract=Get-InkWorkflowContract (Resolve-Path (Join-Path $PSScriptRoot '../..'))
Check ($contract.configureMenuDown -eq 5) 'source journal menu operation differs'
Check ($contract.cornellConfig -ceq 'iq=2,m1=166,r1=24') 'source Cornell configuration differs'
Check ($contract.templateTitle -ceq 'Configure new page template') 'source dialog contract differs'
Add-InkWorkflowTypes
if ($IsWindows) {
    Add-Type -AssemblyName System.Windows.Forms
    $form=[Windows.Forms.Form]::new();$edit=[Windows.Forms.TextBox]::new();$form.Controls.Add($edit);$form.Text='Scriblark qualification native fixture';$form.Width=600;$form.Height=500
    $menuStrip=[Windows.Forms.MenuStrip]::new();$fileMenu=[Windows.Forms.ToolStripMenuItem]::new('&File')
    $exportMenu=[Windows.Forms.ToolStripMenuItem]::new('&Export fixture');$script:nativeExportHits=0
    $exportMenu.add_Click({$script:nativeExportHits++});[void]$fileMenu.DropDownItems.Add($exportMenu)
    [void]$menuStrip.Items.Add($fileMenu);$form.Controls.Add($menuStrip);$form.MainMenuStrip=$menuStrip
    try {
        $form.Show();[Windows.Forms.Application]::DoEvents()
        $items=@([InkQuayWorkflow.Native]::Windows($PID))
        $match=@($items|Where-Object Title -CEQ $form.Text)
        Check ($match.Count -eq 1 -and $match[0].Handle -eq $form.Handle.ToInt64()) 'real native window was not discovered exactly'
        [InkQuayWorkflow.Native]::Focus($form.Handle,$PID)
        [void]$edit.Focus();[Windows.Forms.Application]::DoEvents()
        $inputState=[InkQuayWorkflow.Native]::InspectInput($form.Handle,$PID)
        Check ($inputState.MainHandle -eq $form.Handle.ToInt64() -and $inputState.ProcessId -eq $PID -and $inputState.ThreadId -gt 0) 'real retained main identity differs'
        Check ($inputState.ForegroundHandle -eq $form.Handle.ToInt64() -and $inputState.ForegroundProcessId -eq $PID) 'real foreground identity differs'
        Check ($inputState.FocusHandle -eq $edit.Handle.ToInt64() -and $inputState.FocusRoot -eq $form.Handle.ToInt64() -and $inputState.FocusProcessId -eq $PID) 'real GUI thread child focus/root differs'
        Check ($inputState.ForegroundOwnerChain[0] -eq $form.Handle.ToInt64()) 'real foreground owner chain differs'
        Reject { [InkQuayWorkflow.Native]::InspectInput($form.Handle,($PID+1)) }
        Reject { [InkQuayWorkflow.Native]::Focus($form.Handle,($PID+1)) }
        # Exercise the private production emitter against this owned native
        # fixture. This checks actual key delivery, never GTK/menu acceptance.
        $emit=[InkQuayWorkflow.Native].GetMethod('EmitExportKeys',[Reflection.BindingFlags]'NonPublic,Static')
        $argsForEmit=[object[]]::new(1)
        $argsForEmit[0]=[InkQuayWorkflow.ExportKey[]]@([InkQuayWorkflow.ExportKey]::new(18,$false),[InkQuayWorkflow.ExportKey]::new(70,$false),[InkQuayWorkflow.ExportKey]::new(70,$true),[InkQuayWorkflow.ExportKey]::new(18,$true))
        Check ($emit.Invoke($null,$argsForEmit) -eq 4) 'Native File chord count differs'
        $deadline=[DateTime]::UtcNow.AddSeconds(3)
        do {[Windows.Forms.Application]::DoEvents();[Threading.Thread]::Sleep(20)}while(-not $fileMenu.DropDown.Visible -and [DateTime]::UtcNow -lt $deadline)
        Check $fileMenu.DropDown.Visible 'Native File chord did not open the fixture menu'
        $inputState=[InkQuayWorkflow.Native]::InspectInput($form.Handle,$PID)
        Check ($inputState.ForegroundProcessId -eq $PID -and -not $inputState.AltDown -and -not $inputState.ControlDown -and -not $inputState.ShiftDown) 'Fixture input ownership or released modifiers differ'
        $argsForEmit[0]=[InkQuayWorkflow.ExportKey[]]@([InkQuayWorkflow.ExportKey]::new(69,$false),[InkQuayWorkflow.ExportKey]::new(69,$true))
        Check ($emit.Invoke($null,$argsForEmit) -eq 2) 'Native Export key count differs'
        $deadline=[DateTime]::UtcNow.AddSeconds(3)
        do {[Windows.Forms.Application]::DoEvents();[Threading.Thread]::Sleep(20)}while($script:nativeExportHits -eq 0 -and [DateTime]::UtcNow -lt $deadline)
        Check ($script:nativeExportHits -eq 1 -and -not $fileMenu.DropDown.Visible) 'Native fixture Export action did not occur exactly once'
        Write-Output 'PASS actual native SendInput File/Export delivery, four/two inserted events and one fixture action.'
        $exportMenu.ShortcutKeys=[Windows.Forms.Keys]::Control -bor [Windows.Forms.Keys]::Alt -bor [Windows.Forms.Keys]::E
        foreach($expectedHits in @(2,3)) {
            [void]$edit.Focus();[Windows.Forms.Application]::DoEvents()
            $argsForEmit[0]=[InkQuayWorkflow.ExportKey[]]@([InkQuayWorkflow.ExportKey]::new(17,$false),[InkQuayWorkflow.ExportKey]::new(18,$false),[InkQuayWorkflow.ExportKey]::new(69,$false),[InkQuayWorkflow.ExportKey]::new(69,$true),[InkQuayWorkflow.ExportKey]::new(18,$true),[InkQuayWorkflow.ExportKey]::new(17,$true))
            Check ($emit.Invoke($null,$argsForEmit) -eq 6) 'Direct PDF shortcut native event count differs'
            $deadline=[DateTime]::UtcNow.AddSeconds(3)
            do {[Windows.Forms.Application]::DoEvents();[Threading.Thread]::Sleep(20)}while($script:nativeExportHits -lt $expectedHits -and [DateTime]::UtcNow -lt $deadline)
            Check ($script:nativeExportHits -eq $expectedHits) 'Direct shortcut did not invoke exactly one native fixture action'
            $observed=[InkQuayWorkflow.Native]::InspectInput($form.Handle,$PID)
            Check (-not $observed.ControlDown -and -not $observed.ShiftDown -and -not $observed.AltDown -and -not $observed.WindowsKeyDown) 'Shortcut left a modifier pressed'
        }
        Write-Output 'PASS two consecutive native Ctrl+Alt+E invocations, six events each, released modifiers and exactly one action each.'
        $popup=[Windows.Forms.Form]::new();$popup.Text='Owned observer popup fixture'
        try {
            $popup.Show($form);[Windows.Forms.Application]::DoEvents()
            [InkQuayWorkflow.Native]::Focus($popup.Handle,$PID)
            $inputState=[InkQuayWorkflow.Native]::InspectInput($form.Handle,$PID)
            Check ($inputState.ForegroundHandle -eq $popup.Handle.ToInt64() -and $inputState.ForegroundProcessId -eq $PID) 'real owned popup foreground differs'
            Check ($inputState.ForegroundOwnerChain[0] -eq $popup.Handle.ToInt64() -and $inputState.ForegroundOwnerChain[1] -eq $form.Handle.ToInt64()) 'real popup-to-main owner chain differs'
        } finally {$popup.Close();$popup.Dispose()}
    } finally { $form.Close();$form.Dispose() }
} else { Write-Output 'Native Windows HWND fixture not executed on this host.' }
Write-Output 'PASS: exact workflow window ownership, ambiguity/error rejection and source-backed action contract.'
