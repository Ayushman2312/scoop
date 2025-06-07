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
def run_blog_automation_pipeline(lookback_hours=1):
    """
    Main function that runs the entire blog automation pipeline:
    1. Fetch trending topics
    2. Ask Gemini to select the best topic
    3. Generate content for that topic
    4. Publish the blog post IMMEDIATELY
    
    This task is scheduled to run every 5 minutes to ensure frequent blog publishing
    
    Args:
        lookback_hours: How many hours back to look for trending topics (default: 1)
    """
    # Create a process logger for this automation run
    process_logger = BlogProcessLogger()
    process_logger.info(f"Starting blog automation pipeline - 5-minute blog creation cycle (lookback: {lookback_hours}h)")
    
    try:
        # Step 1: Fetch trending topics if we don't have recent ones
        step1 = process_logger.step("FETCH_TRENDING_TOPICS", "Checking for recent trending topics")
        
        # Look for topics from the last hour by default for 5-minute cycles
        recent_topics = TrendingTopic.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=lookback_hours),
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
                timestamp__gte=timezone.now() - timedelta(hours=lookback_hours),
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
        
        # Get trending topics from the last 30 minutes to check for duplication
        # For 5-minute cycles, we need a shorter window to detect duplicates
        recent_minutes = 30
        topics_last_period = TrendingTopic.objects.filter(
            timestamp__gte=timezone.now() - timedelta(minutes=recent_minutes),
            processed=True
        ).order_by('-timestamp')
        
        # Extract unique keywords from recent topics
        recent_keywords = list(set([t.keyword.lower() for t in topics_last_period]))
        
        # Check if we have the same trending topics for consecutive runs
        is_duplicate_trend = False
        topic_duplication_counts = {}
        
        for keyword in recent_keywords:
            # Count how many times this topic appeared in the recent period
            count = topics_last_period.filter(keyword__iexact=keyword).count()
            topic_duplication_counts[keyword] = count
            if count >= 2:  # Topic appeared in 2 or more consecutive runs
                is_duplicate_trend = True
                process_logger.info(f"Detected duplicate trending topic: {keyword} (appeared {count} times in last {recent_minutes} minutes)")
        
        process_logger.info(f"Duplication analysis: {is_duplicate_trend}", {"duplication_counts": topic_duplication_counts})
        
        # If we have duplication, check if a blog was already created for any of these topics
        fresh_content_strategy = None
        if is_duplicate_trend:
            # Look for blogs created in the last 1-2 hours for these keywords
            # For 5-minute runs, we're more aggressive with recency
            recent_blog_hours = 2
            
            # Find topics that already have blog posts in the last hours
            topics_with_recent_blogs = []
            for keyword in recent_keywords:
                recent_blogs = BlogPost.objects.filter(
                    trending_topic__keyword__iexact=keyword,
                    created_at__gte=timezone.now() - timedelta(hours=recent_blog_hours)
                )
                
                if recent_blogs.exists():
                    topics_with_recent_blogs.append({
                        "keyword": keyword,
                        "blog_count": recent_blogs.count(),
                        "blog_templates": list(recent_blogs.values_list('template_type', flat=True))
                    })
            
            if topics_with_recent_blogs:
                process_logger.info(f"Found {len(topics_with_recent_blogs)} topics with recent blogs in the last {recent_blog_hours} hours")
                
                # We'll set a strategy for content freshness
                fresh_content_strategy = "different_angle"
                process_logger.info(f"Setting fresh content strategy: {fresh_content_strategy}")
        
        # Limit to 5 topics to make selection faster for 5-minute cycles
        selected_topic, template_type = select_topic_with_gemini(
            recent_topics[:5], 
            process_logger,
            topics_with_recent_blogs=topics_with_recent_blogs if is_duplicate_trend else None,
            fresh_content_strategy=fresh_content_strategy
        )
        
        if not selected_topic:
            error_msg = "Gemini couldn't select a topic"
            process_logger.fail_step(step2, "SELECT_TOPIC", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return f"Error: {error_msg}"
            
        process_logger.complete_step(step2, "SELECT_TOPIC", {
            "selected_topic": selected_topic.keyword,
            "template_type": template_type,
            "fresh_content_strategy": fresh_content_strategy
        })
        
        # Mark this topic as processed to avoid reusing in future runs
        selected_topic.processed = True
        selected_topic.save()
        
        # Step 3: Generate content for the selected topic
        step3 = process_logger.step("GENERATE_CONTENT", "Generating blog content with Gemini AI")
        
        # Check if we need to generate fresh content with a different angle
        if fresh_content_strategy:
            # Get the previously used templates for this topic
            used_templates = []
            for topic_data in topics_with_recent_blogs:
                if topic_data["keyword"].lower() == selected_topic.keyword.lower():
                    used_templates = topic_data["blog_templates"]
                    break
                    
            process_logger.info(f"Content freshness strategy active: {fresh_content_strategy}", {
                "previous_templates": used_templates,
                "selected_template": template_type
            })
            
            # Generate blog with a different angle instruction
            blog_content = generate_blog_content_with_gemini(
                selected_topic.keyword, 
                template_type, 
                process_logger,
                fresh_content_strategy=fresh_content_strategy,
                used_templates=used_templates
            )
        else:
            # Standard blog generation
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
        
        # Step 4: Create and publish the blog post IMMEDIATELY
        step4 = process_logger.step("CREATE_BLOG_POST", "Creating and IMMEDIATELY publishing blog post")
        
        # Always force immediate publishing
        blog_post = create_blog_post(selected_topic, template_type, blog_content, process_logger, publish_now=True)
        
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
            "template_type": template_type,
            "fresh_strategy": fresh_content_strategy
        })
        
        return f"Success: Created and published blog post with ID: {blog_post.id}"
        
    except Exception as e:
        process_logger.error(f"Error in blog automation pipeline: {str(e)}")
        process_logger.end_process("FAILED", {"error": str(e)})
        return f"Error: {str(e)}"

def select_topic_with_gemini(trending_topics, process_logger, topics_with_recent_blogs=None, fresh_content_strategy=None):
    """
    Uses Gemini AI to select the best topic for a blog post
    
    Args:
        trending_topics: QuerySet of TrendingTopic objects
        process_logger: The process logger instance
        topics_with_recent_blogs: List of topics that already have recent blogs
        fresh_content_strategy: Strategy for fresh content if duplicates are detected
        
    Returns:
        tuple: (selected_topic, template_type)
    """
    if not trending_topics:
        return None, None
    
    # Create a prompt for Gemini
    topics_list = "\n".join([f"{i+1}. {topic.keyword}" for i, topic in enumerate(trending_topics)])
    
    # Create a conversation ID for this template selection session
    conversation_id = f"template_selection_{int(time.time())}"
    
    # Construct prompt based on whether we have duplicate topics
    if topics_with_recent_blogs and fresh_content_strategy:
        # Provide information about topics with recent blogs for Gemini to avoid
        recent_blogs_info = "\n".join([
            f"- {topic['keyword']} (already has {topic['blog_count']} recent blog(s) with templates: {', '.join(topic['blog_templates'])})"
            for topic in topics_with_recent_blogs
        ])
        
        prompt = f"""As a professional blog editor, your task is to select the best trending topic from the list below for our next blog post.

Here are the current trending topics:
{topics_list}

IMPORTANT: We have already published blogs on some of these topics recently:
{recent_blogs_info}

For topics that already have recent blogs, please follow these rules:
1. PREFER selecting a completely different topic that doesn't have a recent blog if possible
2. If you must select a topic with a recent blog, please choose a VERY DIFFERENT template type than what was used before

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
  "reason": "This topic has high search volume and evergreen appeal...",
  "content_approach": "Focusing on a different angle than previous posts by covering recent statistics and case studies"
}}
```"""
    else:
        # Standard prompt
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
            
            # Log content approach if provided (for fresh content strategy)
            if 'content_approach' in selected_data:
                process_logger.info(f"Content approach: {selected_data['content_approach']}")
            
            # Now ask Gemini to select the best template for this topic
            template_prompt = f"""Now that you've selected the topic "{selected_topic.keyword}", choose the most appropriate blog template from our template library.

You MUST choose one of our 5 blog templates for this topic. Each template has a specific structure and purpose.

TEMPLATE INFORMATION:
- Template 1: Evergreen Pillar Page Structure - For comprehensive, authoritative content on broad topics that remains relevant over time
- Template 2: Trending SEO Blog Structure - For timely, trending topics that need immediate coverage with latest information 
- Template 3: Comparison/Review Blog Structure - For comparing products, services, or approaches with pros/cons
- Template 4: Local SEO Blog Template - For location-specific content targeting local audiences
- Template 5: How-To Guide SEO Blog Template - For step-by-step instructional content and tutorials

Based on the topic "{selected_topic.keyword}", select the SINGLE MOST APPROPRIATE template that would best present this content.

You MUST return your response as valid JSON in this exact format:
```json
{{
  "template_number": 2, 
  "template_type": "template2",
  "reason": "This template is best for this topic because..."
}}
```

IMPORTANT: The template_type field MUST be one of these exact values: "template1", "template2", "template3", "template4", or "template5".
"""
            
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
                
                # Get the template type - prioritize the explicit template_type field
                template_type = template_data.get('template_type')
                
                # If template_type not present, try template_number
                if not template_type and 'template_number' in template_data:
                    template_num = template_data.get('template_number')
                    if isinstance(template_num, int) and 1 <= template_num <= 5:
                        template_type = f"template{template_num}"
                
                # Map to actual template name used in the system
                # Fixed mapping between template types and template names
                template_mapping = {
                    'template1': 'evergreen',
                    'template2': 'trend',
                    'template3': 'comparison',
                    'template4': 'local',
                    'template5': 'how_to'
                }
                
                # Ensure we have a valid template type
                if template_type not in template_mapping:
                    process_logger.warning(f"Invalid template type: {template_type}. Using default template.")
                    template_type = 'template5'  # Default to how-to
                
                template_name = template_mapping.get(template_type, 'how_to')
                process_logger.info(f"Selected template: {template_type} (maps to: {template_name})")
                
            except (json.JSONDecodeError, KeyError) as e:
                process_logger.warning(f"Error parsing template JSON: {e}. Using default template.")
                template_name = 'how_to'  # Default to how-to template
            
            # Clean up
            chatbot.clear_conversation(conversation_id)
            
            return selected_topic, template_name
            
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

def generate_blog_content_with_gemini(keyword, template_type, process_logger, fresh_content_strategy=None, used_templates=None):
    """
    Uses Gemini AI to generate blog content for a specific keyword and template type
    
    Args:
        keyword: The keyword to generate content for
        template_type: The type of template to use
        process_logger: The process logger instance
        fresh_content_strategy: Strategy for fresh content if duplicates are detected
        used_templates: List of previously used templates for this topic
        
    Returns:
        dict: The generated content data
    """
    try:
        process_logger.info(f"Generating blog content for keyword: {keyword} with template: {template_type}")
        
        # Add fresh content instructions if needed
        fresh_content_instructions = ""
        if fresh_content_strategy == "different_angle":
            process_logger.info("Adding instructions for fresh content with a different angle")
            fresh_content_instructions = f"""
IMPORTANT: This topic has been covered in recent blogs, so you must create FRESH CONTENT with a DIFFERENT ANGLE:

1. Focus on a completely different aspect of the topic than what's typical
2. Use a different structure or format (e.g., if previous was a how-to, make this a listicle)
3. Target a different audience segment or intent (e.g., beginners vs experts)
4. Include the latest data, statistics, or trends that differentiate this content
5. Provide a unique perspective or contrarian viewpoint
6. Include novel examples, case studies, or applications
7. If possible, focus on trending quotes, images, or statistics related to this topic

The goal is to create a blog that feels completely fresh even though the topic has been covered before.
"""
            
            # If we know which templates were used before, explicitly avoid them
            if used_templates:
                template_mapping = {
                    'how_to': 'How-To Guide',
                    'listicle': 'Listicle',
                    'news': 'News Article',
                    'review': 'Review',
                    'opinion': 'Opinion/Editorial'
                }
                
                used_template_names = [template_mapping.get(t, t) for t in used_templates]
                fresh_content_instructions += f"\nPreviously used template types: {', '.join(used_template_names)}. Please use a DIFFERENT approach."
        
        # Generate the SEO-optimized prompt for JSON content
        prompt = f"""Generate comprehensive blog content for the keyword "{keyword}" using a {template_type} template format.

Your content must be original, highly engaging, SEO-optimized, and provided in valid JSON format following the structure below.

{fresh_content_instructions}

CREATE COMPLETE, DETAILED BLOG CONTENT with thorough explanations of each point, actionable advice, and relevant examples.

You MUST return ONLY the following valid JSON structure without any additional text or explanation before or after the JSON:

```json
{{
  "title": "Create an SEO-optimized title with the keyword '{keyword}'",
  "meta_description": "Write a compelling 150-160 character meta description that includes the keyword",
  "introduction": "Write a 2-3 paragraph introduction that hooks the reader, establishes expertise, and briefly outlines what the blog will cover",
  "table_of_contents": ["Section 1: Title", "Section 2: Title", "..."],
  "sections": [
    {{
      "heading": "Section 1 Heading (Include H2 tag)",
      "content": "Write 3-5 paragraphs with detailed, valuable information for this section",
      "subsections": [
        {{
          "heading": "Subsection Heading (Include H3 tag)",
          "content": "Write 2-3 paragraphs of detailed content for this subsection"
        }}
      ]
    }}
  ],
  "conclusion": "Write a 2-paragraph conclusion that summarizes key points and includes a call to action",
  "faq": [
    {{
      "question": "Common question about {keyword}?",
      "answer": "Detailed, helpful answer to the question (at least 100 words)"
    }},
    {{
      "question": "Another question about {keyword}?",
      "answer": "Detailed, helpful answer to the question (at least 100 words)"
    }}
  ]
}}
```

IMPORTANT GUIDELINES:
1. Create at least 5 comprehensive sections with detailed content
2. Include at least 2-3 subsections per section where appropriate
3. Ensure all content is factual, well-researched, and valuable to readers
4. Include statistics, examples, and actionable advice where relevant
5. Create at least 4-5 relevant FAQ items with thorough answers
6. Naturally incorporate the keyword and related terms throughout the content
7. Focus on providing genuine value, not just keyword stuffing
8. Ensure the overall word count is substantial (2000+ words equivalent)
9. Write in a conversational yet authoritative tone
10. CRITICAL: Ensure the JSON is properly formatted and valid - check all brackets, commas, and quotes
"""

        # Initialize the Gemini chatbot with appropriate temperature
        chatbot = GeminiChatbot(
            model_name="gemini-1.5-pro",
            temperature=0.7,
            system_prompt="You are a professional blog content creator specializing in creating in-depth, SEO-optimized content."
        )
        
        # Get response from Gemini
        process_logger.info("Asking Gemini to generate blog content")
        response = chatbot.chat(prompt, conversation_id=f"blog_generation_{int(time.time())}")
        response_text = response.get('response', '')
        
        # Extract JSON from response
        try:
            # Log the raw response for debugging (truncated for brevity)
            process_logger.info(f"Received response with length: {len(response_text)} characters")
            if len(response_text) > 200:
                sample = response_text[:100] + "..." + response_text[-100:]
                process_logger.info(f"Response sample: {sample}")
            
            # First attempt: Try to find JSON block with markdown code markers
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                process_logger.info("Found JSON inside markdown code block")
            else:
                # Second attempt: Look for JSON in triple backticks without specifying language
                json_match = re.search(r'```\s*({\s*".*?})\s*```', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    process_logger.info("Found JSON inside generic code block")
                else:
                    # Third attempt: Find the largest JSON-like structure in the text
                    json_match = re.search(r'({[\s\S]*})', response_text)
                    if json_match:
                        json_str = json_match.group(1)
                        process_logger.info("Found JSON structure without code blocks")
                    else:
                        # If all else fails, try to clean the entire response
                        json_str = response_text.strip()
                        process_logger.info("No JSON structure found, using entire response")
            
            # Clean the JSON string
            json_str = json_str.strip()
            
            # Fix common JSON issues that might cause parsing errors
            json_str = fix_json_string(json_str)
            
            # Log first few characters of the cleaned JSON string
            process_logger.info(f"Cleaned JSON: {json_str[:100]}...")
            
            # Try to parse the JSON
            try:
                content_data = json.loads(json_str)
            except json.JSONDecodeError as e:
                process_logger.warning(f"Initial JSON parsing failed: {str(e)}")
                
                # Try an alternate approach to fix the JSON using a more aggressive method
                json_str = aggressive_json_repair(json_str)
                process_logger.info("Attempting to parse with aggressively repaired JSON")
                content_data = json.loads(json_str)
            
            # Validate the content data
            if not content_data.get('title') or not content_data.get('sections'):
                process_logger.warning("Generated content is missing required fields")
                return None
                
            # Add template type to content data
            content_data['template_type'] = template_type
            
            # If using fresh content strategy, note it in the content
            if fresh_content_strategy:
                content_data['fresh_content_strategy'] = fresh_content_strategy
            
            process_logger.info(f"Successfully generated blog content with title: {content_data.get('title')}")
            return content_data
            
        except (json.JSONDecodeError, AttributeError) as e:
            process_logger.error(f"Failed to parse JSON from Gemini response: {str(e)}")
            # Log a portion of the response that might contain the error
            if len(response_text) > 1000:
                error_location = min(8910, len(response_text) - 100)  # Around the error position we saw
                error_context = response_text[error_location-50:error_location+50]
                process_logger.error(f"Error context: ...{error_context}...")
            
            return None
        
    except Exception as e:
        process_logger.error(f"Error generating blog content: {str(e)}")
        return None

def fix_json_string(json_str):
    """
    Fix common JSON formatting issues
    """
    # Remove any leading/trailing non-JSON characters
    json_str = re.sub(r'^[^{]*', '', json_str)
    json_str = re.sub(r'[^}]*$', '', json_str)
    
    # Fix unclosed quotes
    lines = json_str.split('\n')
    fixed_lines = []
    for line in lines:
        # Count quotes in the line
        quote_count = line.count('"')
        if quote_count % 2 == 1:  # Odd number of quotes
            # Find position of the last quote
            last_quote_pos = line.rfind('"')
            if last_quote_pos != -1:
                # Add a closing quote if it seems to be missing
                line = line[:last_quote_pos+1] + '"' + line[last_quote_pos+1:]
        fixed_lines.append(line)
    
    json_str = '\n'.join(fixed_lines)
    
    # Fix missing commas between objects in arrays
    json_str = re.sub(r'}\s*{', '}, {', json_str)
    
    # Fix trailing commas in arrays or objects
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)
    
    # Ensure property names are quoted
    json_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)(\s*:)', r'\1"\2"\3', json_str)
    
    return json_str

def aggressive_json_repair(json_str):
    """
    More aggressive JSON repair for severely malformed JSON strings
    """
    # Remove common text that might appear before or after the JSON
    cleaned = re.sub(r'.*?({.*})[^}]*$', r'\1', json_str, flags=re.DOTALL)
    
    # If the JSON is still severely malformed, build a minimal valid structure
    if not is_valid_json(cleaned):
        # Extract whatever content we can and create a minimal blog structure
        title_match = re.search(r'"title"\s*:\s*"([^"]+)"', cleaned)
        title = title_match.group(1) if title_match else "Generated Blog Post"
        
        meta_match = re.search(r'"meta_description"\s*:\s*"([^"]+)"', cleaned)
        meta = meta_match.group(1) if meta_match else "Generated blog post with minimal content"
        
        # Create a minimal valid structure
        minimal_json = {
            "title": title,
            "meta_description": meta,
            "introduction": "This is a placeholder introduction.",
            "table_of_contents": ["Section 1"],
            "sections": [
                {
                    "heading": "Section 1",
                    "content": "This is placeholder content. The original content generation had errors."
                }
            ],
            "conclusion": "This is a placeholder conclusion.",
            "faq": [
                {
                    "question": "What happened to the original content?",
                    "answer": "There was an error in generating the original content."
                }
            ]
        }
        return json.dumps(minimal_json)
    
    return cleaned

def is_valid_json(json_str):
    """Check if a string is valid JSON"""
    try:
        json.loads(json_str)
        return True
    except:
        return False

def create_blog_post(topic, template_type, content_data, process_logger, publish_now=False):
    """
    Creates and publishes a blog post based on the generated content
    
    Args:
        topic: The TrendingTopic instance
        template_type: The type of template to use
        content_data: The generated content data in JSON format
        process_logger: The process logger instance
        publish_now: Boolean indicating whether to publish immediately
        
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
            status='published' if publish_now else 'draft',
            published_at=timezone.now() if publish_now else None,
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