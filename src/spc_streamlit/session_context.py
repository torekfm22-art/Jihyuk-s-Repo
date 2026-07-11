"""Streamlit app — analysis target session helpers."""
from __future__ import annotations

import hashlib

import streamlit as st

from src.spc.control_chart_interpreter import ControlChartInterpretation
from src.spc.pipeline import SpcPipelineResult
from src.spc_streamlit.analysis_runner import (
    StreamlitAnalysisBundle,
    get_active_result,
    get_interpretation,
    list_analysis_targets,
)

_SUMMARY_TABLE_KEYS = (
    "summary_table_bytes",
    "summary_table_name",
    "summary_table_path",
    "summary_table_err",
    "summary_table_save_err",
    "summary_table_ready",
    "summary_table_fingerprint",
)

_REPORT_CACHE_PREFIXES = (
    "excel_bytes_",
    "excel_name_",
    "excel_path_",
    "excel_err_",
    "excel_save_err_",
    "excel_ready_",
    "pdf_bytes_",
    "pdf_name_",
    "pdf_path_",
    "pdf_err_",
    "pdf_save_err_",
    "pdf_ready_",
)

_DATA_INPUT_CACHE_PREFIXES = (
    "workbook_",
    "manual_split_",
    "composite_",
    "group_spec_rows_",
    "group_spec_excluded_",
    "group_spec_excluded_norm_",
    "mp_selected_original_",
    "group_spec_pick_",
    "mp_selected_",
    "mp_comp_pick_",
    "mp_auto_comp_pick_",
    "mp_manual_pick_",
    "mp_auto_pick_",
    "excel_preview_v2_",
    "excel_preview_",
    "norm_df_",
)


def compute_upload_fingerprint(
    uploads,
    *,
    sheet_name: str | int | None = None,
) -> str:
    """첨부 파일·시트 기준 세션 서명 (내용 해시 포함)."""
    parts: list[str] = []
    for uf in uploads or []:
        data = uf.getvalue()
        digest = hashlib.sha256(data).hexdigest()[:20]
        parts.append(f"{uf.name}:{len(data)}:{digest}")
    if sheet_name is not None and str(sheet_name).strip() != "":
        parts.append(f"sheet={sheet_name}")
    raw = "|".join(sorted(parts))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def clear_data_input_caches() -> None:
    """데이터 입력 단계 — Excel·분리·규격 미리보기 캐시 제거."""
    for key in list(st.session_state.keys()):
        k = str(key)
        if any(k.startswith(prefix) for prefix in _DATA_INPUT_CACHE_PREFIXES):
            st.session_state.pop(key, None)
        if k.startswith("group_spec_rows_") and k.endswith("_targets"):
            st.session_state.pop(key, None)


def export_cache_is_stale() -> bool:
    """첨부 데이터 변경 후 분석을 다시 실행하지 않은 상태."""
    current = st.session_state.get("upload_fingerprint")
    analyzed = st.session_state.get("analysis_upload_fingerprint")
    if not current or not analyzed:
        return bool(current) and not analyzed
    return current != analyzed


def reset_session_for_new_upload(*, keep_upload_fingerprint: str | None = None) -> None:
    """새 Excel 첨부 — 분석·다운로드·입력 캐시 전부 초기화."""
    clear_data_input_caches()
    reset_export_session_state()
    st.session_state.analysis_done = False
    st.session_state.bundle = None
    st.session_state.pop("active_analysis_target", None)
    st.session_state.pop("auto_summary_path", None)
    st.session_state.pop("auto_summary_save_err", None)
    st.session_state.pop("analysis_upload_fingerprint", None)
    for key in list(st.session_state.keys()):
        k = str(key)
        if k.startswith(
            ("baseline_sample_", "extreme_exclude_", "extreme_mode_", "stratification_")
        ):
            st.session_state.pop(key, None)
    if keep_upload_fingerprint is not None:
        st.session_state["upload_fingerprint"] = keep_upload_fingerprint


def sync_upload_session(
    uploads,
    *,
    sheet_name: str | int | None = None,
) -> bool:
    """
    첨부·시트 변경 감지. 변경 시 캐시 초기화.
    Returns: True if this is a change from a previous upload (not first load).
    """
    fp = compute_upload_fingerprint(uploads, sheet_name=sheet_name)
    prev = st.session_state.get("upload_fingerprint")
    if prev == fp:
        return False
    reset_session_for_new_upload(keep_upload_fingerprint=fp)
    return prev is not None


def mark_analysis_upload_session() -> None:
    """분석 성공 직후 — 현재 첨부와 분석 결과를 짝지음."""
    fp = st.session_state.get("upload_fingerprint")
    if fp:
        st.session_state["analysis_upload_fingerprint"] = fp


def pipeline_export_fingerprint(pipe: SpcPipelineResult) -> str:
    """결론 Excel 캐시 무효화용 — 분석 대상·표본·판정 기준 서명."""
    from src.spc.characteristic_split import format_split_label
    from src.spc.summary_table_export import iter_leaf_pipeline_results

    split_col = pipe.split_column or ""
    parts: list[str] = [f"batch={int(pipe.is_batch)}", f"split={split_col}"]
    for leaf in iter_leaf_pipeline_results(pipe):
        label = format_split_label(leaf.characteristic or "-", split_col)
        n = int(leaf.sample_count or 0)
        verdict = "?"
        if leaf.decision and leaf.decision.control_chart:
            verdict = "S" if leaf.decision.control_chart.is_stable else "U"
        ppk = ""
        if leaf.analysis and leaf.analysis.capability and leaf.analysis.capability.ppk is not None:
            ppk = f"{float(leaf.analysis.capability.ppk):.4f}"
        parts.append(f"{label}|n={n}|{verdict}|ppk={ppk}")

    study = pipe.study_info or {}
    for key in ("source_files", "file_name", "input_path", "title"):
        val = study.get(key)
        if val:
            parts.append(f"{key}={val}")
    raw = "||".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def clear_summary_table_cache() -> None:
    for key in _SUMMARY_TABLE_KEYS:
        st.session_state.pop(key, None)


def reset_export_session_state() -> None:
    """새 분석·재분석 후 — 결론 Excel/PDF 캐시 초기화."""
    clear_summary_table_cache()
    for key in list(st.session_state.keys()):
        if any(str(key).startswith(prefix) for prefix in _REPORT_CACHE_PREFIXES):
            st.session_state.pop(key, None)
    st.session_state.pop("_summary_table_stale_notice", None)


def invalidate_summary_table_if_stale(current_fingerprint: str) -> None:
    """현재 분석과 캐시된 요약표 fingerprint가 다르면 무효화."""
    cached_fp = st.session_state.get("summary_table_fingerprint")
    if not st.session_state.get("summary_table_ready"):
        return
    if cached_fp == current_fingerprint:
        return
    clear_summary_table_cache()
    st.session_state["_summary_table_stale_notice"] = True


def ensure_analysis_target_options(targets: list[str]) -> None:
    """
    측정 포인트 selectbox **생성 전에만** 호출.
    Streamlit은 위젯 생성 후 동일 key의 session_state 수정을 금지함.
    """
    if not targets:
        st.session_state.pop("active_analysis_target", None)
        return
    current = st.session_state.get("active_analysis_target")
    if current not in targets:
        st.session_state.pop("active_analysis_target", None)
        st.session_state.active_analysis_target = targets[0]


def reset_analysis_targets(targets: list[str] | None = None) -> None:
    """새 분석 실행 직후 — selectbox 위젯이 아직 없는 시점에서만 호출."""
    st.session_state.pop("active_analysis_target", None)
    if targets:
        st.session_state.active_analysis_target = targets[0]


def reset_extreme_value_session(pipe: SpcPipelineResult) -> None:
    """새 분석 실행 시 극단치 기준 표본·제외 상태 초기화."""
    for k in list(st.session_state.keys()):
        if k.startswith(("baseline_sample_", "extreme_exclude_", "extreme_mode_")):
            st.session_state.pop(k, None)

    def _seed(result: SpcPipelineResult) -> None:
        if result.sample_df is None or result.sample_df.empty:
            return
        from src.spc.characteristic_split import normalize_split_value

        key = normalize_split_value(result.characteristic) or "default"
        st.session_state[f"baseline_sample_{key}"] = result.sample_df.copy()

    if pipe.is_batch:
        for child in pipe.split_results:
            if child.is_batch:
                for sub in child.split_results:
                    _seed(sub)
            else:
                _seed(child)
    else:
        _seed(pipe)


def resolve_analysis_context(
    bundle: StreamlitAnalysisBundle | None,
) -> tuple[SpcPipelineResult | None, SpcPipelineResult | None, object, object, ControlChartInterpretation | None]:
    """선택된 분석 대상 기준 analysis · decision · interpretation 반환."""
    if bundle is None:
        return None, None, None, None, None

    pipe = bundle.pipeline

    if pipe.is_batch:
        target = st.session_state.get("active_analysis_target")
        active = get_active_result(pipe, target)
    else:
        active = pipe

    analysis = active.analysis
    decision = active.decision
    interp = get_interpretation(bundle, active) if analysis and decision else None
    return pipe, active, analysis, decision, interp
