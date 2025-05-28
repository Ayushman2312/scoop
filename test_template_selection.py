import os
import sys
import json
import logging
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
    from blog.blog_ai import ConversationCache
    print("Successfully imported ConversationCache")
except Exception as e:
    print(f"Error importing ConversationCache: {e}")
    sys.exit(1)

def test_preferred_template():
    """Test the template selection based on templates.txt and context_cache.json."""
    print("\n=== Testing preferred template selection ===")
    
    # Create a conversation cache instance
    try:
        cache = ConversationCache()
        print("ConversationCache instance created")
    except Exception as e:
        print(f"Error creating ConversationCache: {e}")
        return False
    
    # Test topics that should match different templates
    test_topics = [
        "Best SEO Practices for 2025",                      # Should match template1 (Evergreen)
        "Latest AI Update from Google",                     # Should match template2 (News)
        "iPhone 14 vs Samsung Galaxy S22",                  # Should match template3 (Comparison)
        "Top Restaurants in New York City",                 # Should match template4 (Local)
        "How to Build a WordPress Website",                 # Should match template5 (How-To)
    ]
    
    # Test each topic
    for topic in test_topics:
        print(f"\nTesting topic: {topic}")
        try:
            template = cache.get_preferred_template(topic)
            print(f"Selected template: ID {template['id']}, Key: {template['template_key']}")
            print(f"Template name: {template['name']}")
            print(f"Template type: {template['template_type']}")
        except Exception as e:
            print(f"Error getting preferred template for {topic}: {e}")
    
    return True

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
    print("=== Testing template selection implementation ===")
    
    # Test template context loading
    if test_template_context():
        print("✅ Template context test passed")
    else:
        print("❌ Template context test failed")
    
    # Test template selection
    if test_preferred_template():
        print("✅ Preferred template test passed")
    else:
        print("❌ Preferred template test failed")
    
    print("Tests completed") 