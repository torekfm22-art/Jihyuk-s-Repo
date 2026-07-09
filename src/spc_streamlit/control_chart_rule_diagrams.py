"""관리도 해석 Rule 9종 — 조건별 SVG 도식."""
from __future__ import annotations

from typing import Callable

W, H = 300, 112
CL, UCL, LCL = 55, 14, 96
S1U, S1L = 41, 69
S2U, S2L = 28, 82
USL_Y, LSL_Y = 6, 104


def _svg_wrap(body: str, title: str = "") -> str:
    title_el = f'<title>{title}</title>' if title else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="100%" height="auto" role="img" aria-label="{title}">'
        f"{title_el}{body}</svg>"
    )


def _axis_lines(
    *,
    show_spec: bool = False,
    show_sigma: bool = True,
) -> str:
    parts = [
        f'<line x1="8" y1="{CL}" x2="{W-8}" y2="{CL}" stroke="#333" stroke-width="1.2"/>',
        f'<line x1="8" y1="{UCL}" x2="{W-8}" y2="{UCL}" stroke="#C00000" stroke-width="1" stroke-dasharray="5,3"/>',
        f'<line x1="8" y1="{LCL}" x2="{W-8}" y2="{LCL}" stroke="#C00000" stroke-width="1" stroke-dasharray="5,3"/>',
    ]
    if show_sigma:
        for y in (S1U, S1L, S2U, S2L):
            parts.append(
                f'<line x1="8" y1="{y}" x2="{W-8}" y2="{y}" stroke="#999" stroke-width="0.8" stroke-dasharray="3,3"/>'
            )
    if show_spec:
        parts.append(
            f'<line x1="8" y1="{USL_Y}" x2="{W-8}" y2="{USL_Y}" stroke="#7030A0" stroke-width="1.2"/>'
        )
        parts.append(
            f'<line x1="8" y1="{LSL_Y}" x2="{W-8}" y2="{LSL_Y}" stroke="#7030A0" stroke-width="1.2"/>'
        )
        parts.append(f'<text x="10" y="{USL_Y-3}" font-size="7" fill="#7030A0">USL</text>')
        parts.append(f'<text x="10" y="{LSL_Y+9}" font-size="7" fill="#7030A0">LSL</text>')
    parts.append(f'<text x="{W-22}" y="{UCL+3}" font-size="7" fill="#C00000">UCL</text>')
    parts.append(f'<text x="{W-20}" y="{CL+3}" font-size="7" fill="#333">CL</text>')
    parts.append(f'<text x="{W-22}" y="{LCL+3}" font-size="7" fill="#C00000">LCL</text>')
    return "".join(parts)


def _polyline(points: list[tuple[float, float]], *, stroke: str = "#1F4E79") -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="2" stroke-linejoin="round"/>'


def _dots(points: list[tuple[float, float]], *, fill: str = "#1F4E79", r: float = 3) -> str:
    return "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" stroke="#fff" stroke-width="0.5"/>'
        for x, y in points
    )


def _highlight(points: list[tuple[float, float]], *, r: float = 4.5) -> str:
    return _dots(points, fill="#FFC000", r=r)


def _diagram_spec_limit_out() -> str:
    pts = [(22, 58), (42, 54), (62, 4), (82, 56), (102, 52), (122, 55), (142, 53)]
    body = _axis_lines(show_spec=True, show_sigma=True)
    body += _polyline(pts)
    body += _dots(pts)
    body += _highlight([(62, 4)])
    return _svg_wrap(body, "규격상한/하한 이탈")


def _diagram_control_limit_out() -> str:
    pts = [(22, 56), (42, 52), (62, 8), (82, 54), (102, 50), (122, 53), (142, 51)]
    body = _axis_lines()
    body += _polyline(pts)
    body += _dots(pts)
    body += _highlight([(62, 8)])
    return _svg_wrap(body, "관리상한/하한 이탈")


def _diagram_oscillation() -> str:
    xs = list(range(18, 285, 18))
    ys = [CL + (10 if i % 2 == 0 else -10) for i in range(len(xs))]
    pts = list(zip(xs, ys, strict=True))
    body = _axis_lines()
    body += _polyline(pts)
    body += _dots(pts[:8], fill="#1F4E79")
    body += _highlight(list(pts[4:12]))
    return _svg_wrap(body, "주기성 Oscillation")


def _diagram_zone_rule_1() -> str:
    pts = [(40, 56), (70, 24), (100, 26), (130, 54), (160, 52)]
    body = _axis_lines()
    body += _polyline(pts)
    body += _dots(pts)
    body += _highlight([(70, 24), (100, 26)])
    body += '<rect x="34" y="12" width="78" height="50" fill="none" stroke="#E67E22" stroke-width="1" stroke-dasharray="4,2"/>'
    return _svg_wrap(body, "2σ/3σ 편중")


def _diagram_hugging() -> str:
    xs = list(range(20, 280, 16))
    ys = [CL + (3 if i % 3 == 0 else -2 if i % 3 == 1 else 1) for i in range(len(xs))]
    pts = list(zip(xs, ys, strict=True))
    body = _axis_lines()
    body += f'<rect x="12" y="{S1U}" width="{W-24}" height="{S1L-S1U}" fill="#E8F4FC" stroke="#1F4E79" stroke-width="0.8" opacity="0.5"/>'
    body += _polyline(pts)
    body += _highlight(pts[2:10])
    return _svg_wrap(body, "중심 집중")


def _diagram_shift() -> str:
    pts = [(30, 38), (55, 36), (80, 39), (105, 37), (130, 38), (155, 40), (180, 36)]
    body = _axis_lines()
    body += _polyline(pts)
    body += _highlight(pts[:7])
    body += _dots(pts[5:])
    return _svg_wrap(body, "한쪽 집중 Shift")


def _diagram_trend() -> str:
    pts = [(25, 88), (50, 76), (75, 66), (100, 56), (125, 46), (150, 36), (175, 28)]
    body = _axis_lines()
    body += _polyline(pts)
    body += _highlight(pts[:6])
    body += _dots(pts[6:])
    return _svg_wrap(body, "경향성 Trend")


def _diagram_zone_rule_2() -> str:
    pts = [(25, 36), (55, 38), (85, 35), (115, 37), (145, 54), (175, 52)]
    body = _axis_lines()
    body += _polyline(pts)
    body += _highlight(pts[:4])
    body += _dots(pts[4:])
    body += '<rect x="18" y="30" width="108" height="14" fill="none" stroke="#E67E22" stroke-width="1" stroke-dasharray="4,2"/>'
    return _svg_wrap(body, "1σ 외 편중")


def _diagram_excess_dispersion() -> str:
    ys = [32, 84, 30, 86, 34, 88, 31, 85, 52, 54]
    xs = list(range(22, 22 + 18 * len(ys), 18))
    pts = list(zip(xs, ys, strict=True))
    body = _axis_lines()
    body += _polyline(pts)
    body += _highlight(pts[:8])
    body += _dots(pts[8:])
    return _svg_wrap(body, "과도 분산")


_RULE_DIAGRAMS: dict[str, Callable[[], str]] = {
    "SPEC_LIMIT_OUT": _diagram_spec_limit_out,
    "CONTROL_LIMIT_OUT": _diagram_control_limit_out,
    "OSCILLATION": _diagram_oscillation,
    "ZONE_RULE_1": _diagram_zone_rule_1,
    "HUGGING": _diagram_hugging,
    "SHIFT": _diagram_shift,
    "TREND": _diagram_trend,
    "ZONE_RULE_2": _diagram_zone_rule_2,
    "EXCESS_DISPERSION": _diagram_excess_dispersion,
}


def rule_diagram_svg(rule_id: str) -> str:
    fn = _RULE_DIAGRAMS.get(rule_id)
    if fn is None:
        return _svg_wrap(_axis_lines(), rule_id)
    return fn()
