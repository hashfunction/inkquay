# Copyright 2026 Trieflow LLC. MIT. Real sequencing boundary; no Windows claim.
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix.ps1') -LibraryOnly
foreach($case in @('normal','diagnostic','first-build-fails','first-install-fails','store-install-fails')) {
    $script:observed=[Collections.Generic.List[string]]::new()
    $build={param($Mode) $script:observed.Add('build:'+ $Mode);if($case -eq 'first-build-fails'){throw 'build failed'}}
    $install={param($Mode) $script:observed.Add('install:'+ $Mode);if(($Mode -eq 'qualification' -and $case -eq 'first-install-fails') -or ($Mode -eq 'store' -and $case -eq 'store-install-fails')){throw 'install failed'}}
    $export={$script:observed.Add('export')}
    $failure=$null
    try {Invoke-InkQuayPackageSequence $build $install $export ($case -eq 'diagnostic')}catch{$failure=$_}
    $expected=switch($case){
        'normal'{@('build:qualification','install:qualification','build:store','install:store','export')}
        'diagnostic'{@('build:qualification','install:qualification')}
        'first-build-fails'{@('build:qualification')}
        'first-install-fails'{@('build:qualification','install:qualification')}
        'store-install-fails'{@('build:qualification','install:qualification','build:store','install:store')}
    }
    if(($script:observed -join '|') -cne ($expected -join '|') -or [bool]$failure -ne $case.EndsWith('fails')){throw "Incorrect actual package sequencing: $case"}
    Write-Output "PASS actual package orchestration: $case"
}
# Replay the actual final dispatch expression so the input flag cannot accidentally
# take the normal Store/export branch while GDB remains off.
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'qualify-msix.ps1'),[ref]$tokens,[ref]$errors)
$dispatch=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -ceq 'Invoke-InkQuayPackageSequence'},$true))
if($errors.Count -or $dispatch.Count -ne 1){throw 'Actual final package dispatch is ambiguous'}
foreach($flags in @(@($false,$false),@($true,$false),@($false,$true),@($true,$true))) {
    $CaptureCrashStack=$flags[0];$CaptureInputDiagnostics=$flags[1]
    $script:observed=[Collections.Generic.List[string]]::new()
    $build={param($mode)$script:observed.Add('build:'+ $mode)}
    $install={param($mode)$script:observed.Add('install:'+ $mode)}
    $export={$script:observed.Add('export')}
    & ([scriptblock]::Create($dispatch[0].Extent.Text))
    $expected=if($flags[0] -or $flags[1]){'build:qualification|install:qualification'}else{'build:qualification|install:qualification|build:store|install:store|export'}
    if(($script:observed -join '|') -cne $expected){throw 'Actual diagnostic flag dispatch conferred Store export'}
    Write-Output "PASS actual flag dispatch: GDB=$($flags[0]), input=$($flags[1])"
}
