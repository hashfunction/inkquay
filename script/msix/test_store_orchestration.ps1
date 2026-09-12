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
