import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings')

app = Celery('blogify')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Configure the Celery Beat schedule
# Configure the Celery Beat schedule
app.conf.beat_schedule = {
    # Fetch trending topics at the start of each hour
    'fetch-trending-topics': {
        'task': 'blog.tasks.fetch_trending_topics',
        'schedule': crontab(minute=0, hour='*'),  # Run at XX:00
    },
    
    # Process trending topics 10 minutes after fetching
    'process-new-trending-topics': {
        'task': 'blog.tasks.process_trending_topics',
        'schedule': crontab(minute=10, hour='*'),  # Run at XX:10
    },
    
    # Run the main blog automation pipeline 20 minutes after the hour
    'automated-blog-pipeline': {
        'task': 'blog.automation.run_blog_automation_pipeline',
        'schedule': crontab(minute=20, hour='*'),  # Run at XX:20
    },
    
    # Check for scheduled blogs to publish every hour at 30 minutes past
    'publish-scheduled-blogs': {
        'task': 'blog.tasks.publish_scheduled_blogs',
        'schedule': crontab(minute=30, hour='*'),  # Run at XX:30
    },
    
    # Update blog analytics every hour at 40 minutes past
    'update-blog-analytics': {
        'task': 'blog.tasks.update_blog_analytics',
        'schedule': crontab(minute=40, hour='*'),  # Run at XX:40
    },
    
    # Weekly database backup
    'backup-database': {
        'task': 'blog.tasks.backup_database',
        'schedule': crontab(hour=2, minute=0, day_of_week=1),  # Run at 2:00 AM every Monday
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 