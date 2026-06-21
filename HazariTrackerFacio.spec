# ─────────────────────────────────────────────────────────────────────────────
# PyInstaller spec — builds a one-folder Windows EXE (64-bit Python).
#
# Build command:
#   python -m PyInstaller HazariTrackerFacio.spec --clean
# ─────────────────────────────────────────────────────────────────────────────

import os, sys
from version import VERSION, APP_NAME

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("pages",   "pages"),
        ("version.py", "."),
        ("icon.png", "."),
        ("icon.ico", "."),
    ] + collect_data_files("face_recognition_models"),
    hiddenimports=[
        "face_recognition",
        "cv2",
        "numpy",
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        "sqlite3",
        "csv",
        "threading",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "urllib.request",
        "urllib.parse",
        "urllib.error",
        "json",
        "base64",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=f"HazariTrackerFacio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # Disable system black console window
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=f"HazariTrackerFacio-v{VERSION}",
)
