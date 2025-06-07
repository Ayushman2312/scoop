#!/usr/bin/env python
"""
Test script to verify template selection for different keywords
"""
import os
import django
import sys
import json
import logging
import re
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

print("Script started")

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
print(f"Working directory: {os.getcwd()}")
print(f"Python path: {sys.path}")

# Load environment variables
load_dotenv()
print("Environment variables loaded")

# Import after environment setup
try:
    from blog.blog_ai import GeminiChatbot, ConversationCache
    print("Successfully imported GeminiChatbot and ConversationCache")
except Exception as e:
    print(f"Error importing GeminiChatbot and ConversationCache: {e}")
    sys.exit(1)

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings')
django.setup()

from blog.tasks import predict_template_type
from blog.logger import BlogProcessLogger

def test_template_selection():
    """
    Test template selection for different types of keywords
    """
    logger = BlogProcessLogger()
    logger.info("Testing template selection for different keywords")
    
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
    
    logger.info(f"Tested {len(test_keywords)} keywords with the following results: {template_counts}")
    
    return results

def test_template_context():
    """Test that template context is properly loaded and contains both structured and raw data."""
    print("\n=== Testing template context loading ===")
    
    # Create a conversation cache instance
    try:
        cache = ConversationCache()
        print("ConversationCache instance created")
    except Exception as e:
        print(f"Error creating ConversationCache: {e}")
        return False
    
    # Check if template info is loaded
    if not cache.template_info:
        print("ERROR: Template information not loaded")
        return False
    
    # Check if we have structured templates
    templates = cache.template_info.get("templates", [])
    print(f"Loaded {len(templates)} structured templates from context_cache.json")
    
    # Check if we have raw templates content
    raw_templates = cache.template_info.get("raw_templates", "")
    if raw_templates:
        print(f"Loaded raw templates content from templates.txt ({len(raw_templates)} bytes)")
        # Print the first 100 characters to verify
        print(f"First 100 chars: {raw_templates[:100]}...")
    else:
        print("ERROR: Raw templates content not loaded")
        # Print the blog templates.txt path and check if it exists
        templates_txt_path = Path("blog/templates.txt")
        print(f"Templates.txt path: {templates_txt_path.absolute()}")
        print(f"Templates.txt exists: {templates_txt_path.exists()}")
        return False
    
    return True

if __name__ == "__main__":
    print("\n=== Starting Template Selection Tests ===")
    
    # First test template context loading
    context_test_passed = test_template_context()
    
    if context_test_passed:
        # Then test template selection
        selection_test_passed = test_template_selection()
        
        if selection_test_passed:
            print("\n✅ All tests passed!")
            sys.exit(0)
        else:
            print("\n❌ Template selection test failed")
            sys.exit(1)
    else:
        print("\n❌ Template context test failed")
        sys.exit(1) 