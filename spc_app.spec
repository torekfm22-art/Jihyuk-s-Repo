# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — SPC GUI exe (경량 onedir, 빠른 시작)."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

try:
    _ctk_datas = collect_data_files("customtkinter")
except Exception:
    _ctk_datas = []

ROOT = Path(SPEC).resolve().parent

datas = [
    (str(ROOT / "config" / "spc_job.yaml"), "config"),
]
datas += collect_data_files("matplotlib", subdir="mpl-data")
datas += _ctk_datas

_hidden = (
    collect_submodules("config")
    + collect_submodules("src.spc")
    + collect_submodules("src.xy_matrix")
)
hiddenimports = [
    "config",
    "config.app_paths",
    "config.settings",
    "src.spc.pipeline",
    "src.spc.sampler",
    "src.spc.data_extractor",
    "src.spc.excel_reader",
    "src.spc.comprehensive_report",
    "src.spc.report_validation_sheet",
    "src.spc.report_glossary_sheet",
    "src.spc.minitab_charts",
    "src.spc.statistics",
    "src.spc.sample_data",
    "src.spc.datetime_utils",
    "src.spc.path_utils",
    "src.spc.font_setup",
    "src.spc.constants",
    "src.xy_matrix",
    "src.xy_matrix.analyzer",
    "src.xy_matrix.analysis_engine",
    "src.xy_matrix.data_detection",
    "src.xy_matrix.column_aliases",
    "src.xy_matrix.multiple_regression",
    "src.xy_matrix.output",
    "src.xy_matrix.report_summary",
    "src.xy_matrix.excel_verification",
    "src.xy_matrix.excel_format",
    "src.xy_matrix.visualization",
    "src.xy_matrix.spc_recommendations",
    "src.xy_matrix.gui_panel",
    "src.xy_matrix.sample_data",
    "src.xy_matrix.constants",
    "statsmodels.api",
    "statsmodels.stats.outliers_influence",
    "sklearn.metrics",
    "openpyxl.cell._writer",
    "matplotlib.backends.backend_agg",
    "scipy.stats",
    "scipy.special",
    "reportlab.graphics.barcode",
    "reportlab.graphics.barcode.qr",
    "reportlab.pdfbase.ttfonts",
    "msoffcrypto",
    "olefile",
    "yaml",
    "customtkinter",
    "darkdetect",
    "pandas.plotting",
    "pandas.plotting._core",
    "pandas.plotting._misc",
] + _hidden

excludes = [
    "tkinter.test",
    "matplotlib.tests",
    "numpy.tests",
    "scipy.tests",
    "pandas.tests",
    "pytest",
    "IPython",
    "notebook",
    "jupyter",
    "torch",
    "numba",
    "sqlalchemy",
    "tables",
    "h5py",
    "botocore",
    "boto3",
]

block_cipher = None

a = Analysis(
    [str(ROOT / "src" / "spc_gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(ROOT / "build" / "runtime_pyi_paths.py"),
        str(ROOT / "build" / "runtime_mpl_tkagg.py"),
    ],
    excludes=excludes,
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
    name="SPC_공정능력분석",
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

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SPC_공정능력분석",
)
