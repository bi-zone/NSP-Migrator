### Firewall Policies Migrator - Windows command runner
#
# This is the Windows analogue of the root Makefile. It keeps the public target
# names and option names aligned with Makefile variables while using PowerShell
# syntax: .\win\migrator-commands.ps1 up -MODE prod -NO_CHECK 1.

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = "help",

    [ValidateSet("local", "prod")]
    [string]$MODE = "local",

    [ValidateNotNullOrEmpty()]
    [string]$SERVICE = "streamlit",

    [ValidateNotNullOrEmpty()]
    [string[]]$SERVICES = @("streamlit"),

    [ValidateSet(0, 1)]
    [int]$ASSUME_YES = 0,

    [ValidateSet(0, 1)]
    [int]$NO_CHECK = 0,

    [ValidateNotNullOrEmpty()]
    [string]$TEST_PATH = "tests",

    [string[]]$PYTEST_ARGS = @(),

    [string]$MSG = "",

    [ValidateRange(1, 2147483647)]
    [int]$DOWN = 1,

    [string]$REV = "head",

    [ValidateSet(0, 1)]
    [int]$CONFIRM = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"


### Shared script state

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvironmentFile = Join-Path $ProjectRoot ".env"
$DoctorScript = Join-Path $PSScriptRoot "doctor.ps1"
$script:ExitCode = 0

function Set-MigratorFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [int]$Code = 1
    )

    if ($script:ExitCode -eq 0) {
        $script:ExitCode = $Code
    }
    Write-Error -ErrorAction Continue -Message "[migrator] ERROR: $Message"
}

function Test-MigratorSucceeded {
    return $script:ExitCode -eq 0
}

function Require-DestructiveConfirmation {
    param([Parameter(Mandatory = $true)][string]$Operation)

    if ($CONFIRM -eq 1) {
        return $true
    }

    Set-MigratorFailure -Code 2 -Message "Refusing '$Operation' without CONFIRM=1."
    return $false
}


### Environment file and Compose configuration

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Environment file '$Path' was not found. Run 'env-init' first."
    }

    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        $separator = $line.IndexOf("=")
        if ($separator -lt 1 -or $line.Substring(0, $separator).Trim() -ne $Name) {
            continue
        }

        # Values are parsed as data only: no expansion and no logging of secrets.
        $value = $line.Substring($separator + 1).Trim()
        if ($value.Length -ge 2) {
            $first = $value[0]
            $last = $value[$value.Length - 1]
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                return $value.Substring(1, $value.Length - 2)
            }
        }
        return $value
    }

    return $null
}

function Initialize-EnvironmentFile {
    $template = Join-Path $ProjectRoot ".env.example"

    if (Test-Path -LiteralPath $EnvironmentFile) {
        if (-not (Test-Path -LiteralPath $EnvironmentFile -PathType Leaf)) {
            throw "Environment path '$EnvironmentFile' exists but is not a file."
        }
        Write-Output "[env-init] .env already exists; leaving it unchanged."
        return
    }

    if (-not (Test-Path -LiteralPath $template -PathType Leaf)) {
        throw "Environment template '$template' was not found."
    }

    Copy-Item -LiteralPath $template -Destination $EnvironmentFile -ErrorAction Stop
    Write-Output "[env-init] Created .env from .env.example."
}

function Get-ComposeConfiguration {
    $files = [System.Collections.Generic.List[string]]::new()
    $files.Add((Join-Path $ProjectRoot "docker-compose.yml"))

    if ($MODE -eq "local") {
        $files.Add((Join-Path $ProjectRoot "docker-compose.local.yml"))
    }

    $hostname = Get-EnvValue -Path $EnvironmentFile -Name "APP_SDWAN_CSP_HOSTNAME"
    $hostIp = Get-EnvValue -Path $EnvironmentFile -Name "APP_SDWAN_CSP_HOST_IP"
    $hasHostname = -not [string]::IsNullOrWhiteSpace([string]$hostname)
    $hasHostIp = -not [string]::IsNullOrWhiteSpace([string]$hostIp)
    if ($hasHostname -xor $hasHostIp) {
        throw "APP_SDWAN_CSP_HOSTNAME and APP_SDWAN_CSP_HOST_IP must both be set or both be empty."
    }
    if ($hasHostname) {
        $files.Add((Join-Path $ProjectRoot "docker-compose.csp-hosts.yml"))
    }

    foreach ($file in $files) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Required Compose file '$file' was not found."
        }
    }

    return [pscustomobject]@{
        EnvironmentFile = $EnvironmentFile
        ComposeFiles = $files.ToArray()
        CspHostsOverlayEnabled = $hasHostname
    }
}

function Get-ComposeArguments {
    param([Parameter(Mandatory = $true)][pscustomobject]$Configuration)

    $arguments = [System.Collections.Generic.List[string]]::new()
    $arguments.Add("compose")
    $arguments.Add("--project-directory")
    $arguments.Add($ProjectRoot)
    $arguments.Add("--env-file")
    $arguments.Add($Configuration.EnvironmentFile)
    foreach ($file in $Configuration.ComposeFiles) {
        $arguments.Add("-f")
        $arguments.Add($file)
    }
    return $arguments.ToArray()
}

function Get-ToolsComposeArguments {
    $toolsFile = Join-Path $ProjectRoot "docker-compose.tools.yml"
    if (-not (Test-Path -LiteralPath $EnvironmentFile -PathType Leaf)) {
        throw "Environment file '$EnvironmentFile' was not found. Run 'env-init' first."
    }
    if (-not (Test-Path -LiteralPath $toolsFile -PathType Leaf)) {
        throw "Tools Compose file '$toolsFile' was not found."
    }
    return @("compose", "--project-directory", $ProjectRoot, "--env-file", $EnvironmentFile, "-f", $toolsFile)
}

function Get-ComposeConfigurationForCommand {
    try {
        return Get-ComposeConfiguration
    }
    catch {
        Set-MigratorFailure -Message $_.Exception.Message
        return $null
    }
}


### Docker invocation

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)][pscustomobject]$Configuration,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
        Set-MigratorFailure -Message "Docker CLI is unavailable. Run 'doctor' for details."
        return
    }

    $dockerArguments = Get-ComposeArguments -Configuration $Configuration
    $dockerArguments += $Arguments
    & docker @dockerArguments
    $nativeExitCode = $LASTEXITCODE
    if ($nativeExitCode -ne 0) {
        Set-MigratorFailure -Code $nativeExitCode -Message "Docker Compose command failed with exit code $nativeExitCode."
    }
}

function Invoke-ToolsCompose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
        Set-MigratorFailure -Message "Docker CLI is unavailable. Run 'doctor' for details."
        return
    }

    try {
        $dockerArguments = Get-ToolsComposeArguments
    }
    catch {
        Set-MigratorFailure -Message $_.Exception.Message
        return
    }
    $dockerArguments += $Arguments
    & docker @dockerArguments
    $nativeExitCode = $LASTEXITCODE
    if ($nativeExitCode -ne 0) {
        Set-MigratorFailure -Code $nativeExitCode -Message "Docker Compose tools command failed with exit code $nativeExitCode."
    }
}

function Get-ServiceUrl {
    param(
        [Parameter(Mandatory = $true)][pscustomobject]$Configuration,
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][int]$ContainerPort,
        [string]$Profile = ""
    )

    if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
        Set-MigratorFailure -Message "Docker CLI is unavailable. Run 'doctor' for details."
        return $null
    }

    $arguments = Get-ComposeArguments -Configuration $Configuration
    if ($Profile) {
        $arguments += @("--profile", $Profile)
    }
    $arguments += @("port", $Service, [string]$ContainerPort)
    $ports = @(& docker @arguments 2>$null)
    if ($LASTEXITCODE -ne 0) {
        Set-MigratorFailure -Code $LASTEXITCODE -Message "Unable to determine the host port for '$Service'."
        return $null
    }

    $portLine = $ports | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1
    $match = if ($null -ne $portLine) { [regex]::Match($portLine.Trim(), ":(?<port>\d+)$") } else { $null }
    if ($null -eq $match -or -not $match.Success) {
        Set-MigratorFailure -Message "Docker did not return a supported port mapping for '$Service'."
        return $null
    }
    return "http://localhost:$($match.Groups["port"].Value)"
}

function Invoke-EnsureDocker {
    Write-Output "[ensure-docker] Ensure-docker operation not implemented for Windows environment."
}

function Invoke-Doctor {
    try { & $DoctorScript $EnvironmentFile }
    catch { Set-MigratorFailure -Message $_.Exception.Message }
}

function Invoke-Setup {
    Initialize-EnvironmentFile
    if ($NO_CHECK -eq 1) {
        Write-Output "[setup] NO_CHECK=1: skipping ensure-docker and doctor."
        return
    }
    Invoke-EnsureDocker
    if (Test-MigratorSucceeded) {
        Invoke-Doctor
    }
}


### Database migrations

function Invoke-Alembic {
    param(
        [Parameter(Mandatory = $true)][pscustomobject]$Configuration,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    Invoke-Compose -Configuration $Configuration -Arguments (@("run", "--rm", "streamlit", "alembic") + $Arguments)
}

function Invoke-Migrate {
    $configuration = Get-ComposeConfigurationForCommand
    if ($null -ne $configuration) {
        Invoke-Alembic -Configuration $configuration -Arguments @("upgrade", "head")
    }
}

function Invoke-MigrationRevision {
    param([switch]$Autogenerate)

    if ([string]::IsNullOrWhiteSpace($MSG)) {
        Set-MigratorFailure -Code 2 -Message "MSG is required for migration revision creation."
        return
    }
    $configuration = Get-ComposeConfigurationForCommand
    if ($null -eq $configuration) {
        return
    }
    $arguments = @("revision")
    if ($Autogenerate) { $arguments += "--autogenerate" }
    $arguments += @("-m", $MSG.Trim())
    Invoke-Alembic -Configuration $configuration -Arguments $arguments
}


### Lifecycle helpers

function Start-StreamlitStack {
    Invoke-Setup
    if (-not (Test-MigratorSucceeded)) { return }
    $configuration = Get-ComposeConfigurationForCommand
    if ($null -eq $configuration) { return }

    Write-Output "[up] 1/5 Building Streamlit image..."
    Invoke-Compose -Configuration $configuration -Arguments @("build", "streamlit")
    if (-not (Test-MigratorSucceeded)) { return }
    Write-Output "[up] 2/5 Starting PostgreSQL..."
    Invoke-Compose -Configuration $configuration -Arguments @("up", "-d", "--wait", "--remove-orphans", "postgres")
    if (-not (Test-MigratorSucceeded)) { return }
    Write-Output "[up] 3/5 Applying database migrations..."
    Invoke-Alembic -Configuration $configuration -Arguments @("upgrade", "head")
    if (-not (Test-MigratorSucceeded)) { return }
    Write-Output "[up] 4/5 Starting Streamlit..."
    Invoke-Compose -Configuration $configuration -Arguments @("up", "-d", "--wait", "--remove-orphans", "streamlit")
    if (-not (Test-MigratorSucceeded)) { return }
    $url = Get-ServiceUrl -Configuration $configuration -Service "streamlit" -ContainerPort 8501
    if ($null -ne $url) { Write-Output "[up] Streamlit is ready: $url" }
}

function Start-ApiStack {
    Invoke-Setup
    if (-not (Test-MigratorSucceeded)) { return }
    $configuration = Get-ComposeConfigurationForCommand
    if ($null -eq $configuration) { return }

    Invoke-Compose -Configuration $configuration -Arguments @("--profile", "api", "build", "app")
    if (-not (Test-MigratorSucceeded)) { return }
    Invoke-Compose -Configuration $configuration -Arguments @("up", "-d", "--wait", "--remove-orphans", "postgres")
    if (-not (Test-MigratorSucceeded)) { return }
    Invoke-Alembic -Configuration $configuration -Arguments @("upgrade", "head")
    if (-not (Test-MigratorSucceeded)) { return }
    Invoke-Compose -Configuration $configuration -Arguments @("--profile", "api", "up", "-d", "--wait", "--remove-orphans", "app")
    if (-not (Test-MigratorSucceeded)) { return }
    $url = Get-ServiceUrl -Configuration $configuration -Service "app" -ContainerPort 8000 -Profile "api"
    if ($null -ne $url) { Write-Output "[api-up] FastAPI is ready: $url" }
}

function Open-Streamlit {
    $configuration = Get-ComposeConfigurationForCommand
    if ($null -eq $configuration) { return }
    $url = Get-ServiceUrl -Configuration $configuration -Service "streamlit" -ContainerPort 8501
    if ($null -eq $url) { return }
    Write-Output $url
    try { Start-Process -FilePath $url -ErrorAction Stop }
    catch { Set-MigratorFailure -Message "Unable to open '$url' in the default browser." }
}


### Help and command dispatch

function Show-Help {
    Write-Output "Firewall Policies Migrator - Windows commands"
    ""
    "Usage: .\win\migrator-commands.ps1 COMMAND [-MODE local|prod] [-SERVICE name] [-SERVICES name,...]"
    ""
    "Getting started:"
    "   help, env-init, ensure-docker, doctor, setup"
    "Local stack:"
    "   up, down, ps, logs, shell, open, api-up, api-down"
    "Prod-like:"
    "   prod-up, prod-down"
    "Runtime:"
    "   build, restart, rebuild, config, image-size, smoke"
    "Quality:"
    "   tools-build, format, format-check, lint, typecheck, test, check"
    "Migrations:"
    "   migrate, migrate-current, migrate-history, migrate-down, migrate-create, migrate-autogenerate, migrate-stamp, db-reset"
    ""
    "Options mirror Makefile variables:"
    "   MODE, SERVICE, SERVICES, ASSUME_YES, NO_CHECK, TEST_PATH, PYTEST_ARGS, MSG, DOWN, REV, CONFIRM."
}

switch ($Command) {
    "help" { Show-Help }
    "env-init" { Initialize-EnvironmentFile }
    "ensure-docker" { Invoke-EnsureDocker }
    "doctor" { Invoke-Doctor }
    "setup" { Invoke-Setup }

    "up" { Start-StreamlitStack }
    "down" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments @("down") }
    }
    "ps" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments @("ps") }
    }
    "logs" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments @("logs", "--tail=200", "-f", $SERVICE) }
    }
    "shell" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments @("exec", $SERVICE, "sh") }
    }
    "open" { Open-Streamlit }
    "api-up" { Start-ApiStack }
    "api-down" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments @("--profile", "api", "stop", "app") }
    }
    "prod-up" { $MODE = "prod"; Start-StreamlitStack }
    "prod-down" {
        $MODE = "prod"
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments @("down") }
    }

    "build" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments (@("build") + $SERVICES) }
    }
    "restart" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments (@("restart") + $SERVICES) }
    }
    "rebuild" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) {
            Invoke-Compose -Configuration $configuration -Arguments (@("build") + $SERVICES)
            if (Test-MigratorSucceeded) { Invoke-Compose -Configuration $configuration -Arguments (@("up", "-d", "--force-recreate") + $SERVICES) }
        }
    }
    "config" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Compose -Configuration $configuration -Arguments @("config") }
    }
    "image-size" {
        if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
            Set-MigratorFailure -Message "Docker CLI is unavailable."
        }
        else {
            Write-Output ("{0,-42} {1,-10} {2}" -f "IMAGE", "SIZE", "IMAGE ID")
            foreach ($image in @("policy-migrator-streamlit:runtime", "policy-migrator-streamlit:dev", "policy-migrator-api:runtime", "policy-migrator-api:dev")) {
                & docker image inspect $image 1>$null 2>$null
                if ($LASTEXITCODE -eq 0) { & docker image ls --format "{{.Repository}}:{{.Tag}}`t{{.Size}}`t{{.ID}}" $image }
                else { Write-Output ("{0,-42} {1}" -f $image, "not built") }
            }
        }
    }
    "smoke" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) {
            Invoke-Compose -Configuration $configuration -Arguments @("exec", "-T", "postgres", "sh", "-ec", 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"')
            if (Test-MigratorSucceeded) {
                $url = Get-ServiceUrl -Configuration $configuration -Service "streamlit" -ContainerPort 8501
                if ($null -ne $url) {
                    try { [void](Invoke-WebRequest -UseBasicParsing -Uri "$url/_stcore/health") }
                    catch { Set-MigratorFailure -Message "Streamlit health check failed at '$url/_stcore/health'." }
                    if (Test-MigratorSucceeded) { Write-Output "Smoke checks passed (postgres + streamlit)." }
                }
            }
        }
    }

    "tools-build" { Invoke-ToolsCompose -Arguments @("build", "tools") }
    "format" { Invoke-ToolsCompose -Arguments @("build", "tools"); if (Test-MigratorSucceeded) { Invoke-ToolsCompose -Arguments @("run", "--rm", "tools", "ruff", "format", "src", "tests") } }
    "format-check" { Invoke-ToolsCompose -Arguments @("build", "tools"); if (Test-MigratorSucceeded) { Invoke-ToolsCompose -Arguments @("run", "--rm", "tools", "ruff", "format", "--check", "src", "tests") } }
    "lint" { Invoke-ToolsCompose -Arguments @("build", "tools"); if (Test-MigratorSucceeded) { Invoke-ToolsCompose -Arguments @("run", "--rm", "tools", "ruff", "check", ".") } }
    "typecheck" { Invoke-ToolsCompose -Arguments @("build", "tools"); if (Test-MigratorSucceeded) { Invoke-ToolsCompose -Arguments @("run", "--rm", "tools", "mypy", ".") } }
    "test" { Invoke-ToolsCompose -Arguments @("build", "tools"); if (Test-MigratorSucceeded) { Invoke-ToolsCompose -Arguments (@("run", "--rm", "tools", "pytest") + $PYTEST_ARGS + @($TEST_PATH)) } }
    "check" {
        Invoke-ToolsCompose -Arguments @("build", "tools")
        $checks = @(
            [pscustomobject]@{ Arguments = @("ruff", "check", ".") },
            [pscustomobject]@{ Arguments = @("ruff", "format", "--check", "src", "tests") },
            [pscustomobject]@{ Arguments = @("mypy", ".") },
            [pscustomobject]@{ Arguments = (@("pytest") + $PYTEST_ARGS + @($TEST_PATH)) }
        )
        foreach ($check in $checks) {
            if (-not (Test-MigratorSucceeded)) { break }
            Invoke-ToolsCompose -Arguments (@("run", "--rm", "tools") + $check.Arguments)
        }
    }

    "migrate" { Invoke-Migrate }
    "migrate-current" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Alembic -Configuration $configuration -Arguments @("current") }
    }
    "migrate-history" {
        $configuration = Get-ComposeConfigurationForCommand
        if ($null -ne $configuration) { Invoke-Alembic -Configuration $configuration -Arguments @("history") }
    }
    "migrate-create" { Invoke-MigrationRevision }
    "migrate-autogenerate" { Invoke-MigrationRevision -Autogenerate }
    "migrate-down" {
        if (Require-DestructiveConfirmation -Operation "migrate-down") {
            $configuration = Get-ComposeConfigurationForCommand
            if ($null -ne $configuration) { Invoke-Alembic -Configuration $configuration -Arguments @("downgrade", "-$DOWN") }
        }
    }
    "migrate-stamp" {
        if (Require-DestructiveConfirmation -Operation "migrate-stamp") {
            if ([string]::IsNullOrWhiteSpace($REV)) { Set-MigratorFailure -Code 2 -Message "REV must not be empty." }
            else {
                $configuration = Get-ComposeConfigurationForCommand
                if ($null -ne $configuration) { Invoke-Alembic -Configuration $configuration -Arguments @("stamp", $REV.Trim()) }
            }
        }
    }
    "db-reset" {
        if (Require-DestructiveConfirmation -Operation "db-reset") {
            $configuration = Get-ComposeConfigurationForCommand
            if ($null -ne $configuration) {
                Invoke-Compose -Configuration $configuration -Arguments @("down", "-v")
                if (Test-MigratorSucceeded) { Start-StreamlitStack }
            }
        }
    }
    default { Set-MigratorFailure -Code 2 -Message "Unknown command '$Command'. Run '.\win\migrator-commands.ps1 help'." }
}

exit $script:ExitCode
