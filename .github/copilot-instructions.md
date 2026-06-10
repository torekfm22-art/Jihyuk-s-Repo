# 품질실적 집계 자동화 프로그램 - Copilot 가이드

## 프로젝트 개요
- **목적**: Excel 기반 품질실적 데이터의 자동 집계 및 분석
- **언어**: Python 3.9+
- **주요 기능**:
  - Excel 파일에서 품질데이터 읽기
  - 불량률, 합격률 등 수치 자동 계산
  - 일정 기반 스케줄 자동화

## 프로젝트 구조
```
.
├── src/                          # 소스 코드
│   ├── __init__.py
│   ├── main.py                  # 메인 애플리케이션
│   ├── data_processor.py         # Excel 데이터 처리
│   ├── metrics_calculator.py     # 품질지표 계산
│   └── scheduler.py              # 스케줄 관리
├── config/                       # 설정 파일
│   ├── __init__.py
│   └── settings.py               # 프로젝트 설정
├── data/                         # 데이터 디렉토리
│   ├── input/                    # 입력 데이터
│   └── output/                   # 출력 결과
├── requirements.txt              # Python 의존성
├── .env.example                  # 환경 변수 예시
├── README.md                     # 프로젝트 문서
└── .github/copilot-instructions.md  # 이 파일

## 설정 및 실행 방법

### 1. 환경 설정
```bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (Windows)
venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 설정 파일 작성
- `.env` 파일을 `.env.example`을 기준으로 생성
- `config/settings.py`에서 필요한 설정 수정

### 3. 데이터 준비
- Excel 파일을 `data/input/` 디렉토리에 배치

### 4. 프로그램 실행
```bash
python src/main.py
```

## 주요 모듈 설명

### data_processor.py
- Excel 파일 읽기/쓰기
- 데이터 검증 및 정제

### metrics_calculator.py
- 불량률 계산
- 합격률 계산
- 기타 품질지표 계산

### scheduler.py
- APScheduler를 이용한 스케줄 관리
- 정기적인 자동 실행

## 개발 팁
- 모든 데이터 처리는 pandas를 활용
- Excel 작업은 openpyxl 사용
- 로깅은 Python logging 모듈 활용
- 설정값은 environment variables 또는 config/settings.py에서 관리
