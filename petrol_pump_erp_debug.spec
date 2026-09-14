# -*- mode: python ; coding: utf-8 -*-
"""DIAGNOSTIC-ONLY build spec, not for release.

Identical to petrol_pump_erp.spec except console=True and a different
exe name, so stdout/stderr are actually visible - the production spec
uses console=False (runw.exe bootloader), which means sys.stdout is
None and a first-launch failure shows as total silence instead of a
traceback. Built to diagnose the CRITICAL first-launch hang recorded
in PROJECT_CONTEXT.md. Not wired into release.yml and not meant to be
distributed - dist/PetrolPumpERP.exe (built from petrol_pump_erp.spec)
remains the only artifact that ships.

Build with:  pyinstaller petrol_pump_erp_debug.spec
Output:      dist/PetrolPumpERP-debug.exe
"""

EXCLUDED_MODULES = []

DATA_FILES = [
    ("alembic.ini", "."),
    ("alembic", "alembic"),
    ("app/ui/qml", "app/ui/qml"),
]

QML_HIDDEN_IMPORTS = [
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
]

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

UNUSED_QUICKCONTROLS_STYLES = (
    "Imagine", "Material", "Universal", "Fusion", "FluentWinUI3", "NativeStyle", "Windows", "macOS", "iOS",
)


def _is_unused_qt_entry(entry) -> bool:
    dest_path = entry[0].replace("\\", "/")
    dest_path_lower = dest_path.lower()
    name = dest_path.rsplit("/", 1)[-1]

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

a.datas = [entry for entry in a.datas if not _is_unused_qt_entry(entry)]
a.binaries = [entry for entry in a.binaries if not _is_unused_qt_entry(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PetrolPumpERP-debug",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
