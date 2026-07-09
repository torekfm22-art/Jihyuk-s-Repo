"""MES 형식 '값' 열 자동 인식·미리보기 테스트."""
import pandas as pd
import pytest
from pathlib import Path

from src.spc.data_extractor import (
    MesQmsExtractor,
    _normalize_columns,
    _resolve_column_name,
    _suggest_value_columns,
    list_value_column_choices,
    preview_excel_columns,
)

COLS = [
    "S/NO", "품번", "공정", "공정명", "설비 ID", "작업", "작업명",
    "네트 갯수", "값 갯수", "단위", "하한값", "상한값", "값",
    "하한값(런다운)", "상한값(런다운)", "값(런다운)",
    "트랜잭션 시간",
]


def test_normalize_maps_value_column():
    df = pd.DataFrame({c: [1.0] * 3 for c in COLS})
    out = _normalize_columns(df.copy())
    assert "value" in out.columns


def test_suggest_value_includes_primary():
    df = pd.DataFrame({c: [1.0] for c in COLS})
    hints = _suggest_value_columns(df)
    assert "값" in hints


def test_resolve_value_column():
    df = pd.DataFrame({c: [1.0] for c in COLS})
    assert _resolve_column_name(df, "값") == "값"


def test_extract_with_numeric_value():
    df = pd.DataFrame({c: [1.0, 2.0, 3.0] for c in COLS})
    ext = MesQmsExtractor([df])
    out = ext.extract()
    assert "value" in out.columns
    assert len(out) == 3


def test_preview_excel_columns(tmp_path: Path):
    df = pd.DataFrame({c: [1.0, 2.0] for c in COLS})
    path = tmp_path / "mes_sample.xlsx"
    df.to_excel(path, index=False)
    preview = preview_excel_columns(path)
    assert preview.error is None
    assert "값" in preview.value_candidates
    assert preview.recommended_column == "값"


def test_normalize_no_duplicate_process_column():
    """공정·공정명 동시 존재 시 process 컬럼 중복 방지."""
    df = pd.DataFrame({
        "공정": ["A", "B"],
        "공정명": ["조립", "조립"],
        "값": [1.0, 2.0],
        "트랜잭션 시간": ["2026-01-01 10:00:00", "2026-01-01 11:00:00"],
    })
    out = _normalize_columns(df)
    assert list(out.columns).count("process") <= 1
    assert "process_name" in out.columns
    ext = MesQmsExtractor([out])
    sampled = ext.extract()
    assert len(sampled) == 2


def test_suggest_value_from_numeric_wide_columns_without_value_header():
    df = pd.DataFrame({
        "LOT": ["L1", "L2", "L3"],
        "설비 ID": ["EQ-01", "EQ-01", "EQ-02"],
        "두께": [1.2, 1.3, 1.25],
        "폭": [10.0, 10.1, 9.9],
        "트랜잭션 시간": ["2026-01-01 10:00:00", "2026-01-01 11:00:00", "2026-01-01 12:00:00"],
    })
    hints = _suggest_value_columns(df)
    assert "두께" in hints
    assert "폭" in hints
    manual = list_value_column_choices(df)
    assert "두께" in manual
    assert "LOT" not in manual


def test_preview_keeps_columns_when_secondary_preview_step_fails(monkeypatch, tmp_path: Path):
    df = pd.DataFrame({
        "값": [1.0, 2.0],
        "트랜잭션 시간": ["2026-01-01 10:00:00", "2026-01-01 11:00:00"],
    })
    path = tmp_path / "partial.xlsx"
    df.to_excel(path, index=False)

    import src.spc.data_extractor as de

    def boom(*args, **kwargs):
        raise RuntimeError("spec detect failed")

    monkeypatch.setattr(de, "detect_spec_limits", boom)
    preview = preview_excel_columns(path)
    assert preview.columns == ["값", "트랜잭션 시간"]
    assert "값" in preview.manual_value_options
    assert preview.error is not None
