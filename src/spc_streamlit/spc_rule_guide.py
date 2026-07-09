"""Streamlit — 관리도 해석방법 (JSON 기반 표 + Rule 도식)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.spc.control_chart_rules_catalog import load_control_chart_rules
from src.spc_streamlit.control_chart_rule_diagrams import rule_diagram_svg

_XBAR_COL = "X-bar 관리도 해석"
_RS_COL = "R/S 관리도 해석"


def _inject_guide_table_css() -> None:
    st.markdown(
        """
        <style>
        .spc-rule-guide-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.86rem;
            margin: 0.5rem 0 1rem 0;
        }
        .spc-rule-guide-table th,
        .spc-rule-guide-table td {
            border: 1px solid #d0d7de;
            padding: 10px 12px;
            vertical-align: top;
        }
        .spc-rule-guide-table th {
            background: #1F4E79;
            color: #fff;
            text-align: center;
            font-weight: 600;
        }
        .spc-rule-guide-table tr:nth-child(even) td {
            background: #f8fafc;
        }
        .spc-rule-guide-table .diagram-cell {
            width: 300px;
            min-width: 260px;
            padding: 6px 8px;
            text-align: center;
            background: #fff;
            vertical-align: middle;
        }
        .spc-rule-guide-table .diagram-cell svg {
            max-width: 280px;
            height: auto;
        }
        .spc-rule-guide-table .cat-cell {
            font-weight: 600;
            white-space: nowrap;
            background: #eef4fa;
            vertical-align: middle;
        }
        .spc-rule-guide-table .rule-name {
            font-weight: 600;
            color: #1F4E79;
            white-space: nowrap;
            vertical-align: middle;
        }
        .spc-rule-guide-table .interp-xbar {
            background: #f0f7ff;
            min-width: 180px;
        }
        .spc-rule-guide-table .interp-rs {
            background: #fff8f0;
            min-width: 180px;
        }
        .spc-rule-guide-table .cond-cell {
            min-width: 140px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_rule_table_html(df: pd.DataFrame) -> None:
    rows_html: list[str] = []
    for _, row in df.iterrows():
        svg = rule_diagram_svg(str(row["_id"]))
        rows_html.append(
            "<tr>"
            f'<td class="cat-cell">{row["구분"]}</td>'
            f'<td class="rule-name">{row["규칙명"]}</td>'
            f'<td class="diagram-cell">{svg}</td>'
            f'<td class="cond-cell">{row["조건"]}</td>'
            f'<td class="interp-xbar">{row[_XBAR_COL]}</td>'
            f'<td class="interp-rs">{row[_RS_COL]}</td>'
            "</tr>"
        )
    table = f"""
    <table class="spc-rule-guide-table">
    <thead><tr>
        <th>구분</th><th>규칙명</th><th>관리도 도식</th><th>조건</th>
        <th>{_XBAR_COL}</th><th>{_RS_COL}</th>
    </tr></thead>
    <tbody>{"".join(rows_html)}</tbody>
    </table>
    """
    st.markdown(table, unsafe_allow_html=True)


def render_spc_rule_guide_page() -> None:
    st.markdown("### 관리도 해석방법")
    st.caption(
        "관리도 Rule 9종 — 조건별 도식 · **X-bar(평균·μ)** vs **R/S(산포·σ)** 분리 해석 (JSON 카탈로그)"
    )

    rules = load_control_chart_rules()
    rows = [
        {
            "구분": r.category,
            "규칙명": r.rule_name,
            "조건": r.condition,
            _XBAR_COL: r.interpretation_xbar,
            _RS_COL: r.interpretation_dispersion,
            "_tooltip": r.tooltip,
            "_id": r.id,
        }
        for r in rules
    ]
    df = pd.DataFrame(rows)

    col1, col2 = st.columns([1, 2])
    with col1:
        categories = sorted(df["구분"].unique())
        selected_cats = st.multiselect("구분 필터", categories, default=categories)
    with col2:
        keyword = st.text_input("검색 (규칙명·조건·해석)", "")

    filtered = df[df["구분"].isin(selected_cats)].copy()
    if keyword.strip():
        kw = keyword.strip().lower()
        mask = (
            filtered["규칙명"].str.lower().str.contains(kw, na=False)
            | filtered["조건"].str.lower().str.contains(kw, na=False)
            | filtered[_XBAR_COL].str.lower().str.contains(kw, na=False)
            | filtered[_RS_COL].str.lower().str.contains(kw, na=False)
        )
        filtered = filtered[mask]

    sort_col = st.selectbox("정렬 컬럼", ["구분", "규칙명", "조건", _XBAR_COL, _RS_COL], index=0)
    ascending = st.checkbox("오름차순", value=True)
    display = filtered.sort_values(sort_col, ascending=ascending).reset_index(drop=True)

    st.markdown("**노란 점** = Rule 조건 · **빨간 점선** = UCL/LCL · **보라 실선** = USL/LSL")
    st.markdown(
        "**해석 순서:** R/S(산포) 차트 이상 확인 → 이상 없을 때 X-bar(평균) 해석 (R-chart-first)"
    )
    _inject_guide_table_css()
    _render_rule_table_html(display)

    with st.expander("Rule 상세 (Tooltip)"):
        for r in rules:
            if r.id not in set(display["_id"]):
                continue
            col_d, col_t = st.columns([1, 2])
            with col_d:
                st.markdown(rule_diagram_svg(r.id), unsafe_allow_html=True)
            with col_t:
                st.markdown(f"**{r.rule_name}** (`{r.id}`)")
                st.markdown(f"**{_XBAR_COL}:** {r.interpretation_xbar}")
                st.markdown(f"**{_RS_COL}:** {r.interpretation_dispersion}")
                if r.tooltip:
                    st.caption(r.tooltip)
            st.divider()

    st.info(
        "SPC 판정 엔진은 위 표와 동일한 9 Rule을 적용합니다. "
        "Rule 발생 시 **규칙명·발생 위치·데이터 값·해석**이 분석 결과에 표시되며, "
        "이상 신호가 있으면 **비관리상태**, 없으면 **관리상태**로 판정합니다. "
        "**Cp/Cpk는 관리상태에서만** 유효합니다."
    )
