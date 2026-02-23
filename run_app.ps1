Write-Host "Starting Financial Analyst Agent Streamlit UI..."

if (Test-Path ".venv\Scripts\Activate.ps1") {
    . ".venv\Scripts\Activate.ps1"
    Write-Host "Activated .venv"
}

if (-not $env:SEC_USER_AGENT) {
    $envFile = ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match "^SEC_USER_AGENT=(.+)$") { $env:SEC_USER_AGENT = $Matches[1] }
        }
    }
}

if (-not $env:SEC_USER_AGENT) {
    $ua = Read-Host "SEC_USER_AGENT is required by SEC policy. Enter value (e.g. Name email@example.com)"
    if (-not $ua) {
        Write-Error "SEC_USER_AGENT cannot be empty."
        exit 1
    }
    $env:SEC_USER_AGENT = $ua
}

try {
    streamlit run app.py
} catch {
    Write-Host "If script execution is blocked, run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"
    throw
}
