"""입력 파일 경로 해석 (전체 경로 / data/input 상대 경로)."""
from __future__ import annotations

from pathlib import Path


def resolve_input_path(file_ref: str | None, input_dir: Path) -> Path | None:
    """
    GUI·설정에서 넘어온 파일 참조를 실제 Path로 변환.
    파일이 없으면 None (MES/QMS 선택적 입력).
    """
    if not file_ref or not str(file_ref).strip():
        return None

    ref = Path(file_ref.strip())
    if ref.is_absolute() and ref.exists():
        return ref.resolve()

    candidate = input_dir / ref.name
    if candidate.exists():
        return candidate.resolve()

    if ref.exists():
        return ref.resolve()

    raise FileNotFoundError(
        f"파일을 찾을 수 없습니다: {file_ref}\n"
        f"확인: {candidate}\n"
        f"※ QMS 미사용 시 QMS 입력란을 비워두세요."
    )
