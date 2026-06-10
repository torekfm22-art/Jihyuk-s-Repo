"""
품질지표 계산 모듈
"""
import pandas as pd
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MetricsCalculator:
    """품질지표 계산"""
    
    def __init__(self, data: pd.DataFrame):
        self.data = data.copy()
        self.results = None
    
    def calculate_defect_rate(self) -> Optional[pd.DataFrame]:
        """
        불량률 계산 (불량건수 / 검사건수 * 100)
        
        Returns:
            불량률이 추가된 DataFrame
        """
        try:
            if '검사건수' not in self.data.columns or '불량건수' not in self.data.columns:
                logger.error("필수 컬럼이 없습니다")
                return None
            
            self.data['불량률(%)'] = (
                self.data['불량건수'] / self.data['검사건수'] * 100
            ).round(2)
            
            logger.info("불량률 계산 완료")
            return self.data
        
        except Exception as e:
            logger.error(f"불량률 계산 오류: {str(e)}")
            return None
    
    def calculate_pass_rate(self) -> Optional[pd.DataFrame]:
        """
        합격률 계산 (1 - 불량률)
        
        Returns:
            합격률이 추가된 DataFrame
        """
        try:
            if '불량률(%)' not in self.data.columns:
                self.calculate_defect_rate()
            
            self.data['합격률(%)'] = (100 - self.data['불량률(%)']).round(2)
            
            logger.info("합격률 계산 완료")
            return self.data
        
        except Exception as e:
            logger.error(f"합격률 계산 오류: {str(e)}")
            return None
    
    def calculate_all_metrics(self) -> Optional[pd.DataFrame]:
        """모든 품질지표 계산"""
        try:
            self.calculate_defect_rate()
            self.calculate_pass_rate()
            
            # 일일 통계
            if '날짜' in self.data.columns:
                self.data['요일'] = self.data['날짜'].dt.day_name()
            
            self.results = self.data
            logger.info("모든 품질지표 계산 완료")
            return self.results
        
        except Exception as e:
            logger.error(f"통합 계산 오류: {str(e)}")
            return None
    
    def get_summary_statistics(self) -> dict:
        """
        요약 통계 반환
        
        Returns:
            요약 통계 딕셔너리
        """
        if self.data is None or len(self.data) == 0:
            return {}
        
        stats = {
            '총검사건수': self.data['검사건수'].sum(),
            '총불량건수': self.data['불량건수'].sum(),
            '평균불량률(%)': self.data['불량률(%)'].mean() if '불량률(%)' in self.data.columns else 0,
            '평균합격률(%)': self.data['합격률(%)'].mean() if '합격률(%)' in self.data.columns else 0,
            '최고불량률(%)': self.data['불량률(%)'].max() if '불량률(%)' in self.data.columns else 0,
            '최저불량률(%)': self.data['불량률(%)'].min() if '불량률(%)' in self.data.columns else 0,
        }
        
        return stats
    
    def get_results(self) -> Optional[pd.DataFrame]:
        """계산 결과 반환"""
        return self.results
