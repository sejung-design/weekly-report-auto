param(
    [string]$TargetRoot,
    [switch]$ForceSecrets
)

$ErrorActionPreference = "Stop"

$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $TargetRoot) {
    $TargetRoot = $sourceRoot
}
$sourceScripts = Join-Path $sourceRoot "scripts"
$sourceSecrets = Join-Path $sourceRoot "secrets.json"

$targetScripts = Join-Path $TargetRoot "scripts"
$targetConfig = Join-Path $TargetRoot "config"
$targetReports = Join-Path $TargetRoot "reports"
$targetArchive = Join-Path $TargetRoot "archive"
$targetSecrets = Join-Path $targetConfig "secrets.json"

$directories = @(
    $TargetRoot,
    $targetScripts,
    $targetConfig,
    $targetReports,
    $targetArchive
)

foreach ($directory in $directories) {
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory | Out-Null
    }
}

Copy-Item -Path (Join-Path $sourceScripts "*.py") -Destination $targetScripts -Force

if ($ForceSecrets -or -not (Test-Path -LiteralPath $targetSecrets)) {
    Copy-Item -LiteralPath $sourceSecrets -Destination $targetSecrets -Force
    $secretsMessage = "copied"
} else {
    $secretsMessage = "skipped"
}

$docs = @(
    "COWORK_SETUP.md",
    "THURSDAY_TASK.md",
    "FRIDAY_TASK.md",
    "HOW_TO_APPROVE.md"
)

foreach ($doc in $docs) {
    $sourceDoc = Join-Path $sourceRoot $doc
    if (Test-Path -LiteralPath $sourceDoc) {
        Copy-Item -LiteralPath $sourceDoc -Destination (Join-Path $TargetRoot $doc) -Force
    }
}

Write-Host "Deployment complete."
Write-Host "Target root   : $TargetRoot"
Write-Host "Scripts copied: $targetScripts"
Write-Host "Secrets file  : $secretsMessage"
Write-Host "Next step     : update $targetSecrets with real SMTP/Notion values if needed"
