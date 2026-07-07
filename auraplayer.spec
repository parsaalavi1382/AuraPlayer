# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# Resolve absolute path to project directory
project_dir = os.path.abspath(os.path.dirname(__file__) if '__file__' in locals() else os.getcwd())

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=[
        # Include all SVG icons and PNG logo assets from the assets directory
        (os.path.join(project_dir, 'assets'), 'assets'),
    ],
    hiddenimports=[
        # Ensure mutagen and QtSvg are bundled correctly
        'mutagen',
        'mutagen.mp3',
        'mutagen.easyid3',
        'mutagen.easymp4',
        'mutagen.asf',
        'mutagen.flac',
        'mutagen.ogg',
        'mutagen.oggvorbis',
        'mutagen.oggopus',
        'mutagen.wave',
        'PyQt6.QtSvg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'email', 'xml', 'pydoc'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out common Windows system DLLs that should always be loaded from the host OS (resolves Ordinal 380/comctl32.dll crash)
excluded_binaries = {
    'comctl32.dll',
    'shell32.dll',
    'shlwapi.dll',
    'user32.dll',
    'kernel32.dll',
    'gdi32.dll',
    'msvcrt.dll',
    'ole32.dll',
    'advapi32.dll',
    'ws2_32.dll'
}
a.binaries = [x for x in a.binaries if os.path.basename(x[0]).lower() not in excluded_binaries]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Dynamically switch the icon path based on the compilation platform
ico_path = os.path.join(project_dir, 'assets', 'logo.ico')
icns_path = os.path.join(project_dir, 'assets', 'logo.icns')
png_path = os.path.join(project_dir, 'assets', 'logo.png')

icon_path = png_path
if sys.platform == 'win32' and os.path.exists(ico_path):
    icon_path = ico_path
elif sys.platform == 'darwin' and os.path.exists(icns_path):
    icon_path = icns_path

# Standard setup for a Single-Folder Distribution (Highly recommended for PyQt apps for fast startup)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AuraPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to False to hide the terminal window on launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AuraPlayer',
)
