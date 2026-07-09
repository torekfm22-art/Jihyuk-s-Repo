# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — SPC 공정 안정성 점검 (Streamlit Desktop, onedir)."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPEC).resolve().parent

# Streamlit 정적 리소스
_st_datas = collect_data_files("streamlit")
_st_hidden = collect_submodules("streamlit")

try:
    _wv_datas = collect_data_files("webview")
except Exception:
    _wv_datas = []

datas = [
    (str(ROOT / "config" / "spc_policy.yaml"), "config"),
    (str(ROOT / "src" / "spc_streamlit" / "app.py"), "src/spc_streamlit"),
    (str(ROOT / "src" / "spc_streamlit" / "components.py"), "src/spc_streamlit"),
    (str(ROOT / "src" / "spc_streamlit" / "analysis_runner.py"), "src/spc_streamlit"),
    (str(ROOT / ".streamlit" / "config.toml"), ".streamlit"),
]
datas += collect_data_files("matplotlib", subdir="mpl-data")
datas += _st_datas
datas += _wv_datas

_hidden = (
    collect_submodules("config")
    + collect_submodules("src.spc")
    + collect_submodules("src.spc_streamlit")
    + _st_hidden
)

hiddenimports = [
    "config",
    "config.app_paths",
    "config.settings",
    "src.spc_streamlit.app",
    "src.spc_streamlit.components",
    "src.spc_streamlit.analysis_runner",
    "src.spc.control_chart_interpreter",
    "src.spc.pipeline",
    "src.spc.decision_service",
    "src.spc.rule_engine",
    "src.spc.comprehensive_report",
    "streamlit",
    "streamlit.web",
    "streamlit.web.bootstrap",
    "streamlit.runtime",
    "streamlit.runtime.scriptrunner",
    "tornado",
    "tornado.platform.asyncio",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "click",
    "altair",
    "pyarrow",
    "webview",
    "PIL",
    "openpyxl.cell._writer",
    "matplotlib.backends.backend_agg",
    "scipy.stats",
    "reportlab.pdfbase.ttfonts",
    "msoffcrypto",
    "yaml",
    "pandas.plotting",
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
    "customtkinter",
]

block_cipher = None

a = Analysis(
    [str(ROOT / "src" / "spc_streamlit" / "desktop_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "build" / "runtime_pyi_paths.py")],
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
    name="SPC_공정안정성점검",
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
    name="SPC_공정안정성점검",
)
