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

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Import after environment setup
from blog.blog_ai import GeminiChatbot

def test_template_context():
    """Test that template context is properly loaded and used by Gemini."""
    
    # Check if template_context.json exists
    template_file = Path("cache/template_context.json")
    if not template_file.exists():
        logger.error(f"Template context file not found: {template_file}")
        return False
    
    # Read the template information
    with open(template_file, 'r') as f:
        template_info = json.load(f)
        logger.info(f"Loaded {len(template_info.get('templates', []))} templates from context file")
    
    # Initialize the chatbot
    chatbot = GeminiChatbot(
        model_name="gemini-1.5-pro",
        temperature=0.7,
        system_prompt="You are a helpful AI assistant for a blog platform."
    )
    
    # Create a conversation with template context
    conversation_id = f"test_template_context_{int(os.urandom(2).hex(), 16)}"
    
    # Add a specific test prompt for template selection
    test_prompt = """I need to select a template for a blog post comparing iPhone vs Samsung Galaxy phones.

Refer to the TEMPLATE INFORMATION provided to you as context. Based on that information ONLY, which specific template (reference it by ID and name) would be most appropriate for this comparison topic?

Your response should:
1. Clearly state which template you recommend (include both the template ID and name)
2. Explain why this template is the best match for a phone comparison article
3. Include at least 2-3 specific features of the recommended template that make it suitable"""
    
    # Include template information in the context
    logger.info("Sending test prompt with template context...")
    response = chatbot.chat(test_prompt, conversation_id, include_template_info=True)
    
    logger.info(f"Response received in {response.get('processing_time', 0):.2f} seconds")
    logger.info("Response content:")
    print(response.get('response', 'No response'))
    
    # Check if the response mentions template information
    response_text = response.get('response', '')
    
    # Various ways the model might reference Template 3
    template3_references = [
        "template3", 
        "template 3",
        "template id 3",
        "template id: 3",
        "comparison blog structure",
        "comparison blog template", 
        "affiliate / review focused",
        "affiliate/review focused",
        "comparison structure"
    ]
    
    template_mentioned = any(ref.lower() in response_text.lower() for ref in template3_references)
    
    # Clean up the test conversation
    chatbot.clear_conversation(conversation_id)
    
    if template_mentioned:
        logger.info("✅ Test PASSED: Response correctly identifies Template 3 (Comparison Blog) for comparison")
        return True
    else:
        logger.error("❌ Test FAILED: Response does not properly reference Template 3")
        return False

if __name__ == "__main__":
    if test_template_context():
        print("\n✅ Template context test completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Template context test failed")
        sys.exit(1) 