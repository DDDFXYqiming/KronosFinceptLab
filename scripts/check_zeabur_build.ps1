param(
    [switch]$SkipFrontendBuild,
    [switch]$SkipDocker,
    [string]$DockerTag = "kronos-fincept-lab:zeabur-check"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$WebDir = Join-Path $Root "web"
$NextDir = Join-Path $WebDir ".next"
$Dockerfile = Join-Path $Root "Dockerfile"
$PublicDir = Join-Path $WebDir "public"

function Assert-PathExists($Path, $Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label missing: $Path"
    }
}

function Assert-FileContains($Path, $Pattern, $Label) {
    $Text = Get-Content -LiteralPath $Path -Raw
    if ($Text -notmatch $Pattern) {
        throw "$Label not found in $Path"
    }
}

if (-not $SkipFrontendBuild) {
    $ResolvedNext = Resolve-Path -LiteralPath $WebDir
    $Target = Join-Path $ResolvedNext ".next"
    if ((Test-Path -LiteralPath $Target) -and $Target.StartsWith($ResolvedNext.Path)) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }

    Push-Location $WebDir
    try {
        $env:NEXT_IGNORE_INCORRECT_LOCKFILE = "1"
        $env:NEXT_TELEMETRY_DISABLED = "1"
        npm run build:zeabur
    }
    finally {
        Pop-Location
    }
}

Assert-PathExists (Join-Path $NextDir "standalone") "Next standalone output"
Assert-PathExists (Join-Path $NextDir "static") "Next static output"
Assert-PathExists $PublicDir "Web public directory"
Assert-PathExists (Join-Path $PublicDir ".gitkeep") "Tracked public placeholder"

Assert-FileContains $Dockerfile "NEXT_IGNORE_INCORRECT_LOCKFILE=1" "Docker SWC lockfile guard"
Assert-FileContains $Dockerfile "\.next/standalone" "Docker standalone copy"
Assert-FileContains $Dockerfile "web/public" "Docker public copy"
Assert-FileContains $Dockerfile "zeabur_start\.sh" "Docker startup script"

if (-not $SkipDocker) {
    $Docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($null -eq $Docker) {
        throw "Docker CLI not found. Re-run with -SkipDocker for local frontend-only validation."
    }
    Push-Location $Root
    try {
        docker build --target backend -t $DockerTag .
    }
    finally {
        Pop-Location
    }
}

Write-Host "Zeabur build checks passed."
