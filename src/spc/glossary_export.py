"""SPC 용어·개념 — Streamlit/UI용 Markdown보내기."""
from __future__ import annotations

from src.spc.report_glossary_sheet import _formula_sections, _glossary_sections
from src.spc.statistics import SpcAnalysisResult


def glossary_to_markdown(result: SpcAnalysisResult | None = None) -> str:
    """용어_초보가이드 시트 내용을 Markdown으로 변환."""
    lines = [
        "# SPC · 공정능력 — 초보자용 용어 설명",
        "",
        "보고서를 처음 보실 때 이 내용부터 읽으시면 됩니다. "
        "§6 산출식은 본 프로그램이 실제로 사용하는 계산식(AIAG/Minitab 기준)입니다.",
        "",
    ]

    for section_title, entries in _glossary_sections(result):
        lines.append(f"## {section_title}")
        lines.append("")
        for term, short, detail, where in entries:
            lines.append(f"### {term}")
            lines.append(f"- **한 줄 요약:** {short}")
            lines.append(f"- **상세:** {detail}")
            lines.append(f"- **보고서 위치:** {where}")
            lines.append("")

    lines.append("## 6. 주요 산출값 산출식 (본 프로그램 적용)")
    lines.append("")
    for subtitle, entries in _formula_sections(result):
        lines.append(f"### {subtitle}")
        lines.append("")
        for name, formula, vars_desc, source, verify in entries:
            lines.append(f"**{name}**")
            lines.append(f"```\n{formula}\n```")
            lines.append(f"- 변수: {vars_desc}")
            lines.append(f"- 출처: {source} | 검증: {verify}")
            lines.append("")

    return "\n".join(lines)
