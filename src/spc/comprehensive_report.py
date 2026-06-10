"""AIAG/VDA 스타일 종합 보고서 (Excel 종합시트 + PDF) 및 세부 시트."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.spc.chart_expert_review import format_conclusions_for_report
from src.spc.decision_models import SpcDecisionResult
from src.spc.minitab_charts import ChartPaths
from src.spc.report_decision_dashboard import (
    add_decision_dashboard_sheet,
    apply_decision_sheet_styles,
    write_verdict_strip_on_summary,
)
from src.spc.report_glossary_sheet import add_glossary_sheet
from src.spc.report_validation_sheet import SheetMeta, add_validation_sheet, sanitize_xlsx_formula_file
from src.spc.statistics import SpcAnalysisResult

logger = logging.getLogger(__name__)

THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
LABEL_FONT = Font(bold=True, size=9)
VALUE_FONT = Font(size=9)


def _raw_values_from_sample(raw_sample: pd.DataFrame | None):
    if raw_sample is None or "value" not in raw_sample.columns:
        return None
    return raw_sample["value"].to_numpy()


def _conclusion_text(
    result: SpcAnalysisResult,
    raw_sample: pd.DataFrame | None = None,
    decision: SpcDecisionResult | None = None,
) -> str:
    base = format_conclusions_for_report(result, _raw_values_from_sample(raw_sample))
    if decision is None:
        return base
    return base + "\n\n" + format_decision_for_report(decision)


def format_decision_for_report(decision: SpcDecisionResult) -> str:
    """회사 기준 판정·해석 코멘트 보고서 텍스트."""
    v = decision.verdict_summary
    lines = [
        "【자동 판정 요약】",
        f"  공정상태: {v.process_stability}",
        f"  정규성: {v.normality_verdict}",
        f"  공정능력: {v.capability_verdict}",
        f"  관리용 관리도 적용: {v.control_chart_deploy}",
        f"  우선 조치: {v.priority_action}",
        "",
        "【회사 기준 판정 근거 (Decision Log)】",
    ]
    for entry in decision.control_chart.decision_log:
        lines.append(f"  · [{entry.rule_id}] {entry.message}")
    lines.extend([
        "",
        "【SPC 전문가 해석】",
        f"▶ 경영진 요약: {decision.expert_commentary.executive_summary}",
        f"▶ 실무 해석: {decision.expert_commentary.field_operator_comment}",
        f"▶ 정규성: {decision.expert_commentary.normality_comment}",
        f"▶ 공정능력: {decision.expert_commentary.capability_comment}",
        f"▶ 후속조치: {decision.expert_commentary.followup_action_comment}",
        "",
        "【AIAG-VDA 확장 점검】",
        f"  Pre-control: {decision.aiag_vda_extensions.pre_control_recommendation}",
        f"  기계성능(Cm/Cmk) 필요: {'예' if decision.aiag_vda_extensions.machine_capability_needed else '아니오'}",
        f"  {decision.aiag_vda_extensions.machine_capability.message}",
        f"  Pp/Ppk 기준: {decision.aiag_vda_extensions.pp_ppk_basis_note}",
        f"  Cp/Cpk 기준: {decision.aiag_vda_extensions.cp_cpk_basis_note}",
        "",
        "【리포트 완전성】",
    ])
    rc = decision.aiag_vda_extensions.report_completeness
    status = "완전" if rc.completeness_ok else "누락 있음"
    lines.append(f"  상태: {status}")
    if rc.missing_items:
        lines.append(f"  누락: {', '.join(rc.missing_items)}")
    for w in rc.warnings:
        lines.append(f"  ⚠ {w}")
    return "\n".join(lines)


class ComprehensiveReportGenerator:
    """종합시트(Excel+PDF) + 세부 Excel 시트."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        result: SpcAnalysisResult,
        *,
        charts: ChartPaths,
        raw_sample: pd.DataFrame,
        study_info: dict,
        report_title: str = "SPC 및 공정능력 연구 보고서",
        decision: SpcDecisionResult | None = None,
    ) -> dict[str, Path]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = self.output_dir / f"SPC_종합보고서_{ts}.xlsx"
        pdf_path = self.output_dir / f"SPC_종합보고서_{ts}.pdf"

        self._write_excel(excel_path, result, charts, raw_sample, study_info, report_title, decision)
        self._write_pdf(pdf_path, result, charts, study_info, report_title, raw_sample, decision)

        logger.info("종합 보고서: %s, %s", excel_path, pdf_path)
        return {"excel": excel_path, "pdf": pdf_path, "excel_detail": excel_path}

    def _write_excel(
        self,
        path: Path,
        result: SpcAnalysisResult,
        charts: ChartPaths,
        raw_sample: pd.DataFrame,
        study_info: dict,
        title: str,
        decision: SpcDecisionResult | None = None,
    ) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "종합"

        # 제목
        ws.merge_cells("A1:L1")
        c = ws["A1"]
        c.value = title
        c.font = Font(bold=True, size=14, color="1F4E79")
        c.alignment = Alignment(horizontal="center")

        ws.merge_cells("A2:L2")
        ws["A2"].value = "AIAG / VDA SPC Harmonized Standard — Process Capability Study"
        ws["A2"].font = Font(size=9, italic=True, color="666666")
        ws["A2"].alignment = Alignment(horizontal="center")

        row = 4
        if decision:
            row = write_verdict_strip_on_summary(ws, decision, start_row=3)

        meta_start = row

        # 메타데이터 (좌측)
        meta_rows = self._build_meta_rows(result, study_info, decision)
        for label, value in meta_rows:
            ws.cell(row, 1, label).font = LABEL_FONT
            ws.cell(row, 1).border = BORDER
            val_cell = ws.cell(row, 2, value)
            val_cell.font = VALUE_FONT
            val_cell.border = BORDER
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
            row += 1

        # 공정능력 지표 (우측) — 메타와 동일 시작행 (판정 스트립과 겹치지 않게)
        cap_start = meta_start
        cap_headers = ["지표", "값"]
        for i, h in enumerate(cap_headers):
            cell = ws.cell(cap_start, 6 + i, h)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.border = BORDER

        cap_rows = self._capability_rows(result)
        for i, (k, v) in enumerate(cap_rows):
            r = cap_start + 1 + i
            ws.cell(r, 6, k).font = LABEL_FONT
            ws.cell(r, 6).border = BORDER
            ws.cell(r, 7, v).font = VALUE_FONT
            ws.cell(r, 7).border = BORDER

        # 차트 2x2 배치
        chart_row = row + 1
        positions = [
            (charts.histogram, f"A{chart_row}"),
            (charts.raw_chart, f"G{chart_row}"),
            (charts.prob_plot, f"A{chart_row + 18}"),
            (charts.control_chart, f"G{chart_row + 18}"),
        ]
        for img_path, anchor in positions:
            if img_path.exists():
                img = XLImage(str(img_path))
                img.width = 340
                img.height = 255
                ws.add_image(img, anchor)

        # §20 차트별 전문가 결론·권고
        concl_row = chart_row + 36
        ws.merge_cells(f"A{concl_row}:L{concl_row}")
        ws[f"A{concl_row}"].value = "20. Conclusions / Recommendations (차트별 품질 전문가 점검)"
        ws[f"A{concl_row}"].font = LABEL_FONT
        concl_body_row = concl_row + 1
        concl_end_row = concl_row + 32
        ws.merge_cells(f"A{concl_body_row}:L{concl_end_row}")
        concl_cell = ws[f"A{concl_body_row}"]
        concl_cell.value = _conclusion_text(result, raw_sample, decision)
        concl_cell.alignment = Alignment(wrap_text=True, vertical="top")
        concl_cell.font = Font(size=8)

        for col in range(1, 13):
            ws.column_dimensions[get_column_letter(col)].width = 14

        sheet_registry = self._add_detail_sheets(wb, result, raw_sample, decision)
        if decision:
            add_decision_dashboard_sheet(wb, decision, study_info=study_info, insert_at=0)
            apply_decision_sheet_styles(wb, decision)
        add_glossary_sheet(wb, result)
        add_validation_sheet(wb, result, sheet_registry)
        wb.save(path)
        sanitize_xlsx_formula_file(path)

    def _build_meta_rows(
        self,
        result: SpcAnalysisResult,
        info: dict,
        decision: SpcDecisionResult | None = None,
    ) -> list[tuple[str, str]]:
        cap = result.capability
        rows = [
            ("1. 공정명", info.get("process", "-")),
            ("2. 설비/라인", info.get("machine", "-")),
            ("3. 품목", info.get("item", "-")),
            ("4. 특성(검사항목)", info.get("characteristic", "-")),
            ("5. USL", f"{cap.usl}" if cap else "-"),
            ("6. LSL", f"{cap.lsl}" if cap else "-"),
            ("7. 표본수", str(result.normality.n)),
            ("8. Subgroup 크기", str(result.control_limits.subgroup_size or "-")),
            ("9. 관리도 유형", result.control_limits.chart_type),
            ("10. 분석일시", datetime.now().strftime("%Y-%m-%d %H:%M")),
            ("15. 정규성 검정", f"{result.normality.test_name}, p={result.normality.p_value:.4f}"),
            ("16. 정규성 판정", "정규" if result.normality.is_normal else "비정규"),
            ("17. 관리상태", "관리外" if result.out_of_control_points else "관리內"),
        ]
        if info.get("data_source"):
            rows.insert(3, ("데이터 출처", info["data_source"]))
        if info.get("sampling"):
            rows.append(("18. 채취 방식", info["sampling"]))
        return rows

    def _capability_rows(self, result: SpcAnalysisResult) -> list[tuple[str, str]]:
        if not result.capability:
            return [("공정능력", "USL/LSL 미지정")]
        from scipy import stats as sp_stats

        c = result.capability
        pct_above = sp_stats.norm.sf((c.usl - c.mean) / c.std_within) * 100 if c.std_within else 0
        pct_below = sp_stats.norm.cdf((c.lsl - c.mean) / c.std_within) * 100 if c.std_within else 0
        return [
            ("USL", f"{c.usl:g}"),
            ("LSL", f"{c.lsl:g}"),
            ("Mean", f"{c.mean:.6f}"),
            ("Std(within)", f"{c.std_within:.6f}"),
            ("Std(overall)", f"{c.std_overall:.6f}"),
            ("Cp", f"{c.cp:.4f}"),
            ("Cpk", f"{c.cpk:.4f}"),
            ("Pp", f"{c.pp:.4f}"),
            ("Ppk", f"{c.ppk:.4f}"),
            ("예상 PPM", f"{c.ppm_est:.2f}"),
            ("P% > USL", f"{pct_above:.4f}%"),
            ("P% < LSL", f"{pct_below:.4f}%"),
        ]

    def _add_detail_sheets(
        self,
        wb: Workbook,
        result: SpcAnalysisResult,
        raw_sample: pd.DataFrame,
        decision: SpcDecisionResult | None = None,
    ) -> dict[str, SheetMeta]:
        sheets: list[tuple[str, pd.DataFrame]] = [
            ("정규성검정", pd.DataFrame([result.normality.to_dict()])),
        ]

        limits_data = []
        cl = result.control_limits
        for chart, lims in [
            ("Xbar", cl.xbar_limits),
            ("S", cl.s_limits),
            ("R", cl.r_limits),
            ("I", cl.i_limits),
            ("MR", cl.mr_limits),
        ]:
            if lims:
                for k, v in lims.items():
                    limits_data.append({"차트": chart, "항목": k, "값": v})
        sheets.append(("관리한계", pd.DataFrame(limits_data)))

        if result.capability:
            sheets.append(("공정능력", pd.DataFrame([result.capability.to_dict()])))

        if result.subgroup_stats is not None:
            sheets.append(("Subgroup통계", result.subgroup_stats))
        if result.individual_stats is not None:
            sheets.append(("Individual통계", result.individual_stats))

        sheets.append(("채취표본", raw_sample))

        if decision:
            log_rows = [
                {"rule_id": e.rule_id, "message": e.message, "priority": e.priority}
                for e in decision.control_chart.decision_log
            ]
            sheets.append(("판정로그", pd.DataFrame(log_rows)))
            verdict_rows = [{"항목": k, "값": v} for k, v in decision.verdict_summary.to_dict().items()]
            sheets.append(("판정요약", pd.DataFrame(verdict_rows)))
            commentary_rows = [
                {"구분": k, "내용": v}
                for k, v in decision.expert_commentary.to_dict().items()
            ]
            sheets.append(("전문가해석", pd.DataFrame(commentary_rows)))
            aiag_rows = [
                {"항목": "pre_control", "값": decision.aiag_vda_extensions.pre_control_recommendation},
                {"항목": "machine_capability_needed", "값": decision.aiag_vda_extensions.machine_capability_needed},
                {"항목": "machine_capability", "값": decision.aiag_vda_extensions.machine_capability.message},
                {"항목": "completeness_ok", "값": decision.aiag_vda_extensions.report_completeness.completeness_ok},
                {"항목": "missing_items", "값": ", ".join(decision.aiag_vda_extensions.report_completeness.missing_items)},
            ]
            sheets.append(("AIAG_VDA점검", pd.DataFrame(aiag_rows)))

        registry: dict[str, SheetMeta] = {}
        for name, df in sheets:
            registry[name] = self._write_dataframe_sheet(wb, name, df)
        return registry

    @staticmethod
    def _write_dataframe_sheet(wb: Workbook, name: str, df: pd.DataFrame) -> SheetMeta:
        ws = wb.create_sheet(name)
        headers: dict[str, int] = {}
        for c_idx, col in enumerate(df.columns, 1):
            cell = ws.cell(1, c_idx, col)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            headers[str(col)] = c_idx
        for r_idx, row in enumerate(df.itertuples(index=False), 2):
            for c_idx, val in enumerate(row, 1):
                if isinstance(val, float) and pd.isna(val):
                    val = None
                ws.cell(r_idx, c_idx, val)
        end_row = max(1, 1 + len(df))
        return SheetMeta(name=name, headers=headers, data_start_row=2, data_end_row=end_row)

    def _write_pdf(
        self,
        path: Path,
        result: SpcAnalysisResult,
        charts: ChartPaths,
        study_info: dict,
        title: str,
        raw_sample: pd.DataFrame | None = None,
        decision: SpcDecisionResult | None = None,
    ) -> None:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as exc:
            raise ImportError("PDF 생성에 reportlab 필요: pip install reportlab") from exc

        font_path = Path(r"C:\Windows\Fonts\malgun.ttf")
        font_name = "Helvetica"
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("MalgunGothic", str(font_path)))
            font_name = "MalgunGothic"

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontName=font_name, fontSize=14)
        body_style = ParagraphStyle("Body", parent=styles["Normal"], fontName=font_name, fontSize=9)
        label_style = ParagraphStyle("Label", parent=styles["Normal"], fontName=font_name, fontSize=8)

        doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm)
        story = []

        story.append(Paragraph(title, title_style))
        story.append(Paragraph("AIAG / VDA SPC Process Capability Study Report", body_style))
        story.append(Spacer(1, 6))

        meta = self._build_meta_rows(result, study_info, decision)
        meta_table = Table([[a, b] for a, b in meta[:10]], colWidths=[55 * mm, 80 * mm])
        meta_table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), font_name, 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8EEF4")),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 8))

        cap = self._capability_rows(result)
        cap_table = Table([["지표", "값"]] + list(cap), colWidths=[40 * mm, 35 * mm])
        cap_table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), font_name, 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]))
        story.append(cap_table)
        story.append(Spacer(1, 8))

        img_w, img_h = 120 * mm, 55 * mm
        for chart_path in [charts.histogram, charts.raw_chart, charts.prob_plot, charts.control_chart]:
            if chart_path.exists():
                story.append(Image(str(chart_path), width=img_w, height=img_h))
                story.append(Spacer(1, 4))

        concl_style = ParagraphStyle(
            "Conclusion",
            parent=label_style,
            fontSize=7,
            leading=9,
            spaceBefore=4,
        )
        concl_html = _conclusion_text(result, raw_sample, decision).replace("\n", "<br/>")
        story.append(Paragraph("<b>20. Conclusions / Recommendations</b>", label_style))
        story.append(Paragraph(concl_html, concl_style))
        doc.build(story)
