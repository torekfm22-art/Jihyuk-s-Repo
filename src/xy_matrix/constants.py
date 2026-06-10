"""X-Y 매트릭스 분석 상수."""
from __future__ import annotations

# 인자 유형 행 키워드 (부분 일치, 대소문자 무시)
Y_TYPE_KEYWORDS = (
    "결과 y", "결과y", "y인자", "종속", "종속변수", "response", "target",
    "품질특성", "검사결과", "출력", "y변수",
)
X_QUANT_KEYWORDS = (
    "계량형 x", "계량형x", "계량 x", "연속형 x", "연속 x", "numeric x",
    "공정변수", "measurement", "연속형",
)
X_CAT_KEYWORDS = (
    "범주형 x", "범주형x", "범주 x", "이산 x", "categorical", "범주형",
    "구분 x", "수준",
)
X_GENERIC_KEYWORDS = ("x인자", "독립", "공정인자", "predictor", "입력", "x변수", "factor")

# 날짜/시간 컬럼명 패턴
DATETIME_NAME_KEYWORDS = (
    "생산일", "측정일", "작업일", "검사일", "일시", "시각", "timestamp",
    "date", "time", "datetime", "수집일",
)

# 제어 불가(환경) 인자 키워드
ENV_UNCONTROLLABLE_KEYWORDS = (
    "외기", "대기", "습도", "기온_외", "온도_외부", "외부온", "날씨",
    "ambient", "humidity", "outside",
)

DEFAULT_SCORE_THRESHOLDS = {"strong": 0.7, "moderate": 0.4}
P_VALUE_ALPHA = 0.05

# Y/X 유형 라벨
TYPE_CONTINUOUS = "계량형"
TYPE_CATEGORICAL = "범주형"
TYPE_COUNT = "계수형"
