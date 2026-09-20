# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows desktop app.

One-folder, deliberately not --onefile: onnxruntime, opencv, and PyMuPDF push
the bundle past 400 MB, and onefile re-extracts all of that to a temp directory
on every launch, which is slow and trips antivirus heuristics.
"""

from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH)

datas = []
for optional in ("app/fonts", "app/assets"):
    directory = ROOT / optional
    if not directory.is_dir():
        continue
    for item in sorted(directory.iterdir()):
        # onnxruntime caches a hardware-specific optimised graph next to the
        # model. It is 75 MB, and it is only valid on the machine that built it.
        if item.is_file() and item.suffix != ".optimized":
            datas.append((str(item), optional))

datas += collect_data_files("customtkinter")
datas += collect_data_files("tkinterdnd2")
datas += collect_data_files("babeldoc")

tree_datas = []
# Tesseract OCR (pdf2zh/ocr.py): bundle the native binary, its DLLs, and its
# tessdata language files so OCR mode works with no separate install on the
# end user's machine. build.ps1 installs it to this well-known location via
# Chocolatey before PyInstaller runs; a local dev build without it simply
# ships without OCR bundled; app/gui.py's locate_tesseract() then falls back
# to a system install if the user has one.
tesseract_dir = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR"
if tesseract_dir.is_dir():
    tree_datas.append(Tree(str(tesseract_dir), prefix="tesseract"))

hiddenimports = [
    "peewee",
    "pdf2zh.doclayout",  # reached through importlib.import_module, not a static import
    "pdf2zh.high_level",
    "pdf2zh.converter",
    "pdf2zh.translator",
    # pdf2zh/ocr.py imports this lazily, inside a function, guarded by
    # try/except -- PyInstaller's static analysis is not always reliable at
    # following that pattern, so it is named explicitly rather than trusted
    # to be found on its own.
    "pytesseract",
    # Reached only through pdf2zh.high_level; naming them keeps the compiled
    # extension and its vendored qpdf in the bundle even if that trail changes.
    "pikepdf",
    "pikepdf._core",
]

analysis = Analysis(
    [str(ROOT / "app" / "gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "app" / "runtime_hook_dlls.py")],
    excludes=[
        "matplotlib",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "IPython",
        "pytest",
        "scipy",
        "pandas",
        # Model-optimisation trees pulled in with onnxruntime. Inference never
        # touches them, and they drag in torch and transformers references.
        "onnxruntime.transformers",
        "onnxruntime.tools",
        "onnxruntime.quantization",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="PDFTranslate",
    icon=str(ROOT / "app" / "assets" / "icon.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    *tree_datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PDFTranslate",
)
