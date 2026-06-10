"""
프로젝트 설정 모듈
"""
import os
from dotenv import load_dotenv
from pathlib import Path

from config.app_paths import get_project_root

# .env 파일 로드 (exe 옆 .env 있으면 적용)
load_dotenv(get_project_root() / ".env")

# 기본 경로 설정 (exe: 실행 파일 폴더 기준)
BASE_DIR = get_project_root()
INPUT_PATH = os.getenv('INPUT_PATH', str(BASE_DIR / 'data' / 'input'))
OUTPUT_PATH = os.getenv('OUTPUT_PATH', str(BASE_DIR / 'data' / 'output'))

# 로깅 설정
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# 스케줄 설정
SCHEDULE_ENABLED = os.getenv('SCHEDULE_ENABLED', 'true').lower() == 'true'
SCHEDULE_TIME = os.getenv('SCHEDULE_TIME', '09:00')
SCHEDULE_INTERVAL_DAYS = int(os.getenv('SCHEDULE_INTERVAL_DAYS', '1'))

# Excel 설정
EXCEL_SHEET_NAME = os.getenv('EXCEL_SHEET_NAME', 'Quality')
EXCEL_DATE_FORMAT = os.getenv('EXCEL_DATE_FORMAT', '%Y-%m-%d')

# 디렉토리 생성
os.makedirs(INPUT_PATH, exist_ok=True)
os.makedirs(OUTPUT_PATH, exist_ok=True)
