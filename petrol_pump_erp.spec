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
#
# app/ui/qml/ is the same situation for the QML login screen (Phase A of
# the hybrid QML UI upgrade, 2026-09-02) - LoginWindow loads .qml files
# from disk at runtime (app/ui/login_window.py:_qml_dir), not via import.
DATA_FILES = [
    ("alembic.ini", "."),
    ("alembic", "alembic"),
    ("app/ui/qml", "app/ui/qml"),
]

# Importing PySide6.QtQuickWidgets (app/ui/login_window.py) pulls in
# QtQuick and QtQml transitively. PyInstaller's own hook for QtQml
# (hook-PySide6.QtQml.py -> collect_qtqml_files()) bundles the ENTIRE
# installed PySide6/qml/ directory - every Qt Quick submodule shipped
# with PySide6 (Qt3D, QtWebEngine, QtCharts, QtMultimedia, and a dozen
# more this app never uses) - plus each of those submodules' own native
# DLL, which PyInstaller's dependency walk pulls in as a SEPARATE
# top-level binary (e.g. PySide6\Qt6WebEngineCore.dll), not something
# living inside the qml/ folder at all. A first pass here only filtered
# the qml/ folder and missed those top-level DLLs - Qt6WebEngineCore.dll
# alone (an embedded Chromium engine, unrelated to anything this app
# does) turned out to be ~205MB uncompressed on its own, dwarfing every
# other module combined. hiddenimports below makes the QtQuick
# dependency explicit (defensive - see the EXCLUDED_MODULES comment
# above for a real precedent of this app's Qt plugin bundling being
# fragile to get right from static analysis alone); the datas/binaries
# filter after Analysis() is what actually removes the unused
# submodules and their DLLs, keeping only what LoginScreen.qml's
# `import QtQuick` / `import QtQuick.Controls.Basic` actually need.
QML_HIDDEN_IMPORTS = [
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
]

# Substrings matched against both the qml/ plugin folder path AND each
# module's own top-level DLL/pyd filename (e.g. "WebEngine" matches both
# qml/QtWebEngine/... and PySide6\Qt6WebEngineCore.dll). Kept as an
# explicit denylist - not an allowlist of what to keep - so a future
# addition of a real QtQuick submodule this app does start using won't
# be silently stripped back out by this filter without the list being
# touched. "6Pdf" (not bare "Pdf") specifically targets Qt's own PdF
# module (a WebEngine dependency, unrelated to this app's ReportLab-based
# PDF export) without accidentally matching unrelated filenames.
UNUSED_QT_MODULE_KEYWORDS = (
    "WebEngine",
    "WebView",
    "WebChannel",
    "WebSockets",
    "3DRender", "3DQuick", "3DAnimation", "3DExtras", "3DInput", "3DLogic", "3DCore", "3DAssetImport",
    "Quick3D",
    "Charts",
    "Graphs",
    "DataVisualization",
    "Location",
    "Positioning",
    "Multimedia",
    "Sensors",
    "Scxml",
    "TextToSpeech",
    "RemoteObjects",
    "5Compat",
    "VirtualKeyboard",
    "Bluetooth",
    "Nfc",
    "SerialPort",
    "SerialBus",
    "LabsStyleKit",
    "6Pdf",
)

# QtQuick Controls 2 ships one native style plugin per visual style;
# LoginScreen.qml only imports QtQuick.Controls.Basic, so every other
# style's plugin DLL and qml/ resource folder is dead weight. The base
# QtQuickControls2/QtQuickTemplates2 modules are NOT style-specific and
# must be kept - the Basic style itself depends on them.
UNUSED_QUICKCONTROLS_STYLES = (
    "Imagine", "Material", "Universal", "Fusion", "FluentWinUI3", "NativeStyle", "Windows", "macOS", "iOS",
)


def _is_unused_qt_entry(entry) -> bool:
    # Analysis().datas/.binaries entries are (dest_path, src_path, typecode)
    # tuples.
    dest_path = entry[0].replace("\\", "/")
    dest_path_lower = dest_path.lower()
    name = dest_path.rsplit("/", 1)[-1]

    # case-insensitive: a module's own DLL/pyd is PascalCase
    # ("Qt63DRender.dll") but its QML plugin loader is lowercase
    # ("quick3drenderplugin.dll") - both need to match the same keyword.
    if any(keyword.lower() in dest_path_lower for keyword in UNUSED_QT_MODULE_KEYWORDS):
        return True

    return any(
        f"QuickControls2{style}" in name or f"Controls/{style}/" in dest_path
        for style in UNUSED_QUICKCONTROLS_STYLES
    )


a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=QML_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=0,
)

# Strip the unused Qt Quick submodules (and their DLLs) the QtQml hook
# pulled in by default (see the comment above DATA_FILES) - done here,
# after Analysis(), rather than via `excludes=`, since these are plugin
# data files and shared libraries pulled in by a hook's own dependency
# walk, not importable Python modules `excludes` can name.
a.datas = [entry for entry in a.datas if not _is_unused_qt_entry(entry)]
a.binaries = [entry for entry in a.binaries if not _is_unused_qt_entry(entry)]

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
