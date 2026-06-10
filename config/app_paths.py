"""개발 환경 / PyInstaller exe 공통 경로."""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_project_root() -> Path:
    """쓰기 가능한 앱 루트 (exe 폴더 또는 저장소 루트)."""
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_resource_root() -> Path:
    """번들 리소스 (_MEIPASS 또는 저장소 루트)."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return get_project_root()
