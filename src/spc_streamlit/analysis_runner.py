"""Streamlit — SPC 분석 실행 (업로드 파일 → Pipeline)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import OUTPUT_PATH
from src.spc.characteristic_split import normalize_split_value
from src.spc.control_chart_interpreter import ControlChartInterpretation, build_control_chart_interpretation
from src.spc.pipeline import SpcJobConfig, SpcPipeline, SpcPipelineResult


@dataclass
class StreamlitAnalysisBundle:
    """Streamlit UI용 분석 결과 묶음."""

    pipeline: SpcPipelineResult
    interpretation: ControlChartInterpretation
    interpretations: dict[str, ControlChartInterpretation] = field(default_factory=dict)


def _split_key(characteristic: str | None) -> str:
    return normalize_split_value(characteristic) if characteristic else ""


def list_analysis_targets(pipe: SpcPipelineResult) -> list[str]:
    """배치 분석 시 선택 가능한 대상 키 목록 (중첩 배치 포함)."""
    if not pipe.is_batch:
        return []

    out: list[str] = []
    for child in pipe.split_results:
        if child.is_batch:
            for sub in child.split_results:
                if sub.characteristic:
                    out.append(sub.characteristic)
        elif child.characteristic:
            out.append(child.characteristic)
    return out


def _find_active_in_pipe(pipe: SpcPipelineResult, target: str | None) -> SpcPipelineResult | None:
    if not pipe.is_batch:
        return pipe
    norm_target = _split_key(target)
    if not norm_target:
        return pipe.split_results[0] if pipe.split_results else pipe
    for child in pipe.split_results:
        if child.is_batch:
            for sub in child.split_results:
                if _split_key(sub.characteristic) == norm_target:
                    return sub
        elif _split_key(child.characteristic) == norm_target:
            return child
    return pipe.split_results[0] if pipe.split_results else pipe


def get_active_result(pipe: SpcPipelineResult, characteristic: str | None = None) -> SpcPipelineResult:
    """배치 분석 시 선택 항목·포인트에 해당하는 결과 반환."""
    if not pipe.is_batch:
        return pipe
    return _find_active_in_pipe(pipe, characteristic) or pipe


def get_interpretation(
    bundle: StreamlitAnalysisBundle,
    active: SpcPipelineResult,
) -> ControlChartInterpretation:
    """선택 대상에 맞는 관리도 해석 (캐시 또는 재생성)."""
    key = _split_key(active.characteristic)
    if key and key in bundle.interpretations:
        return bundle.interpretations[key]
    if active.analysis is None or active.decision is None:
        return bundle.interpretation
    return build_control_chart_interpretation(active.analysis, active.decision)


def _build_interpretation_map(pipe: SpcPipelineResult) -> dict[str, ControlChartInterpretation]:
    out: dict[str, ControlChartInterpretation] = {}

    def _add(result: SpcPipelineResult) -> None:
        if result.analysis is None or result.decision is None:
            return
        key = _split_key(result.characteristic)
        if key:
            out[key] = build_control_chart_interpretation(result.analysis, result.decision)

    if not pipe.is_batch:
        _add(pipe)
        return out
    for child in pipe.split_results:
        if child.is_batch:
            for sub in child.split_results:
                _add(sub)
        else:
            _add(child)
    return out


def _build_condition_mask(
    filtered_df: pd.DataFrame,
    split_columns: list[str],
    group_key: str,
) -> pd.Series:
    parts = str(group_key).split("|")
    mask = pd.Series(True, index=filtered_df.index)
    for col, val in zip(split_columns, parts):
        if col not in filtered_df.columns:
            continue
        mask &= filtered_df[col].astype(str).fillna("").eq(str(val))
    return mask


def run_spc_analysis(
    uploaded_paths: list[Path],
    *,
    usl: float | None = None,
    lsl: float | None = None,
    spec_type: str | None = None,
    process: str | None = None,
    characteristic: str | None = None,
    item: str | None = None,
    chart_type: str = "auto",
    subgroup_size: int = 5,
    n_subgroups: int = 25,
    sampling_method: str = "consecutive",
    imr_sampling_unit: str = "auto",
    stage: str = "mass_production",
    process_name: str | None = None,
    machine_name: str | None = None,
    special_characteristic: bool = False,
    process_change_detected: bool = False,
    use_full_population: bool = False,
    subgroup_boundary_mode: str = "auto",
    subgroup_boundary_keys: list[str] | None = None,
    subgroup_boundary_columns: list[str] | None = None,
    subgroup_boundary_columns_display: list[str] | None = None,
    output_dir: Path | None = None,
    sheet_name: str | int | None = None,
    value_column: str | None = None,
    measurement_point_mode: str = "auto",
    measurement_point_column: str | None = None,
    measurement_point_columns: list[str] | None = None,
    measurement_point_values: list[str] | None = None,
) -> StreamlitAnalysisBundle:
    sheet = sheet_name if sheet_name is not None else 0
    config = SpcJobConfig(
        input_files=[p.name for p in uploaded_paths],
        usl=usl,
        lsl=lsl,
        filter_process=process or None,
        filter_characteristic=characteristic or None,
        filter_item=item or None,
        chart_type=chart_type,  # type: ignore[arg-type]
        subgroup_size=subgroup_size,
        n_subgroups=n_subgroups,
        sampling_method=sampling_method,  # type: ignore[arg-type]
        imr_sampling_unit=imr_sampling_unit,  # type: ignore[arg-type]
        stage=stage,  # type: ignore[arg-type]
        process_name=process_name,
        machine_name=machine_name,
        special_characteristic=special_characteristic,
        process_change_detected=process_change_detected,
        use_full_population=use_full_population,
        subgroup_boundary_mode=subgroup_boundary_mode,  # type: ignore[arg-type]
        subgroup_boundary_keys=subgroup_boundary_keys or [],
        subgroup_boundary_columns=subgroup_boundary_columns or [],
        subgroup_boundary_columns_display=subgroup_boundary_columns_display or [],
        output_dir=str(output_dir or OUTPUT_PATH),
        auto_split_characteristics=not bool(characteristic),
        measurement_point_mode=measurement_point_mode,  # type: ignore[arg-type]
        measurement_point_column=measurement_point_column,
        measurement_point_columns=list(measurement_point_columns or []),
        measurement_point_values=measurement_point_values or [],
        save_reports=False,
        sheet_name=sheet,
        value_column=value_column,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        resolved_paths: list[str] = []
        for src in uploaded_paths:
            dest = tmp_path / src.name
            dest.write_bytes(src.read_bytes())
            resolved_paths.append(str(dest.resolve()))

        config.input_files = resolved_paths
        result = SpcPipeline(config, spec_type_override=spec_type).run()

    interpretations = _build_interpretation_map(result)
    child = get_active_result(result, list_analysis_targets(result)[0] if result.is_batch else None)
    if child.decision is None or child.analysis is None:
        raise ValueError("분석 결과가 생성되지 않았습니다.")

    first_interp = interpretations.get(_split_key(child.characteristic)) or build_control_chart_interpretation(
        child.analysis, child.decision
    )
    return StreamlitAnalysisBundle(
        pipeline=result,
        interpretation=first_interp,
        interpretations=interpretations,
    )


def job_config_from_active(active: SpcPipelineResult) -> SpcJobConfig:
    """현재 분석 결과에서 재분석용 JobConfig 복원."""
    cfg = active.sampling_config or {}
    cap = active.analysis.capability if active.analysis else None
    study = active.study_info or {}
    chart_type = cfg.get("chart_type", "xbar_s")
    return SpcJobConfig(
        usl=cap.usl if cap else None,
        lsl=cap.lsl if cap else None,
        chart_type=chart_type,  # type: ignore[arg-type]
        subgroup_size=int(cfg.get("subgroup_size", 5)),
        n_subgroups=int(cfg.get("n_subgroups", 25)),
        use_full_population=bool(cfg.get("use_full_population", False)),
        sampling_method=cfg.get("sampling_method", "consecutive"),  # type: ignore[arg-type]
        process_name=study.get("process") if study.get("process") != "-" else None,
        machine_name=study.get("machine") if study.get("machine") != "-" else None,
        save_reports=False,
        sheet_name=cfg.get("sheet_name", 0),
        value_column=cfg.get("value_column"),
    )


def rerun_with_sample_df(
    bundle: StreamlitAnalysisBundle,
    active: SpcPipelineResult,
    sample_df,
    *,
    data_source_note: str = "극단값 처리",
) -> StreamlitAnalysisBundle:
    """지정 sample_df로 현재 대상 SPC 재분석."""
    import pandas as pd

    if not isinstance(sample_df, pd.DataFrame):
        raise ValueError("sample_df는 DataFrame이어야 합니다.")

    cfg = job_config_from_active(active)
    pipe = SpcPipeline(cfg)
    new_result = pipe.run_from_sample_df(
        cfg,
        active.filtered_df if active.filtered_df is not None else sample_df,
        sample_df,
        data_source=data_source_note,
        raw_count=active.raw_count,
        characteristic_label=active.characteristic,
        split_column=active.split_column,
    )
    if new_result.sampling_config:
        new_result.sampling_config.update(active.sampling_config or {})

    root = bundle.pipeline
    if root.is_batch:
        target_key = _split_key(active.characteristic)
        children: list[SpcPipelineResult] = []
        for child in root.split_results:
            if child.is_batch:
                sub_children: list[SpcPipelineResult] = []
                for sub in child.split_results:
                    if _split_key(sub.characteristic) == target_key:
                        sub_children.append(new_result)
                    else:
                        sub_children.append(sub)
                children.append(
                    SpcPipelineResult(
                        raw_count=child.raw_count,
                        sample_count=sum(c.sample_count for c in sub_children),
                        sampling_note=child.sampling_note,
                        split_column=child.split_column,
                        split_results=sub_children,
                        report_paths=child.report_paths,
                    )
                )
            elif _split_key(child.characteristic) == target_key:
                children.append(new_result)
            else:
                children.append(child)
        updated_pipe = SpcPipelineResult(
            raw_count=root.raw_count,
            sample_count=sum(c.sample_count for c in children),
            sampling_note=root.sampling_note,
            split_column=root.split_column,
            split_results=children,
            report_paths=root.report_paths,
        )
    else:
        updated_pipe = new_result

    interpretations = _build_interpretation_map(updated_pipe)
    active_key = _split_key(new_result.characteristic)
    first_interp = interpretations.get(active_key) or build_control_chart_interpretation(
        new_result.analysis, new_result.decision  # type: ignore[arg-type]
    )
    return StreamlitAnalysisBundle(
        pipeline=updated_pipe,
        interpretation=first_interp,
        interpretations=interpretations,
    )


def rerun_with_stratified_sample(
    bundle: StreamlitAnalysisBundle,
    active: SpcPipelineResult,
    sample_df,
) -> StreamlitAnalysisBundle:
    """재구성 subgroup 데이터로 현재 대상 SPC 재분석."""
    import pandas as pd

    if not isinstance(sample_df, pd.DataFrame):
        raise ValueError("sample_df는 DataFrame이어야 합니다.")

    return rerun_with_sample_df(
        bundle,
        active,
        sample_df,
        data_source_note="혼합분포 재구성",
    )


def rerun_with_condition_split(
    bundle: StreamlitAnalysisBundle,
    active: SpcPipelineResult,
    sample_df,
    *,
    split_columns: list[str],
    split_basis: str,
) -> StreamlitAnalysisBundle:
    """재구성 후 조건별로 측정포인트 분리처럼 각각 SPC 재분석."""
    import pandas as pd

    if not isinstance(sample_df, pd.DataFrame):
        raise ValueError("sample_df는 DataFrame이어야 합니다.")
    group_col = "split_key" if "split_key" in sample_df.columns else None
    if not group_col:
        raise ValueError("재구성 데이터에 split_key가 없습니다.")

    cfg = job_config_from_active(active)
    pipe = SpcPipeline(cfg)
    base_char = active.characteristic or "전체"
    filtered = active.filtered_df if active.filtered_df is not None else sample_df

    children: list[SpcPipelineResult] = []
    for gkey, grp in sample_df.groupby(group_col, sort=False):
        label = f"{base_char} · {gkey}" if active.characteristic else str(gkey)
        mask = _build_condition_mask(filtered, split_columns, str(gkey))
        cond_filtered = filtered.loc[mask].copy() if mask.any() else grp.copy()
        child = pipe.run_from_sample_df(
            cfg,
            cond_filtered,
            grp,
            data_source=f"혼합분포 재구성 ({split_basis})",
            raw_count=len(cond_filtered),
            characteristic_label=label,
            split_column="strat_condition",
        )
        if child.sampling_config:
            child.sampling_config["stratified_rerun"] = True
            child.sampling_config["strat_split_basis"] = split_basis
        children.append(child)

    if not children:
        raise ValueError("조건별 재분석할 그룹이 없습니다.")

    condition_batch = SpcPipelineResult(
        raw_count=active.raw_count,
        sample_count=sum(c.sample_count for c in children),
        sampling_note=f"혼합분포 조건별 분리 ({split_basis})",
        split_column="strat_condition",
        split_results=children,
        characteristic=active.characteristic,
        filtered_df=filtered.copy(),
    )

    root = bundle.pipeline
    if root.is_batch and active.characteristic:
        target_key = _split_key(active.characteristic)
        new_children: list[SpcPipelineResult] = []
        for child in root.split_results:
            if _split_key(child.characteristic) == target_key:
                new_children.append(condition_batch)
            else:
                new_children.append(child)
        updated_pipe = SpcPipelineResult(
            raw_count=root.raw_count,
            sample_count=sum(c.sample_count for c in new_children),
            sampling_note=root.sampling_note,
            split_column=root.split_column,
            split_results=new_children,
            filtered_df=root.filtered_df,
            report_paths=root.report_paths,
        )
    else:
        updated_pipe = condition_batch

    interpretations = _build_interpretation_map(updated_pipe)
    targets = list_analysis_targets(updated_pipe)
    first = _find_active_in_pipe(updated_pipe, targets[0] if targets else None)
    first_interp = build_control_chart_interpretation(first.analysis, first.decision)  # type: ignore[arg-type]
    return StreamlitAnalysisBundle(
        pipeline=updated_pipe,
        interpretation=first_interp,
        interpretations=interpretations,
    )
