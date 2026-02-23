[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message"
}

function Write-NextStep {
    param([string]$Message)
    Write-Host "[NEXT] $Message" -ForegroundColor Yellow
}

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    Write-Host "Python 3.11+ is required. Install from python.org, then re-run Run-Agent.cmd" -ForegroundColor Red
    exit 1
}

function Invoke-Python {
    param(
        [string[]]$Command,
        [string[]]$Arguments
    )

    if ($Command.Length -gt 1) {
        & $Command[0] $Command[1..($Command.Length - 1)] @Arguments
    }
    else {
        & $Command[0] @Arguments
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($Command -join ' ') $($Arguments -join ' ')"
    }
}

function Update-DotEnv {
    param(
        [string]$EnvPath,
        [string]$Value
    )

    if (Test-Path $EnvPath) {
        $lines = Get-Content -Path $EnvPath
        $updated = $false
        $newLines = foreach ($line in $lines) {
            if ($line -match '^\s*SEC_USER_AGENT\s*=') {
                $updated = $true
                "SEC_USER_AGENT=$Value"
            }
            else {
                $line
            }
        }

        if (-not $updated) {
            $newLines += "SEC_USER_AGENT=$Value"
        }

        Set-Content -Path $EnvPath -Value $newLines
    }
    else {
        Set-Content -Path $EnvPath -Value "SEC_USER_AGENT=$Value"
    }
}

function Get-SecUserAgent {
    param([string]$EnvPath)

    if (-not [string]::IsNullOrWhiteSpace($env:SEC_USER_AGENT)) {
        return $env:SEC_USER_AGENT.Trim()
    }

    if (Test-Path $EnvPath) {
        $match = Select-String -Path $EnvPath -Pattern '^\s*SEC_USER_AGENT\s*=\s*(.+)\s*$' | Select-Object -First 1
        if ($match) {
            $value = $match.Matches[0].Groups[1].Value.Trim()
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                return $value
            }
        }
    }

    Write-Host "SEC requires a descriptive User-Agent with contact info." -ForegroundColor Yellow
    Write-Host "Example: Your Name your.email@example.com" -ForegroundColor Yellow

    do {
        $inputValue = Read-Host "Enter SEC_USER_AGENT"
        $inputValue = $inputValue.Trim()
        if ([string]::IsNullOrWhiteSpace($inputValue)) {
            Write-Host "SEC_USER_AGENT cannot be empty. Please try again." -ForegroundColor Red
        }
    } while ([string]::IsNullOrWhiteSpace($inputValue))

    Update-DotEnv -EnvPath $EnvPath -Value $inputValue
    Write-Info "Saved SEC_USER_AGENT to .env for future runs."
    return $inputValue
}

try {
    $RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $RepoRoot

    $reinstall = $false
    $port = 8501
    $headless = $false

    for ($i = 0; $i -lt $RemainingArgs.Count; $i++) {
        switch ($RemainingArgs[$i]) {
            "--reinstall" {
                $reinstall = $true
            }
            "--no-browser" {
                $headless = $true
            }
            "--port" {
                if ($i + 1 -ge $RemainingArgs.Count) {
                    throw "Missing value for --port. Example: --port 8502"
                }

                $portCandidate = $RemainingArgs[$i + 1]
                $parsedPort = 0
                if (-not [int]::TryParse($portCandidate, [ref]$parsedPort)) {
                    throw "Invalid --port value '$portCandidate'. Use an integer such as 8501."
                }

                if ($parsedPort -lt 1 -or $parsedPort -gt 65535) {
                    throw "Port must be between 1 and 65535."
                }

                $port = $parsedPort
                $i++
            }
            default {
                throw "Unknown argument '$($RemainingArgs[$i])'. Supported: --reinstall, --port <int>, --no-browser"
            }
        }
    }

    $pythonCommand = Get-PythonCommand

    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $venvCreated = $false
    if (-not (Test-Path $venvPython)) {
        Write-Info "Creating virtual environment in .venv..."
        Invoke-Python -Command $pythonCommand -Arguments @("-m", "venv", ".venv")
        $venvCreated = $true
    }
    else {
        Write-Info "Using existing virtual environment (.venv)."
    }

    if (-not (Test-Path $venvPython)) {
        throw "Virtual environment creation failed. Could not find $venvPython"
    }

    Write-Info "Upgrading pip..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip in .venv"
    }

    $requirementsPath = Join-Path $RepoRoot "requirements.txt"
    $depsMarkerPath = Join-Path $RepoRoot ".venv\.deps_installed"
    $shouldInstallDeps = $reinstall -or $venvCreated -or -not (Test-Path $depsMarkerPath)

    if ($shouldInstallDeps) {
        $pipArgs = @("-m", "pip", "install")
        if ($reinstall) {
            Write-Info "Forcing dependency reinstall (--reinstall)."
            $pipArgs += @("--upgrade", "--force-reinstall")
        }

        if (Test-Path $requirementsPath) {
            Write-Info "Installing dependencies from requirements.txt..."
            $pipArgs += @("-r", "requirements.txt")
        }
        else {
            Write-Info "requirements.txt not found. Installing fallback dependency set..."
            $pipArgs += @("streamlit", "plotly", "kaleido", "pandas", "numpy", "requests", "lxml", "jsonschema", "pytest")
        }

        & $venvPython @pipArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Dependency installation failed."
        }

        Set-Content -Path $depsMarkerPath -Value "Dependencies installed $(Get-Date -Format o)"
    }
    else {
        Write-Info "Dependencies already installed. Skipping install step (use --reinstall to force)."
    }

    $envFilePath = Join-Path $RepoRoot ".env"
    $env:SEC_USER_AGENT = Get-SecUserAgent -EnvPath $envFilePath

    $appPath = Join-Path $RepoRoot "app.py"
    if (-not (Test-Path $appPath)) {
        throw "Could not find app.py in the repository root. Make sure the Streamlit entrypoint exists, then re-run Run-Agent.cmd."
    }

    Write-Host "Launching Financial Analyst Agent UI..." -ForegroundColor Green
    Write-Host "If the browser doesn't open automatically, go to http://localhost:$port" -ForegroundColor Green

    $streamlitArgs = @("-m", "streamlit", "run", "app.py", "--server.port", "$port", "--server.address", "localhost")
    if ($headless) {
        $streamlitArgs += @("--server.headless", "true")
    }

    & $venvPython @streamlitArgs
    exit $LASTEXITCODE
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-NextStep "If Python is missing, install Python 3.11+ from python.org."
    Write-NextStep "Then run Run-Agent.cmd again from the repository root."
    exit 1
}
