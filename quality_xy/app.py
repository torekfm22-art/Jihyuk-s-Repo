"""품질 X-Y 상관 분석 — 데이터 연결·시간 정렬 도구."""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from quality_xy.correlation import build_correlation_matrix  # noqa: E402
from quality_xy.graph_linker import DatasetGraph  # noqa: E402
from quality_xy.key_discovery import discover_key_links, links_to_dataframe  # noqa: E402
from quality_xy.loader import DatasetProfile, detect_datetime_column, load_dataframe, list_sheets  # noqa: E402
from quality_xy.sample_data import make_sample_datasets  # noqa: E402
from quality_xy.temporal_matcher import MatchConfig, XFactorSpec, build_wide_table  # noqa: E402

st.set_page_config(page_title="품질 X-Y 연결 분석", layout="wide")
st.title("품질 데이터 연결 · 시간 정렬 · X-Y 상관 분석")
st.caption("여러 데이터를 공통 키로 연결하고, 동일 시간대로 맞춘 뒤 X-Y 매트릭스 상관 분석을 수행합니다.")

K_PROFILES = "xy_profiles"
K_LINKS = "xy_links"
K_GRAPH = "xy_graph"


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for col in df.columns:
        if pd.to_numeric(df[col], errors="coerce").notna().sum() >= 3:
            cols.append(str(col))
    return cols


def _load_uploads(files) -> dict[str, pd.DataFrame]:
    datasets: dict[str, pd.DataFrame] = {}
    for uploaded in files:
        name = Path(uploaded.name).stem
        if uploaded.name.lower().endswith(".csv"):
            df = load_dataframe(BytesIO(uploaded.getvalue()))
            datasets[name] = df
            continue
        sheets = list_sheets(BytesIO(uploaded.getvalue()))
        if len(sheets) == 1:
            df = load_dataframe(BytesIO(uploaded.getvalue()), sheet_name=0)
            datasets[name] = df
        else:
            for sn in sheets:
                df = load_dataframe(BytesIO(uploaded.getvalue()), sheet_name=sn)
                datasets[f"{name}_{sn}"] = df
    return datasets


with st.sidebar:
    st.header("데이터 입력")
    use_sample = st.checkbox("샘플 데이터로 체험", value=False)
    uploads = st.file_uploader(
        "엑셀/CSV 여러 개 업로드",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
    )

    if use_sample:
        raw = make_sample_datasets()
    elif uploads:
        raw = _load_uploads(uploads)
    else:
        raw = {}

    if raw:
        profiles = {name: DatasetProfile(name, df) for name, df in raw.items()}
        st.session_state[K_PROFILES] = profiles
    elif K_PROFILES in st.session_state:
        profiles = st.session_state[K_PROFILES]
    else:
        profiles = {}

    st.divider()
    min_intersection = st.number_input("최소 교집합 건수", min_value=1, value=3, step=1)
    min_overlap = st.slider("최소 겹침 비율", 0.0, 1.0, 0.05, 0.01)

if not profiles:
    st.info("왼쪽에서 파일을 업로드하거나 샘플 데이터를 선택하세요.")
    st.stop()

tab_upload, tab_link, tab_match, tab_corr = st.tabs(
    ["① 데이터 미리보기", "② 연결 키 탐지", "③ 시간 정렬", "④ X-Y 상관"]
)

with tab_upload:
    for name, prof in profiles.items():
        with st.expander(f"📄 {name} ({len(prof.df):,}행)", expanded=len(profiles) <= 4):
            c1, c2 = st.columns(2)
            c1.markdown(f"**시간 컬럼 후보:** `{prof.datetime_col or '미탐지'}`")
            c2.markdown(f"**키 컬럼 후보:** {', '.join(prof.suggested_keys) or '없음'}")
            st.dataframe(prof.df.head(20), use_container_width=True)

with tab_link:
    st.subheader("데이터셋 간 공통 키(교집합) 탐지")
    links = discover_key_links(
        profiles,
        min_intersection=int(min_intersection),
        min_overlap_ratio=float(min_overlap),
    )
    st.session_state[K_LINKS] = links
    st.session_state[K_GRAPH] = DatasetGraph(links)

    if not links:
        st.warning("연결 가능한 키를 찾지 못했습니다. 컬럼명·데이터 형식을 확인하세요.")
    else:
        st.dataframe(links_to_dataframe(links), use_container_width=True)
        anchor_preview = st.selectbox("연결 맵 기준 데이터셋", list(profiles.keys()))
        st.markdown("```mermaid\n" + st.session_state[K_GRAPH].adjacency_mermaid(anchor_preview) + "\n```")
        components = st.session_state[K_GRAPH].connected_components()
        if len(components) > 1:
            st.warning(f"연결되지 않은 그룹이 {len(components)}개 있습니다. 일부 X 인자는 경로가 없을 수 있습니다.")
        else:
            st.success("모든 데이터셋이 하나의 연결 그룹에 속합니다.")

with tab_match:
    st.subheader("동일 시간대 정렬 → Wide 테이블")
    graph: DatasetGraph = st.session_state.get(K_GRAPH, DatasetGraph([]))
    anchor = st.selectbox("Y(결과) 데이터셋", list(profiles.keys()), key="anchor_ds")
    anchor_prof = profiles[anchor]

    time_col = st.selectbox(
        "Y 시각 컬럼",
        list(anchor_prof.df.columns),
        index=list(anchor_prof.df.columns).index(anchor_prof.datetime_col)
        if anchor_prof.datetime_col in anchor_prof.df.columns
        else 0,
    )
    y_candidates = _numeric_columns(anchor_prof.df) or list(anchor_prof.df.columns)
    y_col = st.selectbox("Y 인자 컬럼", y_candidates)

    window_min = st.slider("시간 허용 범위 (±분)", 5, 24 * 60, 120, 5)

    reachable = graph.reachable_datasets(anchor)
    st.markdown(f"**연결 가능 데이터셋:** {', '.join(reachable)}")

    x_specs: list[XFactorSpec] = []
    st.markdown("#### X 인자 선택")
    for name in profiles:
        if name not in reachable:
            continue
        prof = profiles[name]
        numeric_cols = _numeric_columns(prof.df)
        if not numeric_cols:
            continue
        with st.expander(f"X ← {name}", expanded=name != anchor):
            picked = st.multiselect(
                f"{name}에서 가져올 X 컬럼",
                numeric_cols,
                default=numeric_cols[:2] if name != anchor else [],
                key=f"x_pick_{name}",
            )
            strategy = st.selectbox(
                "매칭 방식",
                ["nearest", "mean", "first", "last", "count"],
                format_func=lambda x: {
                    "nearest": "가장 가까운 시각",
                    "mean": "평균",
                    "first": "첫 번째",
                    "last": "마지막",
                    "count": "건수",
                }[x],
                key=f"x_strat_{name}",
            )
            for col in picked:
                x_specs.append(XFactorSpec(dataset=name, column=col, strategy=strategy))

    if st.button("시간 정렬 실행", type="primary"):
        config = MatchConfig(
            anchor_dataset=anchor,
            anchor_time_col=str(time_col),
            y_column=str(y_col),
            window_minutes=int(window_min),
            x_factors=x_specs,
        )
        wide_df, detail_df = build_wide_table(profiles, graph, config)
        st.session_state["wide_df"] = wide_df
        st.session_state["detail_df"] = detail_df
        st.session_state["y_col"] = y_col

    if "wide_df" in st.session_state:
        wide_df = st.session_state["wide_df"]
        detail_df = st.session_state["detail_df"]
        st.markdown("#### 정렬 결과 (분석용 Wide 테이블)")
        st.dataframe(wide_df, use_container_width=True)
        with st.expander("매칭 상세"):
            st.dataframe(detail_df, use_container_width=True)
        buf = BytesIO()
        wide_df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button("Wide 테이블 엑셀 다운로드", buf.getvalue(), "xy_wide_table.xlsx")

with tab_corr:
    st.subheader("X-Y 상관 매트릭스")
    if "wide_df" not in st.session_state:
        st.info("먼저 ③ 시간 정렬 탭에서 정렬을 실행하세요.")
    else:
        wide_df = st.session_state["wide_df"]
        y_col = st.session_state.get("y_col", "")
        meta = {"_anchor_index", "_anchor_time"}
        x_cols = [c for c in wide_df.columns if c not in meta and c != y_col]
        method = st.radio("상관 계수", ["pearson", "spearman"], horizontal=True)

        full_matrix, y_vs_x, valid_n = build_correlation_matrix(
            wide_df, y_col, x_cols, method=method
        )

        st.markdown(f"**유효 관측 수:** {valid_n}행 (모든 X·Y가 숫자로 채워진 행)")
        if valid_n < 5:
            st.warning("유효 행이 5건 미만이면 상관 분석이 불안정합니다. 시간 창·키 연결을 조정하세요.")
        elif not full_matrix.empty:
            fig = px.imshow(
                full_matrix,
                text_auto=".2f",
                color_continuous_scale="RdBu_r",
                zmin=-1,
                zmax=1,
                title="X-Y 상관 매트릭스",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("#### Y 대 X 요약")
            st.dataframe(y_vs_x, use_container_width=True)

            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                wide_df.to_excel(writer, sheet_name="wide", index=False)
                full_matrix.to_excel(writer, sheet_name="correlation")
            st.download_button("분석 결과 엑셀 다운로드", buf.getvalue(), "xy_correlation.xlsx")
