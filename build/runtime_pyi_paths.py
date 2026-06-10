"""PyInstaller: 번들(_MEIPASS) 경로를 import 전에 등록."""
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        p = str(Path(bundle))
        if p not in sys.path:
            sys.path.insert(0, p)
