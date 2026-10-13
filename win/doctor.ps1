### Firewall Policies Migrator environment diagnostics for Windows
#
# PowerShell analogue of scripts/doctor.sh

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env")
)

# -- powershell specific configuration
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# --

# -- tools for doctor check
$errors = 0
$warnings = 0

function Write-DoctorOk {
    param([Parameter(Mandatory = $true)][string]$Message)

    Write-Output "[doctor] OK: $Message"
}

function Write-DoctorWarning {
    param([Parameter(Mandatory = $true)][string]$Message)

    $script:warnings++
    Write-Warning "[doctor] WARN: $Message"
}

function Write-DoctorError {
    param([Parameter(Mandatory = $true)][string]$Message)

    $script:errors++
    Write-Error -ErrorAction Continue "[doctor] ERROR: $Message"
}

function Get-EnvValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    foreach ($line in [System.IO.File]::ReadAllLines($EnvFile)) {
        $separator = $line.IndexOf("=")
        if ($separator -lt 1 -or $line.Substring(0, $separator).Trim() -ne $Name) {
            continue
        }

        # Environment values are parsed as data only and never written to output.
        return $line.Substring($separator + 1).Trim()
    }

    return $null
}

function Require-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Hint
    )

    if ([string]::IsNullOrWhiteSpace([string](Get-EnvValue -Name $Name))) {
        Write-DoctorError "$Name is missing or empty. $Hint"
    }
    else {
        Write-DoctorOk "$Name is configured."
    }
}
# --

# -- run check
if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-DoctorError "Docker CLI is missing. Install and start Docker Desktop, then retry."
}
else {
    Write-DoctorOk "Docker CLI is installed."

    # Docker can write non-fatal daemon warnings to stderr. With Stop enabled,
    # Windows PowerShell treats those warnings as terminating native errors.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker compose version 2>$null | Out-Null
        $composeExitCode = $LASTEXITCODE

        & docker info 2>$null | Out-Null
        $dockerInfoExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($composeExitCode -eq 0) {
        Write-DoctorOk "Docker Compose plugin is installed."
    }
    else {
        Write-DoctorError "Docker Compose plugin is missing. Update Docker Desktop, then retry."
    }

    if ($dockerInfoExitCode -eq 0) {
        Write-DoctorOk "Docker daemon is reachable."
    }
    else {
        Write-DoctorError "Docker daemon is not reachable. Start Docker Desktop, then retry."
    }
}

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    Write-DoctorError "$EnvFile is missing. Run 'env-init' or 'setup' first."
}
else {
    Write-DoctorOk "$EnvFile exists."

    Require-EnvValue -Name "PYTHON_IMAGE" -Hint "Docker image for python service should be set."
    Require-EnvValue -Name "POSTGRES_IMAGE" -Hint "Docker image for postgres service should be set."
    Require-EnvValue -Name "APP_DB_HOST" -Hint "Use postgres for the bundled Compose database."
    Require-EnvValue -Name "APP_DB_PORT" -Hint "Use 5432 for the bundled Compose database."
    Require-EnvValue -Name "APP_DB_USER" -Hint "Set the PostgreSQL user."
    Require-EnvValue -Name "APP_DB_PASSWORD" -Hint "Set the PostgreSQL password."
    Require-EnvValue -Name "APP_DB_NAME" -Hint "Set the PostgreSQL database name."

    if (-not [string]::IsNullOrWhiteSpace([string](Get-EnvValue -Name "APP_DATABASE_URL"))) {
        Write-DoctorWarning "APP_DATABASE_URL is not used by the legacy release settings. Configure APP_DB_HOST, APP_DB_PORT, APP_DB_USER, APP_DB_PASSWORD, and APP_DB_NAME instead."
    }

    $hostname = Get-EnvValue -Name "APP_SDWAN_CSP_HOSTNAME"
    $hostIp = Get-EnvValue -Name "APP_SDWAN_CSP_HOST_IP"
    $hasHostname = -not [string]::IsNullOrWhiteSpace([string]$hostname)
    $hasHostIp = -not [string]::IsNullOrWhiteSpace([string]$hostIp)
    if ($hasHostname -and $hasHostIp) {
        Write-DoctorOk "APP_SDWAN_CSP_HOSTNAME/APP_SDWAN_CSP_HOST_IP set; Compose will include docker-compose.csp-hosts.yml ($hostname -> $hostIp)."
    }
    elseif ($hasHostname -or $hasHostIp) {
        Write-DoctorError "Set both APP_SDWAN_CSP_HOSTNAME and APP_SDWAN_CSP_HOST_IP together, or leave both empty for normal DNS."
    }
    else {
        Write-DoctorOk "APP_SDWAN_CSP_HOSTNAME/APP_SDWAN_CSP_HOST_IP are empty; no Compose extra_hosts overlay."
    }
}

Write-Output "[doctor] Result: $errors error(s), $warnings warning(s)."
if ($errors -gt 0) {
    throw "Environment diagnostics failed."
}

# --
