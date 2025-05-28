import os
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
import re

import requests
import google.generativeai as genai
from django.conf import settings
from django.utils import timezone
from celery import shared_task

from .models import TrendingTopic, BlogPost
from .blog_ai import GeminiChatbot
from .tasks import fetch_trending_topics, format_json_to_html
from .logger import BlogProcessLogger

# Configure logging
logger = logging.getLogger(__name__)

# Configure Google Generative AI
if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY not configured in settings")

@shared_task
def run_blog_automation_pipeline():
    """
    Main function that runs the entire blog automation pipeline:
    1. Fetch trending topics
    2. Ask Gemini to select the best topic
    3. Generate content for that topic
    4. Publish the blog post
    
    This task is scheduled to run every hour
    """
    # Create a process logger for this automation run
    process_logger = BlogProcessLogger()
    process_logger.info("Starting blog automation pipeline")
    
    try:
        # Step 1: Fetch trending topics if we don't have recent ones
        step1 = process_logger.step("FETCH_TRENDING_TOPICS", "Checking for recent trending topics")
        
        recent_topics = TrendingTopic.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=4),
            processed=False,
            filtered_out=False
        ).order_by('-timestamp')
        
        if not recent_topics.exists():
            process_logger.info("No recent trending topics found, fetching new ones")
            fetch_task = fetch_trending_topics.delay()
            process_logger.info("Fetching task started", {"task_id": fetch_task.id})
            
            # Give some time for the task to complete
            time.sleep(5)  
            
            # Refresh our list
            recent_topics = TrendingTopic.objects.filter(
                timestamp__gte=timezone.now() - timedelta(hours=4),
                processed=False,
                filtered_out=False
            ).order_by('-timestamp')
            
            process_logger.info("Topics refresh complete", {"topics_count": recent_topics.count()})
        
        if not recent_topics.exists():
            error_msg = "Still no trending topics available after fetching"
            process_logger.fail_step(step1, "FETCH_TRENDING_TOPICS", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return f"Error: {error_msg}"
        
        process_logger.complete_step(step1, "FETCH_TRENDING_TOPICS", {
            "topics_count": recent_topics.count(),
            "topics": [{"id": t.id, "keyword": t.keyword} for t in recent_topics[:5]]
        })
            
        # Step 2: Ask Gemini to select the best topic
        step2 = process_logger.step("SELECT_TOPIC", "Selecting best topic using Gemini AI")
        
        selected_topic, template_type = select_topic_with_gemini(recent_topics[:10], process_logger)
        
        if not selected_topic:
            error_msg = "Gemini couldn't select a topic"
            process_logger.fail_step(step2, "SELECT_TOPIC", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return f"Error: {error_msg}"
            
        process_logger.complete_step(step2, "SELECT_TOPIC", {
            "selected_topic": selected_topic.keyword,
            "template_type": template_type
        })
        
        # Step 3: Generate content for the selected topic
        step3 = process_logger.step("GENERATE_CONTENT", "Generating blog content with Gemini AI")
        
        blog_content = generate_blog_content_with_gemini(selected_topic.keyword, template_type, process_logger)
        
        if not blog_content:
            error_msg = "Failed to generate blog content"
            process_logger.fail_step(step3, "GENERATE_CONTENT", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return f"Error: {error_msg}"
        
        process_logger.complete_step(step3, "GENERATE_CONTENT", {
            "content_length": len(json.dumps(blog_content)),
            "sections_count": len(blog_content.get("table_of_contents", []))
        })
        
        # Step 4: Create and publish the blog post
        step4 = process_logger.step("CREATE_BLOG_POST", "Creating and publishing blog post")
        
        blog_post = create_blog_post(selected_topic, template_type, blog_content, process_logger)
        
        if not blog_post:
            error_msg = "Failed to create blog post"
            process_logger.fail_step(step4, "CREATE_BLOG_POST", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return f"Error: {error_msg}"
        
        process_logger.complete_step(step4, "CREATE_BLOG_POST", {
            "blog_id": str(blog_post.id),
            "blog_title": blog_post.title,
            "blog_status": blog_post.status,
            "blog_url": blog_post.slug
        })
            
        process_logger.success(f"Successfully created and published blog post: {blog_post.title}")
        process_logger.end_process("COMPLETED", {
            "blog_id": str(blog_post.id),
            "blog_title": blog_post.title,
            "topic": selected_topic.keyword,
            "template_type": template_type
        })
        
        return f"Success: Created blog post with ID: {blog_post.id}"
        
    except Exception as e:
        process_logger.error(f"Error in blog automation pipeline: {str(e)}")
        process_logger.end_process("FAILED", {"error": str(e)})
        return f"Error: {str(e)}"

def select_topic_with_gemini(trending_topics, process_logger):
    """
    Uses Gemini AI to select the best topic for a blog post
    
    Args:
        trending_topics: QuerySet of TrendingTopic objects
        
    Returns:
        tuple: (selected_topic, template_type)
    """
    if not trending_topics:
        return None, None
    
    # Create a prompt for Gemini
    topics_list = "\n".join([f"{i+1}. {topic.keyword}" for i, topic in enumerate(trending_topics)])
    
    # Create a conversation ID for this template selection session
    conversation_id = f"template_selection_{int(time.time())}"
    
    prompt = f"""As a professional blog editor, your task is to select the best trending topic from the list below for our next blog post.

Here are the current trending topics:
{topics_list}

Analyze these topics and select the ONE that would make the most engaging, valuable, and relevant blog post.
Consider factors like:
- Search intent (informational, commercial, etc.)
- Potential audience size
- Relevance to current events
- Staying power (not just a flash trend)
- Our ability to provide unique insights

You must return your response in valid JSON format only:
```json
{{
  "selected_topic_number": 5,
  "reason": "This topic has high search volume and evergreen appeal..."
}}
```"""
    try:
        # Initialize the Gemini chatbot with appropriate temperature
        chatbot = GeminiChatbot(
            model_name="gemini-1.5-pro",
            temperature=0.7,
            system_prompt="You are a helpful AI assistant for a blog platform that specializes in selecting trending topics for blog posts."
        )
        
        # Get response from Gemini
        process_logger.info("Asking Gemini to select best trending topic")
        response = chatbot.chat(prompt, conversation_id)
        response_text = response.get('response', '')
        process_logger.info(f"Received response from Gemini: {response_text[:100]}...")
        
        # Extract JSON from response
        try:
            # Clean up the response to extract valid JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON without the markdown code blocks
                json_match = re.search(r'({.*})', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = response_text
            
            selected_data = json.loads(json_str)
            selected_topic_number = selected_data.get('selected_topic_number')
            
            if not selected_topic_number or selected_topic_number < 1 or selected_topic_number > len(trending_topics):
                process_logger.warning(f"Invalid topic number: {selected_topic_number}")
                selected_topic = trending_topics[0]  # Default to first topic
            else:
                selected_topic = trending_topics[selected_topic_number - 1]
                
            process_logger.info(f"Selected topic: {selected_topic.keyword}")
            
            # Now ask Gemini to select the best template for this topic
            template_prompt = f"""Now that you've selected the topic "{selected_topic.keyword}", choose the most appropriate blog template from our template library.

You MUST refer to the TEMPLATE INFORMATION provided to you as context to determine which specific template is most appropriate for this topic: "{selected_topic.keyword}".

Return your response in valid JSON format only:
```json
{{
  "template_id": 2,
  "template_key": "template2", 
  "template_name": "Trend-Based SEO Blog Structure",
  "reason": "This template works best for this topic because..."
}}
```"""
            
            # Include template context in this conversation
            chatbot.cache.add_template_context_to_conversation(conversation_id)
            
            # Get template selection from Gemini
            process_logger.info("Asking Gemini to select best template")
            template_response = chatbot.chat(template_prompt, conversation_id)
            template_text = template_response.get('response', '')
            process_logger.info(f"Received template response from Gemini: {template_text[:100]}...")
            
            # Extract JSON from template response
            try:
                # Clean up the response to extract valid JSON
                json_match = re.search(r'```json\s*(.*?)\s*```', template_text, re.DOTALL)
                if json_match:
                    template_json_str = json_match.group(1)
                else:
                    # Try to find JSON without the markdown code blocks
                    json_match = re.search(r'({.*})', template_text, re.DOTALL)
                    if json_match:
                        template_json_str = json_match.group(1)
                    else:
                        template_json_str = template_text
                
                template_data = json.loads(template_json_str)
                template_key = template_data.get('template_key')
                
                # Map template_key to template_type
                template_type_mapping = {
                    'template1': 'evergreen',
                    'template2': 'trend',
                    'template3': 'comparison',
                    'template4': 'local',
                    'template5': 'how_to'
                }
                
                template_type = template_type_mapping.get(template_key, 'how_to')
                process_logger.info(f"Selected template: {template_key} ({template_type})")
                
            except (json.JSONDecodeError, KeyError) as e:
                process_logger.warning(f"Error parsing template JSON: {e}. Using default template.")
                template_type = 'how_to'
            
            # Clean up
            chatbot.clear_conversation(conversation_id)
            
            return selected_topic, template_type
            
        except (json.JSONDecodeError, KeyError) as e:
            process_logger.warning(f"Error parsing JSON: {e}")
            if trending_topics:
                return trending_topics[0], 'how_to'  # Default to first topic and how-to template
            return None, None
    except Exception as e:
        process_logger.error(f"Error in select_topic_with_gemini: {e}")
        if trending_topics:
            return trending_topics[0], 'how_to'  # Default to first topic and how-to template
        return None, None

def generate_blog_content_with_gemini(keyword, template_type, process_logger):
    """
    Generates blog content for a specific keyword using Gemini AI
    
    Args:
        keyword: The topic keyword
        template_type: The template type to use
        process_logger: The process logger instance
        
    Returns:
        dict: The generated content in JSON format
    """
    try:
        process_logger.info(f"Generating content for topic: {keyword} using template: {template_type}")
        
        # Initialize the Gemini chatbot
        chatbot = GeminiChatbot(
            model_name="gemini-1.5-pro",
            temperature=0.7,
            max_output_tokens=8192,  # Using higher token limit for longer content
            system_prompt="You are an expert content writer that specializes in creating SEO-optimized, engaging blog content in JSON format."
        )
        
        # Create a unique conversation ID
        conversation_id = f"content_generation_{int(time.time())}"
        
        # Add template context to the conversation
        chatbot.cache.add_template_context_to_conversation(conversation_id)
        
        # Create a detailed prompt for content generation
        prompt = f"""
Create a comprehensive, SEO-optimized blog post about "{keyword}".

Based on the TEMPLATE INFORMATION provided in the context, you should use the template that best matches the type: "{template_type}".

You MUST return your content in a valid JSON format matching the following structure:

```json
{{
  "title": "Engaging, SEO-optimized title with the keyword",
  "meta_description": "Compelling meta description under 160 characters that includes the keyword",
  "introduction": "Engaging introduction paragraph that hooks the reader and introduces the topic",
  "table_of_contents": ["First H2 heading", "Second H2 heading", "Third H2 heading", "..."],
  "sections": [
    {{
      "h2": "First main heading (H2)",
      "content": "Detailed, informative paragraph(s) for this section",
      "subsections": [
        {{
          "h3": "Sub-heading (H3)",
          "content": "Content for this subsection",
          "list_items": ["First bullet point", "Second bullet point", "..."]
        }}
      ]
    }},
    // Additional sections with H2 headings
  ],
  "conclusion": "Summary paragraph that reinforces the main points and includes a call to action",
  "faq": [
    {{
      "question": "Common question about {keyword}?",
      "answer": "Detailed, helpful answer to the question"
    }},
    // Additional FAQ items
  ]
}}
```

IMPORTANT GUIDELINES:
1. Create engaging, valuable content that genuinely helps the reader
2. Include the main keyword naturally throughout the content, especially in headings
3. Structure the content with proper H2 and H3 headings
4. Make all JSON fields valid - use escaped quotes and avoid trailing commas
5. Write at least 3-5 sections with H2 headings
6. Include 3-5 FAQs related to the topic
7. Ensure the total content is comprehensive (1500+ words)
8. Write in a conversational but authoritative tone
9. Include practical examples, statistics, or case studies where relevant
"""
        
        # Get content from Gemini
        process_logger.info("Requesting content generation from Gemini")
        response = chatbot.chat(prompt, conversation_id)
        response_text = response.get('response', '')
        
        process_logger.info(f"Received {len(response_text)} characters of content from Gemini")
        
        # Extract JSON from response
        try:
            # Clean up the response to extract valid JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON without the markdown code blocks
                json_match = re.search(r'({.*})', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = response_text
            
            # Parse the JSON
            content_data = json.loads(json_str)
            
            # Validate required fields
            required_fields = ['title', 'meta_description', 'sections']
            missing_fields = [field for field in required_fields if field not in content_data]
            
            if missing_fields:
                process_logger.warning(f"Generated content missing required fields: {', '.join(missing_fields)}")
                
                # Make a second attempt to generate content with specific instructions about missing fields
                if missing_fields:
                    retry_prompt = f"""Your previous response was missing these required fields: {', '.join(missing_fields)}.

Please regenerate the COMPLETE blog post content about "{keyword}" in valid JSON format, ensuring you include ALL of these fields:
- title
- meta_description
- introduction
- table_of_contents
- sections (with h2, content, and subsections)
- conclusion
- faq

Return the FULL JSON content again."""
                    
                    process_logger.info("Making second attempt to generate content with missing fields")
                    retry_response = chatbot.chat(retry_prompt, conversation_id)
                    retry_text = retry_response.get('response', '')
                    
                    # Try to extract JSON again
                    json_match = re.search(r'```json\s*(.*?)\s*```', retry_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        json_match = re.search(r'({.*})', retry_text, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1)
                        else:
                            json_str = retry_text
                    
                    # Try to parse the JSON again
                    try:
                        content_data = json.loads(json_str)
                        process_logger.info("Successfully retrieved content on second attempt")
                    except json.JSONDecodeError:
                        process_logger.error("Failed to parse JSON on second attempt")
            
            # Clean up
            chatbot.clear_conversation(conversation_id)
            
            # Log content stats
            sections_count = len(content_data.get('sections', []))
            faqs_count = len(content_data.get('faq', []))
            
            process_logger.info(f"Generated content with {sections_count} sections and {faqs_count} FAQs")
            
            return content_data
            
        except json.JSONDecodeError as e:
            process_logger.error(f"Error parsing JSON content: {e}")
            process_logger.error(f"Raw content: {response_text[:500]}...")
            return None
        
    except Exception as e:
        process_logger.error(f"Error generating content with Gemini: {e}")
        return None

def create_blog_post(topic, template_type, content_data, process_logger):
    """
    Creates and publishes a blog post based on the generated content
    
    Args:
        topic: The TrendingTopic instance
        template_type: The type of template to use
        content_data: The generated content data in JSON format
        process_logger: The process logger instance
        
    Returns:
        BlogPost: The created blog post
    """
    try:
        process_logger.info(f"Creating blog post for topic: {topic.keyword}")
        
        # Extract title and meta description from content data
        title = content_data.get('title', f"Blog about {topic.keyword}")
        meta_description = content_data.get('meta_description', f"Learn about {topic.keyword} in this comprehensive blog post.")
        
        # Format the JSON content to HTML
        process_logger.info("Converting JSON content to HTML")
        html_content = format_json_to_html(content_data, template_type)
        
        # Generate a slug from the title
        slug = title.lower()
        # Replace spaces with dashes and remove special characters
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s-]+', '-', slug)
        
        # Create the blog post
        process_logger.info("Creating blog post entry in database")
        blog_post = BlogPost.objects.create(
            title=title,
            content=html_content,
            meta_description=meta_description,
            template_type=template_type,
            trending_topic=topic,
            status='published',  # Publish immediately
            published_at=timezone.now(),
            slug=slug
        )
        
        # Log the creation with detailed information
        process_logger.info(f"Successfully created blog post: {title}", {
            "blog_id": str(blog_post.id),
            "title": title,
            "template_type": template_type,
            "content_length": len(html_content),
            "slug": slug
        })
        
        # Log details about the content to help with debugging
        sections_count = len(content_data.get('sections', []))
        faq_count = len(content_data.get('faq', []))
        process_logger.info(f"Content statistics: {sections_count} sections, {faq_count} FAQs")
        
        # Mark the trending topic as processed and used
        topic.processed = True
        topic.save()
        
        return blog_post
        
    except Exception as e:
        process_logger.error(f"Error creating blog post: {e}")
        return None 