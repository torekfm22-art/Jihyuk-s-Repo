"""유니투스 품질 표준인원 산출 시스템 - Streamlit 메인 앱."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from quality_mh.ai_analyzer import full_analysis  # noqa: E402
from quality_mh.calc_pipeline import run_calculation_pipeline  # noqa: E402
from quality_mh.database import (  # noqa: E402
    delete_quantitative_records,
    init_db,
    load_calc_results,
    load_freq_db,
    load_qualitative_records,
    load_quantitative_records,
    load_rules,
    save_freq_db,
    save_record,
)
from quality_mh.mh_program_exporter import export_mh_program_excel  # noqa: E402
from quality_mh.mh_program_importer import import_mh_program  # noqa: E402
from quality_mh.models import (  # noqa: E402
    FrequencyDB,
    FrequencyMethod,
    JudgmentStatus,
    QualitativeRecord,
    QuantitativeRecord,
    RoundingPolicy,
)
from quality_mh.plant_config import (  # noqa: E402
    PLANT_PRESETS,
    SHIFT_TYPES,
    PlantConfig,
    WG_CATEGORIES,
)
from quality_mh.ppt_exporter import export_ppt  # noqa: E402
from quality_mh.reference_guide import get_reference_sections  # noqa: E402
from quality_mh.rule_master import RuleMasterRegistry  # noqa: E402
from quality_mh.method_table import (  # noqa: E402
    FREQ_METHOD_DESC,
    entries_for_tool,
    entry_to_display_row,
    list_wg_values,
)
from quality_mh.mh_tool_engine import FG_STYLE_TASKS, calc_mh_tool_result, resolve_rule, unit_time_method_guide  # noqa: E402
from quality_mh.summary_engine import build_summary_report, simulate_production_change  # noqa: E402

# session keys
K_CONFIG = "plant_config"
K_RULES = "rules_registry"
K_FREQ = "freq_db_list"
K_QUANT = "quant_records"
K_QUAL = "qual_records"
K_CALC = "calc_results"
K_HISTORY = "yearly_history"
K_ADMIN = "is_admin"
K_DB = "db_initialized"
K_QUANT_EDIT = "quant_edit_id"
K_MH_TOOL_SEL = "mh_tool_selection"
K_MH_TOOL_RESULT = "mh_tool_last_result"

MONTH_LABELS = [f"{m}월" for m in range(1, 13)]
WG_OPTIONS = ["입고", "공정", "완성", "시험", "공통"]
ESTIMATION_METHODS = ["모답스", "관측법", "업무기준", "동작모듈화"]
FREQ_METHODS = ["생산계획 연동", "3개년 가중평균", "수행주기"]
CYCLE_TYPES = ["일간", "주간", "월간", "분기", "연간"]
QUAL_TASKS = ["OEM 상주원", "전진관리", "CS/RS", "고품분석"]
FREQ_METHOD_MAP = {
    "3개년 가중평균": FrequencyMethod.WEIGHTED_AVG,
    "생산계획 연동": FrequencyMethod.PLAN_LINKED,
    "수행주기": FrequencyMethod.PERIODIC,
}


def _list_index(options: list[str], value: str | None, default: int = 0) -> int:
    if value and value in options:
        return options.index(value)
    return default


def _freq_method_index(text: str | None) -> int:
    if not text:
        return 0
    compact = text.replace(" ", "")
    for i, method in enumerate(FREQ_METHODS):
        if method.replace(" ", "") in compact or compact in method.replace(" ", ""):
            return i
    if "가중" in text:
        return 1
    if "연동" in text or "생산" in text:
        return 0
    if "주기" in text:
        return 2
    return 0


def _persist_quantitative_record(
    cfg: PlantConfig,
    rule,
    *,
    existing: QuantitativeRecord | None,
    wg: str,
    sub_task: str,
    line: str | None,
    performers: float,
    unit_min: float,
    estimation: str,
    freq_method: str,
    cycle_type: str,
    annual_freq: float,
    data_source: str,
    remark: str,
) -> None:
    rec = QuantitativeRecord(
        record_id=existing.record_id if existing else f"R-{uuid.uuid4().hex[:8]}",
        plant=cfg.plant_name,
        wg=wg,
        task_code=rule.task_code,
        task_name=rule.task_name,
        sub_task=sub_task or None,
        line=line or None,
        line_group=existing.line_group if existing else None,
        performers=performers,
        unit_time_min=unit_min,
        current_headcount=existing.current_headcount if existing else 0.0,
        estimation_method=estimation,
        frequency_method_text=freq_method,
        cycle_type=cycle_type,
        annual_frequency=annual_freq if annual_freq > 0 else None,
        frequency_override=annual_freq if annual_freq > 0 else None,
        data_source=data_source or None,
        remark=remark or None,
        judgment_status=existing.judgment_status if existing else JudgmentStatus.CONFIRMED,
        hq_review=existing.hq_review if existing else None,
    )
    save_record(rec, "quantitative")
    fm = FREQ_METHOD_MAP[freq_method]
    freq_entry = FrequencyDB(
        task_code=rule.task_code,
        frequency_method=fm,
        cycle_type=cycle_type,
        cycle_count=annual_freq or 1.0,
        plan_qty=cfg.annual_production,
    )
    if fm == FrequencyMethod.PLAN_LINKED and annual_freq > 0 and cfg.annual_production > 0:
        freq_entry.ref_ratio = annual_freq / cfg.annual_production
        freq_entry.plan_qty = cfg.annual_production
    if fm == FrequencyMethod.PLAN_LINKED and cfg.annual_production > 0:
        freq_entry.ref_ratio = (annual_freq / cfg.annual_production) if annual_freq > 0 else 0.0
        freq_entry.plan_qty = cfg.annual_production
    save_freq_db(freq_entry)
    st.session_state[K_QUANT] = load_quantitative_records()
    st.session_state[K_FREQ] = load_freq_db()
    _recalc()

    # 방금 저장한 레코드 단건 즉시 계산 (검증 실패 시 UI 피드백용)
    fresh_results = {r.record_id: r for r in st.session_state[K_CALC]}
    if rec.record_id not in fresh_results:
        from quality_mh.validation import ValidationError, validate_record

        freq_map = {f.task_code: f for f in st.session_state[K_FREQ]}
        freq_db = freq_map.get(rule.task_code)
        try:
            if freq_db:
                validate_record(rec, rule, freq_db)
        except ValidationError as exc:
            st.session_state["_quant_last_save_error"] = str(exc)
            return
    st.session_state.pop("_quant_last_save_error", None)


def _init() -> None:
    if not st.session_state.get(K_DB):
        init_db()
        st.session_state[K_DB] = True
    if K_RULES not in st.session_state:
        st.session_state[K_RULES] = RuleMasterRegistry(load_rules())
    if K_FREQ not in st.session_state:
        st.session_state[K_FREQ] = load_freq_db()
    if K_QUANT not in st.session_state:
        st.session_state[K_QUANT] = load_quantitative_records()
    if K_QUAL not in st.session_state:
        st.session_state[K_QUAL] = load_qualitative_records()
    if K_CALC not in st.session_state:
        st.session_state[K_CALC] = load_calc_results()
    if K_CONFIG not in st.session_state:
        st.session_state[K_CONFIG] = PlantConfig()
    if K_HISTORY not in st.session_state:
        st.session_state[K_HISTORY] = {}
    if K_ADMIN not in st.session_state:
        st.session_state[K_ADMIN] = False


def _recalc() -> None:
    run_calculation_pipeline(
        st.session_state[K_QUANT],
        st.session_state[K_RULES],
        st.session_state[K_FREQ],
        st.session_state[K_CONFIG],
    )
    st.session_state[K_CALC] = load_calc_results()


def _quant_display_label(rec: QuantitativeRecord) -> str:
    parts = [rec.wg, rec.task_name]
    if rec.sub_task:
        parts.append(rec.sub_task)
    if rec.line:
        parts.append(f"라인:{rec.line}")
    return " · ".join(parts)


def _get_dataframe_row_selection(key: str) -> list[int]:
    """st.dataframe 행 선택 인덱스 (버전/위젯 차이 대응)."""
    state = st.session_state.get(key)
    if state is None:
        return []
    selection = state.get("selection", {}) if isinstance(state, dict) else getattr(state, "selection", None)
    if selection is None:
        return []
    if isinstance(selection, dict):
        return list(selection.get("rows", []) or [])
    return list(getattr(selection, "rows", []) or [])


def _show_formula_box(lines: list[str]) -> None:
    with st.expander("산출 근거 / 계산식 Trace", expanded=False):
        for line in lines:
            st.code(line, language=None)


# ─────────────────────────────────────────────
# ① 기본 정보 입력
# ─────────────────────────────────────────────
def page_basic_info() -> None:
    st.header("① 기본 정보 입력")
    cfg: PlantConfig = st.session_state[K_CONFIG]

    c1, c2, c3 = st.columns(3)
    with c1:
        preset = st.selectbox("공장명", PLANT_PRESETS, index=0)
        if preset == "사용자 정의":
            cfg.plant_name = st.text_input("공장명 직접입력", value=cfg.plant_name)
        else:
            cfg.plant_name = preset
    with c2:
        cfg.analysis_year = st.selectbox("분석년도", [2025, 2026, 2027], index=[2025, 2026, 2027].index(cfg.analysis_year) if cfg.analysis_year in [2025, 2026, 2027] else 0)
    with c3:
        cfg.work_hours_per_day = st.number_input(
            "1인당 근무시간 (hr/일)",
            min_value=1.0,
            max_value=12.0,
            value=float(cfg.work_hours_per_day),
            step=0.01,
            format="%.2f",
            help="예: 10.00, 9.33, 9.23, 8.00 — 공장별 실제 적용시간을 직접 입력",
        )

    st.info(f"연간 가용시간 = {cfg.work_hours_per_day} × 20일 × 12개월 = **{cfg.work_hours_per_year:,.1f} 시간**")

    c4, c5, c6 = st.columns(3)
    with c4:
        pct = st.selectbox("부가공수 (%)", [5, 10, 15, 20], index=[5, 10, 15, 20].index(int(cfg.allowance_rate * 100)) if int(cfg.allowance_rate * 100) in [5, 10, 15, 20] else 1)
        cfg.allowance_rate = pct / 100
    with c5:
        cfg.shift_type = st.selectbox("교대근무 조건", SHIFT_TYPES, index=SHIFT_TYPES.index(cfg.shift_type))
    with c6:
        cfg.use_even_shift_rounding = st.checkbox("교대근무 짝수 정수화", value=cfg.use_even_shift_rounding or cfg.shift_type in ("2교대", "3교대"))

    st.subheader("생산계획 (월별 EA)")
    df_prod = pd.DataFrame({
        "월": MONTH_LABELS,
        "생산량 (EA)": [float(cfg.monthly_production[m]) for m in range(12)],
    })
    edited_prod = st.data_editor(
        df_prod,
        use_container_width=False,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "월": st.column_config.TextColumn("월", disabled=True, width="small"),
            "생산량 (EA)": st.column_config.NumberColumn(
                "생산량 (EA)",
                min_value=0,
                step=1,
                format="%d",
                width="medium",
            ),
        },
        key="monthly_production_editor",
    )
    cfg.monthly_production = [float(v) for v in edited_prod["생산량 (EA)"].tolist()]
    st.metric("연간 생산량 합계", f"{sum(cfg.monthly_production):,.0f} EA")

    st.subheader("현재원 (W/G별)")
    hc_cols = st.columns(3)
    for i, cat in enumerate(WG_CATEGORIES):
        with hc_cols[i % 3]:
            cfg.current_headcount[cat] = st.number_input(f"현재원 — {cat}", min_value=0.0, value=float(cfg.current_headcount.get(cat, 0)), key=f"hc_{cat}")

    st.subheader("표준외 인원")
    ns_cols = st.columns(3)
    for i, label in enumerate(("그룹장", "파트장", "지원조")):
        with ns_cols[i]:
            cfg.non_standard_headcount[label] = st.number_input(label, min_value=0.0, value=float(cfg.non_standard_headcount.get(label, 0)), key=f"ns_{label}")

    st.session_state[K_CONFIG] = cfg

    st.divider()
    st.subheader("엑셀 데이터 가져오기")
    uploaded = st.file_uploader("MH Program.xlsx 업로드", type=["xlsx"], key="upload_basic")
    if uploaded and st.button("엑셀에서 불러오기", type="primary"):
        try:
            config, quant, qual, freq = import_mh_program(BytesIO(uploaded.getvalue()), st.session_state[K_RULES])
            for f in freq:
                save_freq_db(f)
            for r in quant:
                save_record(r, "quantitative")
            for r in qual:
                save_record(r, "qualitative")
            st.session_state[K_CONFIG] = config
            st.session_state[K_FREQ] = load_freq_db()
            st.session_state[K_QUANT] = load_quantitative_records()
            st.session_state[K_QUAL] = load_qualitative_records()
            _recalc()
            st.success(f"가져오기 완료 — 정량 {len(quant)}건, 정성 {len(qual)}건")
            st.rerun()
        except Exception as exc:
            st.error(f"가져오기 실패: {exc}")

    if st.button("설정 저장 및 전체 재계산", type="primary"):
        _recalc()
        st.success("저장 및 재계산 완료")
        st.rerun()


# ─────────────────────────────────────────────
# ② 정량 업무 M/H 분석 (상세)
# ─────────────────────────────────────────────
def page_quantitative() -> None:
    st.header("② 정량 업무 M/H 분석 (상세)")
    cfg: PlantConfig = st.session_state[K_CONFIG]
    registry: RuleMasterRegistry = st.session_state[K_RULES]
    records: list[QuantitativeRecord] = st.session_state[K_QUANT]
    results = {r.record_id: r for r in st.session_state[K_CALC]}

    st.caption(f"공장: {cfg.plant_name} | 근무시간 {cfg.work_hours_per_day}hr | 연간가용 {cfg.work_hours_per_year:,.0f}hr | 부가공수 {cfg.allowance_rate*100:.0f}%")

    wg_filter = st.selectbox("W/G 필터", ["전체"] + ["입고", "공정", "완성", "시험", "공통"])
    filtered = records if wg_filter == "전체" else [r for r in records if r.wg == wg_filter]

    if filtered:
        record_ids: list[str] = []
        rows = []
        for rec in filtered:
            record_ids.append(rec.record_id)
            calc = results.get(rec.record_id)
            rows.append({
                "W/G": rec.wg,
                "업무항목": rec.task_name,
                "업무명": rec.sub_task or "",
                "산정기준": rec.estimation_method or "",
                "단위시간(분)": rec.unit_time_min,
                "발생빈도": rec.annual_frequency or (calc.final_frequency if calc else ""),
                "표준공수": round(calc.standard_mh, 4) if calc else "",
                "표준인원": calc.standard_headcount if calc else "",
            })

        st.caption("행 클릭 선택 후 삭제 · 수정은 아래 목록에서 선택 후 「수정 불러오기」")
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            height=350,
            on_select="rerun",
            selection_mode="multi-row",
            key="quant_dataframe",
        )

        sel_rows = _get_dataframe_row_selection("quant_dataframe")
        default_edit_idx = sel_rows[0] if len(sel_rows) == 1 else 0

        btn_del, info_col = st.columns([1, 4])
        with btn_del:
            if st.button(
                "선택 행 삭제",
                type="secondary",
                disabled=not sel_rows,
                use_container_width=True,
            ):
                ids = [record_ids[i] for i in sel_rows if i < len(record_ids)]
                delete_quantitative_records(ids)
                st.session_state[K_QUANT] = load_quantitative_records()
                st.session_state[K_CALC] = load_calc_results()
                st.session_state.pop("quant_dataframe", None)
                if st.session_state.get(K_QUANT_EDIT) in ids:
                    st.session_state.pop(K_QUANT_EDIT, None)
                st.success(f"{len(ids)}건 삭제 완료")
                st.rerun()
        with info_col:
            if sel_rows:
                st.caption(f"테이블 선택: {len(sel_rows)}건")

        pick_col, load_col = st.columns([4, 1])
        with pick_col:
            edit_idx = st.selectbox(
                "수정할 업무",
                range(len(filtered)),
                index=min(default_edit_idx, len(filtered) - 1),
                format_func=lambda i: _quant_display_label(filtered[i]),
                key="quant_edit_pick",
            )
        with load_col:
            st.write("")
            st.write("")
            if st.button("수정 불러오기", type="primary", use_container_width=True):
                st.session_state[K_QUANT_EDIT] = filtered[edit_idx].record_id
                st.rerun()

        if len(sel_rows) == 1:
            calc = results.get(record_ids[sel_rows[0]])
            if calc:
                rec = filtered[sel_rows[0]]
                st.markdown(f"**산출 근거** — {rec.wg} · {rec.task_name}" + (f" · {rec.sub_task}" if rec.sub_task else ""))
                _show_formula_box(calc.calc_log)
        elif len(sel_rows) > 1:
            st.caption("산출 근거는 행 1건만 선택했을 때 표시됩니다.")
    else:
        st.info("정량 레코드가 없습니다. 아래에서 신규 추가하거나 엑셀을 가져오세요.")

    st.divider()
    edit_id = st.session_state.get(K_QUANT_EDIT)
    edit_rec = next((r for r in records if r.record_id == edit_id), None) if edit_id else None
    if edit_id and not edit_rec:
        st.session_state.pop(K_QUANT_EDIT, None)
        edit_rec = None

    st.subheader("신규 / 수정 입력")
    if edit_rec:
        title = f"{edit_rec.wg} · {edit_rec.task_name}"
        if edit_rec.sub_task:
            title += f" · {edit_rec.sub_task}"
        st.info(f"**수정 모드** — {title}")
        if st.button("신규 작성으로 전환", key="quant_clear_edit"):
            st.session_state.pop(K_QUANT_EDIT, None)
            st.session_state.pop("q_line", None)
            st.rerun()

    prefill_wg = edit_rec.wg if edit_rec else WG_OPTIONS[0]

    with st.form("quant_form"):
        fc1, fc2 = st.columns(2)
        wg = fc1.selectbox(
            "W/G",
            WG_OPTIONS,
            index=_list_index(WG_OPTIONS, prefill_wg),
        )
        rules = [r for r in registry.get_quantitative_rules() if r.wg == wg]
        task_labels = [f"{r.task_name} ({r.task_code})" for r in rules]
        task_idx = 0
        if edit_rec and wg == edit_rec.wg:
            for i, r in enumerate(rules):
                if r.task_code == edit_rec.task_code:
                    task_idx = i
                    break
        task_sel = fc1.selectbox(
            "업무항목",
            task_labels if task_labels else ["—"],
            index=task_idx if task_labels else 0,
        )
        rule = rules[task_labels.index(task_sel)] if task_labels else None

        line = fc2.text_input("라인", value=edit_rec.line or "" if edit_rec else "")
        sub_task = fc2.text_input("업무명 (세부)", value=edit_rec.sub_task or "" if edit_rec else "")
        estimation = fc1.selectbox(
            "산정기준",
            ESTIMATION_METHODS,
            index=_list_index(ESTIMATION_METHODS, edit_rec.estimation_method if edit_rec else None),
        )
        freq_method = fc2.selectbox(
            "발생빈도 방식",
            FREQ_METHODS,
            index=_freq_method_index(edit_rec.frequency_method_text if edit_rec else None),
        )

        fc3, fc4, fc5 = st.columns(3)
        unit_min = fc3.number_input(
            "단위시간 (분)",
            min_value=0.1,
            value=float(edit_rec.unit_time_min if edit_rec else 30.0),
        )
        performers = fc4.number_input(
            "수행인원 (명)",
            min_value=0.1,
            value=float(edit_rec.performers if edit_rec else 1.0),
        )
        freq_val = 0.0
        if edit_rec:
            freq_val = float(
                edit_rec.annual_frequency
                or edit_rec.frequency_override
                or 0.0
            )
        annual_freq = fc5.number_input("발생빈도", min_value=0.0, value=freq_val)
        cycle_type = fc3.selectbox(
            "수행주기",
            CYCLE_TYPES,
            index=_list_index(CYCLE_TYPES, edit_rec.cycle_type if edit_rec else None),
        )
        data_source = fc4.text_input("근거자료", value=edit_rec.data_source or "" if edit_rec else "")
        remark = fc5.text_input("비고", value=edit_rec.remark or "" if edit_rec else "")

        submit_label = "수정 저장 및 계산" if edit_rec else "등록 및 계산"
        submitted = st.form_submit_button(submit_label, type="primary")
        if submitted and rule:
            if annual_freq <= 0:
                st.error("발생빈도를 0보다 크게 입력해 주세요.")
            else:
                _persist_quantitative_record(
                    cfg,
                    rule,
                    existing=edit_rec,
                    wg=wg,
                    sub_task=sub_task,
                    line=line or None,
                    performers=performers,
                    unit_min=unit_min,
                    estimation=estimation,
                    freq_method=freq_method,
                    cycle_type=cycle_type,
                    annual_freq=annual_freq,
                    data_source=data_source,
                    remark=remark,
                )
                err = st.session_state.pop("_quant_last_save_error", None)
                if err:
                    st.error(f"산출 실패: {err}")
                else:
                    st.session_state.pop(K_QUANT_EDIT, None)
                    st.success("수정 완료" if edit_rec else "등록 및 산출 완료")
                    st.rerun()


# ─────────────────────────────────────────────
# ③ 정성 업무 M/H 분석 (상세)
# ─────────────────────────────────────────────
def page_qualitative() -> None:
    st.header("③ 정성 업무 M/H 분석 (상세)")
    cfg: PlantConfig = st.session_state[K_CONFIG]
    records: list[QualitativeRecord] = st.session_state[K_QUAL]
    plant_records = [r for r in records if r.plant == cfg.plant_name] or records

    if plant_records:
        df = pd.DataFrame([{
            "공장": r.plant,
            "W/G": r.wg,
            "업무항목": r.task_name,
            "업무정의": r.task_definition or "",
            "업무내용": (r.workload_desc or "")[:80],
            "표준인원(명)": r.standard_headcount,
            "현재인원": r.current_headcount,
            "차이": r.standard_headcount - r.current_headcount,
        } for r in plant_records])
        st.dataframe(df, use_container_width=True)
        st.metric("정성 표준인원 합계", f"{sum(r.standard_headcount for r in plant_records)}명")
    else:
        st.info("정성 레코드가 없습니다.")

    st.divider()
    with st.form("qual_form"):
        c1, c2 = st.columns(2)
        task = c1.selectbox("업무항목", QUAL_TASKS + ["기타"])
        custom_task = c1.text_input("기타 업무명") if task == "기타" else ""
        wg = c2.text_input("W/G", value="공통")
        task_def = c2.text_area("업무 정의")
        workload = c1.text_area("업무 설명 (상세)")
        reason = c2.text_input("필요 사유")
        std_hc = c1.number_input("표준인원 (명)", min_value=0, value=1)
        cur_hc = c2.number_input("현재인원 (명)", min_value=0, value=1)
        attach = c1.file_uploader("근거자료 첨부", type=["pdf", "xlsx", "png", "jpg"])

        if st.form_submit_button("저장", type="primary"):
            name = custom_task if task == "기타" else task
            rec = QualitativeRecord(
                record_id=f"QL-{uuid.uuid4().hex[:8]}",
                plant=cfg.plant_name,
                wg=wg,
                task_name=name,
                task_definition=task_def or None,
                workload_desc=workload or None,
                standard_headcount=int(std_hc),
                current_headcount=int(cur_hc),
                diff=int(std_hc) - int(cur_hc),
                selection_reason=reason or None,
                remark=f"첨부: {attach.name}" if attach else None,
            )
            save_record(rec, "qualitative")
            st.session_state[K_QUAL] = load_qualitative_records()
            st.rerun()


# ─────────────────────────────────────────────
# ④ M/H 분석 결과 (종합)
# ─────────────────────────────────────────────
def page_summary() -> None:
    st.header("④ M/H 분석 결과 (종합)")
    cfg: PlantConfig = st.session_state[K_CONFIG]
    calc_results = st.session_state[K_CALC]
    qualitative = st.session_state[K_QUAL]

    if not calc_results:
        st.warning("계산 결과가 없습니다. 기본정보 입력 후 재계산하세요.")
        return

    report = build_summary_report(cfg, calc_results, qualitative)
    st.subheader(f"■ {cfg.plant_name} 품질 M/H 분석 ({cfg.analysis_year})")
    st.caption(f"근무시간 {cfg.work_hours_per_day}hr/일 | 연간가용 {report.annual_available_hours:,.0f}hr | 부가공수 {report.allowance_rate*100:.0f}%")

    # 현황 요약 테이블 (엑셀 종합 시트 틀)
    st.markdown("##### 현황 요약")
    summary_rows = []
    for qr in report.quantitative_rows:
        if qr.sub_label in ("입고", "공정", "완성", "시험", "合"):
            summary_rows.append({
                "구분": "표준" if qr.sub_label != "合" else "표준",
                "업무항목": "정 량" if qr.sub_label != "合" else "정 량 合",
                "세부": qr.sub_label,
                "현재원": qr.current,
                "표준인원": round(qr.standard, 2),
                "차이": round(qr.diff, 2),
                "비고": qr.comment,
            })
    if report.qualitative_row:
        q = report.qualitative_row
        summary_rows.append({"구분": "표준", "업무항목": "정 성 合", "세부": "", "현재원": q.current, "표준인원": q.standard, "차이": q.diff, "비고": ""})
    if report.total_row:
        t = report.total_row
        summary_rows.append({"구분": "표준外", "업무항목": "총 계", "세부": "", "현재원": t.current, "표준인원": round(t.standard, 2), "차이": round(t.diff, 2), "비고": ""})
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

    # Gap 분석
    st.markdown("##### Gap 분석")
    for comment in report.gap_comments:
        st.warning(comment)
    if not report.gap_comments:
        st.success("현재원과 표준인원 차이가 허용 범위 내입니다.")

    tab1, tab2, tab3, tab4 = st.tabs(["Pareto TOP10", "전년도 비교", "생산량 시뮬레이션", "AI 분석"])

    with tab1:
        if report.pareto:
            df_p = pd.DataFrame(report.pareto)
            fig = px.bar(df_p, x="업무", y="표준공수", color="W/G", title="M/H 비중 TOP10", text="비중(%)")
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_p, use_container_width=True)

    with tab2:
        hist: dict = st.session_state[K_HISTORY]
        year_key = str(cfg.analysis_year)
        hist[year_key] = {
            "mh": sum(r.standard_mh for r in calc_results),
            "headcount": sum(r.standard_headcount for r in calc_results) + sum(r.standard_headcount for r in qualitative),
            "current": sum(cfg.current_headcount.get(c, 0) for c in ["입고", "공정", "완성", "시험", "정성"]),
        }
        st.session_state[K_HISTORY] = hist
        if len(hist) >= 1:
            df_t = pd.DataFrame(hist).T.reset_index().rename(columns={"index": "연도"})
            fig2 = px.line(df_t, x="연도", y=["mh", "headcount", "current"], markers=True, title="연도별 추이")
            st.plotly_chart(fig2, use_container_width=True)
        st.caption("매년 분석 시 자동 누적됩니다. 이전 연도 데이터는 엑셀 가져오기로 추가 가능합니다.")

    with tab3:
        pct = st.slider("생산량 변화율 (%)", -30, 30, 10)
        sim = simulate_production_change(cfg, calc_results, pct)
        c1, c2, c3 = st.columns(3)
        c1.metric("현재 표준인원", sim["base_headcount"])
        c2.metric(f"시뮬({pct:+.0f}%)", sim["simulated_headcount"])
        c3.metric("인원 변화", f"{sim['delta_headcount']:+d}명")
        if sim["details"]:
            st.dataframe(pd.DataFrame(sim["details"]), use_container_width=True)

    with tab4:
        analysis = full_analysis(cfg, calc_results, qualitative)
        st.markdown("**M/H TOP5**")
        st.dataframe(pd.DataFrame(analysis["top5_mh"]), use_container_width=True)
        st.markdown("**표준인원 영향도 TOP5**")
        st.dataframe(pd.DataFrame(analysis["headcount_impact"]), use_container_width=True)
        st.markdown("**과부족 원인 분석**")
        for cause in analysis["gap_causes"]:
            st.write(f"- {cause}")

    st.divider()
    st.subheader("보고서 출력")
    col1, col2 = st.columns(2)
    with col1:
        xls_buf = export_mh_program_excel(cfg, calc_results, st.session_state[K_QUANT], qualitative, report)
        st.download_button(
            "Excel 다운로드 (종합/정량/정성/정수화/그래프)",
            data=xls_buf,
            file_name=f"품질MH_{cfg.plant_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        ppt_buf = export_ppt(cfg, calc_results, qualitative, report)
        st.download_button(
            "PowerPoint 다운로드",
            data=ppt_buf,
            file_name=f"품질MH_{cfg.plant_name}_{datetime.now().strftime('%Y%m%d')}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )


# ─────────────────────────────────────────────
# M/H 산출 Tool
# ─────────────────────────────────────────────
def _default_fg_products() -> list[str]:
    return ["리어램프", "리어센터", "센터램프", "헤드램프"]


def page_mh_tool() -> None:
    st.header("M/H 산출 Tool")
    st.caption("method table 기준 · 수행주기 제외 · 단위시간 직접기입 · 발생빈도 자동 산출")

    cfg: PlantConfig = st.session_state[K_CONFIG]
    registry: RuleMasterRegistry = st.session_state[K_RULES]

    wg_filter = st.selectbox("W/G 필터", ["전체"] + list_wg_values(), key="mh_tool_wg_filter")
    tool_entries = entries_for_tool(wg_filter=wg_filter)
    if not tool_entries:
        st.warning("선택한 W/G에 해당하는 Tool 대상 업무가 없습니다.")
        return

    st.subheader("업무 목록 (산정방법 매핑)")
    st.dataframe(
        pd.DataFrame([entry_to_display_row(e) for e in tool_entries]),
        use_container_width=True,
        height=280,
        hide_index=True,
    )

    labels = [f"{e.wg} · {e.task_name}" for e in tool_entries]
    prev_sel = st.session_state.get(K_MH_TOOL_SEL)
    default_idx = 0
    if prev_sel in labels:
        default_idx = labels.index(prev_sel)

    selected_label = st.selectbox("산출할 업무 선택", labels, index=default_idx, key="mh_tool_task_pick")
    st.session_state[K_MH_TOOL_SEL] = selected_label
    entry = tool_entries[labels.index(selected_label)]
    rule = resolve_rule(registry, entry)

    if not rule:
        st.error(f"업무 마스터에 '{entry.task_name}' 항목이 없습니다.")
        return

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**단위시간 산정방법:** {entry.unit_time_method}")
        st.info(unit_time_method_guide(entry.unit_time_method))
        unit_min = st.number_input(
            "단위시간 (분) — 직접 기입",
            min_value=0.1,
            value=30.0,
            step=0.1,
            key=f"mh_ut_{entry.key}",
        )
    with c2:
        st.markdown(f"**발생빈도 산정방법:** {entry.frequency_method}")
        st.info(FREQ_METHOD_DESC.get(entry.frequency_method, entry.frequency_method))
        if entry.remark:
            st.caption(f"비고: {entry.remark}")

    freq_inputs: dict = {}
    st.subheader("발생빈도 산정 입력")

    if entry.frequency_method == "3개년 가중평균":
        st.caption("전년(Y-1)·전전년(Y-2)·전전전년(Y-3) 실적 — 가중치 기본 5:3:2")
        yc1, yc2, yc3 = st.columns(3)
        freq_inputs["y1"] = yc1.number_input(
            f"Y-1 ({cfg.analysis_year - 1}년) 실적",
            min_value=0.0,
            value=0.0,
            key=f"mh_y1_{entry.key}",
        )
        freq_inputs["y2"] = yc2.number_input(
            f"Y-2 ({cfg.analysis_year - 2}년) 실적",
            min_value=0.0,
            value=0.0,
            key=f"mh_y2_{entry.key}",
        )
        freq_inputs["y3"] = yc3.number_input(
            f"Y-3 ({cfg.analysis_year - 3}년) 실적",
            min_value=0.0,
            value=0.0,
            key=f"mh_y3_{entry.key}",
        )
        wc1, wc2, wc3 = st.columns(3)
        freq_inputs["w1"] = wc1.number_input("가중치 Y-1", min_value=0.1, value=5.0, key=f"mh_w1_{entry.key}")
        freq_inputs["w2"] = wc2.number_input("가중치 Y-2", min_value=0.1, value=3.0, key=f"mh_w2_{entry.key}")
        freq_inputs["w3"] = wc3.number_input("가중치 Y-3", min_value=0.1, value=2.0, key=f"mh_w3_{entry.key}")

    elif entry.frequency_method == "생산계획 연동":
        use_fg = entry.task_name in FG_STYLE_TASKS
        mode = st.radio(
            "산출 양식",
            ["FG 유형별 (완성품 검사 등)", "단순 연동 (전년 합계 비율)"] if use_fg else ["단순 연동 (전년 합계 비율)"],
            key=f"mh_pl_mode_{entry.key}",
        )
        st.caption(
            f"당해년({cfg.analysis_year}) 생산계획은 ① 기본정보 월별 생산량 사용 · "
            f"연간 합계 {cfg.annual_production:,.0f} EA"
        )

        if use_fg and mode.startswith("FG"):
            freq_inputs["use_fg_style"] = True
            st.markdown(f"**전년({cfg.analysis_year - 1}) 월별 검사수량 — 유형별**")
            products = _default_fg_products()
            month_cols = [f"{m}월" for m in range(1, 13)]
            prior_rows = []
            for p in products:
                row = {"유형": p}
                for m in month_cols:
                    row[m] = 0.0
                prior_rows.append(row)
            prior_df = st.data_editor(
                pd.DataFrame(prior_rows),
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                key=f"mh_prior_prod_{entry.key}",
            )
            freq_inputs["prior_monthly_by_product"] = {
                row["유형"]: [float(row[m]) for m in month_cols]
                for _, row in prior_df.iterrows()
            }

            st.markdown(f"**전년({cfg.analysis_year - 1}) 월별 생산실적**")
            prior_prod_df = pd.DataFrame({
                "월": month_cols,
                "생산실적 (EA)": [0.0] * 12,
            })
            edited_prior_prod = st.data_editor(
                prior_prod_df,
                use_container_width=False,
                hide_index=True,
                num_rows="fixed",
                key=f"mh_prior_plan_{entry.key}",
            )
            freq_inputs["prior_monthly_production"] = [
                float(v) for v in edited_prior_prod["생산실적 (EA)"].tolist()
            ]
            freq_inputs["ratio_months"] = st.number_input(
                "비율 평균에 사용할 전년 월 수 (공백=전체)",
                min_value=1,
                max_value=12,
                value=8,
                help="FG 양식: 1~8월 실적 기준 평균비율 (AVERAGE)",
                key=f"mh_ratio_mo_{entry.key}",
            )
        else:
            freq_inputs["use_fg_style"] = False
            pc1, pc2 = st.columns(2)
            freq_inputs["prior_inspection_total"] = pc1.number_input(
                f"전년({cfg.analysis_year - 1}) 검사수량 합계",
                min_value=0.0,
                value=0.0,
                key=f"mh_prior_ins_{entry.key}",
            )
            freq_inputs["prior_production_total"] = pc2.number_input(
                f"전년({cfg.analysis_year - 1}) 생산실적 합계",
                min_value=0.0,
                value=cfg.annual_production if cfg.annual_production > 0 else 0.0,
                key=f"mh_prior_prod_sum_{entry.key}",
            )

    st.divider()
    if st.button("M/H 산출 실행", type="primary", key=f"mh_calc_{entry.key}"):
        try:
            frequency, calc_log, factors, result = calc_mh_tool_result(
                entry=entry,
                rule=rule,
                config=cfg,
                unit_time_min=unit_min,
                freq_inputs=freq_inputs,
            )
            st.session_state[K_MH_TOOL_RESULT] = {
                "label": selected_label,
                "frequency": frequency,
                "calc_log": calc_log,
                "factors": factors,
                "result": result,
                "entry_key": entry.key,
                "unit_min": unit_min,
            }
        except Exception as exc:
            st.error(f"산출 실패: {exc}")

    last = st.session_state.get(K_MH_TOOL_RESULT)
    if last and last.get("entry_key") == entry.key:
        result = last["result"]
        st.subheader("산출 결과")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("발생빈도 (연간)", f"{last['frequency']:,.2f}")
        m2.metric("표준작업시간 (hr)", f"{result.standard_work_time_hr:,.2f}")
        m3.metric("표준공수 (M/H)", f"{result.standard_mh:.4f}")
        m4.metric("표준인원", f"{result.standard_headcount}명")

        if entry.frequency_method == "생산계획 연동" and last["factors"].get("monthly_forecast_by_product"):
            st.markdown("**월별 검사 예상 (유형별)**")
            forecast = last["factors"]["monthly_forecast_by_product"]
            fc_df = pd.DataFrame(forecast)
            fc_df.index = [f"{i + 1}월" for i in range(len(next(iter(forecast.values()))))]
            st.dataframe(fc_df.style.format("{:,.1f}"), use_container_width=True)

        _show_formula_box(last["calc_log"])

        if st.button("② 정량 업무에 반영", key=f"mh_apply_{entry.key}"):
            _persist_quantitative_record(
                cfg,
                rule,
                existing=None,
                wg=entry.wg,
                sub_task="",
                line=None,
                performers=1.0,
                unit_min=last["unit_min"],
                estimation=entry.unit_time_method,
                freq_method=entry.frequency_method,
                cycle_type="연간",
                annual_freq=last["frequency"],
                data_source="M/H 산출 Tool",
                remark=entry.remark or None,
            )
            err = st.session_state.pop("_quant_last_save_error", None)
            if err:
                st.error(f"반영 실패: {err}")
            else:
                st.success("② 정량 업무 M/H 분석에 등록되었습니다.")
                st.rerun()


# ─────────────────────────────────────────────
# ⑤ 업무 정의 및 M/H 산정 기준
# ─────────────────────────────────────────────
def page_reference() -> None:
    st.header("⑤ 업무 정의 및 M/H 산정 기준")
    st.caption("품질 업무 및 인원 표준 Rev.01 | MH Std.pptx 기준")

    admin = st.checkbox("관리자 모드 (가이드 수정)", value=st.session_state[K_ADMIN])
    st.session_state[K_ADMIN] = admin

    sections = get_reference_sections()
    for sec in sections:
        with st.expander(sec["title"], expanded=sec["title"].startswith("1.")):
            if admin:
                new_content = st.text_area(f"내용 수정 — {sec['title']}", value=sec["content"], height=200, key=f"ref_{sec['title']}")
                sec["content"] = new_content
            st.markdown(sec["content"])

    st.divider()
    st.subheader("업무 마스터 (36개 정량 + 4개 정성)")
    registry: RuleMasterRegistry = st.session_state[K_RULES]
    rules_df = pd.DataFrame([{
        "코드": r.task_code,
        "W/G": r.wg,
        "업무항목": r.task_name,
        "유형": r.task_type.value,
        "발생빈도방식": r.frequency_method.value,
        "부가공수": r.default_allowance_rate,
    } for r in registry.get_all()])
    st.dataframe(rules_df, use_container_width=True, height=300)


def main() -> None:
    st.set_page_config(
        page_title="품질 표준인원 산출 시스템",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init()

    st.sidebar.title("품질 M/H 분석")
    st.sidebar.caption("유니투스 품질 표준인원 산출 시스템")
    cfg: PlantConfig = st.session_state[K_CONFIG]
    st.sidebar.metric("공장", cfg.plant_name)
    st.sidebar.metric("분석년도", cfg.analysis_year)
    st.sidebar.metric("연간가용시간", f"{cfg.work_hours_per_year:,.0f}hr")

    pages = {
        "① 기본 정보 입력": page_basic_info,
        "M/H 산출 Tool": page_mh_tool,
        "② 정량 업무 M/H 분석": page_quantitative,
        "③ 정성 업무 M/H 분석": page_qualitative,
        "④ M/H 분석 결과 (종합)": page_summary,
        "⑤ 업무 정의 및 M/H 산정 기준": page_reference,
    }
    choice = st.sidebar.radio("메뉴", list(pages.keys()))
    pages[choice]()


if __name__ == "__main__":
    main()
