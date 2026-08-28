<#
.SYNOPSIS
    Start / stop / restart / inspect the Football Data Platform's Docker Compose stack.

.DESCRIPTION
    Thin wrapper around `docker compose` for the always-on services defined in
    docker-compose.yml (postgres, pgadmin, minio, backend, frontend).

    Does NOT touch the one-shot "tools" profile services (crawlers, ingestion, dbt) —
    those are run on demand via `docker compose run --rm <service>`, not started/stopped
    like long-running services. See CLAUDE.md for those commands.

.PARAMETER Action
    start   - docker compose up -d
    stop    - docker compose down (containers removed, volumes/data kept)
    restart - docker compose restart [service] (does NOT pick up a rebuilt image -- use 'up -d' for that)
    status  - docker compose ps
    logs    - docker compose logs -f --tail=100 [service]
    build   - docker compose build [service]

.PARAMETER Service
    Optional. Limit restart/logs/build to a single service (e.g. backend, frontend).
    Ignored by start/stop/status, which always act on the whole stack.

.EXAMPLE
    .\manage.ps1 start
.EXAMPLE
    .\manage.ps1 restart -Service backend
.EXAMPLE
    .\manage.ps1 logs -Service postgres
#>

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "build")]
    [string]$Action,

    [Parameter(Position = 1)]
    [string]$Service = ""
)

function Write-Info($msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host $msg -ForegroundColor Green }
function Write-Warn($msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-ErrorMsg($msg) { Write-Host $msg -ForegroundColor Red }

# Fail fast if Docker Desktop isn't running, instead of letting `docker compose`
# produce a confusing low-level connection error.
function Test-DockerRunning {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Docker doesn't seem to be running. Start Docker Desktop and try again."
        exit 1
    }
}

function Test-EnvFile {
    if (-not (Test-Path ".env")) {
        Write-Warn "No .env file found in project root. Copy .env.example to .env and fill in real values first:"
        Write-Warn "    Copy-Item .env.example .env"
    }
}

Test-DockerRunning

switch ($Action) {
    "start" {
        Test-EnvFile
        Write-Info "Starting Football Data Platform (postgres, pgadmin, minio, backend, frontend)..."
        docker compose up -d
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Stack is up. Check status with: .\manage.ps1 status"
        } else {
            Write-ErrorMsg "docker compose up failed. See output above."
            exit $LASTEXITCODE
        }
    }

    "stop" {
        Write-Info "Stopping Football Data Platform..."
        docker compose down
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Stack is down. Volumes (pgdata, minio_data, pgadmin_data) are preserved."
        } else {
            Write-ErrorMsg "docker compose down failed. See output above."
            exit $LASTEXITCODE
        }
    }

    "restart" {
        Write-Warn "Note: 'restart' just restarts the existing container from its current image -- it does NOT pick up a freshly built image. After '.\manage.ps1 build', use 'docker compose up -d [service]' (not restart) to actually swap in the new image."
        if ($Service) {
            Write-Info "Restarting service: $Service..."
            docker compose restart $Service
        } else {
            Write-Info "Restarting all services..."
            docker compose restart
        }
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Restart complete."
        } else {
            Write-ErrorMsg "docker compose restart failed. See output above."
            exit $LASTEXITCODE
        }
    }

    "status" {
        docker compose ps
    }

    "logs" {
        if ($Service) {
            Write-Info "Tailing logs for $Service (Ctrl+C to stop)..."
            docker compose logs -f --tail=100 $Service
        } else {
            Write-Info "Tailing logs for all services (Ctrl+C to stop)..."
            docker compose logs -f --tail=100
        }
    }

    "build" {
        Write-Warn "Reminder: crawlers/ingestion/dbt Dockerfiles COPY source at build time -- rebuild is required after editing their code (see CLAUDE.md)."
        if ($Service) {
            Write-Info "Building image for $Service..."
            docker compose build $Service
        } else {
            Write-Info "Building images for all services..."
            docker compose build
        }
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Build complete."
        } else {
            Write-ErrorMsg "docker compose build failed. See output above."
            exit $LASTEXITCODE
        }
    }
}
