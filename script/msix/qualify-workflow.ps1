# Copyright 2026 Trieflow LLC. MIT. Actual installed GTK consumer workflow, no product hooks.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'workflow_crash.ps1')
function Add-InkWorkflowTypes {
    if (-not ('InkQuayWorkflow.Native' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'WorkflowNative.cs') }
}
function Select-InkWorkflowWindow($Windows,[int]$ProcessId,[long]$MainHandle,[string]$Title,[bool]$Dialog) {
    $owned=@($Windows | Where-Object { $_.ProcessId -eq $ProcessId -and $_.Visible })
    $matches=@($owned | Where-Object { $_.Title -ceq $Title -and $_.Handle -ne 0 -and $_.Enabled -and
        $(if($Dialog){$_.Owner -eq $MainHandle -and $_.Handle -ne $MainHandle}else{$_.Handle -eq $MainHandle}) -and
        $_.ClassName -ceq 'gdkWindowToplevel' -and $_.Width -ge 200 -and $_.Height -ge 100 })
    $unexpected=@($owned | Where-Object { $_.Handle -ne $MainHandle -and $_.Title -cne $Title -and
        $_.ClassName -cne 'gdkWindowTemp' })
    if ($unexpected.Count) { throw ('Unexpected owned workflow window: '+(($unexpected|ForEach-Object Title)-join ', ')) }
    if ($matches.Count -ne 1) { throw "Expected one exact owned workflow window: $Title (found $($matches.Count))" }
    return $matches[0]
}
function Get-InkWorkflowContract([string]$Source) {
    [xml]$menus=Get-Content (Join-Path $Source 'ui/mainmenubar.xml') -Raw -Encoding utf8
    $journal=@($menus.interface.menu.submenu | Where-Object { @($_.attribute | Where-Object name -eq 'label').'#text' -ceq '_Journal' })
    $items=@($journal[0].section[0].item)
    $index=-1
    for($i=0;$i -lt $items.Count;$i++){ if (@($items[$i].attribute|Where-Object name -eq 'action').'#text' -ceq 'win.configure-page-template'){$index=$i} }
    if($index -ne 5){throw 'Journal keyboard contract changed; review actual enabled menu layout.'}
    $ini=Get-Content (Join-Path $Source 'resources-templates/pagetemplates.ini.in') -Raw -Encoding utf8
    $groups=[regex]::Matches($ini,'(?m)^\[([^\]]+)\]')
    $preset=-1
    for($i=0;$i -lt $groups.Count;$i++){if($groups[$i].Groups[1].Value -ceq 'inkquayCornell'){$preset=$i+1}}
    if($preset -lt 1 -or $ini -cnotmatch '(?s)\[inkquayCornell\]\r?\nname=Cornell notes\r?\nformat=lined\r?\nconfig=iq=2,m1=166,r1=24'){throw 'Cornell preset source contract changed.'}
    [xml]$ui=Get-Content (Join-Path $Source 'ui/pageTemplate.glade') -Raw -Encoding utf8
    $title=[string]$ui.SelectSingleNode("//object[@id='templateDialog']/property[@name='title']").InnerText
    if($title -cne 'Configure new page template'){throw 'Template dialog title changed.'}
    return @{configureMenuDown=$index;cornellIndex=$preset;cornellConfig='iq=2,m1=166,r1=24';templateTitle=$title}
}
function Invoke-InkQuayWorkflow($State,[string]$SourceRoot) {
    Add-InkWorkflowTypes
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $contract=Get-InkWorkflowContract $SourceRoot
    $events=[Collections.Generic.List[object]]::new()
    $evidence=Join-Path $State.output 'workflow'
    New-Item -ItemType Directory -Path $evidence -ErrorAction Stop | Out-Null
    # Files are strictly inside the already owned temporary tree; no profile files are injected.
    $root=Join-Path $State.temporary 'consumer-files'
    $main=[long]$State.process.MainWindowHandle
    $python=$env:INKQUAY_QUALIFICATION_PYTHON
    $tools=Split-Path $python
    $originalManifestHash=$null
    $result=[ordered]@{schema_version=1;source_commit=$env:GITHUB_SHA;process_id=$State.process.Id;
        package_full_name=$State.ownedPackageFullName;originals=$null;first=$null;reopened=$null;events=$events;
        passed=$false;error=$null;diagnostic_errors=@();gtk_keyboard_workflow=$true;diagnostic_observer=[bool]$State.observerRequested;
        active_operation=$null;failed_operation=$null;crash_diagnostics=$null}
    function Assert-Live {
        $State.process.Refresh()
        if(-not $State.processOwned -or $State.processHandle.IsClosed -or $State.processHandle.IsInvalid -or $State.process.HasExited){throw 'Retained owned process is unavailable.'}
        if((Get-CanonicalPath $State.process.MainModule.FileName) -ine (Get-CanonicalPath (Join-Path $State.installed.InstallLocation 'bin/inkquay.exe')) -or
            [InkQuayQualification.NativePackageProbe]::GetFullName($State.process.Handle) -cne $State.ownedPackageFullName){throw 'Workflow process executable/package identity changed.'}
    }
    function Observe([string]$Title,[bool]$Dialog=$false) {
        $result.active_operation=@{kind='observe';title=$Title;dialog=$Dialog;at_utc=[DateTime]::UtcNow.ToString('o')}
        $deadline=[DateTime]::UtcNow.AddSeconds(20)
        do {
            Assert-Live
            $windows=@([InkQuayWorkflow.Native]::Windows($State.process.Id))
            try { return Select-InkWorkflowWindow $windows $State.process.Id $main $Title $Dialog }
            catch { $last=$_.Exception.Message }
            Start-Sleep -Milliseconds 150
        }while([DateTime]::UtcNow -lt $deadline)
        throw $last
    }
    function Keys($Window,[string]$Keys,[string]$Action) {
        $result.active_operation=@{kind='input';action=$Action;title=$Window.Title;at_utc=[DateTime]::UtcNow.ToString('o')}
        Assert-Live
        [InkQuayWorkflow.Native]::Focus([IntPtr]$Window.Handle,$State.process.Id)
        [Windows.Forms.SendKeys]::SendWait($Keys)
        $events.Add([ordered]@{action=$Action;title=$Window.Title;handle=$Window.Handle;process_id=$State.process.Id;at_utc=[DateTime]::UtcNow.ToString('o')})
        Start-Sleep -Milliseconds 250
    }
    function TextKeys([string]$Text) { return [regex]::Replace($Text,'[+^%~(){}\[\]]',{param($m) '{'+$m.Value+'}'}) }
    function Capture($Window,[string]$Name) {
        $result.active_operation=@{kind='capture';name=$Name;title=$Window.Title;at_utc=[DateTime]::UtcNow.ToString('o')}
        Assert-Live
        [InkQuayWorkflow.Native]::Focus([IntPtr]$Window.Handle,$State.process.Id)
        $fresh=@([InkQuayWorkflow.Native]::Windows($State.process.Id)|Where-Object Handle -eq $Window.Handle)
        if($fresh.Count -ne 1 -or $fresh[0].Title -cne $Window.Title){throw 'Capture target changed.'}
        $w=$fresh[0];$rect=[Drawing.Rectangle]::new($w.X,$w.Y,$w.Width,$w.Height)
        if(-not [Windows.Forms.SystemInformation]::VirtualScreen.Contains($rect)){throw 'Workflow capture is outside visible desktop.'}
        $bitmap=[Drawing.Bitmap]::new($w.Width,$w.Height);$g=[Drawing.Graphics]::FromImage($bitmap)
        try {
            $g.CopyFromScreen($w.X,$w.Y,0,0,$bitmap.Size)
            $colors=[Collections.Generic.HashSet[int]]::new()
            for($y=0;$y -lt $bitmap.Height;$y+=7){for($x=0;$x -lt $bitmap.Width;$x+=7){[void]$colors.Add($bitmap.GetPixel($x,$y).ToArgb())}}
            if($colors.Count -lt 16){throw 'Workflow capture is blank.'}
            $path=Join-Path $evidence ($Name+'.png')
            if(Test-Path $path){throw 'Workflow screenshot already exists.'}
            $bitmap.Save($path,[Drawing.Imaging.ImageFormat]::Png)
            Write-NewUtf8Json (Join-Path $evidence ($Name+'.json')) @{window=$w;screenshot=[IO.Path]::GetFileName($path);sha256=(Get-FileHash $path).Hash.ToLowerInvariant();sampled_colors=$colors.Count}
        }finally{$g.Dispose();$bitmap.Dispose()}
    }
    function Files([string]$Mode) {
        $result.active_operation=@{kind='file-verification';mode=$Mode;at_utc=[DateTime]::UtcNow.ToString('o')}
        if($originalManifestHash -and (Get-FileHash (Join-Path $root 'originals.json')).Hash -cne $originalManifestHash){throw 'Prepared original manifest changed.'}
        $raw=& $python (Join-Path $PSScriptRoot 'workflow_files.py') $Mode --root $root --tool-directory $tools 2>&1
        if($LASTEXITCODE -ne 0){throw ("Independent $Mode verification failed: "+($raw -join "`n"))}
        return ($raw -join "`n")|ConvertFrom-Json
    }
    function Choose([string]$Title,[string]$File) {
        $window=Observe $Title $true
        Keys $window '^l' 'chooser-location'
        Keys $window ('^a'+(TextKeys $File)+'{ENTER}') ('choose-'+[IO.Path]::GetFileName($File))
    }
    function Open([string]$Title,[string]$Name) {
        Keys (Observe $Title) '^o' ('open-'+$Name)
        Choose 'Open file' (Join-Path $root $Name)
        return Observe ($Name+' - InkQuay')
    }
    function Template([string]$Title) {
        Keys (Observe $Title) ('%j{HOME}{DOWN '+$contract.configureMenuDown+'}{ENTER}') 'configure-template'
        return Observe $contract.templateTitle $true
    }
    function Export([string]$Title,[string]$Mode) {
        $name=$Mode+'.pdf'
        if(Test-Path (Join-Path $root $name)){throw 'Export destination already exists.'}
        Keys (Observe $Title) '%fe' ('export-'+$name)
        Choose 'Export File' (Join-Path $root $name)
        $deadline=[DateTime]::UtcNow.AddSeconds(30)
        do { Assert-Live; $reports=@(Get-ChildItem -LiteralPath $root -Filter ($name+'.*.inkquay-report.json'));if($reports.Count){break};Start-Sleep -Milliseconds 200 }while([DateTime]::UtcNow -lt $deadline)
        $checked=Files $Mode
        # App's message dialog has no explicit GtkWindow title. Require one exact
        # owned GTK modal only after its independently checked published report exists.
        $deadline=[DateTime]::UtcNow.AddSeconds(10)
        do {
            Assert-Live
            $windows=@([InkQuayWorkflow.Native]::Windows($State.process.Id))
            $dialogs=@($windows|Where-Object {$_.Handle -ne $main -and $_.ClassName -ceq 'gdkWindowToplevel' -and $_.Owner -eq $main -and $_.Enabled -and $_.Title -cin @('','InkQuay')})
            if($dialogs.Count -eq 1){break};Start-Sleep -Milliseconds 150
        }while([DateTime]::UtcNow -lt $deadline)
        if($dialogs.Count -ne 1){throw 'Expected the owned GTK checked-export result dialog.'}
        $dialog=Select-InkWorkflowWindow $windows $State.process.Id $main $dialogs[0].Title $true
        Capture $dialog ($Mode+'-report-dialog')
        [IO.File]::Copy((Join-Path $root $checked.report_name),(Join-Path $evidence ($Mode+'-application-report.json')),$false)
        Assert-FileMatchesRecord (Join-Path $evidence ($Mode+'-application-report.json')) $checked.report 'Retained application report' | Out-Null
        Keys $dialog '{ENTER}' 'dismiss-checked-export-report'
        Capture (Observe $Title) ($Mode+'-editor')
        return $checked
    }
    try {
        $result.originals=Files 'prepare'
        $originalManifestHash=(Get-FileHash (Join-Path $root 'originals.json')).Hash
        [void](Open 'Unsaved Document - InkQuay' 'source.xopp')
        $dialog=Template 'source.xopp - InkQuay'
        Keys $dialog ('%t{HOME}{DOWN '+$contract.cornellIndex+'}{TAB}^aInkQuay CI Cornell') 'select-and-name-cornell-preset'
        Keys $dialog '%s' 'save-named-preset'
        Capture $dialog 'saved-template'
        # Cancel defaults, reopen the real library, select its sole new final user
        # entry, then Shift-Tab wraps from first selector to the final Ok button.
        Keys $dialog '{ESC}' 'cancel-template-defaults'
        $dialog=Template 'source.xopp - InkQuay'
        Keys $dialog '%t{END}' 'reload-saved-preset'
        Capture $dialog 'reloaded-template'
        Keys $dialog '%t+{TAB}{ENTER}' 'apply-saved-template'
        Keys (Observe 'source.xopp - InkQuay') '^d' 'insert-template-page'
        if(Test-Path (Join-Path $root 'saved.xopp')){throw 'Save As destination already exists.'}
        Keys (Observe '*source.xopp - InkQuay') '^+s' 'save-new-note'
        Choose 'Save File' (Join-Path $root 'saved.xopp')
        Capture (Observe 'saved.xopp - InkQuay') 'saved-two-page-note'
        $saved=Files 'note'
        $result.first=Export 'saved.xopp - InkQuay' 'first'
        [void](Open 'saved.xopp - InkQuay' 'first.pdf')
        Capture (Observe 'first.pdf - InkQuay') 'reopened-export'
        $result.reopened=Export 'first.pdf - InkQuay' 'reopened'
        if((Get-FileHash (Join-Path $root 'first.pdf')).Hash.ToLowerInvariant() -cne $result.first.sha256 -or
            (Get-FileHash (Join-Path $root 'saved.xopp')).Hash.ToLowerInvariant() -cne $saved.sha256){throw 'Earlier output/note changed during PDF reopen/export.'}
        [void](Files 'note')
        Assert-Live
        $result.passed=$true
    }catch{
        Add-InkWorkflowFailureEvidence $result $State $_
        try {Write-NewUtf8Json (Join-Path $evidence 'failure-windows.json') @([InkQuayWorkflow.Native]::Windows($State.process.Id))}catch{$result.diagnostic_errors+= $_.Exception.ToString()}
        try { $w=@([InkQuayWorkflow.Native]::Windows($State.process.Id)|Where-Object {$_.Enabled -and $_.Handle -eq $main});if($w.Count -eq 1){Capture $w[0] 'failure'} }catch{$result.diagnostic_errors+= $_.Exception.ToString()}
    }
    # Preserve original application failure reports too, without uploading generated PDFs.
    try {
        if(Test-Path -LiteralPath $root) {
            $reports=@(Get-ChildItem -LiteralPath $root -File | Where-Object Name -Match '^(first|reopened)\.pdf\.[0-9a-f-]{36}\.inkquay-report\.json$')
            if($reports.Count -gt 4){throw 'Too many workflow application reports.'}
            foreach($report in $reports){
                Assert-NoReparsePath $report.FullName
                if($report.Length -gt 1048576){throw 'Application report exceeds diagnostic bound.'}
                $before=(Get-FileHash $report.FullName).Hash
                $target=Join-Path $evidence ('retained-'+$report.Name)
                [IO.File]::Copy($report.FullName,$target,$false)
                if((Get-FileHash $target).Hash -cne $before -or (Get-FileHash $report.FullName).Hash -cne $before){throw 'Application report changed during retention.'}
            }
        }
    }catch{
        $result.diagnostic_errors+= $_.Exception.ToString()
        $result.passed=$false
        if(-not $result.error){$result.error='Application report retention failed.'}
    }
    try {Write-NewUtf8Json (Join-Path $evidence 'workflow-result.json') $result}
    catch {throw "Workflow evidence publication failed: $($_.Exception.Message); primary: $($result.error); diagnostics: $($result.diagnostic_errors -join '; ')"}
    if(-not $result.passed){throw $result.error}
    return $result
}
