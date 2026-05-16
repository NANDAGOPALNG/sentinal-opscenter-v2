param(
    [string]$BaseUrl = "http://localhost:8001",
    [string]$Repository = "NANDAGOPALNG/sentinal-opscenter-v2",
    [string]$WebhookSecret = $env:GITHUB_WEBHOOK_SECRET
)

$ErrorActionPreference = "Stop"

function New-GitHubSignature {
    param(
        [Parameter(Mandatory = $true)][string]$Body,
        [Parameter(Mandatory = $true)][string]$Secret
    )

    $hmac = [System.Security.Cryptography.HMACSHA256]::new(
        [System.Text.Encoding]::UTF8.GetBytes($Secret)
    )
    $hashBytes = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Body))
    return "sha256=" + (($hashBytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Invoke-SentinalPost {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Body,
        [hashtable]$Headers = @{}
    )

    if ($WebhookSecret) {
        $Headers["X-Hub-Signature-256"] = New-GitHubSignature -Body $Body -Secret $WebhookSecret
    }

    Invoke-RestMethod `
        -Uri "$BaseUrl$Path" `
        -Method Post `
        -ContentType "application/json" `
        -Headers $Headers `
        -Body $Body
}

Write-Host "== Sentinal smoke test =="
Write-Host "Base URL: $BaseUrl"

Write-Host "`n[1/6] Health"
Invoke-RestMethod -Uri "$BaseUrl/health"

Write-Host "`n[2/6] GitHub status"
Invoke-RestMethod -Uri "$BaseUrl/github/status"

Write-Host "`n[3/6] Notification status"
Invoke-RestMethod -Uri "$BaseUrl/notifications/status"

Write-Host "`n[4/6] Webhook normalization preview"
$previewBody = @{
    repository = @{
        full_name = $Repository
    }
    ref = "refs/heads/main"
    head_commit = @{
        message = "Smoke test normalization"
        modified = @("apps/api/main.py", "workflows/incident_graph.py")
    }
} | ConvertTo-Json -Depth 5 -Compress

Invoke-SentinalPost -Path "/webhook/preview" -Body $previewBody

Write-Host "`n[5/6] Idempotency"
$idempotencyKey = "smoke-test-local-$([Guid]::NewGuid().ToString())"
$dedupeBody = @{
    event_type = "smoke_test"
    service = "api"
    severity = "info"
    message = "Smoke test idempotency"
    repository = $Repository
    idempotency_key = $idempotencyKey
} | ConvertTo-Json -Depth 5 -Compress

$first = Invoke-SentinalPost -Path "/webhook" -Body $dedupeBody
$second = Invoke-SentinalPost -Path "/webhook" -Body $dedupeBody

$first
$second

if ($first.status -ne "accepted") {
    throw "Expected first idempotency request to be accepted."
}
if ($second.status -ne "duplicate") {
    throw "Expected second idempotency request to be duplicate."
}

Write-Host "`n[6/6] Workflow listing"
Start-Sleep -Seconds 8
$workflows = Invoke-RestMethod -Uri "$BaseUrl/workflows"
$workflows | Select-Object -First 3

Write-Host "`nSmoke test passed."
