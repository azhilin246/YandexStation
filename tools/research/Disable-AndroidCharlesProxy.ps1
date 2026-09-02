[CmdletBinding()]
param(
    [string]$Serial = "emulator-5556",
    [string]$AdbPath = "C:\Programs\platform-tools\adb.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $AdbPath -PathType Leaf)) {
    throw "adb was not found at $AdbPath"
}

& $AdbPath -s $Serial shell settings put global http_proxy :0
if ($LASTEXITCODE -ne 0) {
    throw "Could not clear the Android proxy setting"
}

& $AdbPath -s $Serial shell settings get global http_proxy
