"""PyInstaller: matplotlib을 TkAgg로 고정 (Qt 탐색 지연 방지)."""
import os

os.environ["MPLBACKEND"] = "TkAgg"
