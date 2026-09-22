<#
.SYNOPSIS
    Build the Windows desktop app into dist\PDFTranslate and zip it for release.

.PARAMETER SkipAssets
    Skip downloading the layout model, font, and Tesseract OCR engine. Use
    this on a machine without Chocolatey/admin rights, or to build faster
    when testing something unrelated to those assets: the app still builds
    and runs, it just downloads the model/font on first use instead of
    running offline, and OCR mode is unavailable until Tesseract is
    installed separately. Without this flag, a failure to install any of
    them stops the build rather than shipping an incomplete one silently.
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

# requirements.txt lists pytesseract, but "pip install" can exit 0 while still
# leaving an individual package unresolved (a resolver skip, a transient
# index error for that one package). That would silently ship a build where
# OCR mode is unusable, with nothing in the log to say so -- so this is
# checked explicitly and turned into a hard failure instead.
& $python -c "import pytesseract" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "pytesseract did not install correctly (pip install exited 0, but 'import pytesseract' failed). OCR mode needs this; check the pip install output above for a skipped or failed package."
}

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
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tesseractExe)) {
            throw "choco install tesseract did not produce $tesseractExe (choco exit code $LASTEXITCODE). Run with -SkipAssets to build without OCR bundled instead of failing here."
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

# pytesseract is a simple pure-Python package with no data files of its own,
# so PyInstaller freezes it straight into the PYZ archive embedded inside
# the exe -- the same reason pdf2zh's own modules aren't in the list above
# as folders either. A Test-Path check for _internal\pytesseract would
# therefore report it missing even on a build where it bundled correctly,
# so this greps the exe's bytes for the module name instead, the same way
# it was confirmed present by hand while diagnosing the original bug.
$exePath = Join-Path $output "PDFTranslate.exe"
& findstr /M /C:"pytesseract" $exePath | Out-Null
if ($LASTEXITCODE -ne 0) {
    $missing += "pytesseract (not found inside PDFTranslate.exe -- see app.spec hiddenimports)"
}

if ($missing) {
    throw "Incomplete build, refusing to package. Missing:`n  " + ($missing -join "`n  ")
}

$archive = Join-Path $root "dist\PDFTranslate-windows.zip"
Write-Host "==> Zipping to $archive" -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $output "*") -DestinationPath $archive -Force

$size = (Get-ChildItem $output -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("==> Done. Folder {0:N0} MB, archive {1:N0} MB" -f $size, ((Get-Item $archive).Length / 1MB)) -ForegroundColor Green
Write-Host "Test on a machine with no Python before publishing." -ForegroundColor Yellow
