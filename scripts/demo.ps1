$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$apiDirectory = Join-Path $projectRoot 'services\business-api'
$webDirectory = Join-Path $projectRoot 'bolo-ride-voice\web'
$demoDirectory = Join-Path $apiDirectory '.demo'
$databasePath = Join-Path $demoDirectory 'bolo-ride.db'
$databaseUrl = 'sqlite+aiosqlite:///' + ($databasePath.Replace('\', '/'))
$businessApiKey = 'local-demo-only-change-before-deploy'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python is required. Install Python and the business API requirements first.'
}
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
    throw 'Bun is required. Install Bun to run the Next.js demo.'
}
if (-not (Test-Path (Join-Path $webDirectory 'node_modules\next\bin\next'))) {
    throw 'Web dependencies are missing. Run bun install in bolo-ride-voice\web first.'
}

New-Item -ItemType Directory -Force -Path $demoDirectory | Out-Null
$apiJob = $null
$webJob = $null

try {
    Push-Location $apiDirectory
    try {
        $env:DATABASE_URL = $databaseUrl
        $env:BUSINESS_API_KEY = $businessApiKey
        $env:MOCK_PAYMENTS_ENABLED = 'true'
        python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw 'Business API migrations failed. Install services\business-api\requirements.txt and retry.'
        }
    } finally {
        Pop-Location
    }

    $apiJob = Start-Job -Name 'BoloRideBusinessApi' -ArgumentList $apiDirectory, $databaseUrl, $businessApiKey -ScriptBlock {
        param($workingDirectory, $databaseConnection, $apiKey)
        Set-Location $workingDirectory
        $env:DATABASE_URL = $databaseConnection
        $env:BUSINESS_API_KEY = $apiKey
        $env:MOCK_PAYMENTS_ENABLED = 'true'
        python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --log-level warning
    }

    $apiReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($apiJob.State -ne 'Running') {
            $jobOutput = Receive-Job -Job $apiJob -Keep | Out-String
            throw "Business API did not start. $jobOutput"
        }
        try {
            $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8010/health' -TimeoutSec 2
            $apiReady = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $apiReady) {
        throw 'Business API did not become ready on http://127.0.0.1:8010.'
    }

    $webJob = Start-Job -Name 'BoloRideWebDemo' -ArgumentList $webDirectory, $businessApiKey -ScriptBlock {
        param($workingDirectory, $apiKey)
        Set-Location $workingDirectory
        $env:BUSINESS_API_URL = 'http://127.0.0.1:8010'
        $env:BUSINESS_API_KEY = $apiKey
        bun run dev -- --hostname 127.0.0.1 --port 3000
    }

    $webReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($webJob.State -ne 'Running') {
            $jobOutput = Receive-Job -Job $webJob -Keep | Out-String
            throw "Next.js demo did not start. $jobOutput"
        }
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:3000/demo' -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $webReady = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $webReady) {
        throw 'Next.js demo did not become ready on http://127.0.0.1:3000.'
    }

    Write-Host ''
    Write-Host 'Bolo Ride demo is ready: http://localhost:3000/demo' -ForegroundColor Green
    Write-Host 'This uses a local SQLite database and simulated rides/payments.'
    Write-Host 'Press Ctrl+C here to stop both local services.'
    while ($apiJob.State -eq 'Running' -and $webJob.State -eq 'Running') {
        Start-Sleep -Seconds 1
    }
    if ($apiJob.State -ne 'Running' -or $webJob.State -ne 'Running') {
        throw 'A demo service stopped unexpectedly. Review the job output and restart the demo.'
    }
} finally {
    foreach ($job in @($webJob, $apiJob)) {
        if ($null -ne $job) {
            if ($job.State -eq 'Running') {
                Stop-Job -Job $job
            }
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        }
    }
}
