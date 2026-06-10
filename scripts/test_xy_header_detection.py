"""헤더 인식 단위 테스트 (보조 행 삭제·인자명/유형 순서)."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.xy_matrix.data_detection import auto_detect_data_structure


def _make_raw(rows: list[list]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_name_then_type():
    raw = _make_raw([
        [None, "생산일", "인플레이터중량", "외기온도", "예열온도", "라인"],
        [None, None, "결과 Y", "계량형 X", "계량형 X", "범주형 X"],
        [1, "2026-01-01", 130.1, 25.0, 180.0, "A"],
        [2, "2026-01-02", 130.2, 26.0, 181.0, "B"],
    ])
    df, st = auto_detect_data_structure(raw)
    assert "인플레이터중량" in st["y_columns"], st
    assert "예열온도" in st["x_columns"], st
    assert "11" not in st["y_columns"] and "0" not in st["x_columns"]
    print("OK name_then_type", st["layout_hint"], st["y_columns"], st["x_columns"])


def test_type_then_name():
    raw = _make_raw([
        [None, None, "결과 Y", "계량형 X", "계량형 X", "범주형 X"],
        [None, "생산일", "인플레이터중량", "외기온도", "예열온도", "라인"],
        [1, "2026-01-01", 130.1, 25.0, 180.0, "A"],
        [2, "2026-01-02", 130.2, 26.0, 181.0, "B"],
    ])
    df, st = auto_detect_data_structure(raw)
    assert st["y_columns"] == ["인플레이터중량"]
    assert "예열온도" in st["x_columns"]
    print("OK type_then_name", st["layout_hint"])


def test_legacy_subtype_row():
    raw = _make_raw([
        [None, None, "결과 Y", "계량형 X", "계량형 X", "범주형 X"],
        [None, None, None, "계량형", "범주형", "범주형"],
        [None, "생산일", "인플레이터중량", "외기온도", "예열온도", "라인"],
        [1, "2026-01-01", 130.1, 25.0, 180.0, "A"],
        [2, "2026-01-02", 130.2, 26.0, 181.0, "B"],
    ])
    df, st = auto_detect_data_structure(raw)
    assert "인플레이터중량" in st["y_columns"]
    assert "예열온도" in st["x_columns"]
    print("OK legacy_subtype", st["x_types"].get("예열온도"), st.get("subtype_row"))


if __name__ == "__main__":
    test_name_then_type()
    test_type_then_name()
    test_legacy_subtype_row()
    print("ALL HEADER TESTS PASSED")
