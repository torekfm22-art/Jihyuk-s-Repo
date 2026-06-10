"""
Excel 데이터 처리 모듈
"""
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class DataProcessor:
    """Excel 파일 읽기/쓰기 및 데이터 처리"""
    
    def __init__(self, input_path: str):
        self.input_path = Path(input_path)
        self.data = None
    
    def read_excel(self, filename: str, sheet_name: str = '품질') -> Optional[pd.DataFrame]:
        """
        Excel 파일 읽기
        
        Args:
            filename: 파일명
            sheet_name: 시트 이름
            
        Returns:
            DataFrame 또는 None
        """
        try:
            file_path = self.input_path / filename
            if not file_path.exists():
                logger.warning(f"파일을 찾을 수 없습니다: {file_path}")
                return None
            
            self.data = pd.read_excel(file_path, sheet_name=sheet_name)
            logger.info(f"파일 읽기 완료: {filename}")
            return self.data
        
        except Exception as e:
            logger.error(f"파일 읽기 오류: {str(e)}")
            return None
    
    def validate_data(self) -> bool:
        """
        데이터 검증
        
        Returns:
            bool: 검증 성공 여부
        """
        if self.data is None:
            logger.warning("검증할 데이터가 없습니다")
            return False
        
        # 필수 컬럼 확인
        required_columns = ['날짜', '검사건수', '불량건수']
        missing_columns = [col for col in required_columns if col not in self.data.columns]
        
        if missing_columns:
            logger.error(f"필수 컬럼이 없습니다: {missing_columns}")
            return False
        
        return True
    
    def clean_data(self):
        """데이터 정제"""
        if self.data is None:
            return
        
        # 빈 행 제거
        self.data = self.data.dropna(subset=['날짜'])
        
        # 데이터 타입 변환
        self.data['날짜'] = pd.to_datetime(self.data['날짜'], errors='coerce')
        self.data['검사건수'] = pd.to_numeric(self.data['검사건수'], errors='coerce')
        self.data['불량건수'] = pd.to_numeric(self.data['불량건수'], errors='coerce')
        
        logger.info("데이터 정제 완료")
    
    def get_data(self) -> Optional[pd.DataFrame]:
        """현재 데이터 반환"""
        return self.data
    
    def save_result(self, output_filename: str, data: pd.DataFrame, output_path: str):
        """
        결과를 Excel 파일로 저장
        
        Args:
            output_filename: 출력 파일명
            data: 저장할 DataFrame
            output_path: 출력 경로
        """
        try:
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = output_dir / output_filename
            data.to_excel(file_path, sheet_name='결과', index=False)
            logger.info(f"결과 저장 완료: {file_path}")
        
        except Exception as e:
            logger.error(f"결과 저장 오류: {str(e)}")
