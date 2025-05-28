#!/usr/bin/env python
import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings')
django.setup()

# Import tasks after Django setup
from blog.tasks import (
    fetch_trending_topics,
    process_trending_topics,
    select_best_trending_topic,
    publish_scheduled_blogs
)

# Import automation pipeline
from blog.automation import run_blog_automation_pipeline

def run_all_tasks():
    """Run all blog automation tasks in sequence"""
    print("=== Starting Blog Automation Pipeline ===")
    
    print("\n1. Fetching trending topics...")
    fetch_result = fetch_trending_topics()
    print(f"Result: {fetch_result}")
    
    print("\n2. Processing trending topics...")
    process_result = process_trending_topics()
    print(f"Result: {process_result}")
    
    print("\n3. Selecting best trending topic and generating content...")
    select_result = select_best_trending_topic()
    print(f"Result: {select_result}")
    
    print("\n4. Publishing any scheduled blogs...")
    publish_result = publish_scheduled_blogs()
    print(f"Result: {publish_result}")
    
    print("\n5. Running full automation pipeline...")
    pipeline_result = run_blog_automation_pipeline()
    print(f"Result: {pipeline_result}")
    
    print("\n=== Blog Automation Pipeline Completed ===")
    
if __name__ == "__main__":
    run_all_tasks() 