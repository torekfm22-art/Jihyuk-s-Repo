"""
품질실적 집계 자동화 프로그램
메인 애플리케이션
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('quality_automation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

from config.settings import INPUT_PATH, OUTPUT_PATH, SCHEDULE_ENABLED, SCHEDULE_TIME, SCHEDULE_INTERVAL_DAYS
from src.data_processor import DataProcessor
from src.metrics_calculator import MetricsCalculator
from src.scheduler import ScheduleManager


class QualityAutomation:
    """품질실적 집계 자동화 메인 클래스"""
    
    def __init__(self):
        self.processor = DataProcessor(INPUT_PATH)
        self.schedule_manager = ScheduleManager()
        self.output_path = OUTPUT_PATH
    
    def process_quality_data(self, filename: str = '품질데이터.xlsx') -> bool:
        """
        품질데이터 처리 메인 함수
        
        Args:
            filename: 입력 Excel 파일명
            
        Returns:
            처리 성공 여부
        """
        logger.info(f"품질데이터 처리 시작: {filename}")
        
        # 데이터 읽기
        data = self.processor.read_excel(filename)
        if data is None:
            logger.error("데이터 읽기 실패")
            return False
        
        # 데이터 검증
        if not self.processor.validate_data():
            logger.error("데이터 검증 실패")
            return False
        
        # 데이터 정제
        self.processor.clean_data()
        
        # 품질지표 계산
        data = self.processor.get_data()
        calculator = MetricsCalculator(data)
        result_data = calculator.calculate_all_metrics()
        
        if result_data is None:
            logger.error("지표 계산 실패")
            return False
        
        # 요약 통계 출력
        stats = calculator.get_summary_statistics()
        logger.info(f"요약 통계: {stats}")
        
        # 결과 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f'품질실적_결과_{timestamp}.xlsx'
        self.processor.save_result(output_filename, result_data, self.output_path)
        
        logger.info("품질데이터 처리 완료")
        return True
    
    def setup_scheduler(self):
        """스케줄 설정"""
        if not SCHEDULE_ENABLED:
            logger.info("스케줄 기능이 비활성화되었습니다")
            return
        
        try:
            # 시간 파싱 (HH:MM 형식)
            hour, minute = map(int, SCHEDULE_TIME.split(':'))
            
            # 크론 작업 추가
            self.schedule_manager.add_cron_job(
                'quality_aggregation',
                self.process_quality_data,
                hour=hour,
                minute=minute,
                day_of_week='mon-fri'
            )
            
            logger.info(f"스케줄 설정 완료 (매일 {SCHEDULE_TIME})")
        
        except Exception as e:
            logger.error(f"스케줄 설정 오류: {str(e)}")
    
    def run(self):
        """프로그램 실행"""
        try:
            logger.info("=" * 50)
            logger.info("품질실적 집계 자동화 프로그램 시작")
            logger.info("=" * 50)
            
            # 일회성 처리
            self.process_quality_data()
            
            # 스케줄 설정
            self.setup_scheduler()
            
            # 스케줄러 시작
            if SCHEDULE_ENABLED:
                self.schedule_manager.start()
                self.schedule_manager.list_jobs()
                
                logger.info("스케줄러가 실행 중입니다. 종료하려면 Ctrl+C를 누르세요...")
                
                # 무한 대기
                import time
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("프로그램을 종료합니다...")
                    self.schedule_manager.stop()
            
        except Exception as e:
            logger.error(f"프로그램 실행 오류: {str(e)}")


def main():
    """메인 함수"""
    app = QualityAutomation()
    app.run()


if __name__ == '__main__':
    main()
