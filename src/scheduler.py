"""
스케줄 관리 모듈
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from typing import Callable

logger = logging.getLogger(__name__)


class ScheduleManager:
    """APScheduler를 이용한 스케줄 관리"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.is_running = False
    
    def add_cron_job(self, 
                     job_name: str,
                     func: Callable,
                     hour: int = 9,
                     minute: int = 0,
                     day_of_week: str = 'mon-fri'):
        """
        크론 기반 일정 추가 (평일 09:00)
        
        Args:
            job_name: 작업 이름
            func: 실행할 함수
            hour: 시간 (0-23)
            minute: 분 (0-59)
            day_of_week: 요일 (mon-sun, mon-fri 등)
        """
        try:
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                day_of_week=day_of_week
            )
            
            self.scheduler.add_job(
                func,
                trigger,
                id=job_name,
                name=job_name,
                replace_existing=True
            )
            
            logger.info(f"작업 추가: {job_name} ({hour:02d}:{minute:02d})")
        
        except Exception as e:
            logger.error(f"작업 추가 오류: {str(e)}")
    
    def add_interval_job(self,
                        job_name: str,
                        func: Callable,
                        days: int = 1,
                        hours: int = 0,
                        minutes: int = 0):
        """
        간격 기반 일정 추가
        
        Args:
            job_name: 작업 이름
            func: 실행할 함수
            days: 일 단위
            hours: 시간 단위
            minutes: 분 단위
        """
        try:
            self.scheduler.add_job(
                func,
                'interval',
                days=days,
                hours=hours,
                minutes=minutes,
                id=job_name,
                name=job_name,
                replace_existing=True
            )
            
            logger.info(f"간격 작업 추가: {job_name} (매 {days}일)")
        
        except Exception as e:
            logger.error(f"작업 추가 오류: {str(e)}")
    
    def start(self):
        """스케줄러 시작"""
        try:
            if not self.is_running:
                self.scheduler.start()
                self.is_running = True
                logger.info("스케줄러 시작")
        
        except Exception as e:
            logger.error(f"스케줄러 시작 오류: {str(e)}")
    
    def stop(self):
        """스케줄러 중지"""
        try:
            if self.is_running:
                self.scheduler.shutdown()
                self.is_running = False
                logger.info("스케줄러 중지")
        
        except Exception as e:
            logger.error(f"스케줄러 중지 오류: {str(e)}")
    
    def get_jobs(self):
        """등록된 작업 목록 반환"""
        return self.scheduler.get_jobs()
    
    def list_jobs(self):
        """등록된 작업 출력"""
        jobs = self.scheduler.get_jobs()
        if not jobs:
            logger.info("등록된 작업이 없습니다")
            return
        
        for job in jobs:
            logger.info(f"작업: {job.name} (ID: {job.id})")
