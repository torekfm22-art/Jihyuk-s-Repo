"""혼합분포 판정 및 데이터 재구성 UI."""
from __future__ import annotations

import streamlit as st
import pandas as pd

from src.spc.decision_models import SpcDecisionResult
from src.spc.mixed_distribution_excel_export import (
    build_reconstructed_excel_bytes,
    build_subgroup_stats_df,
)
from src.spc.mixed_distribution_stratification import (
    StratificationStudyResult,
    StratifiedReanalysisResult,
    needs_mixed_distribution_rebuild,
    run_stratification_study,
    run_stratified_reanalysis,
)
from src.spc.pipeline import SpcPipelineResult
from src.spc.sampler import SampleSelector
from src.spc.statistics import SpcAnalysisResult, SpcAnalyzer


def _get_usl_lsl(active: SpcPipelineResult) -> tuple[float | None, float | None]:
    cap = active.analysis.capability if active.analysis else None
    if cap:
        return cap.usl, cap.lsl
    return None, None


def _cache_key(active: SpcPipelineResult) -> str:
    char = active.characteristic or "single"
    n = len(active.filtered_df) if active.filtered_df is not None else 0
    return f"mixed_rebuild_{char}_{n}"


def render_mixed_distribution_rebuild_section(
    active: SpcPipelineResult,
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> None:
    """정규성 검정 하단 — 혼합분포 2차 분리 · 재채취 · 재분석."""
    if not needs_mixed_distribution_rebuild(analysis, decision):
        return

    if active.filtered_df is None or active.filtered_df.empty or "value" not in active.filtered_df.columns:
        st.warning("혼합분포 분석에 필요한 데이터가 없습니다.")
        return

    st.divider()
    st.subheader("혼합분포 판정 및 데이터 재구성")

    mp_label = active.characteristic or "현재 데이터"
    if active.split_column == "measurement_point" and active.characteristic:
        st.markdown(
            f"**{mp_label}** 포인트는 이미 분리되어 분석 중입니다. "
            "여전히 혼합분포(비정규)이면 **교대·LOT·날짜·설비 등 2차 조건**으로 "
            "다시 나눠 subgroup을 재구성하고 SPC를 재분석할 수 있습니다."
        )
    else:
        st.markdown(
            "데이터가 **비정규**이고 **정규성 변환도 실패**했습니다. "
            "공정 조건(교대·LOT·날짜 등)으로 한 번 더 분리해 보세요."
        )

    usl, lsl = _get_usl_lsl(active)
    cfg = active.sampling_config or {}
    subgroup_size = int(cfg.get("subgroup_size", 5))
    population_std = bool(cfg.get("use_full_population", False))
    key = _cache_key(active)

    c1, c2 = st.columns(2)
    with c1:
        subgroup_size = st.number_input("Subgroup 크기 (n)", 2, 10, subgroup_size, key=f"md_sg_{key}")
    with c2:
        run_btn = st.button("혼합분포 원인 자동 분석", type="primary", key=f"md_run_{key}")

    fixed: list[str] = []
    if active.characteristic and active.split_column == "measurement_point":
        fixed = ["measurement_point"]
        st.caption(f"측정포인트 **{mp_label}** 고정 — 교대·LOT·날짜·Raw 컬럼 후보를 분석합니다.")

    if run_btn:
        with st.spinner("분리 기준별 재구성 시뮬레이션 중..."):
            try:
                st.session_state[key] = run_stratification_study(
                    active.filtered_df,
                    usl=usl,
                    lsl=lsl,
                    subgroup_size=int(subgroup_size),
                    min_subgroup_count=25,
                    fixed_columns=fixed or None,
                    analysis=active.analysis,
                    population_std=population_std,
                    sample_df=active.sample_df,
                )
                st.session_state.pop(f"{key}_rebuild", None)
                st.session_state.pop(f"{key}_excel", None)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
                return

    study: StratificationStudyResult | None = st.session_state.get(key)
    if study is None:
        st.info("「혼합분포 원인 자동 분석」 버튼을 눌러 2차 분리 후보를 비교하세요.")
        return

    if study.diagnosis.suspected:
        st.warning("**혼합분포 가능성 있음** — 아래 추천 순위(재구성 후 기준)를 확인하세요.")
    else:
        st.info("혼합분포 가능성은 낮지만, 2차 분리 비교는 참고할 수 있습니다.")

    if not study.candidates:
        avail = study.available_columns
        if avail:
            labels = ", ".join(f"{k}→`{v}`" for k, v in avail.items())
            st.error(
                "분석할 수 있는 2차 분리 기준이 없습니다. "
                f"인식된 컬럼: {labels}. "
                "각 컬럼에 **서로 다른 값이 2개 이상** 필요합니다."
            )
        else:
            st.error("2차 분리 기준 컬럼이 없습니다. Excel에 교대·LOT·측정일시 등을 포함하세요.")
        return

    for line in study.narrative:
        st.markdown(line)

    st.markdown("**분리 기준 추천 순위** (공정 조건 기준 · subgroup 재구성 후 지표)")
    st.caption(
        "교대·LOT·설비 등 **범주형 공정 조건**을 데이터 형태로 자동 탐지해 평가합니다. "
        "공장마다 항목명이 달라도 수준 수·연속값 여부로 구분하며, "
        "분석 중인 측정치·다른 연속 측정 열은 후보에서 제외됩니다."
    )
    rank_rows = []
    for c in study.candidates:
        sr_before = c.overall_sigma_ratio
        sr_after = c.rebuild_sigma_ratio or c.mean_sigma_ratio
        rank_rows.append({
            "순위": c.rank,
            "분리 기준": c.split_basis,
            "그룹 수": c.group_count,
            "subgroup 수": c.subgroup_count_after,
            "정규성 만족 비율": f"{c.normal_group_ratio:.0%}",
            "재구성 σratio": round(sr_after, 2) if sr_after is not None else "—",
            "현재 σratio": round(sr_before, 2) if sr_before is not None else "—",
            "최저 Ppk": round(c.min_ppk, 3) if c.min_ppk is not None else "—",
            "추천 점수": round(c.total_score, 1),
            "추천 판단": c.recommendation_judgment,
            "점수 근거": c.score_detail or c.summary,
        })
    st.dataframe(pd.DataFrame(rank_rows), use_container_width=True, hide_index=True)

    options = {c.split_basis: c.split_columns for c in study.candidates}
    default_basis = study.recommended_basis or list(options.keys())[0]
    selected = st.selectbox(
        "재구성에 사용할 분리 기준",
        options=list(options.keys()),
        index=list(options.keys()).index(default_basis) if default_basis in options else 0,
        key=f"md_pick_{key}",
    )

    btn_label = f"{selected} 기준으로 샘플 재구성"
    if st.button(btn_label, type="primary", key=f"md_rebuild_{key}"):
        with st.spinner("subgroup 재구성 중..."):
            try:
                result = run_stratified_reanalysis(
                    active.filtered_df,
                    options[selected],
                    usl=usl,
                    lsl=lsl,
                    subgroup_size=int(subgroup_size),
                    incomplete_policy="keep_with_warning",
                    population_std=population_std,
                )
                st.session_state[f"{key}_rebuild"] = result
                st.session_state[f"{key}_split_basis"] = selected
                st.session_state.pop(f"{key}_excel", None)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    rebuild: StratifiedReanalysisResult | None = st.session_state.get(f"{key}_rebuild")
    if rebuild is None:
        return

    for w in rebuild.warnings:
        st.warning(w)

    st.markdown("**조건별 결과 (재구성 후)**")
    st.dataframe(pd.DataFrame(rebuild.comparison_rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**다음 단계 — SPC 재분석**")
    st.caption(
        "재구성만으로는 4~6단계 관리도·공정능력이 바뀌지 않습니다. "
        "아래 버튼으로 **전체 재분석** 또는 **조건별 분리 재분석**을 실행하세요."
    )

    col_a, col_b = st.columns(2)
    split_basis = st.session_state.get(f"{key}_split_basis", selected)
    split_cols = options.get(split_basis, rebuild.split_columns)

    with col_a:
        if st.button("재구성 샘플로 SPC 재분석", type="primary", key=f"md_rerun_{key}"):
            from src.spc_streamlit.analysis_runner import rerun_with_stratified_sample
            from src.spc_streamlit.session_context import reset_analysis_targets

            try:
                bundle = st.session_state.bundle
                new_bundle = rerun_with_stratified_sample(bundle, active, rebuild.sample_df)
                from src.spc_streamlit.session_context import reset_export_session_state

                reset_export_session_state()
                st.session_state.bundle = new_bundle
                reset_analysis_targets([active.characteristic] if active.characteristic else [])
                st.session_state.nav_step = "stability"
                st.success("재구성 샘플로 SPC를 재분석했습니다. 4. 관리도 해석으로 이동합니다.")
                st.rerun()
            except Exception as exc:
                st.error(f"재분석 실패: {exc}")

    with col_b:
        n_cond = rebuild.sample_df["split_key"].nunique() if "split_key" in rebuild.sample_df.columns else 0
        if st.button(
            f"조건별 분리 재분석 ({n_cond}개)",
            type="secondary",
            key=f"md_split_{key}",
            help="측정포인트 1~4 분리처럼, 조건(교대·LOT 등)마다 별도 SPC 결과 생성",
        ):
            from src.spc_streamlit.analysis_runner import (
                list_analysis_targets,
                rerun_with_condition_split,
            )
            from src.spc_streamlit.session_context import reset_analysis_targets

            try:
                bundle = st.session_state.bundle
                new_bundle = rerun_with_condition_split(
                    bundle,
                    active,
                    rebuild.sample_df,
                    split_columns=split_cols,
                    split_basis=split_basis,
                )
                from src.spc_streamlit.session_context import reset_export_session_state

                reset_export_session_state()
                st.session_state.bundle = new_bundle
                targets = list_analysis_targets(new_bundle.pipeline)
                reset_analysis_targets(targets)
                st.session_state.nav_step = "data_analysis"
                st.success(
                    f"조건별 {n_cond}개 대상으로 분리 재분석했습니다. "
                    "사이드바에서 「포인트 · 조건」을 선택하세요."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"조건별 재분석 실패: {exc}")

    sg_stats = build_subgroup_stats_df(rebuild.sample_df)
    if not sg_stats.empty:
        st.markdown("**조건별 subgroup 통계**")
        st.dataframe(sg_stats, use_container_width=True, hide_index=True)

    split_col = "split_key" if "split_key" in rebuild.sample_df.columns else None
    if split_col and (usl is not None or lsl is not None):
        st.markdown("**조건별 관리도 (재구성 기준)**")
        analyzer = SpcAnalyzer(population_std=population_std)
        for gkey, grp in rebuild.sample_df.groupby(split_col, sort=False):
            n_sg = grp["subgroup_id"].nunique() if "subgroup_id" in grp.columns else 0
            if n_sg < 2:
                st.caption(f"{gkey}: subgroup 수 부족 — 관리도 생략")
                continue
            try:
                sub = SampleSelector.to_subgroup_matrix(grp, int(subgroup_size))
                analysis_g = analyzer.analyze_xbar_s(sub, usl=usl, lsl=lsl)
                from src.spc.interactive_charts import build_control_chart_figure

                fig = build_control_chart_figure(analysis_g, grp)
                if fig is not None:
                    st.markdown(f"**{gkey}** (subgroup {n_sg}개)")
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as exc:
                st.caption(f"{gkey}: 관리도 생성 불가 — {exc}")

    with st.expander("재구성된 샘플 데이터 미리보기"):
        st.dataframe(rebuild.sample_df.head(200), use_container_width=True)
        n_sg = rebuild.sample_df["subgroup_id"].nunique() if "subgroup_id" in rebuild.sample_df.columns else 0
        st.caption(f"총 {len(rebuild.sample_df)}행 · subgroup {n_sg}개")

    excel_cache = f"{key}_excel"
    if excel_cache not in st.session_state:
        try:
            data, fname = build_reconstructed_excel_bytes(
                original_df=active.filtered_df,
                study=study,
                reconstructed_df=rebuild.sample_df,
                spc_groups=rebuild.after_groups,
            )
            st.session_state[excel_cache] = (data, fname)
        except Exception as exc:
            st.error(f"엑셀 생성 실패: {exc}")
            return

    xlsx_bytes, xlsx_name = st.session_state[excel_cache]
    st.download_button(
        "재구성 데이터 엑셀 다운로드",
        data=xlsx_bytes,
        file_name=f"{xlsx_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"md_xlsx_{key}",
    )


render_stratification_section = render_mixed_distribution_rebuild_section
