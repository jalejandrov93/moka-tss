# SPDX-License-Identifier: GPL-3.0-or-later
# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec for Mascota, the Turing Smart Screen 3.5" dashboard.
# Entry point: mascota.py at the repository root.
# Modelled on turing-system-monitor.spec; produces a single executable,
# mascota.exe, instead of the three executables joined by COLLECT there.

mascota_a = Analysis(
    ['mascota.py'],
    pathex=[],
    binaries=[],
    # ('res', 'res') already copies the whole res/ tree, which includes our
    # own resources: res/mascota/sprites/ (mascot PNG frames + CREDITS.md),
    # res/mascota/webui/ (index.html, style.css, app.js) and
    # res/mascota/rules.yaml. They are NOT listed separately on purpose:
    # one entry keeps the spec in sync automatically when sprites or webui
    # files are added, and a second overlapping entry would copy them twice.
    datas=[('res', 'res'), ('config.yaml', '.'), ('external', 'external')],
    hiddenimports=[
        'PIL',
        'PIL._imagingtk',
        'PIL._tkinter_finder',
        # pystray loads its OS backend dynamically (pystray._win32 on
        # Windows), so PyInstaller's static analysis never sees the import.
        # CONFIRMED from code: main.py:66-69 swallows the pystray import
        # error, so a missing backend fails invisibly (no tray, no error).
        'pystray._win32',
        # UNVERIFIED: 'clr' is provided at runtime by the pythonnet package
        # (library/sensors/sensors_librehardwaremonitor.py:33 does
        # "import clr"), which PyInstaller historically fails to detect.
        # Only needed on Windows with HW_SENSORS: LHM.
        'clr',
        # UNVERIFIED: psutil ships binary extensions that PyInstaller's
        # hooks usually (but not always, across versions) pick up on their
        # own. Listed explicitly as belt and braces; it is a direct import
        # in library/sensors/sensors_python.py and
        # library/sensors/sensors_librehardwaremonitor.py.
        'psutil',
        # UNVERIFIED: 'serial.tools.list_ports' is imported directly by every
        # LCD driver (e.g. library/lcd/lcd_comm_rev_a.py:25), so static
        # analysis should find it; listed explicitly because port
        # auto-discovery is the first thing that breaks on a fresh machine
        # and the failure looks like "no display found".
        'serial.tools.list_ports',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
mascota_pyz = PYZ(mascota_a.pure)

mascota_exe = EXE(
    mascota_pyz,
    mascota_a.scripts,
    [],
    exclude_binaries=True,
    name='mascota',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # Windowless app: it lives in the tray, started by double-click.
    # Keep True while debugging the frozen build to see tracebacks.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['res/icons/monitor-icon-17865/icon.ico'],
    # Must stay '.': library/mascota/paths.py resolves bundled data from
    # sys._MEIPASS when present and falls back to the directory containing
    # sys.executable, which is only correct when everything is collected
    # next to the exe instead of under an _internal/ subdirectory.
    contents_directory='.',
    version='tools/windows-installer/pyinstaller-version-info.txt',
)

# BUILD MODE: onedir (one mascota.exe plus its folder), NOT onefile.
# Why: library/mascota/paths.py handles both (sys._MEIPASS branch for
# onefile, sys.executable directory otherwise), so either would resolve.
# Onedir wins because a dashboard gan autostarted with Windows should start
# fast: onefile re-extracts every bundled file to a temp dir on each
# launch, while onedir just runs. It also matches the existing
# turing-system-monitor.spec pattern, so the Inno Setup tooling and the
# documented packaging pitfalls keep applying unchanged.
coll = COLLECT(
    mascota_exe,
    mascota_a.binaries,
    mascota_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='mascota',
)
