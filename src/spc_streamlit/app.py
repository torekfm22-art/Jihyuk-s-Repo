"""
SPC 공정 안정성 점검 — Streamlit UI

실행:
    streamlit run src/spc_streamlit/app.py
    또는 run_spc_streamlit.bat
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.spc.control_chart_interpreter import build_control_chart_interpretation
from src.spc.glossary_export import glossary_to_markdown
from src.spc.data_extractor import preview_excel_columns
from src.spc.spec_limits import ui_spec_mode_to_type
from src.spc_streamlit.analysis_runner import run_spc_analysis
from src.spc_streamlit.sample_table_ui import render_filtered_data_with_sample_highlight
from src.spc_streamlit.components import (
    inject_custom_css,
    render_active_target_banner,
    render_capability_panel,
    render_control_chart_panel,
    render_anomaly_detail_status,
    render_histogram_panel,
    render_normality_charts,
    render_data_analysis_summary,
    render_improvement_actions,
    render_measurement_point_panel,
    render_normality_panel,
    render_normality_transform_result,
    _format_cp_cpk_summary,
    _format_pp_ppk_summary,
    render_quantitative_insights,
    render_report_downloads,
    render_summary_table_download,
    render_study_report_chart_grid,
    render_capability_correlation_guide,
    render_sidebar_analysis_target,
    render_step_header,
    render_validation_panel,
    render_value_column_picker,
    render_spec_limit_picker,
    render_group_spec_selector,
    render_measurement_point_picker,
    _split_groups_session_key,
    render_we_table,
    render_data_quality_panel,
    render_value_extreme_panel,
    render_dispersion_deferred_warning,
)
from src.spc_streamlit.session_context import resolve_analysis_context
from src.spc_streamlit.spc_rule_guide import render_spc_rule_guide_page
from src.spc_streamlit.traceability_ui import render_stability_trace_sections

st.set_page_config(
    page_title="SPC 공정 안정성 점검",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

STEPS: list[tuple[str, str, str]] = [
    ("data", "1. 데이터 입력", "MES/QMS Excel · 분석 조건"),
    ("data_analysis", "2. 데이터 분석", "원본·채취 표본 · 샘플링 요약"),
    ("normality", "3. 정규성 검정", "분포 가정 · 혼합분포 재구성"),
    ("stability", "4. 관리도 해석 (이상점 관리)", "관리도 · Raw Value · 데이터 추적"),
    ("capability", "5. 공정능력 평가", "Case 1~4 기반 능력 지표"),
    ("conclusion", "6. 결론", "종합 리포트 · 판정 종합"),
    ("validation", "7. 데이터 검증", "프로그램 vs Excel 수식 · 관리한계 · 정규성"),
    ("rule_guide", "관리도 해석방법", "첨부#2 회사 표준"),
    ("glossary", "SPC 용어 및 개념", "초보자용 용어 가이드"),
]
STEP_KEYS = [s[0] for s in STEPS]
STEP_LABELS = {s[0]: s[1] for s in STEPS}

STAGE_MAP = {"양산": "mass_production", "개발": "development", "파일럿": "pilot", "양산 전": "pre_mass_production"}
CHART_MAP = {"자동": "auto", "X-bar S": "xbar_s", "X-bar R": "xbar_r", "I-MR": "imr"}


def _init_session() -> None:
    for k, v in {
        "bundle": None,
        "analysis_done": False,
        "nav_step": "data",
        "nav_history": ["data"],
        "nav_history_idx": 0,
    }.items():
        st.session_state.setdefault(k, v)


def _push_nav_history(step: str) -> None:
    """메뉴 이동 기록 — 뒤로/앞으로 탐색용."""
    if step not in STEP_KEYS:
        return
    hist: list[str] = list(st.session_state.nav_history)
    idx: int = int(st.session_state.nav_history_idx)
    if idx < len(hist) - 1:
        hist = hist[: idx + 1]
    if not hist or hist[-1] != step:
        hist.append(step)
        idx = len(hist) - 1
    st.session_state.nav_history = hist
    st.session_state.nav_history_idx = idx


def _navigate_back() -> None:
    idx = int(st.session_state.nav_history_idx)
    if idx > 0:
        st.session_state.nav_history_idx = idx - 1
        st.session_state.nav_step = st.session_state.nav_history[idx - 1]
        st.rerun()


def _navigate_forward() -> None:
    idx = int(st.session_state.nav_history_idx)
    hist: list[str] = st.session_state.nav_history
    if idx < len(hist) - 1:
        st.session_state.nav_history_idx = idx + 1
        st.session_state.nav_step = hist[idx + 1]
        st.rerun()


def _render_header_with_nav() -> None:
    """제목 + 우측 상단 뒤로/앞으로 버튼."""
    title_col, nav_col = st.columns([6, 1.35])
    with title_col:
        st.markdown('<p class="main-header">SPC 공정 안정성 점검</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="sub-header">회사 표준 관리도 해석 · Case 1~4 Capability</p>',
            unsafe_allow_html=True,
        )
    with nav_col:
        st.markdown('<div class="nav-toolbar-spacer"></div>', unsafe_allow_html=True)
        back_col, fwd_col = st.columns(2)
        can_back = int(st.session_state.nav_history_idx) > 0
        can_fwd = int(st.session_state.nav_history_idx) < len(st.session_state.nav_history) - 1
        with back_col:
            if st.button("◀", key="nav_back", disabled=not can_back, use_container_width=True, help="뒤로"):
                _navigate_back()
        with fwd_col:
            if st.button("▶", key="nav_forward", disabled=not can_fwd, use_container_width=True, help="앞으로"):
                _navigate_forward()


def _sidebar_nav() -> str:
    st.sidebar.markdown("## 📋 분석 단계")
    st.sidebar.caption("해석용 관리도 우선 · AIAG-VDA · Case 1~4")

    if not st.session_state.analysis_done:
        for i, (key, label, _) in enumerate(STEPS):
            if i == 0:
                st.sidebar.markdown(f"**▶ {label}**")
            elif key == "rule_guide":
                if st.sidebar.button("📖 " + label, use_container_width=True, key="nav_rule_guide"):
                    _push_nav_history("rule_guide")
                    st.session_state.nav_step = "rule_guide"
                    st.rerun()
            else:
                st.sidebar.markdown(f"<span style='color:#aaa'>{label}</span>", unsafe_allow_html=True)
        if st.session_state.nav_step == "rule_guide":
            return "rule_guide"
        return "data"

    if st.session_state.nav_step == "traceability":
        st.session_state.nav_step = "stability"

    idx = STEP_KEYS.index(st.session_state.nav_step) if st.session_state.nav_step in STEP_KEYS else 0
    prev_step = st.session_state.nav_step
    choice = st.sidebar.radio(
        "단계",
        options=STEP_KEYS,
        format_func=lambda k: STEP_LABELS[k],
        index=idx,
        label_visibility="collapsed",
    )
    st.session_state.nav_step = choice
    if choice != prev_step:
        _push_nav_history(choice)

    if st.session_state.bundle and st.session_state.analysis_done and choice != "data":
        pipe = st.session_state.bundle.pipeline
        render_sidebar_analysis_target(pipe)
        _, active, _, _, _ = resolve_analysis_context(st.session_state.bundle)
        n = active.sample_count if active else (
            pipe.sample_count if not pipe.is_batch else sum(c.sample_count for c in pipe.split_results)
        )
        st.sidebar.divider()
        st.sidebar.metric("채취 표본 (선택)", f"{n}건")
        if pipe.is_batch:
            from src.spc.characteristic_split import is_measurement_point_split
            kind = "측정 포인트" if is_measurement_point_split(pipe.split_column) else "항목"
            st.sidebar.caption(f"{kind} {len(pipe.split_results)}개 분석")

    return choice


def _get_context():
    pipe, active, analysis, decision, interp = resolve_analysis_context(st.session_state.bundle)
    return st.session_state.bundle, active, analysis, decision, interp


def _page_data_input() -> None:
    render_step_header(1, "데이터 입력", "분석 대상 데이터와 규격·채취 조건을 설정합니다.")

    c1, c2 = st.columns([2, 1])
    with c1:
        uploads = st.file_uploader(
            "MES / QMS Excel (1개 이상)",
            type=["xlsx", "xls", "xlsm", "csv"],
            accept_multiple_files=True,
        )

    value_column: str | None = None
    preview = None
    sheet_name: str | int | None = None
    mp_mode = "none"
    mp_columns: list[str] = []
    mp_values: list[str] = []
    spec_mode = "양측 공차"
    lsl: float | None = None
    usl: float | None = None
    per_split_spec = False
    split_spec_limits: dict[str, tuple[float | None, float | None]] = {}
    preview_path: Path | None = None

    if uploads:
        from src.spc.excel_reader import list_sheet_names

        preview_dir = Path(tempfile.gettempdir()) / "spc_upload_preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / uploads[0].name
        preview_path.write_bytes(uploads[0].getvalue())

        with c1:
            try:
                sheet_names = list_sheet_names(preview_path)
            except Exception as exc:
                sheet_names = []
                st.warning(f"시트 목록을 읽지 못했습니다: {exc}")

            if sheet_names == ["CSV"]:
                st.caption("CSV 파일 — 시트 선택 없음")
            elif sheet_names and not str(sheet_names[0]).startswith("("):
                if len(uploads) > 1:
                    st.caption(f"시트 목록: **{uploads[0].name}** 기준 (첫 번째 파일)")
                sheet_name = st.selectbox(
                    "Excel 시트 선택",
                    options=sheet_names,
                    key=f"excel_sheet_select_{uploads[0].name}",
                    help="원본 Excel에서 데이터가 있는 시트를 선택하세요. 변경 시 측정값·컬럼 미리보기가 갱신됩니다.",
                )
            elif sheet_names:
                st.warning(str(sheet_names[0]))

        from src.spc_streamlit.session_context import sync_upload_session

        upload_changed = sync_upload_session(uploads, sheet_name=sheet_name)
        if upload_changed:
            st.info(
                "새 데이터가 첨부되어 **이전 분석·Excel 다운로드 캐시**를 초기화했습니다. "
                "설정 후 **공정 안정성 점검 시작**을 다시 실행하세요."
            )

        preview_cache_key = f"excel_preview_v2_{uploads[0].name}_{sheet_name}_{len(uploads[0].getvalue())}"
        if preview_cache_key not in st.session_state:
            with st.spinner("파일 미리보기 로딩 중…"):
                st.session_state[preview_cache_key] = preview_excel_columns(
                    preview_path, sheet_name=sheet_name,
                )
        preview = st.session_state[preview_cache_key]
        if not hasattr(preview, "manual_value_options"):
            with st.spinner("파일 미리보기 갱신 중…"):
                st.session_state[preview_cache_key] = preview_excel_columns(
                    preview_path, sheet_name=sheet_name,
                )
            preview = st.session_state[preview_cache_key]
        value_column = render_value_column_picker(preview)
        mp_mode, mp_columns, mp_values = render_measurement_point_picker(
            preview, preview_path=preview_path,
        )
        if mp_columns:
            split_sel_key = _split_groups_session_key(uploads[0].name, mp_columns)
            if split_sel_key in st.session_state:
                mp_values = list(st.session_state[split_sel_key])
            elif mp_values:
                st.session_state[split_sel_key] = mp_values
        batch_split = mp_mode != "none" and bool(mp_columns)
        spec_mode, lsl, usl, per_split_spec, split_spec_limits = render_spec_limit_picker(
            preview,
            file_key=uploads[0].name,
            batch_split=batch_split,
            split_groups=mp_values,
        )
        if per_split_spec and preview_path is not None and mp_columns:
            mp_values, auto_group_specs = render_group_spec_selector(
                preview_path,
                preview,
                mp_columns,
                suggested_values=mp_values,
            )
            if auto_group_specs:
                split_spec_limits = {**split_spec_limits, **auto_group_specs}
            mp_mode = "manual"
        st.divider()
    else:
        with c1:
            st.caption("Excel을 업로드하면 **시트 목록**이 표시됩니다.")
        if st.session_state.get("upload_fingerprint"):
            from src.spc_streamlit.session_context import reset_session_for_new_upload

            reset_session_for_new_upload()
            st.session_state.pop("upload_fingerprint", None)

    with c2:
        st.info(
            "**점검 순서**\n\n"
            "① 데이터 분석\n"
            "② 정규성\n"
            "③ 관리도 해석\n"
            "④ 공정능력\n\n"
            "Case 1~4 자동 분기"
        )

    with st.expander("분석 조건", expanded=True):
        if not uploads:
            spec_mode, lsl, usl, per_split_spec, split_spec_limits = render_spec_limit_picker(
                None, file_key="no_file",
            )

        process = st.text_input("공정 필터", placeholder="예: 조립공정")
        characteristic = st.text_input("검사항목 필터", placeholder="비우면 자동 분리")

        r5, r6, r7, r8, r9 = st.columns(5)
        chart_label = r5.selectbox("관리도 유형", list(CHART_MAP.keys()))
        subgroup_size = r6.number_input("Subgroup 크기", 2, 10, 5)
        use_full_population = r8.checkbox(
            "전수 데이터",
            help="샘플링 없이 필터 후 전체 사용. σ_overall=STDEV.P",
        )
        n_subgroups = r7.number_input(
            "Subgroup 수",
            5,
            50,
            25,
            disabled=use_full_population,
            help="전수 모드: 데이터에서 자동 산출" if use_full_population else None,
        )
        stage_label = r9.selectbox("공정 단계", list(STAGE_MAP.keys()))

        boundary_mode_label = st.radio(
            "Subgroup 구성 조건",
            ["자동", "직접 지정"],
            horizontal=True,
            help="subgroup을 나눌 때 서로 섞지 않을 공정 조건을 설정합니다.",
        )
        manual_boundary_columns: list[str] = []
        boundary_column_options: list[str] = []
        boundary_column_resolve: dict[str, str] = {}
        if preview is not None and not preview.error:
            boundary_column_options = list(preview.boundary_column_options or [])
            boundary_column_resolve = dict(preview.boundary_column_resolve or {})
        if boundary_mode_label == "직접 지정":
            if not boundary_column_options:
                st.warning("Excel을 업로드하면 Raw data 컬럼명 목록이 표시됩니다.")
            manual_boundary_columns = st.multiselect(
                "분리 조건 — Raw data 컬럼 선택",
                boundary_column_options,
                default=[],
                placeholder="Excel 컬럼명 또는 교대·날짜(자동) 선택",
                help=(
                    "Excel 원본 헤더명 그대로 표시됩니다. "
                    "「교대 (시간대 자동)」은 측정일시 기준 주간/야간을 자동 채움 모드와 동일하게 적용합니다. "
                    "날짜/일시 컬럼 또는 「날짜 (측정일시에서)」 선택 시 일자별 분산 채취가 적용됩니다."
                ),
            )
            if manual_boundary_columns:
                from src.spc.sampler import is_date_like_boundary_column, boundary_column_display_name

                preview_df = preview.dataframe if hasattr(preview, "dataframe") else None
                date_pick = False
                if preview_df is not None:
                    date_pick = any(
                        is_date_like_boundary_column(
                            boundary_column_resolve.get(c, c), preview_df
                        )
                        for c in manual_boundary_columns
                    )
                else:
                    date_pick = any(
                        k in str(c) for c in manual_boundary_columns
                        for k in ("일", "date", "time", "시", "timestamp", "측정일시")
                    )
                display_labels = [
                    boundary_column_display_name(boundary_column_resolve.get(c, c))
                    for c in manual_boundary_columns
                ]
                st.caption(
                    f"적용 예정: **{' · '.join(display_labels)}** "
                    f"({'일자별 분산 채취' if date_pick else '블록 내 연속 채취'})"
                )
            elif boundary_column_options:
                st.warning("Raw data 컬럼을 1개 이상 선택하세요.")
        else:
            if preview is not None and not preview.error and preview.auto_boundary_columns:
                st.caption(
                    f"**자동 적용 컬럼:** {' · '.join(f'`{c}`' for c in preview.auto_boundary_columns)}"
                )
            else:
                st.caption("Excel 업로드 후 Raw data 컬럼 기준 자동 인식 결과가 표시됩니다.")

        r10, r11, r12 = st.columns(3)
        process_name = r10.text_input("공정명", "")
        machine_name = r11.text_input("라인명", "")
        process_change = r12.checkbox("공정 변경 감지")

        r13, r14 = st.columns(2)
        process_number = r13.text_input("공정번호", "")
        special_symbol = r14.text_input("특별특성(기호)", "")

        summary_column_options: list[str] = []
        summary_column_resolve: dict[str, str] = {}
        if preview is not None and not preview.error:
            summary_column_options = list(preview.columns or [])
            summary_column_resolve = dict(
                getattr(preview, "column_resolve", None) or preview.boundary_column_resolve or {}
            )
            for col in summary_column_options:
                summary_column_resolve.setdefault(col, col)

        _none_label = "(선택 안 함)"
        summary_measure_pick = _none_label
        summary_vehicle_pick = _none_label
        if summary_column_options:
            r15, r16 = st.columns(2)
            summary_measure_pick = r15.selectbox(
                "측정항목 — 원본 데이터 열",
                [_none_label, *summary_column_options],
                index=0,
                help="판정 요약표의 측정항목 열에 표시할 원본 데이터 열을 선택합니다.",
            )
            summary_vehicle_pick = r16.selectbox(
                "차종 — 원본 데이터 열",
                [_none_label, *summary_column_options],
                index=0,
                help="판정 요약표의 차종 열에 표시할 원본 데이터 열을 선택합니다.",
            )
        elif uploads:
            st.caption("원본 데이터 열 목록을 불러오는 중이거나 열 정보가 없습니다.")

        summary_measurement_column = None
        if summary_measure_pick != _none_label:
            summary_measurement_column = summary_column_resolve.get(
                summary_measure_pick, summary_measure_pick
            )
        summary_vehicle_column = None
        if summary_vehicle_pick != _none_label:
            summary_vehicle_column = summary_column_resolve.get(
                summary_vehicle_pick, summary_vehicle_pick
            )

        if not uploads:
            st.info("Excel 파일을 업로드하면 **측정값 후보 열** 목록이 위에 표시됩니다.")

    if st.button("🔍 공정 안정성 점검 시작", type="primary", use_container_width=True):
        if not uploads:
            st.error("Excel 파일을 업로드하세요.")
            return
        if split_spec_limits or (per_split_spec and mp_values):
            if not mp_values:
                st.error("데이터 분리 — 분석할 항목(그룹)을 1개 이상 선택하세요.")
                return
            check_specs = split_spec_limits
            if per_split_spec and not check_specs:
                check_specs = {g: (None, None) for g in mp_values}
            for g in mp_values:
                pair = check_specs.get(g)
                if pair is None or (pair[0] is None and pair[1] is None):
                    st.error(f"그룹 `{g}` — LSL 또는 USL을 입력하세요.")
                    return
                glsl, gusl = pair
                if glsl is not None and gusl is not None and glsl >= gusl:
                    st.error(f"그룹 `{g}` — LSL은 USL보다 작아야 합니다.")
                    return
        elif not per_split_spec:
            if spec_mode == "양측 공차" and lsl is not None and usl is not None and lsl >= usl:
                st.error("양측 공차: LSL은 USL보다 작아야 합니다.")
                return
            if spec_mode == "편측 — 상한치" and usl is None:
                st.error("상한치(USL)를 입력하세요.")
                return
            if spec_mode == "편측 — 하한치" and lsl is None:
                st.error("하한치(LSL)를 입력하세요.")
                return
        if boundary_mode_label == "직접 지정" and not manual_boundary_columns:
            st.error("Subgroup 구성 조건(Raw data 컬럼)을 1개 이상 선택하세요.")
            return
        if mp_mode == "manual" and not mp_values:
            st.error("데이터 분리 — 분석할 항목(그룹)을 1개 이상 선택하세요.")
            return
        if per_split_spec and not mp_values:
            st.error("그룹별 규격 확인 후 분석할 그룹이 없습니다.")
            return
        boundary_mode = "manual" if boundary_mode_label == "직접 지정" else "auto"
        boundary_columns_display = list(manual_boundary_columns) if boundary_mode == "manual" else []
        boundary_columns = [
            boundary_column_resolve.get(c, c) for c in manual_boundary_columns
        ] if boundary_mode == "manual" else []
        with st.spinner("채취 · 해석용 관리도 · 판정 엔진 실행 중..."):
            tmp = tempfile.mkdtemp()
            paths = []
            for uf in uploads:
                p = Path(tmp) / uf.name
                p.write_bytes(uf.getvalue())
                paths.append(p)
            from config.settings import OUTPUT_PATH
            from src.spc.path_utils import resolve_nested_output_dir

            analysis_output_dir = resolve_nested_output_dir(
                Path(OUTPUT_PATH),
                process_name=process_name or None,
                machine_name=machine_name or None,
            )
            try:
                bundle = run_spc_analysis(
                    paths,
                    usl=usl,
                    lsl=lsl,
                    spec_type=ui_spec_mode_to_type(spec_mode),
                    process=process or None,
                    characteristic=characteristic or None,
                    chart_type=CHART_MAP[chart_label],
                    subgroup_size=int(subgroup_size),
                    n_subgroups=int(n_subgroups),
                    use_full_population=use_full_population,
                    subgroup_boundary_mode=boundary_mode,
                    subgroup_boundary_columns=boundary_columns,
                    subgroup_boundary_columns_display=boundary_columns_display,
                    stage=STAGE_MAP[stage_label],
                    process_name=process_name or None,
                    machine_name=machine_name or None,
                    process_number=process_number or None,
                    special_characteristic_symbol=special_symbol or None,
                    summary_measurement_column=summary_measurement_column,
                    summary_vehicle_column=summary_vehicle_column,
                    process_change_detected=process_change,
                    sheet_name=sheet_name,
                    value_column=value_column,
                    measurement_point_mode=mp_mode,
                    measurement_point_column=mp_columns[0] if len(mp_columns) == 1 else None,
                    measurement_point_columns=mp_columns if len(mp_columns) >= 2 else None,
                    measurement_point_values=mp_values,
                    per_split_spec=per_split_spec,
                    split_spec_limits=split_spec_limits,
                    output_dir=analysis_output_dir,
                )
                st.session_state.bundle = bundle
                st.session_state.analysis_done = True
                _push_nav_history("data_analysis")
                st.session_state.nav_step = "data_analysis"
                from src.spc_streamlit.analysis_runner import list_analysis_targets
                from src.spc_streamlit.session_context import (
                    mark_analysis_upload_session,
                    reset_analysis_targets,
                    reset_extreme_value_session,
                    reset_export_session_state,
                )

                reset_export_session_state()
                mark_analysis_upload_session()
                reset_analysis_targets(list_analysis_targets(bundle.pipeline))
                reset_extreme_value_session(bundle.pipeline)
                st.rerun()
            except Exception as exc:
                st.error(f"분석 실패: {exc}")


def _page_data_analysis() -> None:
    render_step_header(2, "데이터 분석", "원본 데이터·채취 표본 및 측정 포인트별 분석 대상을 확인합니다.")
    bundle = st.session_state.bundle
    if bundle is None:
        st.warning("1) 데이터 입력에서 분석을 먼저 실행하세요.")
        return

    pipe = bundle.pipeline
    render_measurement_point_panel(pipe)

    _, active, analysis, decision, _ = _get_context()
    if not analysis or not decision or active is None or pipe is None:
        st.warning("분석 결과가 없습니다.")
        return

    render_active_target_banner(pipe, active)
    render_data_analysis_summary(active)
    render_value_extreme_panel(active)

    if pipe.is_batch and active.characteristic and decision:
        from src.spc.characteristic_split import format_split_label
        label = format_split_label(active.characteristic, pipe.split_column or "")
        st.markdown(f"#### 선택: {label}")

    tab_raw, tab_sample = st.tabs(["📋 원본 데이터 (필터 후)", "📌 채취 표본"])
    with tab_raw:
        render_filtered_data_with_sample_highlight(active)
    with tab_sample:
        if active.sample_df is not None and not active.sample_df.empty:
            from src.spc.sample_ordering import sort_sample_dataframe

            display_sample = sort_sample_dataframe(active.sample_df)
            st.dataframe(display_sample, use_container_width=True, height=400)
            st.caption(f"채취 {len(display_sample)}건 (시간순 정렬)")
        else:
            st.info("채취 표본이 없습니다.")


def _page_normality() -> None:
    render_step_header(3, "정규성 검정", "공정능력 해석의 분포 가정 및 후속조치를 확인합니다.")
    _, active, analysis, decision, _ = _get_context()
    if not analysis or not decision or active is None:
        st.warning("1) 데이터 입력에서 분석을 먼저 실행하세요.")
        return
    pipe = st.session_state.bundle.pipeline if st.session_state.bundle else None
    if pipe:
        render_active_target_banner(pipe, active)
    render_data_quality_panel(active)
    render_normality_panel(analysis, decision)

    st.subheader("정규성 검정 차트")
    render_normality_charts(active)

    st.divider()
    st.subheader("전문가 해석")
    st.write(decision.expert_commentary.normality_comment)

    st.divider()
    render_normality_transform_result(analysis, decision)

    from src.spc_streamlit.stratification_ui import render_mixed_distribution_rebuild_section

    render_mixed_distribution_rebuild_section(active, analysis, decision)


def _page_stability() -> None:
    render_step_header(
        4, "관리도 해석 (이상점 관리)",
        "통계적 관리 상태 · Raw Value 추적 · 이상점 상세",
    )
    _, active, analysis, decision, interp = _get_context()
    if not analysis or not decision or active is None or interp is None:
        st.warning("1) 데이터 입력에서 분석을 먼저 실행하세요.")
        return

    pipe = st.session_state.bundle.pipeline if st.session_state.bundle else None
    if pipe:
        render_active_target_banner(pipe, active)

    st.subheader("관리도 차트")
    render_control_chart_panel(active, decision)

    with st.expander("관리도 이상점 상세현황", expanded=False):
        render_anomaly_detail_status(active, analysis, decision)

    render_stability_trace_sections(active, analysis, decision)

    st.subheader("차트별 정량 해석")
    render_quantitative_insights(interp)

    with st.expander("상세 해석 · 개선 포인트"):
        render_dispersion_deferred_warning(decision)
        render_we_table(decision)
        if interp.pattern_narratives:
            st.markdown("**이상 패턴 해석**")
            for n in interp.pattern_narratives:
                st.markdown(n)
        target_key = str(active.characteristic or "single").replace(" ", "_")
        st.markdown("**현장 점검 체크리스트**")
        for i, item in enumerate(interp.operator_checklist):
            st.checkbox(item, key=f"op_chk_{target_key}_{i}")
        st.markdown("**공정 개선 포인트**")
        render_improvement_actions(interp)
        st.markdown(decision.expert_commentary.control_chart_comment)
        if decision.control_chart.is_stable:
            st.success(interp.cp_cpk_gate_message)
        else:
            st.error(interp.cp_cpk_gate_message)


def _page_capability() -> None:
    render_step_header(5, "공정능력 평가", "안정성·정규성 Case 1~4에 따른 공정능력 지표")
    _, active, analysis, decision, _ = _get_context()
    if not analysis or not decision or active is None:
        st.warning("1) 데이터 입력에서 분석을 먼저 실행하세요.")
        return

    pipe = st.session_state.bundle.pipeline if st.session_state.bundle else None
    if pipe:
        render_active_target_banner(pipe, active)

    cap = decision.capability
    if cap and cap.capability_case:
        st.markdown(f"**{cap.capability_case}** — `{cap.analysis_method}`")
        with st.expander("분석 기법 및 선정 사유"):
            st.write(cap.analysis_method_rationale)
            if cap.non_normal_applied and not cap.capability_on_transformed:
                st.caption("Percentile(Non-normal) 지표는 메트릭 아래 **참고**로 표시됩니다.")

    if decision.control_chart.is_stable:
        st.success("Stable (In Control)")
    else:
        st.error("Unstable — Pp/Ppk 중심 평가 (Cp/Cpk는 관리상태에서만 산출)")

    render_capability_panel(decision)
    render_capability_correlation_guide(decision)

    st.subheader("히스토그램")
    render_histogram_panel(active)

    st.divider()
    st.write(decision.expert_commentary.capability_comment)
    v = decision.verdict_summary
    norm = decision.normality
    import pandas as pd
    st.dataframe(
        pd.DataFrame([
            {"항목": "공정 상태", "결과": v.process_stability},
            {"항목": "분석 Case", "결과": cap.capability_case if cap else "-"},
            {"항목": "Pp/Ppk", "결과": _format_pp_ppk_summary(cap, norm)},
            {"항목": "Cp/Cpk", "결과": _format_cp_cpk_summary(cap)},
            {"항목": "공정 레벨", "결과": v.process_level},
            {"항목": "공정능력", "결과": v.capability_verdict},
        ]),
        hide_index=True,
        use_container_width=True,
    )


def _page_validation() -> None:
    render_step_header(
        7, "데이터 검증",
        "프로그램 산출값과 Excel 수식 계산값을 항목별로 대조합니다.",
    )
    _, active, analysis, decision, _ = _get_context()
    if not analysis or not decision or active is None:
        st.warning("1) 데이터 입력에서 분석을 먼저 실행하세요.")
        return

    pipe = st.session_state.bundle.pipeline if st.session_state.bundle else None
    if pipe:
        render_active_target_banner(pipe, active)

    st.caption(
        "구분 열은 **표본 통계 · 관리도 · 공정능력 · 정규성 검정** 상위 항목을 나타냅니다. "
        "일치=OK이면 프로그램과 Excel 수식 결과가 동일합니다."
    )
    render_validation_panel(active, analysis, decision)


def _page_conclusion() -> None:
    render_step_header(6, "결론", "Excel/PDF 종합 리포트 및 판정 종합")
    _, active, analysis, decision, interp = _get_context()
    if not analysis or not decision or active is None:
        st.warning("1) 데이터 입력에서 분석을 먼저 실행하세요.")
        return

    pipe = st.session_state.bundle.pipeline if st.session_state.bundle else None
    if pipe:
        render_active_target_banner(pipe, active)

    render_study_report_chart_grid(active)

    st.subheader("판정 요약")
    st.write(decision.expert_commentary.executive_summary)
    st.subheader("판정 종합(상세)")
    st.info(decision.expert_commentary.field_operator_comment)
    st.subheader("후속 조치")
    st.write(decision.expert_commentary.followup_action_comment)

    interp = interp or build_control_chart_interpretation(analysis, decision)
    with st.expander("관리도 해석 전문 (Markdown)"):
        st.markdown(interp.to_markdown())

    st.divider()
    render_report_downloads(active)
    if pipe:
        render_summary_table_download(pipe)
    else:
        render_summary_table_download(active)


def _page_glossary() -> None:
    st.markdown("### SPC 용어 및 개념")
    st.caption("용어_초보가이드 — Excel 보고서와 동일 내용")
    _, active, analysis, _, _ = _get_context()
    md = glossary_to_markdown(analysis)
    st.markdown(md)


def _page_rule_guide() -> None:
    render_spc_rule_guide_page()


def main() -> None:
    _init_session()
    inject_custom_css()
    _render_header_with_nav()
    step = _sidebar_nav()
    {
        "data": _page_data_input,
        "data_analysis": _page_data_analysis,
        "normality": _page_normality,
        "stability": _page_stability,
        "capability": _page_capability,
        "conclusion": _page_conclusion,
        "validation": _page_validation,
        "glossary": _page_glossary,
        "rule_guide": _page_rule_guide,
    }.get(step, _page_data_input)()


if __name__ == "__main__":
    main()
