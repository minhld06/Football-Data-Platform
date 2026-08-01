<#
Manage the core Football Data Platform services (postgres, pgadmin, minio, backend, frontend)
via docker compose. Does not touch the "tools" profile services (crawlers, ingestion, dbt),
which are one-off jobs, not long-running system components.

Usage:
    .\scripts\manage.ps1 start
    .\scripts\manage.ps1 stop
    .\scripts\manage.ps1 restart
    .\scripts\manage.ps1 status
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Test-DockerRunning {
    # Native command errors must not be redirected under $ErrorActionPreference = "Stop":
    # PowerShell 5.1 wraps redirected stderr into a terminating NativeCommandError.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        docker info *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Start-System {
    Write-Host "Starting core services (postgres, pgadmin, minio, backend, frontend)..."
    docker compose up -d
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed with exit code $LASTEXITCODE"
    }
    Write-Host "Done. Run '.\scripts\manage.ps1 status' to check container health."
}

function Stop-System {
    Write-Host "Stopping core services..."
    docker compose down
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose down failed with exit code $LASTEXITCODE"
    }
}

function Restart-System {
    Stop-System
    Start-System
}

function Show-Status {
    docker compose ps
}

Push-Location $RepoRoot
try {
    if (-not (Test-DockerRunning)) {
        Write-Error "Docker Desktop is not running. Start Docker Desktop first."
        exit 1
    }

    switch ($Action) {
        "start"   { Start-System }
        "stop"    { Stop-System }
        "restart" { Restart-System }
        "status"  { Show-Status }
    }
}
finally {
    Pop-Location
}
