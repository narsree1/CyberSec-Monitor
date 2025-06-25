import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import atexit

logger = logging.getLogger(__name__)

scheduler = None

def scraping_job():
    """Scheduled job to scrape all sources"""
    try:
        logger.info("Starting scheduled scraping job...")
        from app import app
        with app.app_context():
            from scraper import scrape_all_sources
            article_count = scrape_all_sources()
            logger.info(f"Scheduled scraping completed. Found {article_count} new articles")
    except Exception as e:
        logger.error(f"Error in scheduled scraping job: {e}")

def cleanup_job():
    """Scheduled job to cleanup old logs and data"""
    try:
        logger.info("Starting cleanup job...")
        from app import app
        with app.app_context():
            from app import db
            from models import ScrapingLog
            from datetime import datetime, timedelta
            
            # Remove scraping logs older than 30 days
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            old_logs = ScrapingLog.query.filter(ScrapingLog.timestamp < cutoff_date).all()
            
            for log in old_logs:
                db.session.delete(log)
            
            db.session.commit()
            logger.info(f"Cleanup completed. Removed {len(old_logs)} old log entries")
        
    except Exception as e:
        logger.error(f"Error in cleanup job: {e}")

def start_scheduler():
    """Start the background scheduler"""
    global scheduler
    
    if scheduler is not None:
        logger.warning("Scheduler already started")
        return
    
    try:
        scheduler = BackgroundScheduler()
        
        # Schedule scraping every 2 hours
        scheduler.add_job(
            func=scraping_job,
            trigger=IntervalTrigger(hours=2),
            id='scraping_job',
            name='Scrape cybersecurity blogs',
            replace_existing=True,
            next_run_time=datetime.now()  # Run immediately on startup
        )
        
        # Schedule cleanup every day at 3 AM
        scheduler.add_job(
            func=cleanup_job,
            trigger='cron',
            hour=3,
            minute=0,
            id='cleanup_job',
            name='Cleanup old data',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("Scheduler started successfully")
        
        # Shut down the scheduler when exiting the app
        atexit.register(lambda: scheduler.shutdown())
        
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")

def stop_scheduler():
    """Stop the scheduler"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler = None
        logger.info("Scheduler stopped")

def get_scheduler_status():
    """Get current scheduler status"""
    if scheduler and scheduler.running:
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
            })
        return {
            'running': True,
            'jobs': jobs
        }
    else:
        return {
            'running': False,
            'jobs': []
        }
