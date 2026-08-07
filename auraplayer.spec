# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

rlottie_datas = collect_data_files('rlottie_python')
rlottie_binaries = collect_dynamic_libs('rlottie_python')
qtawesome_datas = collect_data_files('qtawesome')

winrt_datas = collect_data_files('winrt') if sys.platform == 'win32' else []
winrt_binaries = collect_dynamic_libs('winrt') if sys.platform == 'win32' else []
winrt_submodules = collect_submodules('winrt') if sys.platform == 'win32' else []

# Resolve absolute path to project directory
project_dir = os.path.abspath(os.path.dirname(__file__) if '__file__' in locals() else os.getcwd())

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=rlottie_binaries + winrt_binaries,
    datas=[
        # Include all SVG icons and PNG logo assets from the assets directory
        (os.path.join(project_dir, 'assets'), 'assets'),
    ] + rlottie_datas + qtawesome_datas + winrt_datas,
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
        'rlottie_python',
        'qtawesome',
        'winrt',
        'winrt._winrt',
        'winrt._winrt_windows_foundation',
        'winrt._winrt_windows_media',
        'winrt._winrt_windows_media_control',
        'winrt._winrt_windows_media_playback',
        'winrt._winrt_windows_storage',
        'winrt._winrt_windows_storage_streams',
        'winrt._winrt_windows_system',
        'winrt.system',
        'winrt.runtime',
        'winrt.windows.media',
        'winrt.windows.media.playback',
        'winrt.windows.media.control',
        'winrt.windows.storage',
        'winrt.windows.storage.streams',
        'winrt.windows.foundation',
    ] + winrt_submodules,
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

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='AuraPlayer.app',
        icon=icns_path,
        bundle_identifier='com.parsaalavi.auraplayer',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'False',
        }
    )
