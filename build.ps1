<#
.SYNOPSIS
    Build the Windows desktop app into dist\PDFTranslate and zip it for release.

.PARAMETER SkipAssets
    Skip downloading the layout model, font, and Tesseract OCR engine. The
    build still works, but the packaged app downloads the model/font on its
    first translation instead of running offline, and OCR mode is unavailable
    until Tesseract is installed separately.
#>
[CmdletBinding()]
param(
    [switch]$SkipAssets
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$output = Join-Path $root "dist\PDFTranslate"

if (-not (Test-Path $python)) {
    throw "No virtual environment found. Run: python -m venv .venv"
}

# A running copy locks its own DLLs, so PyInstaller cannot replace the folder and
# silently produces an incomplete build. Only ever touch the exe from this dist.
$running = Get-Process -Name "PDFTranslate" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($output, [StringComparison]::OrdinalIgnoreCase) }
if ($running) {
    Write-Host "==> Closing the running app that would lock the build output" -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Seconds 2
}

Write-Host "==> Installing app and packaging dependencies" -ForegroundColor Cyan
& $python -m pip install -r (Join-Path $root "requirements-app.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE" }

if (-not $SkipAssets) {
    Write-Host "==> Fetching the layout model and font to bundle" -ForegroundColor Cyan
    & $python (Join-Path $root "scripts\fetch_assets.py")
    if ($LASTEXITCODE -ne 0) { throw "fetch_assets.py failed with exit code $LASTEXITCODE" }
}

# --- Tesseract OCR (pdf2zh/ocr.py) ------------------------------------------
# Not installable via pip: it is a native OCR engine, not a Python package.
# Installed once via Chocolatey (preinstalled on GitHub-hosted Windows
# runners) so app.spec can bundle it and OCR mode works with no separate
# install on the end user's machine. The Chocolatey package ships English
# only, so Vietnamese is fetched separately into the same tessdata folder.
$tesseractDir = Join-Path ${env:ProgramFiles} "Tesseract-OCR"
$tesseractExe = Join-Path $tesseractDir "tesseract.exe"
if (-not $SkipAssets) {
    if (-not (Test-Path $tesseractExe)) {
        Write-Host "==> Installing Tesseract OCR (choco)" -ForegroundColor Cyan
        choco install tesseract -y
        if ($LASTEXITCODE -ne 0) {
            Write-Host "choco install tesseract failed (exit $LASTEXITCODE); OCR mode will not be bundled." -ForegroundColor Yellow
        }
    }
    $vieData = Join-Path $tesseractDir "tessdata\vie.traineddata"
    if ((Test-Path $tesseractExe) -and -not (Test-Path $vieData)) {
        Write-Host "==> Fetching Vietnamese Tesseract language data" -ForegroundColor Cyan
        Invoke-WebRequest -Uri "https://github.com/tesseract-ocr/tessdata_fast/raw/main/vie.traineddata" -OutFile $vieData
    }
}

Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean (Join-Path $root "app.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

if (-not (Test-Path $output)) {
    throw "PyInstaller did not produce $output"
}

# PyInstaller can fail partway through COLLECT and still leave a folder behind, so
# check the payload rather than trusting that the folder exists. pdf2zh and scripts
# are not listed: they are frozen into the PYZ archive, not shipped as folders.
$required = @(
    "PDFTranslate.exe",
    "_internal\base_library.zip",
    "_internal\app\fonts\BeVietnamPro-Regular.ttf",
    "_internal\app\assets\icon.png",
    "_internal\customtkinter",
    "_internal\tkinterdnd2",
    "_internal\cv2",
    "_internal\onnxruntime",
    "_internal\pymupdf"
)
if (-not $SkipAssets -or (Test-Path (Join-Path $root "app\assets\doclayout.onnx"))) {
    $required += "_internal\app\assets\doclayout.onnx"
    $required += "_internal\app\assets\GoNotoKurrent-Regular.ttf"
}
if (Test-Path $tesseractExe) {
    $required += "_internal\tesseract\tesseract.exe"
    $required += "_internal\tesseract\tessdata\eng.traineddata"
}
$missing = $required | Where-Object { -not (Test-Path (Join-Path $output $_)) }
if ($missing) {
    throw "Incomplete build, refusing to package. Missing:`n  " + ($missing -join "`n  ")
}

$archive = Join-Path $root "dist\PDFTranslate-windows.zip"
Write-Host "==> Zipping to $archive" -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $output "*") -DestinationPath $archive -Force

$size = (Get-ChildItem $output -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("==> Done. Folder {0:N0} MB, archive {1:N0} MB" -f $size, ((Get-Item $archive).Length / 1MB)) -ForegroundColor Green
Write-Host "Test on a machine with no Python before publishing." -ForegroundColor Yellow
