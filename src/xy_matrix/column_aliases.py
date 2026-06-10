"""
Raw 템플릿·MES/QMS 컬럼명 alias (구조 인식 보조).
"""
from __future__ import annotations

import re

# 인자 유형 행 셀에 자주 쓰이는 표기 (정규화 전 부분 일치)
FACTOR_TYPE_CELL_HINTS = (
    "결과", "계량", "범주", "인자", "종속", "독립", "공정변수",
    "response", "predictor", "target", "y", "x",
)

# 컬럼명 → Y 후보 (품질 특성)
Y_COLUMN_ALIASES = (
    "인플레이터중량", "인플레이터 중량", "중량", "측정값", "결과값", "결과",
    "검사값", "품질값", "characteristic", "response", "target", "y값",
)

# 컬럼명 → X 후보에서 제외
META_COLUMN_ALIASES = (
    "no", "번호", "id", "seq", "순번", "비고", "remark", "메모",
)

# 컬럼명 힌트: 계량형 X
X_QUANT_NAME_HINTS = (
    "온도", "압력", "속도", "유량", "전압", "전류", "시간", "rpm",
    "temp", "pressure", "weight", "thickness", "값",
)

# 컬럼명 힌트: 범주형 X
X_CAT_NAME_HINTS = (
    "라인", "공정", "설비", "교대", "작업자", "lot", "로트", "품번", "모델", "shift",
)


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", str(name).lower())


def column_name_suggests_y(name: str) -> bool:
    n = _norm(name)
    return any(_norm(a) in n or n in _norm(a) for a in Y_COLUMN_ALIASES)


def column_name_suggests_meta(name: str) -> bool:
    n = _norm(name)
    return any(_norm(a) == n or n.endswith(_norm(a)) for a in META_COLUMN_ALIASES)


def column_name_suggests_x_quant(name: str) -> bool:
    n = _norm(name)
    return any(h in n for h in (_norm(x) for x in X_QUANT_NAME_HINTS))


def column_name_suggests_x_cat(name: str) -> bool:
    n = _norm(name)
    return any(h in n for h in (_norm(x) for x in X_CAT_NAME_HINTS))
