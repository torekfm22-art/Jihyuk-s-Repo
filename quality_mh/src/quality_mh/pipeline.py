"""전체 계산 파이프라인."""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from quality_mh.audit_engine import AuditEngine
from quality_mh.excel_parser import concat_normalized, parse_excel_file
from quality_mh.frequency_engine import FrequencyEngine
from quality_mh.manpower_engine import ManpowerEngine
from quality_mh.mh_engine import MhEngine
from quality_mh.output_excel import prepare_output_data, save_output_excel
from quality_mh.standard_master import StandardMasterService
from quality_mh.unit_time_engine import UnitTimeEngine


@dataclass
class PipelineResult:
    standard_master_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    file_analysis_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    frequency_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    unit_time_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    mh_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    line_agg_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    process_agg_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    manpower_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    factory_summary_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    normalized_raw_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    audit: AuditEngine = field(default_factory=AuditEngine)
    parsed_sheets: dict[str, dict[str, pd.DataFrame]] = field(default_factory=dict)


class QualityMhPipeline:
    def __init__(self) -> None:
        self.audit = AuditEngine()
        self.standard = StandardMasterService(audit=self.audit)
        self.frequency_engine = FrequencyEngine(audit=self.audit)
        self.unit_time_engine = UnitTimeEngine(audit=self.audit)
        self.mh_engine = MhEngine(audit=self.audit)
        self.manpower_engine = ManpowerEngine(audit=self.audit)

    def ingest_files(self, files: list[tuple[str, Path | BytesIO]]) -> PipelineResult:
        result = PipelineResult(audit=self.audit)
        result.standard_master_df = self.standard.to_dataframe()

        file_rows = []
        all_frames: list[pd.DataFrame] = []
        freq_frames: list[pd.DataFrame] = []
        ut_frames: list[pd.DataFrame] = []

        for file_name, source in files:
            classification, parsed = parse_excel_file(source, file_name=file_name)
            file_rows.append(classification.model_dump())
            result.parsed_sheets[file_name] = parsed

            for sheet_name, df in parsed.items():
                all_frames.append(df)
                role = classification.file_role
                if role in ("입고상세", "공정상세", "완성상세", "원본이력", "종합분석"):
                    freq_frames.append(df)
                if role == "모답스동작분석" or any(
                    c in df.columns for c in ("mod_value", "movement_distance_m", "unit_time_value")
                ):
                    ut_frames.append(df)

        result.file_analysis_df = pd.DataFrame(file_rows)
        result.normalized_raw_df = concat_normalized(all_frames)

        if freq_frames:
            result.frequency_df = concat_normalized([
                self.frequency_engine.process_dataframe(f) for f in freq_frames
            ])
        if ut_frames:
            if any("unit_time_value" in f.columns for f in ut_frames):
                result.unit_time_df = concat_normalized(ut_frames)
                if "unit_time_min" not in result.unit_time_df.columns and "unit_time_value" in result.unit_time_df.columns:
                    result.unit_time_df["unit_time_min"] = result.unit_time_df["unit_time_value"]
            else:
                result.unit_time_df = self.unit_time_engine.calc_from_dataframe(concat_normalized(ut_frames))

        return result

    def run_calculation(self, state: PipelineResult) -> PipelineResult:
        if not state.frequency_df.empty and not state.unit_time_df.empty:
            state.mh_df = self.mh_engine.calc_mh(state.frequency_df, state.unit_time_df)
            state.line_agg_df = self.mh_engine.aggregate_by_line(state.mh_df)
            state.process_agg_df = self.mh_engine.aggregate_by_process(state.mh_df)
            state.manpower_df = self.manpower_engine.calc_from_line_aggregate(state.line_agg_df)
            state.factory_summary_df = self.manpower_engine.summarize_by_factory(state.line_agg_df)
        return state

    def export_excel(self, state: PipelineResult, output_path: Path) -> Path:
        data = prepare_output_data(
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
        return save_output_excel(output_path, data)

    def run_demo(self) -> PipelineResult:
        """내장 샘플 데이터로 전체 파이프라인 실행."""
        from quality_mh.sample_data import build_demo_frequency_df, build_demo_unit_time_df

        state = PipelineResult(audit=self.audit)
        state.standard_master_df = self.standard.to_dataframe()
        state.frequency_df = self.frequency_engine.process_dataframe(build_demo_frequency_df())
        state.unit_time_df = self.unit_time_engine.calc_from_dataframe(build_demo_unit_time_df())
        return self.run_calculation(state)
