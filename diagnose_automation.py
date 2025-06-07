#!/usr/bin/env python
"""
Diagnose Blog Automation Script
==============================
This script diagnoses issues with the blog automation system, with a
focus on checking the template selection system.

Usage:
    python diagnose_automation.py
"""

import os
import sys
import logging
import django
import time
from datetime import datetime, timedelta
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('diagnose_automation.log')
    ]
)
logger = logging.getLogger(__name__)

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings')
django.setup()

# Import Django models and tasks after setup
from blog.models import TrendingTopic, BlogPost
from blog.tasks import predict_template_type
from blog.logger import BlogProcessLogger
from django.utils import timezone

def test_template_selection():
    """
    Test template selection for different types of keywords
    """
    test_keywords = [
        # Evergreen content tests
        "What is content marketing",
        "Complete guide to SEO",
        "Understanding artificial intelligence",
        "Ultimate guide to email marketing",
        
        # Trending content tests
        "Breaking news about Apple's latest iPhone",
        "New updates to Windows 11",
        "Latest developments in the Ukraine conflict",
        "Recent changes to Google's algorithm",
        
        # Comparison content tests
        "iPhone vs Samsung Galaxy comparison",
        "Best email marketing platforms",
        "Top 10 CRM solutions compared",
        "WordPress vs Wix: Which is better?",
        
        # Local content tests
        "Best restaurants near me",
        "Things to do in New York City",
        "Chicago real estate market trends",
        "Local SEO strategies for small businesses",
        
        # How-to content tests
        "How to build a website",
        "Step by step guide to content creation",
        "Tutorial for setting up WordPress",
        "Guide to Instagram marketing"
    ]
    
    results = {}
    
    print("\nTEMPLATE SELECTION TEST RESULTS")
    print("===============================")
    
    for keyword in test_keywords:
        template_type = predict_template_type(keyword)
        results[keyword] = template_type
        print(f"Keyword: '{keyword}'")
        print(f"Template selected: '{template_type}'")
        print("---")
    
    # Count template types
    template_counts = {}
    for template in results.values():
        if template in template_counts:
            template_counts[template] += 1
        else:
            template_counts[template] = 1
    
    print("\nSUMMARY")
    print("=======")
    for template, count in template_counts.items():
        print(f"{template}: {count} keywords")
    
    return results

def check_recent_blogs():
    """
    Check recent blogs for template distribution
    """
    # Get blogs from the past 7 days
    recent_blogs = BlogPost.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    ).order_by('-created_at')
    
    print("\nRECENT BLOG ANALYSIS")
    print("===================")
    print(f"Found {recent_blogs.count()} blogs created in the past 7 days")
    
    if recent_blogs.count() == 0:
        print("No recent blogs found.")
        return
    
    # Count template types
    template_counts = {}
    for blog in recent_blogs:
        template_type = blog.template_type
        if template_type in template_counts:
            template_counts[template_type] += 1
        else:
            template_counts[template_type] = 1
    
    print("\nTemplate Distribution:")
    for template, count in template_counts.items():
        percentage = (count / recent_blogs.count()) * 100
        print(f"- {template}: {count} blogs ({percentage:.1f}%)")
    
    # Check for possible invalid templates
    invalid_templates = [b for b in recent_blogs if b.template_type not in ['evergreen', 'trend', 'comparison', 'local', 'how_to']]
    if invalid_templates:
        print("\nWARNING: Found blogs with invalid template types:")
        for blog in invalid_templates[:5]:  # Show only first 5
            print(f"- Blog ID: {blog.id}, Title: '{blog.title}', Template: '{blog.template_type}'")
        
        if len(invalid_templates) > 5:
            print(f"  ... and {len(invalid_templates) - 5} more")
            
        print("\nThese blogs may need to be updated to use one of the 5 valid templates:")
        print("- evergreen: Comprehensive pillar content for broad topics")
        print("- trend: Timely content on trending/newsworthy topics")
        print("- comparison: Reviews and product/service comparisons")
        print("- local: Location-specific content targeting local audiences")
        print("- how_to: Step-by-step tutorials and guides")
    else:
        print("\n✅ All recent blogs use valid template types")

def check_api_keys():
    """Check if required API keys are configured"""
    from django.conf import settings
    
    print("\nAPI KEY CONFIGURATION")
    print("====================")
    
    # Check Gemini API key
    gemini_key = getattr(settings, 'GEMINI_API_KEY', None)
    if gemini_key:
        print("✅ GEMINI_API_KEY is configured")
    else:
        print("❌ GEMINI_API_KEY is missing")
    
    # Check SerpAPI key
    serp_key = getattr(settings, 'SERPAPI_API_KEY', None)
    if serp_key:
        print("✅ SERPAPI_API_KEY is configured")
    else:
        print("❌ SERPAPI_API_KEY is missing")

def main():
    """Main function to run the diagnostic tools"""
    print("=" * 60)
    print("BLOG AUTOMATION DIAGNOSTIC TOOL")
    print("=" * 60)
    print(f"Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    # Check API key configuration
    check_api_keys()
    
    # Test template selection
    test_template_selection()
    
    # Check recent blogs
    check_recent_blogs()
    
    print("\n" + "=" * 60)
    print("Diagnostic completed. Check diagnose_automation.log for details.")

if __name__ == "__main__":
    main() 