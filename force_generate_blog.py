#!/usr/bin/env python
"""
Force Blog Generation Script
===========================
This script bypasses the normal Celery scheduling and directly
generates a blog post to verify the content generation pipeline.

Usage:
    python force_generate_blog.py
    python force_generate_blog.py --topic "Your topic here"
    python force_generate_blog.py --template "evergreen|trend|comparison|local|how_to"
    python force_generate_blog.py --topic "Your topic here" --template "evergreen"

Available Templates:
    - evergreen: Comprehensive pillar content for broad topics
    - trend: Timely content on trending/newsworthy topics
    - comparison: Reviews and product/service comparisons
    - local: Location-specific content targeting local audiences
    - how_to: Step-by-step tutorials and guides
"""

import os
import sys
import logging
import django
import time
import argparse
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('force_blog_generation.log')
    ]
)
logger = logging.getLogger(__name__)

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings')
django.setup()

# Import Django models and tasks after setup
from blog.models import TrendingTopic, BlogPost
from blog.tasks import fetch_trending_topics, generate_blog_for_topic, predict_template_type
from blog.automation import select_topic_with_gemini, generate_blog_content_with_gemini, create_blog_post
from blog.logger import BlogProcessLogger

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Force generate a blog post with optional topic and template')
    parser.add_argument('--topic', type=str, help='Specify a custom topic instead of using trending topics')
    parser.add_argument('--template', type=str, choices=['evergreen', 'trend', 'comparison', 'local', 'how_to'], 
                        help='Specify a template type (evergreen, trend, comparison, local, how_to)')
    return parser.parse_args()

def force_generate_blog(custom_topic=None, template_type=None):
    """Force the generation of a blog post to test the pipeline"""
    process_logger = BlogProcessLogger()
    process_logger.info("Starting forced blog generation test")
    
    try:
        if custom_topic:
            # Use the provided custom topic
            process_logger.info(f"Using custom topic: {custom_topic}")
            # Create a test topic with the custom keyword
            test_topic = TrendingTopic.objects.create(
                keyword=custom_topic,
                rank=1,
                location="global"
            )
            selected_topic = test_topic
            
            # If template type not specified, predict it based on topic
            if not template_type:
                template_type = predict_template_type(custom_topic)
                process_logger.info(f"Predicted template type: {template_type}")
            else:
                process_logger.info(f"Using specified template type: {template_type}")
        else:
            # Step 1: Fetch trending topics directly
            process_logger.info("Fetching trending topics directly")
            result = fetch_trending_topics()
            process_logger.info(f"Fetch result: {result}")
            
            # Step 2: Get most recent unprocessed topic
            topics = TrendingTopic.objects.filter(
                processed=False,
                filtered_out=False
            ).order_by('-timestamp')[:5]
            
            if not topics.exists():
                # Create a test topic
                process_logger.info("No unprocessed topics found. Creating a test topic.")
                test_topic = TrendingTopic.objects.create(
                    keyword="Test Blog Generation Topic",
                    rank=1,
                    location="global"
                )
                topics = [test_topic]
            
            # Step 3: Select topic and template
            process_logger.info(f"Found {len(topics)} topics to choose from")
            if template_type:
                # Use specified template with top topic
                selected_topic = topics[0]
                process_logger.info(f"Using specified template: {template_type} with topic: {selected_topic.keyword}")
            else:
                # Let Gemini select topic and template
                selected_topic, template_type = select_topic_with_gemini(topics, process_logger)
                
                if not selected_topic:
                    # Fallback to first topic and default template
                    selected_topic = topics[0]
                    template_type = "how_to"
        
        process_logger.info(f"Selected topic: {selected_topic.keyword} with template: {template_type}")
        
        # Step 4: Generate content
        process_logger.info("Generating blog content")
        content_data = generate_blog_content_with_gemini(selected_topic.keyword, template_type, process_logger)
        
        if not content_data:
            process_logger.error("Failed to generate content")
            return "Failed to generate content"
        
        # Step 5: Create and publish blog post
        process_logger.info("Creating and publishing blog post")
        blog_post = create_blog_post(selected_topic, template_type, content_data, process_logger, publish_now=True)
        
        if not blog_post:
            process_logger.error("Failed to create blog post")
            return "Failed to create blog post"
        
        process_logger.info(f"Successfully created blog post: {blog_post.title} (ID: {blog_post.id})")
        process_logger.success("Blog generation test completed successfully")
        
        # Display the blog post URL
        blog_url = f"/blog/{blog_post.slug}"
        process_logger.info(f"Blog URL: {blog_url}")
        
        return f"Successfully created blog post: {blog_post.title} (Template: {template_type})"
    
    except Exception as e:
        process_logger.error(f"Error in force_generate_blog: {str(e)}")
        return f"Error: {str(e)}"

if __name__ == "__main__":
    print("=" * 60)
    print("FORCING BLOG GENERATION (BYPASSING CELERY)")
    print("=" * 60)
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Display information about the run
    if args.topic:
        print(f"Topic: {args.topic}")
    else:
        print("Topic: [Will use trending topic]")
        
    if args.template:
        print(f"Template: {args.template}")
    else:
        print("Template: [Will be predicted based on topic]")
    
    print("-" * 60)
    
    start_time = time.time()
    result = force_generate_blog(custom_topic=args.topic, template_type=args.template)
    end_time = time.time()
    
    print("\nRESULT:")
    print(result)
    print(f"\nExecution time: {end_time - start_time:.2f} seconds")
    print("\nCheck force_blog_generation.log for detailed logs") 