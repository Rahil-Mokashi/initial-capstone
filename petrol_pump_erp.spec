# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the Petrol Pump ERP desktop app.

Build with:  pyinstaller petrol_pump_erp.spec
Output:      dist/PetrolPumpERP.exe (single file, no installer required)

Produces a onefile Windows executable. The app itself resolves its
database to a per-user app-data directory when frozen (see
app/database/connection.py:_default_database_path), so each install on
each PC gets its own fresh, persistent database on first run.
"""

# PyInstaller's static analysis pulls in matplotlib/PIL/tkinter as
# optional candidates (via other packages installed on the build
# machine, not anything this app imports). Tried excluding them to
# shrink the build — that broke PySide6's Qt platform-plugin bundling
# (the app would exit silently right after init, no window, no error)
# because matplotlib's Qt-backend hook is what triggers a fuller
# PySide6 plugin collection. Not excluding them costs ~20MB; that's
# cheaper than a build that silently fails to launch.
EXCLUDED_MODULES = []

# init_db() runs real Alembic migrations at startup (app/database/
# migrations.py), which needs alembic.ini and the alembic/ directory
# (env.py, script.py.mako, every versions/*.py) on disk at runtime, not
# just importable Python modules - PyInstaller's import analysis alone
# won't pick these up since they're read as files, not imported.
DATA_FILES = [
    ("alembic.ini", "."),
    ("alembic", "alembic"),
]

a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PetrolPumpERP",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
