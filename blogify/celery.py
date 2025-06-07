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
app.conf.beat_schedule = {
    # Run the complete blog creation cycle every 5 minutes
    'fetch-trending-topics': {
        'task': 'blog.tasks.fetch_trending_topics',
        'schedule': 300,  # Run every 5 minutes (300 seconds)
    },
    
    # Process trending topics 30 seconds after fetching
    'process-new-trending-topics': {
        'task': 'blog.tasks.process_trending_topics',
        'schedule': 300,  # Run every 5 minutes
        'kwargs': {'limit': 1},  # Process just one topic per run
        'relative': 30,  # 30 seconds after fetch
    },
    
    # Ensure fallback topics are available
    'ensure-trending-topics': {
        'task': 'blog.tasks.ensure_trending_topics_available',
        'schedule': 300,  # Run every 5 minutes
        'relative': 60,  # 60 seconds after fetch
    },
    
    # Run the main blog automation pipeline
    'blog-automation': {
        'task': 'blog.automation.run_blog_automation_pipeline',
        'schedule': 300,  # Run every 5 minutes
        'relative': 90,  # 90 seconds after fetch
    },
    
    # Publish any scheduled blog posts
    'publish-scheduled': {
        'task': 'blog.tasks.publish_scheduled_blogs',
        'schedule': 300,  # Run every 5 minutes
    },
    
    # Update blog analytics less frequently (every 15 minutes)
    'update-analytics': {
        'task': 'blog.tasks.update_blog_analytics',
        'schedule': 900,  # Run every 15 minutes (900 seconds)
    },
    
    # Backup the database daily
    'backup-database': {
        'task': 'blog.tasks.backup_database',
        'schedule': crontab(minute=0, hour=0),  # Still run at midnight
    },
    
    # Update topic freshness metrics every hour
    'update-freshness-metrics': {
        'task': 'blog.tasks.update_freshness_metrics',
        'schedule': 3600,  # Run every hour (3600 seconds)
        'options': {'expires': 3600},  # Expires after 1 hour
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 