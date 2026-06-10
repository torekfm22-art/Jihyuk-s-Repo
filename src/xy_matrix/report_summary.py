"""

X-Y 매트릭스 시트 하단 통합 섹션 데이터.

"""

from __future__ import annotations



from typing import Any



import pandas as pd



from src.xy_matrix.constants import TYPE_CONTINUOUS





def _fmt_p(p_val: Any) -> str:

    if p_val is None or (isinstance(p_val, float) and pd.isna(p_val)):

        return "-"

    try:

        fv = float(p_val)

        if fv < 1e-10:

            return "≈0"

        if fv < 0.001:

            return f"{fv:.2e}"

        return f"{fv:.4g}"

    except (TypeError, ValueError):

        return str(p_val)





def _fmt_r2(r2: Any) -> str:

    if r2 is None or (isinstance(r2, float) and pd.isna(r2)):

        return "-"

    try:

        return f"{float(r2):.4f}"

    except (TypeError, ValueError):

        return str(r2)





def _matrix_lookup(matrix: pd.DataFrame | None, name: str) -> pd.Series | None:

    if matrix is None or matrix.empty:

        return None

    key = "x_column" if "x_column" in matrix.columns else matrix.columns[0]

    hit = matrix[matrix[key] == name]

    return hit.iloc[0] if not hit.empty else None





def _factor_detail_line(row: pd.Series) -> str:

    name = row.get("x_column", row.get("X 인자명", ""))

    r2 = _fmt_r2(row.get("r_square"))

    p = _fmt_p(row.get("p_value"))

    score = int(row.get("score", 0) or 0)

    sym = row.get("symbol", "") or ""

    p_part = f"P{p}" if str(p).startswith("≈") else f"P={p}"

    return f"  {name} (R²={r2}, {p_part}) → {score}점 {sym}".strip()





def _y_mean_suffix(df: pd.DataFrame | None, y_col: str) -> str:

    if df is None or y_col not in df.columns:

        return ""

    s = pd.to_numeric(df[y_col], errors="coerce").dropna()

    if s.empty:

        return ""

    m = float(s.mean())

    if abs(m) >= 100:

        return f" / 평균: {m:,.0f}"

    if abs(m) >= 1:

        return f" / 평균: {m:,.2f}"

    return f" / 평균: {m:.4f}"





def build_key_findings_rows(result: dict[str, Any]) -> list[tuple[str, str]]:

    """시트 하단 「핵심 발견」 서술형 요약 (Key Findings)."""

    y_col = result.get("y_column", "")

    structure = result.get("data_structure", {}) or {}

    df = result.get("analysis_data")

    matrix = result.get("matrix")

    rec = result.get("recommendations", {}) or {}

    mr = result.get("multiple_regression")



    y_types = structure.get("y_types", {})

    y_type = y_types.get(y_col, TYPE_CONTINUOUS)

    n_rows = len(df) if df is not None else 0



    rows: list[tuple[str, str]] = [

        ("🎯 핵심 발견 (Key Findings)", ""),

        (

            "",

            f"Y인자: {y_col} — {y_type} / 데이터 수: {n_rows:,}건{_y_mean_suffix(df, y_col)}",

        ),

        ("", ""),

    ]



    if matrix is not None and len(matrix):

        nine = matrix[matrix["score"] == 9]

        three = matrix[matrix["score"] == 3]

        one = matrix[matrix["score"] == 1]



        rows.append(("☑ 9점 인자 (강한 상관관계):", ""))

        if nine.empty:

            rows.append(("", "  (해당 없음)"))

        else:

            for _, r in nine.iterrows():

                rows.append(("", _factor_detail_line(r)))



        rows.append(("", ""))

        rows.append(("☑ 3점 인자 (보통 상관관계):", ""))

        if three.empty:

            rows.append(("", "  (해당 없음)"))

        else:

            for _, r in three.iterrows():

                rows.append(("", _factor_detail_line(r)))



        if not one.empty:

            rows.append(("", ""))

            rows.append(("△ 1점 인자 (약한 상관):", ""))

            for _, r in one.head(5).iterrows():

                rows.append(("", _factor_detail_line(r)))

            if len(one) > 5:

                rows.append(("", f"  … 외 {len(one) - 5}개 (상세는 상단 매트릭스 표 참조)"))



        rows.append(("", ""))

        mr_targets = matrix[matrix["score"] >= 3]["x_column"].tolist()

        if mr and "error" not in mr and mr_targets:

            rows.append(

                ("💡 3단계 다중회귀분석 적용 대상:", ", ".join(mr_targets)),

            )

            adj = mr.get("adjusted_r_square")

            multi_r2 = mr.get("multiple_r_square")

            if adj is not None and multi_r2 is not None:

                rows.append(

                    (

                        "",

                        f"  다중 R²={_fmt_r2(multi_r2)}, Adj.R²={_fmt_r2(adj)}, "

                        f"모형 P={_fmt_p(mr.get('p_value'))}",

                    ),

                )

        elif len(mr_targets) >= 2:

            rows.append(

                ("💡 3단계 다중회귀분석 적용 대상:", ", ".join(mr_targets)),

            )

        else:

            rows.append(

                ("💡 3단계 다중회귀분석 적용 대상:", "유의 인자 2개 미만 — 생략 가능"),

            )



        rows.append(("", ""))

        rows.append(("💡 4단계 SPC 관리 항목 제안 (CTP 지정):", ""))

        ctp_list = rec.get("ctp_factors") or []

        if ctp_list:

            for i, ctp in enumerate(ctp_list, 1):

                name = ctp.get("factor", "")

                mrow = _matrix_lookup(matrix, name)

                r2 = _fmt_r2(mrow["r_square"]) if mrow is not None else "-"

                chart = ctp.get("chart_recommendation", "X-bar R 또는 I-MR")

                rows.append(

                    (

                        "",

                        f"  CTP {i}: {name} — 직접 제어 가능, R²={r2} → {chart}",

                    ),

                )

        else:

            rows.append(("", "  (CTP 후보 없음 — 점수 3점 이상·제어 가능 인자 확인)"))



        ctrl = rec.get("controllability") or {}

        mon_notes: list[str] = []

        for _, r in matrix[matrix["score"] >= 3].iterrows():

            name = str(r["x_column"])

            if not ctrl.get(name, True):

                mon_notes.append(name)

        for m in rec.get("monitoring_factors") or []:

            fname = m.get("factor", "")

            if fname and fname not in mon_notes:

                mon_notes.append(fname)

        for name in mon_notes:

            rows.append(("", f"  ※ {name}은 제어 불가 → 모니터링 항목으로 지정"))



        rows.append(("", ""))

        rows.append(("📌 권고사항:", ""))

        if ctp_list:

            names = [c.get("factor", "") for c in ctp_list]

            charts = sorted(

                {c.get("chart_recommendation", "") for c in ctp_list if c.get("chart_recommendation")}

            )

            chart_txt = ", ".join(charts) if charts else "X-bar·R 관리도"

            rows.append(

                ("", f"  {', '.join(names)}에 대한 SPC 관리도({chart_txt}) 운영 권고"),

            )

        unctrl = [n for n in mon_notes if n]

        ctp_names = [c.get("factor", "") for c in ctp_list]

        if unctrl and ctp_names:

            rows.append(

                (

                    "",

                    f"  {unctrl[0]} 변동 시 {ctp_names[0]} 보상 로직 개발 검토",

                ),

            )

        if rec.get("vif_warnings"):

            rows.append(

                ("", "  다중공선성(VIF>10) 주의 — 인자 선별·교란 제거 후 재분석 권장"),

            )

        rows.append(

            ("", "  상세 수치·수식 검증은 상단 매트릭스 표 및 「수식검증」 시트 참조"),

        )

    else:

        rows.append(("", "  분석 결과가 없습니다."))



    return rows





def build_analysis_meta_rows(result: dict[str, Any]) -> list[tuple[str, str]]:

    """하위 호환 — 핵심 발견 요약과 동일."""

    return build_key_findings_rows(result)





def multi_reg_summary_df(result: dict[str, Any]) -> pd.DataFrame | None:

    """다중회귀 요약 표."""

    mr = result.get("multiple_regression")

    if not mr or "error" in mr:

        return None

    rows: list[tuple[str, Any]] = [

        ("다중 R²", mr.get("multiple_r_square")),

        ("Adjusted R²", mr.get("adjusted_r_square")),

        ("F-value", mr.get("f_value")),

        ("모형 P-value", mr.get("p_value")),

        ("공통 기여도", mr.get("shared_contribution")),

    ]

    uc = mr.get("unique_contributions", {}) or {}

    pct_map = mr.get("unique_contribution_pct", {}) or {}

    for k, v in uc.items():

        pct = pct_map.get(k)

        val = f"{v:.4f}" if isinstance(v, float) else str(v)

        if pct is not None:

            val += f" (기여율 {pct:.1f}%)"

        rows.append((f"순수기여 · {k}", val))

    return pd.DataFrame(rows, columns=["항목", "값"])





def _records_to_dataframe(records: Any) -> pd.DataFrame | None:

    """list[dict] 또는 DataFrame만 허용 (혼합 시퀀스로 인한 dict() 오류 방지)."""

    if records is None:

        return None

    if isinstance(records, pd.DataFrame):

        return records.copy() if not records.empty else None

    if not isinstance(records, list) or not records:

        return None

    if not all(isinstance(r, dict) for r in records):

        return None

    return pd.DataFrame(records)





def ctp_recommendations_df(result: dict[str, Any]) -> pd.DataFrame | None:

    rec = result.get("recommendations", {})

    return _records_to_dataframe(rec.get("ctp_factors"))





def monitoring_df(result: dict[str, Any]) -> pd.DataFrame | None:

    rec = result.get("recommendations", {})

    return _records_to_dataframe(rec.get("monitoring_factors"))





def kv_to_dataframe(rows: list[tuple[str, str]]) -> pd.DataFrame:

    return pd.DataFrame(rows, columns=["항목", "내용"])


