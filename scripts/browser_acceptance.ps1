param(
    [string]$BaseUrl = "http://localhost:8030",
    [string]$ChromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ChromePath)) {
    throw "Chrome not found: $ChromePath"
}

# Public pages render directly; protected pages must redirect an anonymous browser to login.
$cases = [ordered]@{
    "/"                     = "HERTA INTELLIGENCE NETWORK"
    "/characters"           = "CHARACTER ARCHIVE"
    "/lightcones"           = "LIGHT CONE ARCHIVE"
    "/relics"               = "RELIC ARCHIVE"
    "/items"                = "ITEM ARCHIVE"
    "/stories"              = "STORY ARCHIVE"
    "/activities"           = "ACTIVITY ARCHIVE"
    "/community/characters" = "COMMUNITY ARCHIVE"
    "/login"                = "HERTA IDENTITY SYSTEM"
    "/teams"                = "HERTA IDENTITY SYSTEM"
    "/planning"             = "HERTA IDENTITY SYSTEM"
    "/weekly-plan"          = "HERTA IDENTITY SYSTEM"
    "/creator"              = "HERTA IDENTITY SYSTEM"
}

$profile = Join-Path $env:TEMP "star-rail-chrome-acceptance-$PID"
$failed = 0
$index = 0
foreach ($case in $cases.GetEnumerator()) {
    $index += 1
    $stdout = Join-Path $env:TEMP "star-rail-page-$index.html"
    $stderr = Join-Path $env:TEMP "star-rail-page-$index.err"
    $arguments = @(
        "--headless=new"
        "--disable-gpu"
        "--no-first-run"
        "--no-default-browser-check"
        "--user-data-dir=$profile"
        "--virtual-time-budget=5000"
        "--dump-dom"
        "$BaseUrl$($case.Key)"
    )
    $process = Start-Process `
        -FilePath $ChromePath `
        -ArgumentList $arguments `
        -WindowStyle Hidden `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr
    $html = Get-Content -LiteralPath $stdout -Raw -Encoding utf8
    $passed = (
        $process.ExitCode -eq 0 `
        -and $html.Contains([string]$case.Value)
    )
    if (-not $passed) {
        $failed += 1
    }
    Write-Output (
        "{0,-24} pass={1,-5} bytes={2,-8} expected={3}" -f `
            $case.Key, $passed, $html.Length, $case.Value
    )
}

if ($failed -gt 0) {
    throw "Browser acceptance failed: $failed page(s)"
}
Write-Output "Browser acceptance passed: $($cases.Count) pages"
