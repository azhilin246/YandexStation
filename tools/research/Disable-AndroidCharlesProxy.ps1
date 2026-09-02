[CmdletBinding()]
param(
    [string]$Serial = "emulator-5556",
    [string]$AdbPath = "C:\Programs\platform-tools\adb.exe",
    [string]$WifiSsid = "AndroidWifi"
)

$ErrorActionPreference = "Stop"

function Invoke-Adb {
    param([string[]]$AdbArguments)

    $output = & $AdbPath -s $Serial @AdbArguments
    if ($LASTEXITCODE -ne 0) {
        throw "adb failed with exit code $LASTEXITCODE"
    }
    return $output
}

if (-not (Test-Path -LiteralPath $AdbPath -PathType Leaf)) {
    throw "adb was not found at $AdbPath"
}

Invoke-Adb -AdbArguments @("shell", "settings", "put", "global", "http_proxy", ":0") | Out-Null
foreach ($setting in @(
    "global_http_proxy_host",
    "global_http_proxy_port",
    "global_http_proxy_exclusion_list",
    "global_proxy_pac_url"
)) {
    Invoke-Adb -AdbArguments @("shell", "settings", "delete", "global", $setting) | Out-Null
}

$connectivity = Invoke-Adb -AdbArguments @("shell", "dumpsys", "connectivity") | Out-String
if ($connectivity -match "HttpProxy:") {
    $networks = Invoke-Adb -AdbArguments @("shell", "cmd", "wifi", "list-networks")
    $network = $networks | Select-String -Pattern "^\s*(\d+)\s+$([regex]::Escape($WifiSsid))\b" | Select-Object -First 1
    if (-not $network) {
        throw "Could not find Wi-Fi network $WifiSsid to clear its static proxy"
    }

    $networkId = $network.Matches[0].Groups[1].Value
    Invoke-Adb -AdbArguments @("shell", "cmd", "wifi", "forget-network", $networkId) | Out-Null
    Invoke-Adb -AdbArguments @("shell", "cmd", "wifi", "connect-network", $WifiSsid, "open") | Out-Null
}

$connectivity = Invoke-Adb -AdbArguments @("shell", "dumpsys", "connectivity") | Out-String
if ($connectivity -match "HttpProxy:") {
    throw "Android is still using a proxy"
}

[pscustomobject]@{
    Serial = $Serial
    Proxy = "disabled"
    WifiSsid = $WifiSsid
}
