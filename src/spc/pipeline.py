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

from config.settings import INPUT_PATH, OUTPUT_PATH
from src.spc.data_extractor import MesQmsExtractor
from src.spc.path_utils import resolve_input_path
from src.spc.sampler import SampleSelector
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
    usl: Optional[float] = None
    lsl: Optional[float] = None
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

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SpcJobConfig":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if data.get("output_dir") is None:
            data["output_dir"] = OUTPUT_PATH
        # yaml: input_files 리스트 또는 mes_file+qms_file
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
    analysis: Optional[SpcAnalysisResult] = None
    decision: Optional[SpcDecisionResult] = None
    report_paths: dict = field(default_factory=dict)
    charts: Optional[ChartPaths] = None


class SpcPipeline:
    def __init__(self, config: SpcJobConfig):
        self.config = config
        self.analyzer = SpcAnalyzer()

    def run(self) -> SpcPipelineResult:
        cfg = self.config
        input_dir = Path(INPUT_PATH)
        password = cfg.file_password or cfg.mes_password or cfg.qms_password

        # 1) 통합 파일 첨부
        if cfg.input_files:
            paths = []
            for ref in cfg.input_files:
                p = resolve_input_path(ref, input_dir)
                if p:
                    paths.append(p)
            if not paths:
                raise ValueError("첨부된 Excel 파일을 찾을 수 없습니다.")
            extractor = MesQmsExtractor.from_files(
                paths, sheet_name=cfg.sheet_name, password=password
            )
            data_source = ", ".join(p.name for p in paths)
        else:
            # 2) 하위 호환: mes/qms/source 분리
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
                    [src_path], sheet_name=cfg.sheet_name, password=password
                )
                data_source = src_path.name
            else:
                raise ValueError("Excel 파일을 1개 이상 첨부하세요.")

        raw_df = extractor.extract()
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

        usl, lsl = cfg.usl, cfg.lsl
        if usl is None and "usl" in filtered.columns and filtered["usl"].notna().any():
            usl = float(filtered["usl"].dropna().iloc[0])
        if lsl is None and "lsl" in filtered.columns and filtered["lsl"].notna().any():
            lsl = float(filtered["lsl"].dropna().iloc[0])
        if usl is None or lsl is None:
            raise ValueError("USL/LSL을 설정하거나 xlsx에 USL/LSL 컬럼을 포함하세요.")

        selector = SampleSelector(filtered)
        chart_type = cfg.chart_type
        if chart_type == "auto":
            chart_type = "xbar_s" if len(filtered) >= cfg.subgroup_size * 2 else "imr"

        sg_size: int | None = None
        if chart_type in ("xbar_s", "xbar_r"):
            sample_df, sg_size = selector.select(
                method=cfg.sampling_method if cfg.sampling_method != "subgroup" else "consecutive",
                subgroup_size=cfg.subgroup_size,
                n_subgroups=cfg.n_subgroups or 25,
            )
            subgroups = SampleSelector.to_subgroup_matrix(sample_df, sg_size)
            if chart_type == "xbar_s":
                analysis = self.analyzer.analyze_xbar_s(subgroups, usl, lsl)
            else:
                analysis = self.analyzer.analyze_xbar_r(subgroups, usl, lsl)
        else:
            sample_df = selector.select(
                method=cfg.sampling_method if cfg.sampling_method not in ("subgroup", "consecutive") else "latest"
            )
            analysis = self.analyzer.analyze_imr(sample_df["value"].to_numpy(), usl, lsl)

        out_dir = Path(cfg.output_dir or OUTPUT_PATH)
        charts_dir = out_dir / "charts"
        ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        raw_values = sample_df["value"].to_numpy()

        from src.spc.minitab_charts import generate_all_minitab_charts
        from src.spc.comprehensive_report import ComprehensiveReportGenerator

        charts = generate_all_minitab_charts(
            analysis, raw_values, usl, lsl, charts_dir, f"spc_{ts}"
        )

        sampling_note = "-"
        if "sampling_strategy" in sample_df.columns and sample_df["sampling_strategy"].notna().any():
            strat = str(sample_df["sampling_strategy"].iloc[0])
            sampling_note = (
                "순번 연속 랜덤 (LOT·일자 블록 불가 시 대체)"
                if strat == "sequence_random"
                else "일자·LOT·교대 블록 랜덤"
            )

        study_info = {
            "process": cfg.process_name or cfg.filter_process or "-",
            "machine": cfg.machine_name or "-",
            "item": cfg.filter_item or (filtered["item"].iloc[0] if "item" in filtered.columns else "-"),
            "characteristic": cfg.filter_characteristic or "-",
            "data_source": cfg.filter_source or data_source,
            "sampling": sampling_note,
        }

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
                charts=charts,
            )
        )

        report_paths = ComprehensiveReportGenerator(out_dir).generate(
            analysis,
            charts=charts,
            raw_sample=sample_df,
            study_info=study_info,
            report_title=cfg.report_title,
            decision=decision,
        )

        return SpcPipelineResult(
            raw_count=len(raw_df),
            sample_count=len(sample_df),
            analysis=analysis,
            decision=decision,
            report_paths=report_paths,
            charts=charts,
        )
