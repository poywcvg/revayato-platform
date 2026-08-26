# build-webview-apk.ps1 — build the official روایتو Android app into a signed APK
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File tools/build-webview-apk.ps1
#
# Options via env:
#   $env:APP_OUTPUT   output file name (placed in android-app/dist/)
#   $env:GRADLE_ARGS  extra gradle args (e.g. "--stacktrace")
#
# Output: android-app/dist/<APP_OUTPUT>

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$appDir = Join-Path $root 'android-app'

$JAVA_HOME = [System.Environment]::GetEnvironmentVariable('JAVA_HOME', 'Machine')
if (-not $JAVA_HOME) { $JAVA_HOME = [System.Environment]::GetEnvironmentVariable('JAVA_HOME', 'User') }
if (-not $JAVA_HOME -or -not (Test-Path (Join-Path $JAVA_HOME 'bin\java.exe'))) {
    Write-Error 'JAVA_HOME is not set to a JDK 17+.'
}
$env:JAVA_HOME = $JAVA_HOME

# SDK pin is project-local (android-app/local.properties → sdk.dir=C:\Android).
$localProps = Join-Path $appDir 'local.properties'
if (-not (Test-Path $localProps)) {
    Write-Error 'missing android-app/local.properties (sdk.dir=<sdk path>)'
}

Write-Host "== building release APK ==" -ForegroundColor Cyan
Push-Location $appDir
try {
    .\gradlew.bat :app:assembleRelease --no-daemon $env:GRADLE_ARGS
    if ($LASTEXITCODE -ne 0) { throw "gradlew failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$apk = Join-Path $appDir 'app\build\outputs\apk\release\app-release.apk'
if (-not (Test-Path $apk)) {
    Write-Error "expected APK not found: $apk"
}

$outName = if ($env:APP_OUTPUT) { $env:APP_OUTPUT } else { 'revayato-android-v2.0.0.apk' }
$dist = Join-Path $appDir 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$out = Join-Path $dist $outName
Copy-Item -Force $apk $out

# Verify signing (same debug key as the shipped android-app APKs).
$apksigner = Join-Path $env:LOCALAPPDATA '..\..\Android\build-tools\35.0.0\apksigner.bat'
if (Test-Path $apksigner) {
    & $apksigner verify --print-certs $out
} else {
    Write-Host 'apksigner not found at expected path; skipping verify' -ForegroundColor Yellow
}

Write-Host "`nBuilt: $out" -ForegroundColor Green
