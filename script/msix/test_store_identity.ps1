# Copyright 2026 Trieflow LLC. MIT. Exercise the production preflight policy.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
foreach($mode in @('qualification','store')) {
    $record=[pscustomobject]@{schemaVersion=1;identityMode=$mode;identity=[pscustomobject](Get-InkQuayIdentity $mode)
        qualificationIdentityOnly=($mode -eq 'qualification');storeIdentityUsed=($mode -eq 'store')
        signed=$false;publicRelease=$false;licenseClearanceClaimed=$false;installationQualificationPassed=$false}
    Assert-InkQuayRecordIdentity $record $mode
    foreach($field in @('identityMode','qualificationIdentityOnly','storeIdentityUsed','signed','publicRelease','licenseClearanceClaimed','installationQualificationPassed')) {
        $bad=$record|ConvertTo-Json -Depth 8|ConvertFrom-Json
        $bad.$field=if($field -eq 'identityMode'){'foreign'}else{-not $bad.$field}
        $rejected=$false;try{Assert-InkQuayRecordIdentity $bad $mode}catch{$rejected=$true}
        if(-not $rejected){throw "Accepted altered $mode record field $field"}
    }
    foreach($field in $record.identity.PSObject.Properties.Name) {
        $bad=$record|ConvertTo-Json -Depth 8|ConvertFrom-Json;$bad.identity.$field='foreign'
        $rejected=$false;try{Assert-InkQuayRecordIdentity $bad $mode}catch{$rejected=$true}
        if(-not $rejected){throw "Accepted altered $mode identity field $field"}
    }
    $record.identity|Add-Member NoteProperty extension 'foreign'
    $rejected=$false;try{Assert-InkQuayRecordIdentity $record $mode}catch{$rejected=$true}
    if(-not $rejected){throw 'Accepted extra identity property'}
    Write-Output "PASS independent $mode record preflight (flags, every identity field, extra field)"
}
