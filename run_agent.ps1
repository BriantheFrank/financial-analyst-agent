$ErrorActionPreference = "Stop"

function Write-Info($Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Ok($Message) {
    Write-Host "[OK]   $Message" -ForegroundColor Green
}

function Get-PythonBootstrapCommand {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return @{ Executable = "py"; Args = @("-3") }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return @{ Executable = "python"; Args = @() }
    }

    return $null
}

function Parse-Arguments([string[]]$RawArgs) {
    $result = @{ Port = 8501; Reinstall = $false; NoBrowser = $false }

    for ($i = 0; $i -lt $RawArgs.Count; $i++) {
        $arg = $RawArgs[$i]
        switch ($arg) {
            "--reinstall" { $result.Reinstall = $true; continue }
            "--noBrowser" { $result.NoBrowser = $true; continue }
            "--port" {
                if ($i + 1 -ge $RawArgs.Count) {
                    throw "Missing value for --port. Example: --port 8502"
                }

                $next = $RawArgs[$i + 1]
                $parsed = 0
                if (-not [int]::TryParse($next, [ref]$parsed)) {
                    throw "Invalid port '$next'. Use an integer such as 8501."
                }
                if ($parsed -lt 1 -or $parsed -gt 65535) {
                    throw "Port must be between 1 and 65535."
                }

                $result.Port = $parsed
                $i++
                continue
            }
            default {
                throw "Unknown argument '$arg'. Supported: --port <int> --reinstall --noBrowser"
            }
        }
    }

    return $result
}

try {
    $parsedArgs = Parse-Arguments -RawArgs $args

    $RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $RepoRoot

    Write-Info "Repository root: $RepoRoot"

    $bootstrap = Get-PythonBootstrapCommand
    if (-not $bootstrap) {
        Write-Host "Python 3.x is required. Install from python.org and re-run Run-Agent.cmd" -ForegroundColor Red
        exit 1
    }

    $venvDir = Join-Path $RepoRoot ".venv"
    $venvPython = Join-Path $venvDir "Scripts/python.exe"
    $depsMarker = Join-Path $venvDir ".deps_installed"

    if (-not (Test-Path $venvPython)) {
        Write-Info "Creating virtual environment in .venv ..."
        & $bootstrap.Executable @($bootstrap.Args + @("-m", "venv", ".venv"))
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
            throw "Failed to create .venv. Verify your Python 3 installation includes venv support."
        }
        Write-Ok "Virtual environment created"
    }
    else {
        Write-Info "Using existing virtual environment (.venv)"
    }

    Write-Info "Upgrading pip ..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed. Check internet connectivity and retry with --reinstall."
    }

    $shouldInstallDeps = $parsedArgs.Reinstall -or -not (Test-Path $depsMarker)
    if ($shouldInstallDeps) {
        if (Test-Path "$RepoRoot/requirements.txt") {
            Write-Info "Installing dependencies from requirements.txt ..."
            if ($parsedArgs.Reinstall) {
                & $venvPython -m pip install --upgrade -r "$RepoRoot/requirements.txt"
            }
            else {
                & $venvPython -m pip install -r "$RepoRoot/requirements.txt"
            }
        }
        else {
            $packages = @("streamlit", "plotly", "kaleido", "pandas", "numpy", "requests", "lxml", "jsonschema", "pytest")
            Write-Info "requirements.txt not found; installing default package set ..."
            if ($parsedArgs.Reinstall) {
                & $venvPython -m pip install --upgrade @packages
            }
            else {
                & $venvPython -m pip install @packages
            }
        }

        if ($LASTEXITCODE -ne 0) {
            throw "Dependency installation failed. Retry with a stable internet connection or run again with --reinstall."
        }

        "installed=$(Get-Date -Format o)" | Out-File -FilePath $depsMarker -Encoding utf8 -Force
        Write-Ok "Dependencies ready"
    }
    else {
        Write-Info "Dependencies already installed. Use --reinstall to force refresh."
    }

    if ([string]::IsNullOrWhiteSpace($env:SEC_USER_AGENT)) {
        $envPath = Join-Path $RepoRoot ".env"
        $envValue = $null

        if (Test-Path $envPath) {
            $line = Get-Content $envPath | Where-Object { $_ -match '^\s*SEC_USER_AGENT\s*=' } | Select-Object -First 1
            if ($line) {
                $envValue = ($line -replace '^\s*SEC_USER_AGENT\s*=\s*', '').Trim().Trim('"').Trim("'")
            }
        }

        if (-not [string]::IsNullOrWhiteSpace($envValue)) {
            $env:SEC_USER_AGENT = $envValue
            Write-Ok "Loaded SEC_USER_AGENT from .env"
        }
        else {
            do {
                $inputValue = Read-Host "Enter SEC_USER_AGENT (format: Your Name your.email@example.com)"
            } until (-not [string]::IsNullOrWhiteSpace($inputValue))

            $env:SEC_USER_AGENT = $inputValue.Trim()
            $existingLines = @()
            if (Test-Path $envPath) {
                $existingLines = Get-Content $envPath | Where-Object { $_ -notmatch '^\s*SEC_USER_AGENT\s*=' }
            }
            $newLines = @($existingLines + "SEC_USER_AGENT=$($env:SEC_USER_AGENT)")
            Set-Content -Path $envPath -Value $newLines -Encoding utf8
            Write-Ok "Saved SEC_USER_AGENT to .env"
        }
    }
    else {
        Write-Ok "Using SEC_USER_AGENT from existing environment"
    }

    if (-not (Test-Path "$RepoRoot/app.py")) {
        throw "app.py was not found in repository root ($RepoRoot). Ensure you extracted the full project ZIP and re-run Run-Agent.cmd"
    }

    $url = "http://localhost:$($parsedArgs.Port)"
    Write-Host ""
    Write-Host "Starting Financial Analyst Agent UI ..." -ForegroundColor Green
    Write-Host "If your browser does not open, visit: $url" -ForegroundColor Green

    $streamlitArgs = @("-m", "streamlit", "run", "app.py", "--server.port", "$($parsedArgs.Port)", "--server.address", "localhost")
    if ($parsedArgs.NoBrowser) {
        $streamlitArgs += @("--server.headless", "true")
    }

    & $venvPython @streamlitArgs
    exit $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "Launcher error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1) Verify Python 3.x is installed and available in PATH or via 'py -3'."
    Write-Host "  2) Ensure this folder contains app.py and requirements.txt (if used)."
    Write-Host "  3) Re-run Run-Agent.cmd --reinstall to refresh dependencies."
    exit 1
}
