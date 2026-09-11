# Copyright 2026 Trieflow LLC. MIT. Local boundary fixtures, not Windows signature verification.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
$temporaryBase=if ($IsMacOS) { '/private/tmp' } else { [IO.Path]::GetTempPath() }
$fixtureRoot=Join-Path $temporaryBase ('inkquay-defender-'+[guid]::NewGuid().ToString('N'))
$platform=Join-Path $fixtureRoot 'Microsoft/Windows Defender/Platform'
$version=Join-Path $platform '4.18.26080.3-0'
New-Item -ItemType Directory -Path $version -Force | Out-Null
$file=Join-Path $version 'MpOav.dll'
[IO.File]::WriteAllText($file,'fixture DLL bytes; not a signed Windows binary')
$script:signatureStatus='Valid'
$script:signatureSubject='CN=Microsoft Windows Publisher, O=Microsoft Corporation, C=US'
$script:mutateDuringSignature=$false
function Get-AuthenticodeSignature {
    param([string]$LiteralPath)
    if ($script:mutateDuringSignature) { [IO.File]::WriteAllText($LiteralPath,'changed during verification') }
    [pscustomobject]@{ Status=$script:signatureStatus; SignerCertificate=[pscustomobject]@{
        Subject=$script:signatureSubject; SubjectName=[Security.Cryptography.X509Certificates.X500DistinguishedName]::new($script:signatureSubject);
        Issuer='Fixture test authority'; Thumbprint=('A'*40) } }
}
function Assert-Rejected([scriptblock]$Operation) {
    $rejected=$false
    try { & $Operation | Out-Null } catch { $rejected=$true }
    if (-not $rejected) { throw 'Untrusted Defender-module fixture was accepted.' }
}
try {
    $result=Get-VerifiedDefenderModuleEvidence -Path $file -PlatformRoot $platform
    if ($result.signature_status -cne 'Valid' -or $result.sha256 -cne (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'Expected exact module hash and signature evidence.' }
    foreach ($name in @('Microsoft Corporation','Microsoft Windows')) {
        $script:signatureSubject='CN='+$name+', O=Microsoft Corporation, C=US'
        $result=Get-VerifiedDefenderModuleEvidence -Path $file -PlatformRoot $platform
        if ($result.signer_common_name -cne $name) { throw 'Parsed Microsoft signer identity changed.' }
    }
    foreach ($status in @('NotSigned','HashMismatch','UnknownError','NotTrusted')) {
        $script:signatureStatus=$status
        Assert-Rejected { Get-VerifiedDefenderModuleEvidence -Path $file -PlatformRoot $platform }
    }
    $script:signatureStatus='Valid'
    foreach ($subject in @('CN=Microsoft Windows Publisher, O=Someone Else, C=US','CN=Unrelated App, O=Microsoft Corporation, C=US','CN=Microsoft Windows Publisher, O=Microsoft Corporation Fake, C=US',
        'CN=Independent Review Signer, O=Independent Review Org, OU="prefix, CN=Microsoft Windows Publisher, O=Microsoft Corporation, suffix", C=US',
        'CN=Microsoft Windows Publisher, CN=Other, O=Microsoft Corporation, C=US',
        'CN=Microsoft Windows Publisher, O=Microsoft Corporation, O=Other, C=US')) {
        $script:signatureSubject=$subject
        Assert-Rejected { Get-VerifiedDefenderModuleEvidence -Path $file -PlatformRoot $platform }
    }
    $script:signatureSubject='CN=Microsoft Windows Publisher, O=Microsoft Corporation, C=US'
    foreach ($relative in @('4.18.26080.3-0/Other.dll','4.18.26080.3-0/nested/MpOav.dll','invalid-version/MpOav.dll','../PlatformFake/4.18.26080.3-0/MpOav.dll')) {
        $other=Join-Path $platform $relative
        New-Item -ItemType Directory -Path (Split-Path $other -Parent) -Force | Out-Null
        [IO.File]::WriteAllText($other,'wrong location or module')
        Assert-Rejected { Get-VerifiedDefenderModuleEvidence -Path $other -PlatformRoot $platform }
    }
    $script:mutateDuringSignature=$true
    Assert-Rejected { Get-VerifiedDefenderModuleEvidence -Path $file -PlatformRoot $platform }
    $script:mutateDuringSignature=$false
    $link=Join-Path $platform '4.18.99999.0-0'
    $linkType=if ($IsWindows) { 'Junction' } else { 'SymbolicLink' }
    New-Item -ItemType $linkType -Path $link -Target $version | Out-Null
    Assert-Rejected { Get-VerifiedDefenderModuleEvidence -Path (Join-Path $link 'MpOav.dll') -PlatformRoot $platform }
    Write-Output 'PASS: three valid metadata fixtures and 16 signature/path/mutation/link rejection cases. Actual Windows signatures remain a native-run check.'
} finally {
    Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
}
