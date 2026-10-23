param(
    [string]$Python = ".\.venv-windows\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dist = Join-Path $project "dist\windows"
$work = Join-Path $project "build\windows"

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
    throw "Build the Windows executables with Windows Python, not Linux or WSL Python."
}

Push-Location $project
try {
    & $Python -c "import sys; assert sys.platform == 'win32', 'Use Windows Python'"
    if ($LASTEXITCODE -ne 0) { throw "Windows Python is required." }

    $common = @(
        "--noconfirm", "--clean", "--onedir",
        "--distpath", $dist,
        "--workpath", $work,
        "--specpath", (Join-Path $work "spec")
    )
    $web = @("--collect-all", "dash", "--collect-all", "plotly")

    & $Python -m PyInstaller @common @web `
        --name Heroes3Dashboard `
        --hidden-import read_save --hidden-import dashboard `
        --add-data "${project}\creature_ai_values.json:." `
        --add-data "${project}\unit_stats.json:." `
        --add-data "${project}\assets:assets" `
        launcher.py
    if ($LASTEXITCODE -ne 0) { throw "Dashboard build failed." }

    & $Python -m PyInstaller @common `
        --name Heroes3SwapHeroes `
        --hidden-import swap_hero `
        swap_hero_gui.py
    if ($LASTEXITCODE -ne 0) { throw "Hero transfer build failed." }
    Copy-Item -LiteralPath (Join-Path $project "arena.GM4") `
        -Destination (Join-Path $dist "Heroes3SwapHeroes\arena.GM4") -Force

    & $Python -m PyInstaller @common @web `
        --name Heroes3MapHelper `
        --hidden-import map_helper_app `
        map_helper_desktop.py
    if ($LASTEXITCODE -ne 0) { throw "Map Helper build failed." }

    Write-Host "Built three Windows apps in $dist"
    Write-Host "Copy each whole app folder, including _internal, to a writable location."
} finally {
    Pop-Location
}
