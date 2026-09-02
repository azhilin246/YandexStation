[CmdletBinding()]
param(
    [string]$Serial = "emulator-5556",
    [string]$AdbPath = "C:\Programs\platform-tools\adb.exe",
    [string]$CharlesCertificate = "$env:APPDATA\Charles\data\ca\charles-proxy-ssl-proxying-certificate.pem",
    [string]$ProxyHost = "10.0.2.2",
    [int]$ProxyPort = 8888
)

$ErrorActionPreference = "Stop"

function Invoke-Adb {
    param([string[]]$AdbArguments)

    & $AdbPath -s $Serial @AdbArguments
    if ($LASTEXITCODE -ne 0) {
        throw "adb failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $AdbPath -PathType Leaf)) {
    throw "adb was not found at $AdbPath"
}
if (-not (Test-Path -LiteralPath $CharlesCertificate -PathType Leaf)) {
    throw "Charles CA certificate was not found at $CharlesCertificate"
}

$openssl = Get-Command openssl.exe -ErrorAction SilentlyContinue
if (-not $openssl) {
    $gitOpenSsl = "C:\Program Files\Git\usr\bin\openssl.exe"
    if (Test-Path -LiteralPath $gitOpenSsl -PathType Leaf) {
        $openssl = Get-Item -LiteralPath $gitOpenSsl
    } else {
        throw "openssl.exe is required to calculate Android's certificate filename"
    }
}

$certificateHash = (& $openssl.Source x509 -inform PEM -subject_hash_old -noout -in $CharlesCertificate).Trim()
if ($LASTEXITCODE -ne 0 -or $certificateHash -notmatch '^[0-9a-f]{8}$') {
    throw "Could not calculate the Android certificate hash"
}

$localCertificate = Join-Path $env:TEMP "$certificateHash.0"
Copy-Item -LiteralPath $CharlesCertificate -Destination $localCertificate -Force

& $AdbPath -s $Serial root
if ($LASTEXITCODE -ne 0) {
    throw "The selected emulator is not rootable"
}
Invoke-Adb -AdbArguments @("wait-for-device")

$remoteStage = "/data/local/tmp/yandexstation-charles-ca"
Invoke-Adb -AdbArguments @("shell", "mkdir", "-p", $remoteStage)
Invoke-Adb -AdbArguments @("push", $localCertificate, "$remoteStage/$certificateHash.0")
$androidInstallScript = Join-Path $PSScriptRoot "install-charles-ca-android14.sh"
Invoke-Adb -AdbArguments @("push", $androidInstallScript, "$remoteStage/install-charles-ca-android14.sh")
Invoke-Adb -AdbArguments @("shell", "sh", "$remoteStage/install-charles-ca-android14.sh", $certificateHash)
Invoke-Adb -AdbArguments @("shell", "settings", "put", "global", "http_proxy", "${ProxyHost}:$ProxyPort")
Invoke-Adb -AdbArguments @("shell", "am", "force-stop", "com.android.chrome")

$proxy = (Invoke-Adb -AdbArguments @("shell", "settings", "get", "global", "http_proxy") | Out-String).Trim()
$apexCertificate = (Invoke-Adb -AdbArguments @("shell", "ls", "/apex/com.android.conscrypt/cacerts/$certificateHash.0") | Out-String).Trim()

[pscustomobject]@{
    Serial = $Serial
    Proxy = $proxy
    CertificateHash = $certificateHash
    ConscryptCertificate = $apexCertificate
}
