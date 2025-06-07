#!/usr/bin/env python
"""
Blog Automation Script
======================
This script starts the Celery worker and beat scheduler to automate blog publishing.
It ensures that a new blog is published every 5 minutes by running the configured tasks.
"""

import os
import sys
import time
import logging
import subprocess
import signal
import psutil
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('blog_automation.log')
    ]
)
logger = logging.getLogger(__name__)

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings')

def kill_existing_celery():
    """Kill any existing Celery processes to ensure clean startup"""
    logger.info("Checking for existing Celery processes...")
    killed = False
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'celery' in ' '.join(cmdline).lower():
                logger.info(f"Killing existing Celery process: {proc.info['pid']}")
                psutil.Process(proc.info['pid']).terminate()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    if killed:
        time.sleep(3)  # Give processes time to terminate
        logger.info("Existing Celery processes terminated")
    else:
        logger.info("No existing Celery processes found")

def start_celery_worker():
    """Start the Celery worker process with improved configuration"""
    logger.info("Starting Celery worker...")
    
    # Use increased concurrency and fair scheduling for better performance
    worker_cmd = "celery -A blogify worker --loglevel=INFO --concurrency=6 -O fair"
    
    # Start the worker with shell=True to ensure proper environment
    worker_process = subprocess.Popen(worker_cmd, shell=True)
    logger.info(f"Celery worker started with PID: {worker_process.pid}")
    return worker_process

def start_celery_beat():
    """Start the Celery beat scheduler"""
    logger.info("Starting Celery beat scheduler...")
    beat_cmd = "celery -A blogify beat --loglevel=INFO"
    beat_process = subprocess.Popen(beat_cmd, shell=True)
    logger.info(f"Celery beat started with PID: {beat_process.pid}")
    return beat_process

def check_process_health(process, name):
    """Check if a process is still running and healthy"""
    if process.poll() is not None:
        logger.error(f"{name} process died with return code: {process.returncode}")
        return False
    return True

def verify_blog_creation():
    """Verify that blogs are being created by checking the database"""
    try:
        # We need to import Django models here to avoid loading them before Django is configured
        import django
        django.setup()
        from blog.models import BlogPost
        from django.utils import timezone
        
        # Check for blogs created in the last 15 minutes
        recent_time = timezone.now() - timedelta(minutes=15)
        recent_blogs = BlogPost.objects.filter(created_at__gte=recent_time).count()
        
        if recent_blogs > 0:
            logger.info(f"Verification successful: {recent_blogs} blogs created in the last 15 minutes")
            return True
        else:
            logger.warning("No blogs created in the last 15 minutes. Automation may not be working.")
            return False
    except Exception as e:
        logger.error(f"Error verifying blog creation: {e}")
        return False

def run_blog_automation():
    """Run both Celery worker and beat scheduler for blog automation"""
    logger.info("=" * 60)
    logger.info("STARTING BLOG AUTOMATION")
    logger.info("This script will ensure a new blog is published every 5 minutes")
    logger.info("=" * 60)
    
    try:
        # Kill any existing Celery processes to ensure clean startup
        kill_existing_celery()
        
        # Start Celery processes
        worker_process = start_celery_worker()
        time.sleep(5)  # Wait for worker to initialize
        beat_process = start_celery_beat()
        
        # Monitor and keep running
        logger.info("Blog automation system is running. Press Ctrl+C to stop.")
        
        # Display scheduled tasks
        logger.info("Scheduled tasks:")
        logger.info("- Fetch trending topics: Every 5 minutes")
        logger.info("- Process trending topics: Every 5 minutes (30 seconds after fetch)")
        logger.info("- Ensure fallback topics: Every 5 minutes (60 seconds after fetch)")
        logger.info("- Create and publish blog: Every 5 minutes (90 seconds after fetch)")
        logger.info("- Publish scheduled blogs: Every 5 minutes")
        logger.info("- Update blog analytics: Every 15 minutes")
        logger.info("- Update freshness metrics: Every hour")
        
        # Keep the script running until interrupted
        next_verification = datetime.now() + timedelta(minutes=15)
        restart_count = 0
        
        while True:
            # Log status update every 5 minutes
            current_time = datetime.now()
            if current_time.minute % 5 == 0 and current_time.second < 10:
                logger.info(f"Status update: Blog automation running at {current_time.strftime('%H:%M:%S')}")
            
            # Check process health
            worker_healthy = check_process_health(worker_process, "Celery worker")
            beat_healthy = check_process_health(beat_process, "Celery beat")
            
            # Restart processes if needed
            if not worker_healthy:
                logger.warning("Restarting Celery worker...")
                worker_process = start_celery_worker()
                restart_count += 1
            
            if not beat_healthy:
                logger.warning("Restarting Celery beat...")
                beat_process = start_celery_beat()
                restart_count += 1
            
            # Verify blog creation every 15 minutes
            if current_time >= next_verification:
                logger.info("Performing verification check for blog creation...")
                if not verify_blog_creation() and restart_count < 3:
                    logger.warning("Blog creation verification failed. Restarting both processes...")
                    
                    # Kill both processes
                    worker_process.terminate()
                    beat_process.terminate()
                    time.sleep(5)
                    
                    # Restart both
                    worker_process = start_celery_worker()
                    time.sleep(5)
                    beat_process = start_celery_beat()
                    restart_count += 1
                
                next_verification = current_time + timedelta(minutes=15)
            
            # Sleep for a short time to prevent high CPU usage
            time.sleep(10)
            
    except KeyboardInterrupt:
        logger.info("Stopping blog automation...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Terminate processes
        if 'worker_process' in locals():
            logger.info("Stopping Celery worker...")
            worker_process.terminate()
            
        if 'beat_process' in locals():
            logger.info("Stopping Celery beat...")
            beat_process.terminate()
            
        logger.info("Blog automation stopped.")

if __name__ == "__main__":
    run_blog_automation() 