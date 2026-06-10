"""품질 M/H 자동 산출 - Streamlit UI."""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from quality_mh.excel_parser import preview_sheet_structure  # noqa: E402
from quality_mh.incoming_frequency_analyzer import (  # noqa: E402
    analyze_workbook_sheets_with_raw,
    to_frequency_dataframe,
)
from quality_mh.incoming_workbook_reader import read_incoming_workbook  # noqa: E402
from quality_mh.output_excel import build_output_workbook, prepare_output_data  # noqa: E402
from quality_mh.pipeline import QualityMhPipeline  # noqa: E402
from quality_mh.rule_loader import (  # noqa: E402
    load_column_mapping,
    load_frequency_rules,
    load_manpower_rules,
    load_standard_tasks,
    load_unit_time_rules,
)

st.set_page_config(page_title="품질 M/H 자동 산출", layout="wide")
st.title("품질 M/H 자동 산출 프로그램")
st.caption("표준 PPT 철학 + 발생빈도/모답스 분리 구조 | 확인된 rule만 자동 계산")

if "pipeline_state" not in st.session_state:
    st.session_state.pipeline_state = None


def _rules_df(rules):
    return pd.DataFrame([r.model_dump() for r in rules])


tabs = st.tabs([
    "표준 체계",
    "파일 업로드",
    "입고검사 빈도",
    "Rule 확인",
    "계산 실행",
    "결과",
    "검토 필요",
])

with tabs[0]:
    st.subheader("표준 업무 체계 (Layer 1)")
    tasks = load_standard_tasks()
    df_std = pd.DataFrame([t.model_dump() for t in tasks])
    st.dataframe(df_std, use_container_width=True)
    st.info("PPT 원본 미첨부 항목은 SOURCE_NOT_VERIFIED / MANUAL_CONFIRM_REQUIRED 상태입니다.")

with tabs[1]:
    st.subheader("파일 업로드 및 자동 분류")
    uploaded = st.file_uploader(
        "엑셀 파일 업로드 (다중 선택 가능)",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
    )
    if uploaded:
        pipeline = QualityMhPipeline()
        files = [(f.name, BytesIO(f.getvalue())) for f in uploaded]
        state = pipeline.ingest_files(files)
        st.session_state.pipeline_state = state

        st.markdown("### 파일 역할 자동분류")
        st.dataframe(state.file_analysis_df, use_container_width=True)

        st.markdown("### 시트 구조 미리보기")
        for fname, sheets in state.parsed_sheets.items():
            with st.expander(f"📄 {fname}"):
                for sname, df in sheets.items():
                    st.markdown(f"**시트: {sname}**")
                    preview = preview_sheet_structure(df)
                    st.write(f"행 수: {preview['row_count']}, 컬럼: {preview['columns']}")
                    st.dataframe(df.head(10), use_container_width=True)

    if st.button("데모 데이터로 샘플 실행"):
        pipeline = QualityMhPipeline()
        state = pipeline.run_demo()
        st.session_state.pipeline_state = state
        st.success("데모 데이터 로드 완료. '계산 실행' 탭에서 계산하세요.")

with tabs[2]:
    st.subheader("입고검사 발생빈도 분석 (생산계획 연동)")
    st.caption(
        "검사빈도(부품별) 리스트 Raw → Pivot → 발생빈도 집계 자동화 "
        "(생산계획 연동 반영)"
    )
    incoming_file = st.file_uploader(
        "근거 통합문서 업로드",
        type=["xlsx", "xls"],
        key="incoming_workbook",
    )
    year_text = st.text_input("분석 연도", value="2024,2025")
    if incoming_file and st.button("입고검사 빈도 집계", type="primary", key="run_incoming"):
        try:
            sheets = read_incoming_workbook(BytesIO(incoming_file.getvalue()))
            years = [int(y.strip()) for y in year_text.split(",") if y.strip()]
            summary, raw_by_year, pivot_by_year, audit = analyze_workbook_sheets_with_raw(
                sheets,
                years=years,
            )
            freq_df = to_frequency_dataframe(summary)
            st.session_state["incoming_summary"] = summary
            st.session_state["incoming_freq"] = freq_df
            st.session_state["incoming_raw"] = raw_by_year
            st.session_state["incoming_pivot"] = pivot_by_year
            st.session_state["incoming_audit"] = audit
            st.success(f"집계 완료: {len(summary)}행")
            for line in audit:
                st.caption(line)
        except Exception as exc:
            st.error(f"집계 실패: {exc}")

    summary = st.session_state.get("incoming_summary")
    if summary is not None and not summary.empty:
        st.markdown("### 지표별 집계 (샘플링/전수/무검사)")
        metric_filter = st.selectbox(
            "지표 선택",
            sorted(summary["metric"].unique()),
            key="incoming_metric",
        )
        view = summary[summary["metric"] == metric_filter]
        st.dataframe(view, use_container_width=True)

        raw_by_year = st.session_state.get("incoming_raw") or {}
        pivot_by_year = st.session_state.get("incoming_pivot") or {}
        for year, raw_df in raw_by_year.items():
            with st.expander(f"Raw data {year} ({len(raw_df):,}건)"):
                st.dataframe(raw_df.head(200), use_container_width=True)
        for year, pivot_df in pivot_by_year.items():
            with st.expander(f"Raw 기반 Pivot {year}"):
                st.dataframe(pivot_df, use_container_width=True)

        freq_df = st.session_state.get("incoming_freq")
        if freq_df is not None and not freq_df.empty:
            with st.expander("MH 파이프라인 연동용 빈도 데이터"):
                st.dataframe(freq_df, use_container_width=True)

with tabs[3]:
    st.subheader("빈도 Rule")
    st.dataframe(_rules_df(load_frequency_rules()), use_container_width=True)
    st.subheader("단위시간 Rule")
    st.dataframe(_rules_df(load_unit_time_rules()), use_container_width=True)
    st.subheader("표준 인원 Rule")
    st.dataframe(_rules_df(load_manpower_rules()), use_container_width=True)

    with st.expander("컬럼 매핑 dictionary (수정 가능)"):
        mapping = load_column_mapping()
        st.json(mapping)

with tabs[4]:
    st.subheader("계산 실행")
    if st.session_state.pipeline_state is None:
        st.warning("먼저 파일을 업로드하거나 데모 데이터를 로드하세요.")
    else:
        if st.button("MH 계산 실행", type="primary"):
            pipeline = QualityMhPipeline()
            pipeline.audit = st.session_state.pipeline_state.audit
            pipeline.frequency_engine.audit = pipeline.audit
            pipeline.unit_time_engine.audit = pipeline.audit
            pipeline.mh_engine.audit = pipeline.audit
            pipeline.manpower_engine.audit = pipeline.audit
            st.session_state.pipeline_state = pipeline.run_calculation(st.session_state.pipeline_state)
            st.success("계산 완료")

        state = st.session_state.pipeline_state
        col1, col2, col3 = st.columns(3)
        col1.metric("발생빈도 건수", len(state.frequency_df))
        col2.metric("단위시간 건수", len(state.unit_time_df))
        col3.metric("MH 결과 건수", len(state.mh_df))

with tabs[5]:
    st.subheader("결과 Pivot / 집계")
    state = st.session_state.pipeline_state
    if state is None:
        st.warning("계산 데이터 없음")
    else:
        sub1, sub2, sub3, sub4 = st.tabs(["MH 결과", "라인별", "공정별", "공장별 요약"])
        with sub1:
            st.dataframe(state.mh_df, use_container_width=True)
        with sub2:
            st.dataframe(state.line_agg_df, use_container_width=True)
        with sub3:
            st.dataframe(state.process_agg_df, use_container_width=True)
        with sub4:
            st.dataframe(state.factory_summary_df, use_container_width=True)

        st.subheader("표준 인원")
        st.dataframe(state.manpower_df, use_container_width=True)

        if not state.mh_df.empty:
            pivot_cols = [c for c in ["factory_name", "domain", "line_name"] if c in state.mh_df.columns]
            if pivot_cols and "mh_value" in state.mh_df.columns:
                st.subheader("Pivot 보기")
                pivot = pd.pivot_table(
                    state.mh_df,
                    values="mh_value",
                    index=pivot_cols[0],
                    columns=pivot_cols[1:] if len(pivot_cols) > 1 else None,
                    aggfunc="sum",
                    fill_value=0,
                )
                st.dataframe(pivot, use_container_width=True)

        st.subheader("결과 엑셀 다운로드")
        output_data = prepare_output_data(
            standard_master_df=state.standard_master_df,
            file_analysis_df=state.file_analysis_df,
            frequency_df=state.frequency_df,
            unit_time_df=state.unit_time_df,
            mh_df=state.mh_df,
            line_agg_df=state.line_agg_df,
            process_agg_df=state.process_agg_df,
            manpower_df=state.manpower_df,
            normalized_raw_df=state.normalized_raw_df,
            audit=state.audit,
        )
        excel_buf = build_output_workbook(output_data)
        st.download_button(
            "📥 결과 엑셀 다운로드",
            data=excel_buf,
            file_name="품질MH_산출결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tabs[6]:
    st.subheader("검토 필요 항목")
    state = st.session_state.pipeline_state
    if state is None:
        st.warning("데이터 없음")
    else:
        review_df = state.audit.to_dataframes_dict()["review_items"]
        if review_df.empty:
            st.success("검토 필요 항목 없음")
        else:
            st.dataframe(review_df, use_container_width=True)
