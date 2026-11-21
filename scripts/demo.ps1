$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$apiDirectory = Join-Path $projectRoot 'services\business-api'
$voiceDirectory = Join-Path $projectRoot 'bolo-ride-voice\server'
$webDirectory = Join-Path $projectRoot 'bolo-ride-voice\web'
$voiceWorkspace = Join-Path $projectRoot 'bolo-ride-voice'
$demoDirectory = Join-Path $apiDirectory '.demo'
$databasePath = Join-Path $demoDirectory 'bolo-ride.db'
$voiceEnvPath = Join-Path $voiceDirectory '.env'
$databaseUrl = 'sqlite+aiosqlite:///' + ($databasePath.Replace('\', '/'))
$businessApiKey = 'local-demo-only-change-before-deploy'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python is required. Install Python and the business API requirements first.'
}
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
    throw 'Bun is required. Install Bun to run the Next.js demo.'
}
if (-not (Test-Path (Join-Path $voiceWorkspace 'node_modules\next'))) {
    throw 'Web dependencies are missing. Run bun install in bolo-ride-voice first.'
}
if (-not (Test-Path $voiceEnvPath)) {
    throw 'Voice environment is missing. Copy bolo-ride-voice\server\.env.example to .env and configure Agora credentials.'
}

foreach ($port in @(3000, 8000, 8010)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the existing demo service and retry."
    }
}

Push-Location $voiceDirectory
try {
    & python -c 'import fastapi, uvicorn, agora_agent, dotenv, httpx'
    if ($LASTEXITCODE -ne 0) {
        throw 'Voice service dependencies are missing. Run python -m pip install -r bolo-ride-voice\server\requirements.txt.'
    }
    $credentialsReady = & python -c 'from dotenv import load_dotenv; import os; load_dotenv(".env"); app_id=os.getenv("AGORA_APP_ID", ""); certificate=os.getenv("AGORA_APP_CERTIFICATE", ""); print("ready" if app_id and certificate and not app_id.startswith("your_") and not certificate.startswith("your_") else "missing")'
    if ($LASTEXITCODE -ne 0 -or $credentialsReady.Trim() -ne 'ready') {
        throw 'Agora credentials are missing or still set to example values in bolo-ride-voice\server\.env.'
    }
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Force -Path $demoDirectory | Out-Null
$apiJob = $null
$voiceJob = $null
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

    $voiceJob = Start-Job -Name 'BoloRideVoiceApi' -ArgumentList $voiceDirectory, $businessApiKey -ScriptBlock {
        param($workingDirectory, $apiKey)
        Set-Location $workingDirectory
        $env:BUSINESS_API_URL = 'http://127.0.0.1:8010'
        $env:BUSINESS_API_KEY = $apiKey
        $env:PYTHONUNBUFFERED = '1'
        python src/server.py
    }

    $voiceReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($voiceJob.State -ne 'Running') {
            $jobOutput = Receive-Job -Job $voiceJob -Keep | Out-String
            throw "Voice API did not start. $jobOutput"
        }
        try {
            $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 2
            $voiceReady = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $voiceReady) {
        throw 'Voice API did not become ready on http://127.0.0.1:8000.'
    }

    $webJob = Start-Job -Name 'BoloRideWebDemo' -ArgumentList $webDirectory, $businessApiKey -ScriptBlock {
        param($workingDirectory, $apiKey)
        Set-Location $workingDirectory
        $env:AGENT_BACKEND_URL = 'http://127.0.0.1:8000'
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
    Write-Host 'Bolo Ride voice demo is ready: http://localhost:3000/' -ForegroundColor Green
    Write-Host 'Tap-through booking and payment demo: http://localhost:3000/demo'
    Write-Host 'This uses a local SQLite database and simulated rides/payments.'
    Write-Host 'For voice booking tools, set a publicly reachable AGENT_PUBLIC_URL in server\.env; the LLM cannot simulate payment results.'
    Write-Host 'Press Ctrl+C here to stop all three local services.'
    while ($apiJob.State -eq 'Running' -and $voiceJob.State -eq 'Running' -and $webJob.State -eq 'Running') {
        Start-Sleep -Seconds 1
    }
    if ($apiJob.State -ne 'Running' -or $voiceJob.State -ne 'Running' -or $webJob.State -ne 'Running') {
        throw 'A demo service stopped unexpectedly. Review the job output and restart the demo.'
    }
} finally {
    foreach ($job in @($webJob, $voiceJob, $apiJob)) {
        if ($null -ne $job) {
            if ($job.State -eq 'Running') {
                Stop-Job -Job $job
            }
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        }
    }
}
