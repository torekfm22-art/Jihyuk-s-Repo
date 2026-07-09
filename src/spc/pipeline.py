"""
SPC 분석 파이프라인: MES/QMS xlsx → 표본 → 분석 → 종합보고서(Excel+PDF) + 세부시트.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
import yaml

from config import settings
from src.spc.characteristic_split import (
    detect_measurement_point_column,
    detect_split_column,
    format_split_label,
    is_measurement_point_split,
    list_split_values,
    normalize_split_value,
    resolve_split_plan,
    safe_filename_slug,
)
from src.spc.data_extractor import MesQmsExtractor
from src.spc.path_utils import resolve_input_path
from src.spc.sampler import (
    SampleSelector,
    format_subgroup_boundary_labels,
    resolve_auto_subgroup_boundary_keys,
    resolve_auto_boundary_columns,
)
from src.spc.decision_models import SpcDecisionResult
from src.spc.decision_service import SpcDecisionInput, SpcDecisionService
from src.spc.minitab_charts import ChartPaths
from src.spc.statistics import SpcAnalyzer, SpcAnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class SpcJobConfig:
    # 통합 파일 첨부 (우선)
    input_files: list[str] = field(default_factory=list)
    file_password: Optional[str] = None
    sheet_name: str | int = 0
    value_column: Optional[str] = None

    # 하위 호환 (mes/qms 분리 — yaml/CLI)
    source_file: Optional[str] = None
    mes_file: Optional[str] = None
    qms_file: Optional[str] = None
    mes_sheet_name: str | int = 0
    qms_sheet_name: str | int = 0
    mes_password: Optional[str] = None
    qms_password: Optional[str] = None
    chart_type: Literal["auto", "xbar_s", "xbar_r", "imr"] = "auto"
    subgroup_size: int = 5
    n_subgroups: Optional[int] = 25
    sampling_method: Literal["consecutive", "subgroup", "random", "systematic", "latest"] = "consecutive"
    imr_sampling_unit: Literal["auto", "lot", "hour", "shift", "cycle"] = "auto"
    usl: Optional[float] = None
    lsl: Optional[float] = None
    spec_type: Optional[Literal["two_sided", "upper_only", "lower_only"]] = None
    filter_item: Optional[str] = None
    filter_process: Optional[str] = None
    filter_characteristic: Optional[str] = None
    filter_lot: Optional[str] = None
    filter_source: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    report_title: str = "SPC 및 공정능력 연구 보고서"
    output_dir: Optional[str] = None
    process_name: Optional[str] = None
    machine_name: Optional[str] = None
    stage: Literal[
        "development", "pilot", "pre_mass_production", "mass_production"
    ] = "mass_production"
    special_characteristic: bool = False
    customer_exception_mode: bool = False
    process_change_detected: bool = False
    customer_exception_reason: Optional[str] = None
    customer_required_control_zone: Optional[str] = None
    auto_split_characteristics: bool = True
    measurement_point_mode: Literal["auto", "manual", "none"] = "auto"
    measurement_point_column: Optional[str] = None
    measurement_point_columns: list[str] = field(default_factory=list)
    measurement_point_values: list[str] = field(default_factory=list)
    max_auto_measurement_points: int = 8
    save_reports: bool = True
    use_full_population: bool = False
    subgroup_boundary_mode: Literal["auto", "manual"] = "auto"
    subgroup_boundary_keys: list[str] = field(default_factory=list)
    subgroup_boundary_columns: list[str] = field(default_factory=list)
    subgroup_boundary_columns_display: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SpcJobConfig":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if data.get("output_dir") is None:
            data["output_dir"] = settings.OUTPUT_PATH
        if not data.get("input_files"):
            files = []
            for key in ("mes_file", "qms_file", "source_file"):
                if data.get(key):
                    files.append(data[key])
            if files:
                data["input_files"] = files
        return cls(**data)

    def resolve_input_files(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        return self.source_file, self.mes_file, self.qms_file


@dataclass
class SpcPipelineResult:
    raw_count: int = 0
    sample_count: int = 0
    sampling_note: str = "-"
    analysis: Optional[SpcAnalysisResult] = None
    decision: Optional[SpcDecisionResult] = None
    report_paths: dict = field(default_factory=dict)
    study_info: dict = field(default_factory=dict)
    report_title: str = ""
    charts: Optional[ChartPaths] = None
    characteristic: Optional[str] = None
    split_column: Optional[str] = None
    split_results: list["SpcPipelineResult"] = field(default_factory=list)
    filtered_df: Optional[pd.DataFrame] = None
    sample_df: Optional[pd.DataFrame] = None
    sampling_config: dict = field(default_factory=dict)

    @property
    def is_batch(self) -> bool:
        return len(self.split_results) > 0


class SpcPipeline:
    def __init__(
        self,
        config: SpcJobConfig,
        *,
        spec_type_override: Literal["two_sided", "upper_only", "lower_only"] | None = None,
    ):
        self.config = config
        self._spec_type_override = spec_type_override
        self.analyzer = SpcAnalyzer(population_std=config.use_full_population)

    def _effective_spec_type(self, cfg: SpcJobConfig):
        return cfg.spec_type or self._spec_type_override

    def _resolve_spec_limits(
        self,
        cfg: SpcJobConfig,
        filtered: pd.DataFrame,
        *,
        label: str = "?",
    ) -> tuple[float | None, float | None]:
        from src.spc.spec_limits import resolve_effective_spec_limits

        usl, lsl, _ = resolve_effective_spec_limits(
            cfg.usl,
            cfg.lsl,
            filtered,
            spec_type=self._effective_spec_type(cfg),
        )
        if usl is None and lsl is None:
            raise ValueError(
                f"[{label}] USL 또는 LSL 중 최소 하나를 설정하거나 xlsx에 규격 컬럼을 포함하세요."
            )
        return usl, lsl

    def run(self) -> SpcPipelineResult:
        cfg = self.config
        extractor, data_source, raw_df = self._load_data(cfg)

        filtered = extractor.filter_by(
            raw_df,
            item=cfg.filter_item,
            process=cfg.filter_process,
            characteristic=cfg.filter_characteristic,
            lot=cfg.filter_lot,
            source=cfg.filter_source,
            date_from=cfg.date_from,
            date_to=cfg.date_to,
        )
        if filtered.empty:
            raise ValueError("필터 조건에 맞는 데이터가 없습니다.")

        split_col: Optional[str] = None
        split_values: list[str] = []

        filtered, split_col, split_values = resolve_split_plan(
            filtered,
            filter_characteristic=cfg.filter_characteristic,
            auto_split_characteristics=cfg.auto_split_characteristics,
            measurement_point_mode=cfg.measurement_point_mode,
            measurement_point_column=cfg.measurement_point_column,
            measurement_point_columns=cfg.measurement_point_columns,
            measurement_point_values=cfg.measurement_point_values,
            max_auto_measurement_points=cfg.max_auto_measurement_points,
        )

        if len(split_values) == 1 and split_col:
            norm_val = normalize_split_value(split_values[0])
            filtered = filtered[
                filtered[split_col].apply(normalize_split_value) == norm_val  # type: ignore[index]
            ].reset_index(drop=True)
            return self._run_single(
                cfg, filtered, data_source, len(raw_df),
                characteristic_label=split_values[0],
                split_column=split_col,
            )

        if len(split_values) >= 2:
            split_label = "측정 포인트" if is_measurement_point_split(split_col) else "항목"
            logger.info(
                "%s별 자동 분리 분석: %s (%d개) — %s",
                split_label,
                split_col, len(split_values), ", ".join(split_values[:8]),
            )
            children: list[SpcPipelineResult] = []
            for val in split_values:
                norm_val = normalize_split_value(val)
                subset = filtered[
                    filtered[split_col].apply(normalize_split_value) == norm_val  # type: ignore[index]
                ].reset_index(drop=True)
                if len(subset) < 2:
                    logger.warning("항목 '%s' 데이터 %d건 — 분석 건너뜀", val, len(subset))
                    continue
                try:
                    children.append(
                        self._run_single(
                            cfg, subset, data_source, len(raw_df),
                            characteristic_label=val,
                            split_column=split_col,
                        )
                    )
                except Exception as exc:
                    logger.exception("항목 '%s' 분석 실패: %s", val, exc)
                    raise ValueError(f"항목 '{val}' 분석 실패: {exc}") from exc

            if not children:
                raise ValueError("항목별 분석 가능한 데이터가 없습니다.")

            return SpcPipelineResult(
                raw_count=len(raw_df),
                sample_count=sum(c.sample_count for c in children),
                sampling_note=f"{split_label}별 {len(children)}건 분석 ({split_col})",
                split_column=split_col,
                split_results=children,
                report_paths={},
            )

        return self._run_single(
            cfg, filtered, data_source, len(raw_df),
            characteristic_label=cfg.filter_characteristic,
            split_column=split_col,
        )

    def run_from_sample_df(
        self,
        cfg: SpcJobConfig,
        filtered: pd.DataFrame,
        sample_df: pd.DataFrame,
        *,
        data_source: str = "층화 재구성",
        raw_count: int | None = None,
        characteristic_label: str | None = None,
        split_column: str | None = None,
    ) -> SpcPipelineResult:
        """재구성된 sample_df(subgroup_id 포함)로 SPC 재분석."""
        if sample_df is None or sample_df.empty or "value" not in sample_df.columns:
            raise ValueError("재분석할 sample 데이터가 없습니다.")
        if "subgroup_id" not in sample_df.columns:
            raise ValueError("subgroup_id가 있는 재구성 데이터가 필요합니다.")

        from src.spc.data_extractor import resolve_value_column_for_split_label
        from src.spc.sample_ordering import sort_sample_dataframe

        if characteristic_label and split_column in ("characteristic", "measure_item"):
            filtered = resolve_value_column_for_split_label(filtered, characteristic_label)

        usl, lsl = self._resolve_spec_limits(cfg, filtered, label=characteristic_label or "?")

        chart_type = cfg.chart_type
        if chart_type == "auto":
            chart_type = "xbar_s"

        sample_df = sort_sample_dataframe(sample_df.copy())
        sizes = sample_df.groupby("subgroup_id").size()
        sg_size = int(sizes.mode().iloc[0]) if not sizes.empty else cfg.subgroup_size

        if chart_type in ("xbar_s", "xbar_r"):
            subgroups = SampleSelector.to_subgroup_matrix(sample_df, sg_size)
            if chart_type == "xbar_s":
                analysis = self.analyzer.analyze_xbar_s(subgroups, usl, lsl)
            else:
                analysis = self.analyzer.analyze_xbar_r(subgroups, usl, lsl)
        else:
            analysis = self.analyzer.analyze_imr(sample_df["value"].to_numpy(), usl, lsl)
            sg_size = 1

        out_dir = Path(cfg.output_dir or settings.OUTPUT_PATH)
        charts_dir = out_dir / "charts"
        ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        file_tag = safe_filename_slug(characteristic_label) if characteristic_label else None
        chart_prefix = f"spc_strat_{file_tag}_{ts}" if file_tag else f"spc_strat_{ts}"
        raw_values = sample_df["value"].to_numpy()

        from src.spc.minitab_charts import generate_all_minitab_charts
        from src.spc.comprehensive_report import ComprehensiveReportGenerator

        charts = generate_all_minitab_charts(
            analysis, raw_values, usl, lsl, charts_dir, chart_prefix
        )

        sampling_note = self._build_sampling_note(sample_df)
        if sampling_note == "-":
            n_sg = int(sample_df["subgroup_id"].nunique())
            sampling_note = f"층화 재구성 {len(sample_df)}점 ({n_sg}군 × n≈{sg_size})"

        char_display = characteristic_label or (
            filtered["characteristic"].iloc[0]
            if "characteristic" in filtered.columns and len(filtered)
            else "-"
        )
        if characteristic_label and split_column:
            char_display = format_split_label(characteristic_label, split_column)
        study_info = {
            "process": cfg.process_name or cfg.filter_process or "-",
            "machine": cfg.machine_name or "-",
            "item": cfg.filter_item or (filtered["item"].iloc[0] if "item" in filtered.columns else "-"),
            "characteristic": char_display,
            "data_source": cfg.filter_source or data_source,
            "sampling": sampling_note,
        }

        title = cfg.report_title
        if characteristic_label:
            pt_label = format_split_label(characteristic_label, split_column or "")
            title = f"{cfg.report_title} — {pt_label} (층화 재구성)"

        decision = SpcDecisionService().evaluate(
            SpcDecisionInput(
                analysis=analysis,
                raw_data=raw_values,
                stage=cfg.stage,
                special_characteristic=cfg.special_characteristic,
                customer_exception_mode=cfg.customer_exception_mode,
                process_change_detected=cfg.process_change_detected,
                customer_exception_reason=cfg.customer_exception_reason,
                customer_required_control_zone=cfg.customer_required_control_zone,
                usl=usl,
                lsl=lsl,
                subgroup_size=sg_size if chart_type in ("xbar_s", "xbar_r") else None,
                sample_df=sample_df,
                charts=charts,
            )
        )

        report_paths: dict = {}
        if cfg.save_reports:
            report_paths = ComprehensiveReportGenerator(out_dir).generate(
                analysis,
                charts=charts,
                raw_sample=sample_df,
                study_info=study_info,
                report_title=title,
                decision=decision,
                file_tag=characteristic_label,
            )

        effective_n_subgroups = int(sample_df["subgroup_id"].nunique())
        sampling_cfg = {
            "chart_type": chart_type,
            "subgroup_size": sg_size,
            "n_subgroups": effective_n_subgroups,
            "sampling_method": "stratified_reconstruct",
            "sampling_note": sampling_note,
            "sheet_name": cfg.sheet_name,
            "value_column": cfg.value_column,
            "use_full_population": cfg.use_full_population,
            "population_std": cfg.use_full_population,
            "stratified_rerun": True,
        }

        return SpcPipelineResult(
            raw_count=raw_count if raw_count is not None else len(filtered),
            sample_count=len(sample_df),
            sampling_note=sampling_note,
            analysis=analysis,
            decision=decision,
            report_paths=report_paths,
            study_info=study_info,
            report_title=title,
            charts=charts,
            characteristic=characteristic_label,
            split_column=split_column,
            filtered_df=filtered.copy(),
            sample_df=sample_df.copy(),
            sampling_config=sampling_cfg,
        )

    def _load_data(
        self, cfg: SpcJobConfig
    ) -> tuple[MesQmsExtractor, str, pd.DataFrame]:
        input_dir = Path(settings.INPUT_PATH)
        password = cfg.file_password or cfg.mes_password or cfg.qms_password

        if cfg.input_files:
            paths = []
            for ref in cfg.input_files:
                p = resolve_input_path(ref, input_dir)
                if p:
                    paths.append(p)
            if not paths:
                raise ValueError("첨부된 Excel 파일을 찾을 수 없습니다.")
            extractor = MesQmsExtractor.from_files(
                paths,
                sheet_name=cfg.sheet_name,
                password=password,
                value_column=cfg.value_column,
            )
            data_source = ", ".join(p.name for p in paths)
        else:
            source_file, mes_file, qms_file = cfg.resolve_input_files()
            mes_path = resolve_input_path(mes_file, input_dir)
            qms_path = resolve_input_path(qms_file, input_dir)
            src_path = resolve_input_path(source_file, input_dir)

            if mes_path or qms_path:
                extractor = MesQmsExtractor.from_mes_qms_xlsx(
                    mes_path=mes_path,
                    qms_path=qms_path,
                    mes_sheet=cfg.mes_sheet_name,
                    qms_sheet=cfg.qms_sheet_name,
                    mes_password=password,
                    qms_password=password,
                )
                parts = []
                if mes_path:
                    parts.append(mes_path.name)
                if qms_path:
                    parts.append(qms_path.name)
                data_source = ", ".join(parts)
            elif src_path:
                extractor = MesQmsExtractor.from_files(
                    [src_path],
                    sheet_name=cfg.sheet_name,
                    password=password,
                    value_column=cfg.value_column,
                )
                data_source = src_path.name
            else:
                raise ValueError("Excel 파일을 1개 이상 첨부하세요.")

        raw_df = extractor.extract()
        return extractor, data_source, raw_df

    def _run_single(
        self,
        cfg: SpcJobConfig,
        filtered: pd.DataFrame,
        data_source: str,
        raw_count: int,
        *,
        characteristic_label: Optional[str] = None,
        split_column: Optional[str] = None,
    ) -> SpcPipelineResult:
        from src.spc.data_extractor import resolve_value_column_for_split_label

        if characteristic_label and split_column in ("characteristic", "measure_item"):
            filtered = resolve_value_column_for_split_label(filtered, characteristic_label)

        usl, lsl = self._resolve_spec_limits(cfg, filtered, label=characteristic_label or "?")

        if self._is_prepared_stratified_sample(filtered):
            logger.info("재구성 subgroup_id 포함 데이터 — 채취 단계 생략, 표본 그대로 분석")
            return self.run_from_sample_df(
                cfg,
                filtered,
                filtered,
                data_source=data_source,
                raw_count=raw_count,
                characteristic_label=characteristic_label,
                split_column=split_column,
            )

        b_keys, b_cols = self._resolve_subgroup_boundary(cfg, filtered)
        selector = SampleSelector(
            filtered,
            subgroup_boundary_keys=b_keys,
            subgroup_boundary_columns=b_cols,
        )
        chart_type = cfg.chart_type
        if chart_type == "auto":
            chart_type = "xbar_s" if len(filtered) >= cfg.subgroup_size * 2 else "imr"

        sg_size: int | None = None
        if cfg.use_full_population:
            for_xbar = chart_type in ("xbar_s", "xbar_r")
            sample_df, sg_size = selector.select_full_population(
                subgroup_size=cfg.subgroup_size,
                for_xbar=for_xbar,
            )
        elif chart_type in ("xbar_s", "xbar_r"):
            sample_df, sg_size = selector.select(
                method=cfg.sampling_method if cfg.sampling_method != "subgroup" else "consecutive",
                subgroup_size=cfg.subgroup_size,
                n_subgroups=cfg.n_subgroups or 25,
            )
        else:
            n_target = cfg.n_subgroups or 25
            if cfg.sampling_method in ("consecutive", "subgroup"):
                sample_df = selector.select_rational_individuals(
                    n_points=n_target,
                    unit=cfg.imr_sampling_unit,
                    cycle_stride=cfg.subgroup_size,
                )
            else:
                sample_df = selector.select(
                    method=cfg.sampling_method,
                    sample_size=n_target,
                )

        from src.spc.sample_ordering import sort_sample_dataframe

        sample_df = sort_sample_dataframe(sample_df)
        if chart_type in ("xbar_s", "xbar_r"):
            subgroups = SampleSelector.to_subgroup_matrix(sample_df, sg_size)
            if chart_type == "xbar_s":
                analysis = self.analyzer.analyze_xbar_s(subgroups, usl, lsl)
            else:
                analysis = self.analyzer.analyze_xbar_r(subgroups, usl, lsl)
        else:
            analysis = self.analyzer.analyze_imr(sample_df["value"].to_numpy(), usl, lsl)

        out_dir = Path(cfg.output_dir or settings.OUTPUT_PATH)
        charts_dir = out_dir / "charts"
        ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        file_tag = safe_filename_slug(characteristic_label) if characteristic_label else None
        chart_prefix = f"spc_{file_tag}_{ts}" if file_tag else f"spc_{ts}"
        raw_values = sample_df["value"].to_numpy()

        from src.spc.minitab_charts import generate_all_minitab_charts
        from src.spc.comprehensive_report import ComprehensiveReportGenerator

        charts = generate_all_minitab_charts(
            analysis, raw_values, usl, lsl, charts_dir, chart_prefix
        )

        sampling_note = self._build_sampling_note(sample_df)

        char_display = characteristic_label or (
            filtered["characteristic"].iloc[0]
            if "characteristic" in filtered.columns and len(filtered)
            else "-"
        )
        if characteristic_label and split_column:
            char_display = format_split_label(characteristic_label, split_column)
        study_info = {
            "process": cfg.process_name or cfg.filter_process or "-",
            "machine": cfg.machine_name or "-",
            "item": cfg.filter_item or (filtered["item"].iloc[0] if "item" in filtered.columns else "-"),
            "characteristic": char_display,
            "data_source": cfg.filter_source or data_source,
            "sampling": sampling_note,
        }

        title = cfg.report_title
        if characteristic_label:
            pt_label = format_split_label(characteristic_label, split_column or "")
            title = f"{cfg.report_title} — {pt_label}"

        decision = SpcDecisionService().evaluate(
            SpcDecisionInput(
                analysis=analysis,
                raw_data=raw_values,
                stage=cfg.stage,
                special_characteristic=cfg.special_characteristic,
                customer_exception_mode=cfg.customer_exception_mode,
                process_change_detected=cfg.process_change_detected,
                customer_exception_reason=cfg.customer_exception_reason,
                customer_required_control_zone=cfg.customer_required_control_zone,
                usl=usl,
                lsl=lsl,
                subgroup_size=sg_size if chart_type in ("xbar_s", "xbar_r") else None,
                sample_df=sample_df,
                charts=charts,
            )
        )

        report_paths: dict = {}
        if cfg.save_reports:
            report_paths = ComprehensiveReportGenerator(out_dir).generate(
                analysis,
                charts=charts,
                raw_sample=sample_df,
                study_info=study_info,
                report_title=title,
                decision=decision,
                file_tag=characteristic_label,
            )

        effective_n_subgroups = (
            int(sample_df["subgroup_id"].nunique())
            if cfg.use_full_population and "subgroup_id" in sample_df.columns
            else cfg.n_subgroups
        )
        sampling_cfg = {
            "chart_type": chart_type,
            "subgroup_size": sg_size or cfg.subgroup_size,
            "n_subgroups": effective_n_subgroups,
            "sampling_method": cfg.sampling_method,
            "sampling_note": sampling_note,
            "sheet_name": cfg.sheet_name,
            "value_column": cfg.value_column,
            "use_full_population": cfg.use_full_population,
            "population_std": cfg.use_full_population,
            "subgroup_boundary_mode": cfg.subgroup_boundary_mode,
            "subgroup_boundary_keys": selector.subgroup_boundary_keys,
            "subgroup_boundary_columns": selector.subgroup_boundary_columns,
            "subgroup_boundary_columns_display": cfg.subgroup_boundary_columns_display,
            "subgroup_boundary_label": (
                " · ".join(cfg.subgroup_boundary_columns_display)
                if cfg.subgroup_boundary_columns_display
                else format_subgroup_boundary_labels(
                    selector.subgroup_boundary_keys,
                    columns=selector.subgroup_boundary_columns or None,
                )
            ),
        }

        return SpcPipelineResult(
            raw_count=raw_count,
            sample_count=len(sample_df),
            sampling_note=sampling_note,
            analysis=analysis,
            decision=decision,
            report_paths=report_paths,
            study_info=study_info,
            report_title=title,
            charts=charts,
            characteristic=characteristic_label,
            split_column=split_column,
            filtered_df=filtered.copy(),
            sample_df=sample_df.copy(),
            sampling_config=sampling_cfg,
        )

    @staticmethod
    def _is_prepared_stratified_sample(df: pd.DataFrame) -> bool:
        """층화 재구성 Excel 등 — subgroup_id가 이미 부여된 표본."""
        if df is None or df.empty or "subgroup_id" not in df.columns or "value" not in df.columns:
            return False
        if "sampling_strategy" in df.columns:
            strategies = df["sampling_strategy"].astype(str).str.lower()
            if strategies.str.contains("stratified", na=False).any():
                return True
        sg = pd.to_numeric(df["subgroup_id"], errors="coerce").dropna()
        return len(sg) >= 2 and sg.nunique() >= 2

    @staticmethod
    def _resolve_subgroup_boundary(
        cfg: SpcJobConfig,
        filtered: pd.DataFrame,
    ) -> tuple[list[str] | None, list[str] | None]:
        if cfg.subgroup_boundary_mode == "manual" and cfg.subgroup_boundary_columns:
            return None, list(cfg.subgroup_boundary_columns)
        if cfg.subgroup_boundary_mode == "manual" and cfg.subgroup_boundary_keys:
            return list(cfg.subgroup_boundary_keys), None
        return resolve_auto_subgroup_boundary_keys(filtered), None

    @staticmethod
    def _resolve_subgroup_boundary_keys(cfg: SpcJobConfig, filtered: pd.DataFrame) -> list[str]:
        keys, _ = SpcPipeline._resolve_subgroup_boundary(cfg, filtered)
        return keys or resolve_auto_subgroup_boundary_keys(filtered)

    @staticmethod
    def _build_sampling_note(sample_df: pd.DataFrame) -> str:
        if "sampling_strategy" not in sample_df.columns or not sample_df["sampling_strategy"].notna().any():
            return "-"
        strat = str(sample_df["sampling_strategy"].iloc[0])
        if strat.startswith("imr_rational_"):
            from src.spc.sampler import IMR_UNIT_LABELS

            unit_key = strat.replace("imr_rational_", "")
            unit_label = IMR_UNIT_LABELS.get(unit_key, unit_key)  # type: ignore[arg-type]
            return f"I-MR 대표 채취 {len(sample_df)}점 ({unit_label})"
        if strat == "consecutive_individual":
            return f"시간순 연속 {len(sample_df)}점 (I-MR 대체)"
        if strat == "sequence_random":
            return "순번 연속 랜덤 (블록 후보 부족 시 대체)"
        if strat.startswith("boundary_block"):
            keys = strat.split(":", 1)[-1].replace("+", " · ")
            if "date" in strat:
                return f"블록 채취 ({keys}) · 일자 분산"
            return f"블록 채취 ({keys}) · 연속"
        if strat == "date_block":
            return "일자·교대 블록 랜덤 (구버전)"
        if strat == "full_population":
            n = len(sample_df)
            if "subgroup_id" in sample_df.columns:
                n_sg = int(sample_df["subgroup_id"].nunique())
                n_per = int(sample_df.groupby("subgroup_id").size().iloc[0]) if n_sg else 0
                return f"전수 데이터 N={n} ({n_sg}군 × n={n_per}, σ=STDEV.P)"
            return f"전수 데이터 N={n} (σ=STDEV.P)"
        if strat == "stratified_reconstruct":
            n_sg = int(sample_df["subgroup_id"].nunique()) if "subgroup_id" in sample_df.columns else 0
            return f"층화 재구성 {len(sample_df)}점 ({n_sg}군)"
        return "일자·LOT·교대 블록 랜덤"
