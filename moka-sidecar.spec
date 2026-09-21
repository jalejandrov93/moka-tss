# SPDX-License-Identifier: GPL-3.0-or-later
# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec for MOKA TSS sidecar (Tauri desktop integration).
# Entry point: moka.py at the repository root.
#
# Build mode: ONEFILE (single standalone executable, moka-sidecar.exe).
# Console: console=True is mandatory because the Tauri shell plugin launches
# the sidecar and reads stdout to detect the readiness signal:
#   MOKA_READY port=<port>
#
# Resources:
# - datas: only res/moka_tss is required (sprites, webui, rules.yaml, webconfig.json).
#   Extracted to sys._MEIPASS at runtime, resolved transparently by library.moka_tss.paths.
# - excludes: tkinter, _tkinter, Tkinter are excluded to minimize binary size
#   and avoid bundling unused GUI libraries (Tauri owns the desktop UI).

moka_sidecar_a = Analysis(
    ['moka.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('res/moka_tss', 'res/moka_tss'),
    ],
    hiddenimports=[
        'PIL',
        # pystray backend on Windows; keeps tray support available if needed.
        'pystray._win32',
        'clr',
        'psutil',
        'serial.tools.list_ports',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        '_tkinter',
        'Tkinter',
    ],
    noarchive=False,
    optimize=0,
)
moka_sidecar_pyz = PYZ(moka_sidecar_a.pure)

moka_sidecar_exe = EXE(
    moka_sidecar_pyz,
    moka_sidecar_a.scripts,
    moka_sidecar_a.binaries,
    moka_sidecar_a.datas,
    [],
    name='moka-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['res/icons/monitor-icon-17865/icon.ico'],
    version='tools/windows-installer/pyinstaller-version-info.txt',
)
