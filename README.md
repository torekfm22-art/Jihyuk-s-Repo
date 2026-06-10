# 품질실적 집계 자동화 프로그램

Excel 기반의 품질실적 데이터를 자동으로 집계하고 분석하는 Python 프로그램입니다.

## 주요 기능

- **Excel 데이터 처리**: 품질데이터 Excel 파일 읽기 및 검증
- **자동 계산**: 불량률, 합격률 등 품질지표 자동 계산
- **일정 기반 자동화**: APScheduler를 이용한 정기적 자동 실행
- **결과 저장**: 계산 결과를 Excel 파일로 자동 저장
- **로깅**: 모든 작업 과정을 로그 파일에 기록

## 프로젝트 구조

```
quality-automation/
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
└── .github/copilot-instructions.md  # Copilot 가이드
```

## 설치 및 실행

### 1. 환경 설정

```bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (Windows)
venv\Scripts\activate

# 가상환경 활성화 (macOS/Linux)
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 설정 파일 작성

`.env.example` 파일을 참고하여 `.env` 파일을 생성합니다:

```bash
cp .env.example .env
```

필요시 `.env` 파일에서 다음 항목을 수정합니다:
- `INPUT_PATH`: 입력 데이터 경로
- `OUTPUT_PATH`: 출력 결과 경로
- `SCHEDULE_TIME`: 스케줄 시간 (HH:MM)
- `SCHEDULE_INTERVAL_DAYS`: 스케줄 간격 (일)

### 3. 데이터 준비

Excel 파일을 `data/input/` 디렉토리에 배치합니다.

**필수 컬럼:**
- `날짜`: 데이터 날짜
- `검사건수`: 검사한 제품 수량
- `불량건수`: 불량 제품 수량

### 4. 프로그램 실행

```bash
python src/main.py
```

## 주요 모듈 설명

### data_processor.py
Excel 파일의 읽기/쓰기 및 데이터 검증을 담당합니다.

- `read_excel()`: Excel 파일 읽기
- `validate_data()`: 필수 컬럼 검증
- `clean_data()`: 데이터 정제
- `save_result()`: 결과 저장

### metrics_calculator.py
품질지표를 계산합니다.

- `calculate_defect_rate()`: 불량률 계산 (불량건수/검사건수*100)
- `calculate_pass_rate()`: 합격률 계산 (100-불량률)
- `calculate_all_metrics()`: 모든 지표 계산
- `get_summary_statistics()`: 요약 통계

### scheduler.py
APScheduler를 이용한 스케줄 관리를 담당합니다.

- `add_cron_job()`: 크론 기반 작업 추가
- `add_interval_job()`: 간격 기반 작업 추가
- `start()`: 스케줄러 시작
- `stop()`: 스케줄러 중지

## 사용 예시

```python
from src.data_processor import DataProcessor
from src.metrics_calculator import MetricsCalculator

# 데이터 처리
processor = DataProcessor('./data/input')
data = processor.read_excel('품질데이터.xlsx')

# 지표 계산
calculator = MetricsCalculator(data)
results = calculator.calculate_all_metrics()

# 요약 통계 출력
stats = calculator.get_summary_statistics()
print(stats)
```

## 환경 변수

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| LOG_LEVEL | INFO | 로깅 레벨 |
| INPUT_PATH | ./data/input | 입력 데이터 경로 |
| OUTPUT_PATH | ./data/output | 출력 결과 경로 |
| SCHEDULE_ENABLED | true | 스케줄 활성화 |
| SCHEDULE_TIME | 09:00 | 실행 시간 |
| SCHEDULE_INTERVAL_DAYS | 1 | 실행 간격 (일) |
| EXCEL_SHEET_NAME | Quality | Excel 시트 이름 |
| EXCEL_DATE_FORMAT | %Y-%m-%d | 날짜 형식 |

## 로깅

모든 작업은 `quality_automation.log` 파일에 기록되며, 동시에 콘솔에도 출력됩니다.

## 라이선스

이 프로젝트는 내부용 도구입니다.

## 지원

문제가 발생하면 로그 파일을 확인하고, 필요시 설정 파일을 검토하세요.

---

## SPC 공정능력·관리도 자동 분석 (MES/QMS xlsx)

MES·QMS에서 **내보낸 xlsx 파일**을 읽어 표본 채취 → 정규성 검정 → X-bar R / I-MR 관리도 → Cp/Cpk 산출 → Excel·Word 보고서를 자동 생성합니다.

### xlsx 파일 배치

```
data/input/
├── mes_data.xlsx    ← MES에서 export
└── qms_data.xlsx    ← QMS에서 export
```

### GUI 실행 (개발·로컬)

```bash
pip install -r requirements.txt
python src/spc_gui.py
# 또는 run_spc_app.bat 더블클릭
```

앱에서 **「X-Y 매트릭스」** 탭: Raw data 시트(1행=인자유형, 2행=컬럼명)를 읽어 X인자별 통계·1-3-9 점수·CTP/SPC 권고·파레토 차트·Excel 보고서를 생성합니다.

```bash
python scripts/generate_xy_sample_data.py
python scripts/run_xy_matrix_analysis.py
```

결과 Excel: `XY_매트릭스`(서식 표), `파레토`(순위·누적% 표 + 파레토 차트 이미지), `분석요약` 시트.  
파레토 PNG: `data/output/charts/xy_pareto.png`

Raw 시트 작성 안내: `data/templates/XY_MATRIX_RAW_README.txt`

### EXE 배포 (Python 설치 불필요)

개발 PC에서 한 번만 빌드한 뒤, `dist\SPC_공정능력분석` 폴더를 ZIP으로 공유합니다.

```bash
pip install -r requirements.txt -r requirements-build.txt
build_exe.bat
```

- 실행 파일: `dist\SPC_공정능력분석\SPC_공정능력분석.exe`
- **폴더 전체**를 압축·전달 (exe만 복사하면 동작하지 않음)
- 결과·샘플: exe 옆 `data\input`, `data\output`

### CLI 실행

```bash
python scripts/generate_sample_data.py   # 샘플 xlsx 생성

# MES + QMS xlsx 병합 분석 (config/spc_job.yaml 기본)
python -m src.spc_main

# 단일 xlsx
python -m src.spc_main --file "통합데이터.xlsx" --sheet 0

# MES·QMS 각각 지정
python -m src.spc_main --mes-file mes_data.xlsx --qms-file qms_data.xlsx --process "조립공정"
```

### xlsx 필수·선택 컬럼

MES/QMS 시스템마다 컬럼명이 달라도 아래 alias를 자동 인식합니다.

| 구분 | 인식 컬럼명 예시 |
|------|------------------|
| **측정값 (필수)** | 측정값, 검사값, value |
| 측정일시 | 측정일시, 검사일시, datetime |
| 공정 | 공정, 공정명, process |
| 검사항목 | 특성, 검사항목, characteristic |
| USL/LSL | USL, LSL, 상한, 하한 |
| LOT | LOT, 배치번호, batch |

### 설정 예시 (`config/spc_job.yaml`)

```yaml
mes_file: mes_data.xlsx
qms_file: qms_data.xlsx
mes_sheet_name: 0
qms_sheet_name: "검사결과"
usl: 10.50
lsl: 9.50
filter_process: "조립공정"
filter_characteristic: "외径"
filter_source: null   # MES 또는 QMS만 분석할 때 지정
```

### 분석 흐름

```
MES/QMS 추출 → 필터(공정·품목·기간) → 표본 채취
    → Shapiro-Wilk 정규성 검정
    → X-bar R 또는 I-MR 관리도 (관리한계, 이탈점)
    → Cp, Cpk, Pp, Ppk, PPM 산출
    → Excel + PDF 보고서 자동 생성
```
