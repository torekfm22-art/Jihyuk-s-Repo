"""규격 확인 테이블 삭제/제외 — 세션 동기화 시뮬레이션."""
from __future__ import annotations

import pandas as pd
import pytest

from src.spc.characteristic_split import normalize_split_value
from src.spc_streamlit.components import (
    _filter_groups_by_excluded,
    _group_spec_exclude_key,
    _is_row_selected,
    _load_excluded_norms,
    _persist_split_selection,
    _resolve_authoritative_selection,
    _save_excluded_norms,
    _split_groups_original_key,
    _split_groups_session_key,
    _split_pick_cache_key,
    _sync_analysis_groups_after_spec_delete,
)


class FakeSessionState(dict):
    """Streamlit session_state 최소 모사."""


@pytest.fixture
def session(monkeypatch):
    state = FakeSessionState()
    import streamlit as st

    monkeypatch.setattr(st, "session_state", state)
    return state


FILE = "test.xlsx"
SHEET = "Sheet1"
SPLIT_COLS = ["characteristic", "제품명"]
SPLIT_COL = "__composite__"
GROUPS = ["검사A · 모델1", "검사B · 모델2", "검사C · 모델3"]


def _simulate_delete_selected_rows(
    session: FakeSessionState,
    *,
    source_df: pd.DataFrame,
    groups_to_delete: list[str],
) -> tuple[list[str], set[str]]:
    """UI 삭제 버튼 클릭과 동일한 로직."""
    delete_norms = {normalize_split_value(g) for g in groups_to_delete}
    excluded = _load_excluded_norms(_group_spec_exclude_key(FILE, SPLIT_COLS))
    new_excluded = excluded | delete_norms
    remaining = [
        str(row["그룹"])
        for _, row in source_df.iterrows()
        if normalize_split_value(str(row["그룹"])) not in new_excluded
    ]
    _sync_analysis_groups_after_spec_delete(
        file_name=FILE,
        sheet=SHEET,
        split_columns=SPLIT_COLS,
        split_col=SPLIT_COL,
        remaining=remaining,
        excluded_norms=new_excluded,
    )
    return remaining, new_excluded


def test_exclude_norm_persistence(session):
    key = _group_spec_exclude_key(FILE, SPLIT_COLS)
    _save_excluded_norms(key, {"a", "b"})
    assert _load_excluded_norms(key) == {"a", "b"}


def test_filter_groups_removes_excluded():
    excluded = {normalize_split_value("검사B · 모델2")}
    out = _filter_groups_by_excluded(GROUPS, excluded, normalize=normalize_split_value)
    assert out == ["검사A · 모델1", "검사C · 모델3"]


def test_sync_updates_all_session_keys(session):
    pick_key = f"mp_comp_pick_{FILE}_{'_'.join(SPLIT_COLS)}"
    scope_key = f"group_spec_rows_{FILE}_{SHEET}_{SPLIT_COL}_sel"
    split_sel_key = _split_groups_session_key(FILE, SPLIT_COLS)
    exclude_key = _group_spec_exclude_key(FILE, SPLIT_COLS)
    editor_key = f"group_spec_pick_{FILE}_{'_'.join(SPLIT_COLS)}"

    session[scope_key] = [{"그룹": g, "LSL": 0, "USL": 1} for g in GROUPS]
    session[pick_key] = pd.DataFrame({
        "선택": [True, True, True],
        "항목명": GROUPS,
        "행 수": [200, 150, 300],
    })
    session[editor_key] = pd.DataFrame({"그룹": GROUPS, "선택": [False, True, False]})

    remaining = ["검사A · 모델1", "검사C · 모델3"]
    ex_norm = {normalize_split_value("검사B · 모델2")}
    _sync_analysis_groups_after_spec_delete(
        file_name=FILE,
        sheet=SHEET,
        split_columns=SPLIT_COLS,
        split_col=SPLIT_COL,
        remaining=remaining,
        excluded_norms=ex_norm,
    )

    assert session[split_sel_key] == remaining
    assert _load_excluded_norms(exclude_key) == ex_norm
    assert editor_key not in session
    assert session[f"{scope_key}_targets"] == tuple(remaining)
    assert [r["그룹"] for r in session[scope_key]] == remaining

    pick_df = session[pick_key]
    assert list(pick_df["항목명"]) == remaining
    assert list(pick_df["선택"]) == [True, True]
    assert session[_split_pick_cache_key(pick_key)] == remaining


def test_authoritative_selection_overrides_empty_picker(session):
    state_key = f"mp_comp_pick_{FILE}_{'_'.join(SPLIT_COLS)}"
    sel_key = _split_groups_session_key(FILE, SPLIT_COLS)
    session[sel_key] = ["검사A · 모델1", "검사C · 모델3"]

    resolved = _resolve_authoritative_selection(state_key)
    assert resolved == ["검사A · 모델1", "검사C · 모델3"]

    # 데이터 분리 위젯이 빈 선택을 반환해도 authoritative 우선
    out = _persist_split_selection(state_key, [], authoritative=resolved)
    assert out == ["검사A · 모델1", "검사C · 모델3"]


def test_full_delete_simulation_two_step(session):
    """선택 → 삭제 → 규격표·분석대상·데이터분리 동기화 시뮬레이션."""
    original_key = _split_groups_original_key(FILE, SPLIT_COLS)
    split_sel_key = _split_groups_session_key(FILE, SPLIT_COLS)
    pick_key = f"mp_comp_pick_{FILE}_{'_'.join(SPLIT_COLS)}"
    scope_key = f"group_spec_rows_{FILE}_{SHEET}_{SPLIT_COL}_sel"

    session[original_key] = list(GROUPS)
    session[split_sel_key] = list(GROUPS)
    session[scope_key] = [{"그룹": g, "LSL": 0, "USL": 5} for g in GROUPS]
    session[pick_key] = pd.DataFrame({
        "선택": [True, True, True],
        "항목명": GROUPS,
        "행 수": [200, 150, 300],
    })

    spec_table = pd.DataFrame({
        "선택": [False, True, False],
        "그룹": GROUPS,
        "LSL": [0.0, 0.0, 0.0],
        "USL": [5.0, 6.0, 7.0],
    })

    remaining, excluded = _simulate_delete_selected_rows(
        session, source_df=spec_table, groups_to_delete=["검사B · 모델2"],
    )

    assert remaining == ["검사A · 모델1", "검사C · 모델3"]
    assert normalize_split_value("검사B · 모델2") in excluded

    # rerun 후 target_values 계산 (render_group_spec_selector 초반 로직)
    original_values = list(session[original_key])
    target_values = _filter_groups_by_excluded(
        original_values, excluded, normalize=normalize_split_value,
    )
    assert target_values == remaining
    assert session[split_sel_key] == remaining
    assert list(session[pick_key]["항목명"]) == remaining


def test_double_delete_simulation(session):
    original_key = _split_groups_original_key(FILE, SPLIT_COLS)
    session[original_key] = list(GROUPS)
    scope_key = f"group_spec_rows_{FILE}_{SHEET}_{SPLIT_COL}_sel"
    session[scope_key] = [{"그룹": g} for g in GROUPS]

    df1 = pd.DataFrame({"선택": [False, True, False], "그룹": GROUPS})
    _simulate_delete_selected_rows(session, source_df=df1, groups_to_delete=["검사B · 모델2"])

    df2 = pd.DataFrame({
        "선택": [True, False],
        "그룹": ["검사A · 모델1", "검사C · 모델3"],
    })
    remaining, excluded = _simulate_delete_selected_rows(
        session, source_df=df2, groups_to_delete=["검사A · 모델1"],
    )

    assert remaining == ["검사C · 모델3"]
    assert len(excluded) == 2
    assert _split_groups_session_key(FILE, SPLIT_COLS) in session
    assert session[_split_groups_session_key(FILE, SPLIT_COLS)] == ["검사C · 모델3"]


def test_restore_clears_excluded(session):
    exclude_key = _group_spec_exclude_key(FILE, SPLIT_COLS)
    _save_excluded_norms(exclude_key, {normalize_split_value("검사B · 모델2")})
    _sync_analysis_groups_after_spec_delete(
        file_name=FILE,
        sheet=SHEET,
        split_columns=SPLIT_COLS,
        split_col=SPLIT_COL,
        remaining=list(GROUPS),
        excluded_norms=set(),
    )
    assert _load_excluded_norms(exclude_key) == set()
    assert session[_split_groups_session_key(FILE, SPLIT_COLS)] == GROUPS


def test_is_row_selected_for_checkbox_values():
    assert _is_row_selected(True) is True
    assert _is_row_selected(False) is False
    assert _is_row_selected(1) is True
    assert _is_row_selected(0) is False
    assert _is_row_selected(None) is False
