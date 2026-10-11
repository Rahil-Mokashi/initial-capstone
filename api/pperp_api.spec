# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the API SIDECAR that Electron spawns (separate from the Qt app's
petrol_pump_erp.spec, which is untouched).

Build (from the repo root):
    pyinstaller api/pperp_api.spec --noconfirm --distpath desktop/sidecar-dist --workpath desktop/sidecar-build

Output: desktop/sidecar-dist/pperp-api/pperp-api.exe  (onedir: starts faster than onefile because
nothing is unpacked to a temp folder on every launch, and there is no second bootloader process).
Qt is excluded on purpose - the sidecar never imports it, and it is the bulk of the Qt app's size.
"""

from PyInstaller.utils.hooks import collect_submodules

# Same reasons as petrol_pump_erp.spec: Alembic reads alembic.ini and alembic/ from disk at
# runtime (migrations run on first start), and env.py's stdlib imports are invisible to analysis.
DATA_FILES = [("../alembic.ini", "."), ("../alembic", "alembic")]
HIDDEN = ["logging.config", "logging.handlers"] + collect_submodules("uvicorn") + collect_submodules("api")

# PIL is NOT excluded: ReportLab imports it at load time, and the report/receipt PDFs need ReportLab.
EXCLUDES = [
    "PySide6", "shiboken6", "PyQt5", "PyQt6", "tkinter", "matplotlib", "numpy", "pandas",
    "IPython", "jupyter", "notebook", "scipy", "pytest",
]

a = Analysis(
    ["main.py"],
    pathex=[".."],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
# Windows' 260-character path limit is the real constraint on where this can be installed (a deep
# install path once made a migration file unloadable). Two cheap, measurable savings:
#  1. stale __pycache__ folders copied along with alembic/ are never loaded - drop them;
#  2. a one-character contents folder instead of the default "_internal".
a.datas = [d for d in a.datas if "__pycache__" not in d[0]]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pperp-api",
    debug=False,
    strip=False,
    upx=False,
    contents_directory="_",
    console=True,  # Electron starts it with windowsHide, and a console keeps crash output capturable
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="pperp-api")
