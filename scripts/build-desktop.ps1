$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$TargetTriple = "x86_64-pc-windows-msvc"
$SidecarTarget = Join-Path $FrontendRoot "src-tauri\binaries\pansy-server-$TargetTriple.exe"
$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
$TauriConfig = Get-Content (Join-Path $FrontendRoot "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json
# A running development build keeps target\release\pansy-server.exe open on Windows.
# Keep each packaged version in its own Cargo target so an older build cannot block an update.
$CargoTargetDir = Join-Path $FrontendRoot "src-tauri\target\desktop-$($TauriConfig.version)"

if (Test-Path $CargoBin) {
    $env:Path = "$CargoBin;$env:Path"
}

if (-not (Test-Path $Python)) {
    throw "Project virtual environment not found: $Python"
}

Push-Location $FrontendRoot
try {
    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Vue frontend build failed (exit code $LASTEXITCODE)"
    }
} finally {
    Pop-Location
}

& $Python -m PyInstaller --noconfirm --clean `
    --distpath (Join-Path $ProjectRoot "desktop\build\dist") `
    --workpath (Join-Path $ProjectRoot "desktop\build\work") `
    (Join-Path $ProjectRoot "desktop\pansy-server.spec")
if ($LASTEXITCODE -ne 0) {
    throw "Python sidecar build failed (exit code $LASTEXITCODE)"
}

New-Item -ItemType Directory -Force (Split-Path -Parent $SidecarTarget) | Out-Null
Copy-Item -Force (Join-Path $ProjectRoot "desktop\build\dist\pansy-server.exe") $SidecarTarget

Push-Location $FrontendRoot
try {
    $PreviousCargoTargetDir = $env:CARGO_TARGET_DIR
    $env:CARGO_TARGET_DIR = $CargoTargetDir
    # Tauri downloads NSIS tooling on the first build. A transient global timeout
    # should not invalidate the completed frontend and sidecar builds, so retry here.
    $MaxAttempts = 3
    for ($Attempt = 1; $Attempt -le $MaxAttempts; $Attempt++) {
        npm run tauri build
        if ($LASTEXITCODE -eq 0) {
            break
        }
        if ($Attempt -eq $MaxAttempts) {
            throw "Tauri/NSIS build failed $MaxAttempts times (last exit code $LASTEXITCODE)"
        }
        Write-Warning "Tauri/NSIS build failed; retrying in 5 seconds ($Attempt/$MaxAttempts)..."
        Start-Sleep -Seconds 5
    }
} finally {
    if ($null -eq $PreviousCargoTargetDir) {
        Remove-Item Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue
    } else {
        $env:CARGO_TARGET_DIR = $PreviousCargoTargetDir
    }
    Pop-Location
}
