import os
import json
import logging
import subprocess
import requests
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.db.models import Q, Count, Avg, F
from celery import shared_task
from serpapi import GoogleSearch
import re
import google.generativeai as genai
from .models import TrendingTopic, BlogPost, ContentPerformanceLog
from .logger import BlogProcessLogger

# Configure logging
logger = logging.getLogger(__name__)

# Configure Google Generative AI
if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY not configured in settings")


@shared_task
def fetch_trending_topics():
    """
    Fetches currently trending topics using SerpAPI (Google Trends Trending Now)
    """
    process_logger = BlogProcessLogger()
    process_logger.info("Starting trending topics fetch")

    if not hasattr(settings, 'SERPAPI_API_KEY') or not settings.SERPAPI_API_KEY:
        error_msg = "SERPAPI_API_KEY not configured in settings"
        process_logger.error(error_msg)
        process_logger.end_process("FAILED", {"reason": error_msg})
        return f"Error: {error_msg}"

    region = getattr(settings, 'SERP_API_REGION', 'US').lower()

    try:
        # Step 1: Configure API
        step1 = process_logger.step("CONFIGURE_SERPAPI", "Configuring SerpAPI search parameters")

        params = {
            "engine": "google_trends_trending_now",
            "geo": region.upper(),  # SerpAPI requires uppercase geo codes
            "hl": "en",
            "hours": 24,
            "api_key": settings.SERPAPI_API_KEY
        }

        process_logger.complete_step(step1, "CONFIGURE_SERPAPI", {"region": region})

        # Step 2: Execute the search
        step2 = process_logger.step("EXECUTE_SERPAPI", "Executing SerpAPI search")
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # Get trending searches - look for both trending_searches and daily_searches
        trending_stories = results.get("trending_searches", [])
        
        # If trending_searches is empty, try daily_searches (might be used in some API versions)
        if not trending_stories and "daily_searches" in results:
            # Extract the most recent daily searches
            daily_searches = results.get("daily_searches", [])
            if daily_searches and len(daily_searches) > 0:
                # Get the first (most recent) day's searches
                trending_stories = daily_searches[0].get("searches", [])

        process_logger.complete_step(step2, "EXECUTE_SERPAPI", {
            "stories_count": len(trending_stories)
        })

        # Step 3: Store the topics
        step3 = process_logger.step("STORE_TOPICS", "Storing trending topics in database")
        count = 0
        stored_topics = []

        for rank, story in enumerate(trending_stories, 1):
            # Handle different API response formats
            keyword = None
            traffic = ""
            articles = []
            
            # Format 1: Direct query in the story
            if "query" in story:
                keyword = story.get("query", "").strip()
                traffic = str(story.get("search_volume", ""))
                articles = story.get("articles", [])
                
                # For the new API format that includes trend_breakdown
                related_keywords = []
                if "trend_breakdown" in story:
                    related_keywords = story.get("trend_breakdown", [])
                else:
                    # Get related queries if available
                    related_queries = story.get("related_queries", [])
                    related_keywords = [q.get("query", "") for q in related_queries if q.get("query")]
                
                # Get category if available
                category_names = ""
                if "categories" in story:
                    categories = story.get("categories", [])
                    category_names = ", ".join([c.get("name", "") for c in categories if c.get("name")])
            
            # Format 2: Title object contains query
            elif "title" in story and isinstance(story["title"], dict):
                title_info = story.get("title", {})
                keyword = title_info.get("query", "").strip()
                traffic = title_info.get("formattedTraffic", "")
                articles = story.get("articles", [])
                
                # Extract category names from articles
                category_names = ", ".join([a.get("source", "") for a in articles if a.get("source")])
                
                # Extract related keywords from articles
                related_keywords = [a.get("title") for a in articles if a.get("title")]
            
            # Skip if no valid keyword found
            if not keyword:
                continue
                
            # Convert related keywords to JSON
            related_keywords_json = json.dumps(related_keywords) if related_keywords else None

            # Create the trending topic
            topic = TrendingTopic.objects.create(
                keyword=keyword,
                rank=rank,
                location=region,
                search_volume=traffic,
                category=category_names,
                related_keywords=related_keywords_json
            )

            count += 1
            stored_topics.append({
                "id": topic.id,
                "keyword": keyword,
                "rank": rank,
                "traffic": traffic,
                "categories": category_names
            })

        process_logger.complete_step(step3, "STORE_TOPICS", {
            "topics_count": count,
            "topics": stored_topics[:5] if stored_topics else []
        })

        process_logger.success(f"Successfully fetched {count} trending topics")
        process_logger.end_process("COMPLETED", {"topics_count": count, "region": region})
        return f"Successfully fetched {count} trending topics"

    except Exception as e:
        error_msg = f"Error fetching trending topics: {str(e)}"
        process_logger.error(error_msg)
        process_logger.end_process("FAILED", {"error": str(e)})
        return f"Error: {str(e)}"


# @shared_task
# def fetch_trending_topics():
#     """
#     Fetches trending topics from Google Trends using SerpAPI
#     Runs hourly
#     """
#     # Create a process logger for this task
#     process_logger = BlogProcessLogger()
#     process_logger.info("Starting trending topics fetch")
    
#     if not hasattr(settings, 'SERPAPI_API_KEY') or not settings.SERPAPI_API_KEY:
#         error_msg = "SERPAPI_API_KEY not configured in settings"
#         process_logger.error(error_msg)
#         process_logger.end_process("FAILED", {"reason": error_msg})
#         return f"Error: {error_msg}"
        
#     region = getattr(settings, 'SERP_API_REGION', 'IN')
#     category = getattr(settings, 'SERP_API_CATEGORY', 'all')
    
#     try:
#         # Step 1: Configure SerpAPI search
#         step1 = process_logger.step("CONFIGURE_SERPAPI", "Configuring SerpAPI search parameters")
        
#         params = {
#             "engine": "google_trends",
#             "q": "trending",  # Required, even if generic
#             "data_type": "TIMESERIES",
#             "geo": region,
#             "date": "now 4-H",
#             "hl": "en",
#             "api_key": settings.SERPAPI_API_KEY,
#         }

        
#         process_logger.complete_step(step1, "CONFIGURE_SERPAPI", {
#             "region": region,
#             "category": category
#         })
        
#         # Step 2: Execute the search
#         step2 = process_logger.step("EXECUTE_SERPAPI", "Executing SerpAPI search")
        
#         # Execute the search
#         search = GoogleSearch(params)
#         results = search.get_dict()
        
#         # Get trending searches from results
#         trending_searches = results.get("trending_searches", [])
        
#         process_logger.complete_step(step2, "EXECUTE_SERPAPI", {
#             "searches_count": len(trending_searches)
#         })
        
#         # Step 3: Store trending topics
#         step3 = process_logger.step("STORE_TOPICS", "Storing trending topics in database")
        
#         # Store trending topics
#         count = 0
#         stored_topics = []
        
#         for rank, search_item in enumerate(trending_searches, 1):
#             keyword = search_item.get("query", "").strip()
            
#             if keyword:
#                 # Extract additional data from the search item
#                 search_volume = search_item.get("search_volume", 0)
#                 increase_percentage = search_item.get("increase_percentage", 0)
#                 categories = search_item.get("categories", [])
#                 trend_breakdown = search_item.get("trend_breakdown", [])
                
#                 # Convert categories to string format
#                 category_names = [cat.get("name", "") for cat in categories if cat.get("name")]
#                 category_string = ", ".join(category_names) if category_names else ""
                
#                 # Store trend breakdown as JSON for later use in content generation
#                 trend_keywords = json.dumps(trend_breakdown) if trend_breakdown else None
                
#                 # Store in database with enhanced metadata
#                 topic = TrendingTopic.objects.create(
#                     keyword=keyword,
#                     rank=rank,
#                     location=region,
#                     search_volume=search_volume,
#                     increase_percentage=increase_percentage,
#                     category=category_string,
#                     related_keywords=trend_keywords
#                 )
                
#                 count += 1
#                 stored_topics.append({
#                     "id": topic.id,
#                     "keyword": keyword,
#                     "rank": rank,
#                     "search_volume": search_volume,
#                     "categories": category_string,
#                     "related_keywords_count": len(trend_breakdown) if trend_breakdown else 0
#                 })
        
#         process_logger.complete_step(step3, "STORE_TOPICS", {
#             "topics_count": count,
#             "topics": stored_topics[:5] if len(stored_topics) > 5 else stored_topics
#         })
        
#         process_logger.success(f"Successfully fetched {count} trending topics")
#         process_logger.end_process("COMPLETED", {
#             "topics_count": count,
#             "region": region
#         })
        
#         return f"Successfully fetched {count} trending topics"
#     except Exception as e:
#         error_msg = f"Error fetching trending topics: {str(e)}"
#         process_logger.error(error_msg)
#         process_logger.end_process("FAILED", {"error": str(e)})
#         return f"Error: {str(e)}"


@shared_task
def process_trending_topics():
    """
    Processes unprocessed trending topics by filtering and categorizing them
    """
    logger.info("Processing new trending topics")
    
    # Get unprocessed topics
    topics = TrendingTopic.objects.filter(processed=False, filtered_out=False)
    
    if not topics.exists():
        logger.info("No unprocessed trending topics found")
        return "No unprocessed trending topics found"
    
    total = topics.count()
    filtered = 0
    processed = 0
    
    for topic in topics:
        # Filter out low-quality keywords
        keyword = topic.keyword.lower()
        
        # Filter out too short keywords
        if len(keyword.split()) < 2:
            topic.filtered_out = True
            topic.filter_reason = "Too short"
            topic.processed = True
            topic.save()
            filtered += 1
            continue
        
        # Filter out banned words/topics
        banned_words = ['porn', 'xxx', 'sex', 'nude', 'casino', 'gambling', 'hack', 'crack', 'warez']
        if any(word in keyword for word in banned_words):
            topic.filtered_out = True
            topic.filter_reason = "Contains banned words"
            topic.processed = True
            topic.save()
            filtered += 1
            continue
            
        # Calculate engagement potential
        engagement_potential = calculate_engagement_potential(topic.keyword)
        
        # Predict suitable template type
        template_type = predict_template_type(keyword)
        
        # Mark as processed
        topic.processed = True
        topic.save()
        processed += 1
        
        # Queue content generation for this topic
        generate_blog_for_topic.delay(topic.id, template_type, engagement_potential)
    
    logger.info(f"Processed {total} topics: {processed} accepted, {filtered} filtered out")
    return f"Processed {total} topics: {processed} accepted, {filtered} filtered out"


def calculate_engagement_potential(keyword):
    """
    Calculates the engagement potential of a keyword based on:
    1. Search volume/trends
    2. Historical engagement for similar topics
    3. Keyword competition
    
    Returns a score between 0-100
    """
    try:
        # Check historical performance of similar keywords
        similar_topics = TrendingTopic.objects.filter(
            keyword__icontains=keyword.split()[0] if keyword.split() else ""
        ).values('id')
        
        similar_posts = BlogPost.objects.filter(
            trending_topic__in=similar_topics
        )
        
        # Calculate average metrics from similar posts
        avg_views = similar_posts.aggregate(avg_views=Avg('view_count'))['avg_views'] or 0
        avg_time = similar_posts.aggregate(avg_time=Avg('avg_time_on_page'))['avg_time'] or 0
        
        # Base score from rank (higher rank = higher score)
        base_score = 60
        
        # Adjust based on historical performance
        engagement_score = base_score
        
        if avg_views > 1000:
            engagement_score += 20
        elif avg_views > 500:
            engagement_score += 10
        elif avg_views > 100:
            engagement_score += 5
            
        if avg_time > 120:  # 2 minutes
            engagement_score += 20
        elif avg_time > 60:  # 1 minute
            engagement_score += 10
        
        # Ensure score is within range
        return min(max(engagement_score, 0), 100)
    except Exception as e:
        logger.error(f"Error calculating engagement potential: {e}")
        return 50  # Default middle score


@shared_task
def select_best_trending_topic():
    """
    Selects the best trending topic for content generation based on engagement potential,
    search volume, and increase percentage
    Runs hourly before content generation
    """
    logger.info("Selecting best trending topic for content generation")
    
    # Get processed topics that haven't been used for blog posts yet
    topics = TrendingTopic.objects.filter(
        processed=True,
        filtered_out=False,
        blog_posts__isnull=True
    ).order_by('-timestamp')[:10]  # Consider only recent topics
    
    if not topics.exists():
        logger.info("No suitable trending topics found")
        return "No suitable trending topics found"
    
    best_topic = None
    best_score = -1
    best_template = None
    
    for topic in topics:
        # Calculate base engagement potential
        engagement_score = calculate_engagement_potential(topic.keyword)
        
        # Factor in search volume and increase percentage from Google Trends
        if topic.search_volume > 0:
            # Normalize search volume (higher is better)
            volume_factor = min(topic.search_volume / 10000, 1.0) * 20  # Max 20 points for volume
            engagement_score += volume_factor
            
        if topic.increase_percentage > 0:
            # Higher increase percentage means more trending (higher is better)
            trend_factor = min(topic.increase_percentage / 500, 1.0) * 20  # Max 20 points for trend
            engagement_score += trend_factor
        
        # Determine best template type
        template_type = predict_template_type(topic.keyword)
        
        logger.info(f"Topic: {topic.keyword}, Score: {engagement_score}, Template: {template_type}")
        
        if engagement_score > best_score:
            best_score = engagement_score
            best_topic = topic
            best_template = template_type
    
    if best_topic:
        logger.info(f"Selected best topic: {best_topic.keyword} (Score: {best_score}, Template: {best_template})")
        
        # Load related keywords if available
        related_keywords = None
        if best_topic.related_keywords:
            try:
                related_keywords = json.loads(best_topic.related_keywords)
                logger.info(f"Using {len(related_keywords)} related keywords for content generation")
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse related keywords for topic: {best_topic.keyword}")
        
        # Queue content generation with related keywords
        generate_blog_for_topic.delay(best_topic.id, best_template, best_score)
        
        return f"Selected best topic: {best_topic.keyword} (Score: {best_score}, Category: {best_topic.category or 'Unknown'})"
    else:
        return "No suitable topic found"


def predict_template_type(keyword):
    """
    Predicts the most suitable blog template type based on the keyword
    """
    keyword = keyword.lower()
    
    # How-to guide
    if keyword.startswith('how to') or 'step by step' in keyword or 'guide' in keyword or 'tutorial' in keyword:
        return 'how_to'
    
    # Listicle
    if re.match(r'^\d+', keyword) or 'best' in keyword or 'top' in keyword or 'ways to' in keyword:
        return 'listicle'
    
    # Review
    if 'review' in keyword or 'vs' in keyword or 'versus' in keyword or 'comparison' in keyword:
        return 'review'
    
    # News
    if any(word in keyword for word in ['breaking', 'news', 'announced', 'launches', 'update', 'released']):
        return 'news'
    
    # Default to opinion/editorial
    return 'opinion'


@shared_task
def generate_blog_for_topic(topic_id, template_type, engagement_score=50):
    """
    Generates a blog post for a specific trending topic
    """
    try:
        # Get the topic
        topic = TrendingTopic.objects.get(id=topic_id)
        logger.info(f"Generating blog for topic: {topic.keyword} using {template_type} template")
        
        # Load related keywords if available
        related_keywords = None
        if topic.related_keywords:
            try:
                related_keywords = json.loads(topic.related_keywords)
                logger.info(f"Loaded {len(related_keywords)} related keywords for SEO optimization")
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse related keywords JSON for topic: {topic.keyword}")
        
        # Generate the SEO-optimized prompt for structured JSON content
        prompt = generate_json_seo_prompt(topic.keyword, template_type, related_keywords)
        
        # Generate content using Gemini
        json_content = generate_content_with_gemini(prompt)
        
        if not json_content:
            logger.error(f"Failed to generate content for topic: {topic.keyword}")
            return f"Failed to generate content for topic: {topic.keyword}"
        
        # Parse the generated JSON content
        content_data = parse_json_content(json_content, template_type)
        
        if not content_data:
            logger.error(f"Failed to parse JSON content for topic: {topic.keyword}")
            return f"Failed to parse JSON content for topic: {topic.keyword}"
        
        # Create formatted HTML content from JSON structure
        title = content_data.get('title', topic.keyword)
        meta_description = content_data.get('meta_description', f"Learn about {topic.keyword}")
        html_content = format_json_to_html(content_data, template_type)
        
        # Create blog post
        blog_post = BlogPost(
            title=title,
            content=html_content,
            meta_description=meta_description,
            template_type=template_type,
            trending_topic=topic,
            status='scheduled',
            scheduled_at=timezone.now() + timedelta(minutes=10)  # Schedule for publication in 10 minutes
        )
        blog_post.save()
        
        logger.info(f"Successfully created blog post: {blog_post.title}")
        return f"Successfully created blog post: {blog_post.title}"
        
    except TrendingTopic.DoesNotExist:
        logger.error(f"Topic with ID {topic_id} not found")
        return f"Error: Topic with ID {topic_id} not found"
    except Exception as e:
        logger.error(f"Error generating blog for topic ID {topic_id}: {e}")
        return f"Error: {str(e)}"


def generate_json_seo_prompt(keyword, template_type=None, related_keywords=None):
    """
    Generates an SEO-optimized prompt for JSON content generation
    
    Args:
        keyword: The topic keyword
        template_type: Optional suggested template type (Gemini may override)
        related_keywords: Optional list of related keywords for SEO optimization
        
    Returns:
        str: The prompt for Gemini
    """
    # Create a detailed prompt for Gemini to analyze and select the best template
    prompt = """As a professional content writer, your task is to create high-quality blog content about "{0}".

First, analyze the topic to determine the most appropriate template format from the available options:
- How-To Guide: Step-by-step instructions for accomplishing a specific task
- Listicle: A numbered list of items, tips, or examples related to the topic
- News Article: Coverage of recent developments or events
- Review: Evaluation of products, services, or concepts, with pros and cons
- Opinion: Editorial content presenting a perspective on the topic

After analyzing the topic, select the BEST template type for this specific content. 

Then, generate structured content in JSON format according to your selected template. Make sure your content:
- Is well-researched and informative
- Has a clear structure with appropriate headings
- Includes an engaging introduction and conclusion
- Uses a conversational but professional tone
- Is optimized for SEO with appropriate keywords

Return your response in this exact JSON format:
```json
{{
  "template_type": "how_to", // Your selected template type (how_to, listicle, news, review, or opinion)
  "title": "How to [Topic] - A Comprehensive Guide",
  "meta_description": "A concise and SEO-friendly meta description under 160 characters",
  "introduction": "An engaging introduction to the topic",
  "table_of_contents": ["First H2 title", "Second H2 title", "..."],
  "sections": [
    {{
      "type": "introduction", // or "step" for how-to, "list_item" for listicle, "section" for others
      "h2": "Optional H2 heading",
      "content": "Main content text for this section",
      "subsections": [
        {{
          "h3": "Subheading (H3)",
          "content": "Content for this subsection",
          "list_items": ["Optional item 1", "Optional item 2"]
        }}
      ]
    }}
    // Additional sections...
  ],
  "conclusion": "A thoughtful conclusion summarizing key points",
  "faq": [
    {{
      "question": "Frequently asked question 1?",
      "answer": "Answer to the question"
    }},
    // Additional FAQ items...
  ]
}}
```

IMPORTANT NOTES:"""

    # Format the prompt with the keyword
    prompt = prompt.format(keyword)
    
    # Build template instruction without f-strings
    template_instruction = "1. "
    if template_type:
        template_instruction += "The suggested initial template is \"" + template_type + "\", but "
    template_instruction += "Choose the BEST template based on your analysis"
    
    # Add related keywords information if available
    if related_keywords and isinstance(related_keywords, list) and len(related_keywords) > 0:
        keywords_sample = related_keywords[:20] if len(related_keywords) > 20 else related_keywords
        keywords_str = ", ".join(keywords_sample)
        seo_instruction = """
2. IMPORTANT FOR SEO: This topic is trending with these related keywords: {0}

   These keywords represent what people are searching for in relation to the main topic.
   Incorporate these keywords naturally throughout your content where relevant:
   - Include some in your H2 and H3 headings
   - Use them in list items when appropriate
   - Include them in the FAQ questions and answers
   - Work them into the content where they fit naturally

   This will significantly improve SEO performance of the content.""".format(keywords_str)
        
        # Shift other points down one number
        prompt_notes = """
3. Include the template_type field in your JSON response with your chosen template
4. Structure your sections appropriately based on the chosen template
5. Ensure the content is comprehensive, accurate, and valuable to readers
6. Your JSON must be valid, properly formatted, and include all the required fields"""
    else:
        seo_instruction = ""
        # Regular string for prompt notes
        prompt_notes = """
2. Include the template_type field in your JSON response with your chosen template
3. Structure your sections appropriately based on the chosen template
4. Ensure the content is comprehensive, accurate, and valuable to readers
5. Your JSON must be valid, properly formatted, and include all the required fields"""

    # Combine all parts
    return prompt + "\n\n" + template_instruction + seo_instruction + "\n\n" + prompt_notes


def parse_json_content(content, template_type):
    """
    Parses the generated JSON content from Gemini
    Returns a structured dictionary of the content
    """
    try:
        # Clean up the content to ensure it's valid JSON
        # Remove markdown code blocks if present
        content = re.sub(r'```json', '', content)
        content = re.sub(r'```', '', content)
        content = content.strip()
        
        # Handle any special characters that might cause encoding issues
        content = content.encode('utf-8', 'ignore').decode('utf-8')
        
        # Parse the JSON
        data = json.loads(content)
        
        # Validate required fields
        required_fields = ['title', 'meta_description', 'sections']
        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing required field in JSON content: {field}")
                data[field] = "" if field != 'sections' else []
        
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        logger.error(f"Raw content: {content}")
        return None
    except Exception as e:
        logger.error(f"Error parsing JSON content: {e}")
        return None


def format_json_to_html(content_data, template_type):
    """
    Converts the structured JSON content to formatted HTML
    based on the template type
    """
    try:
        html = ""
        
        # Add title as H1
        title = content_data.get('title', '')
        title = title.encode('utf-8', 'ignore').decode('utf-8')
        html += f"<h1>{title}</h1>\n\n"
        
        # Process each section
        for section in content_data.get('sections', []):
            section_type = section.get('type', '')
            
            if section_type == 'introduction':
                # Introduction section
                if 'h1' in section and section['h1'] != content_data.get('title', ''):
                    h1 = section.get('h1', '').encode('utf-8', 'ignore').decode('utf-8')
                    html += f"<h2>{h1}</h2>\n"
                content_text = section.get('content', '').encode('utf-8', 'ignore').decode('utf-8')
                html += f"<p>{content_text}</p>\n\n"
            
            elif section_type == 'conclusion':
                # Conclusion section
                h2 = section.get('h2', 'Conclusion').encode('utf-8', 'ignore').decode('utf-8')
                content_text = section.get('content', '').encode('utf-8', 'ignore').decode('utf-8')
                html += f"<h2>{h2}</h2>\n"
                html += f"<p>{content_text}</p>\n\n"
            
            else:
                # Regular section
                if 'h2' in section:
                    h2 = section.get('h2', '').encode('utf-8', 'ignore').decode('utf-8')
                    html += f"<h2>{h2}</h2>\n"
                
                if 'content' in section:
                    content_text = section.get('content', '').encode('utf-8', 'ignore').decode('utf-8')
                    html += f"<p>{content_text}</p>\n\n"
                
                # Process subsections if present
                for subsection in section.get('subsections', []):
                    if 'h3' in subsection:
                        h3 = subsection.get('h3', '').encode('utf-8', 'ignore').decode('utf-8')
                        html += f"<h3>{h3}</h3>\n"
                    
                    if 'content' in subsection:
                        content_text = subsection.get('content', '').encode('utf-8', 'ignore').decode('utf-8')
                        html += f"<p>{content_text}</p>\n\n"
                    
                    # Process list items if present
                    if 'list_items' in subsection and subsection['list_items']:
                        html += "<ul>\n"
                        for item in subsection['list_items']:
                            item_text = item.encode('utf-8', 'ignore').decode('utf-8')
                            html += f"<li>{item_text}</li>\n"
                        html += "</ul>\n\n"
        
        # Add FAQ section if present
        if 'faq' in content_data and content_data['faq']:
            html += "<h2>Frequently Asked Questions</h2>\n"
            html += "<div class='faq-section'>\n"
            
            for qa in content_data['faq']:
                question = qa.get('question', '').encode('utf-8', 'ignore').decode('utf-8')
                answer = qa.get('answer', '').encode('utf-8', 'ignore').decode('utf-8')
                
                html += f"<div class='faq-item'>\n"
                html += f"<h3>{question}</h3>\n"
                html += f"<p>{answer}</p>\n"
                html += "</div>\n\n"
                
            html += "</div>\n"
        
        return html
    except Exception as e:
        logger.error(f"Error formatting JSON to HTML: {e}")
        return ""


def generate_seo_prompt(keyword, template_type):
    """
    Generates an SEO-optimized prompt for Gemini based on keyword and template
    """
    # Get high-performing content as context
    context = get_high_performing_context(template_type)
    
    base_prompt = f"""Write a detailed SEO-optimized blog post about "{keyword}". """
    
    template_instructions = {
        'how_to': "Use the how-to guide format with numbered steps, clear headings, and actionable advice.",
        'listicle': "Use the listicle format with numbered points, bullet lists where appropriate, and concise explanations.",
        'news': "Use the news article format with an attention-grabbing headline, an informative opening paragraph, and supporting details.",
        'review': "Use the review format with pros and cons, ratings, and comparative analysis.",
        'opinion': "Use the opinion/editorial format with a clear thesis, supporting arguments, and counterpoints."
    }
    
    prompt = base_prompt + template_instructions.get(template_type, "")
    
    # Add SEO best practices
    prompt += """
    Include the following elements:
    1. A catchy title that includes the main keyword
    2. H2 and H3 subheadings that incorporate related keywords
    3. A meta description under 150 characters
    4. Internal paragraph structure with topic sentences
    5. A conclusion with a call-to-action
    
    Format your response with:
    TITLE: [Your title here]
    META: [Meta description under 150 characters]
    CONTENT: [The full blog post content with proper HTML formatting]
    """
    
    # Add context from high-performing content if available
    if context:
        prompt += f"\n\nReference the structure and style of this high-performing content: {context}"
    
    return prompt


def get_high_performing_context(template_type):
    """
    Retrieves context from high-performing content for similar template types
    """
    try:
        # Get the highest-viewed blog post with similar template
        top_post = BlogPost.objects.filter(
            template_type=template_type,
            view_count__gt=100  # Only consider posts with significant views
        ).order_by('-view_count').first()
        
        if top_post:
            # Extract key patterns and structures (simplified)
            return f"Title structure: {top_post.title}, Key subheadings count: {top_post.content.count('<h2>')}"
        return None
    except Exception as e:
        logger.error(f"Error getting high-performing context: {e}")
        return None


def generate_content_with_gemini(prompt):
    """
    Generates content using Google's Gemini model
    """
    try:
        if not hasattr(settings, 'GEMINI_MODEL') or not settings.GEMINI_MODEL:
            model_name = 'gemini-1.5-pro'
        else:
            model_name = settings.GEMINI_MODEL
            
        # Initialize the model
        model = genai.GenerativeModel(model_name=model_name)
        
        # Generate content
        response = model.generate_content(prompt)
        
        if response and hasattr(response, 'text'):
            return response.text
        else:
            logger.error("Empty response from Gemini API")
            return None
    except Exception as e:
        logger.error(f"Error generating content with Gemini: {e}")
        return None


def parse_generated_content(content):
    """
    Parses the generated content to extract title, body, and meta description
    """
    title = None
    meta_description = None
    body = content
    
    # Extract title
    title_match = re.search(r'TITLE:\s*(.*?)(?:\n|$)', content)
    if title_match:
        title = title_match.group(1).strip()
        body = re.sub(r'TITLE:\s*(.*?)(?:\n|$)', '', body, 1)
    
    # Extract meta description
    meta_match = re.search(r'META:\s*(.*?)(?:\n|$)', content)
    if meta_match:
        meta_description = meta_match.group(1).strip()
        body = re.sub(r'META:\s*(.*?)(?:\n|$)', '', body, 1)
    
    # Clean up the content part
    body = re.sub(r'CONTENT:\s*', '', body, 1).strip()
    
    return title, body, meta_description


@shared_task
def generate_blog_content():
    """
    Main task that orchestrates the blog content generation pipeline
    Runs hourly to select the best trending topic and generate content
    """
    logger.info("Starting blog content generation pipeline")
    
    # First select the best trending topic
    select_best_trending_topic.delay()
    
    return "Blog content generation pipeline triggered"


@shared_task
def publish_scheduled_blogs():
    """
    Publishes blogs that are scheduled for publication
    Runs every 10 minutes
    """
    logger.info("Publishing scheduled blog posts")
    
    now = timezone.now()
    
    # Find blog posts that are scheduled and whose scheduled time has passed
    scheduled_posts = BlogPost.objects.filter(
        status='scheduled',
        scheduled_at__lte=now
    )
    
    count = 0
    for post in scheduled_posts:
        post.status = 'published'
        post.published_at = now
        post.save()
        count += 1
    
    logger.info(f"Published {count} scheduled blog posts")
    return f"Published {count} scheduled blog posts"


@shared_task
def update_blog_analytics():
    """
    Updates blog analytics data from external sources
    """
    # Logic to fetch and update analytics would go here
    # This is a placeholder for integration with Google Analytics or similar
    return "Blog analytics updated"


@shared_task
def backup_database():
    """
    Creates a backup of the database
    Runs weekly
    """
    logger.info("Starting database backup")
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(settings.BASE_DIR, 'backups')
    
    # Create backup directory if it doesn't exist
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
        # SQLite backup (file copy)
        db_path = settings.DATABASES['default']['NAME']
        backup_path = os.path.join(backup_dir, f'db_backup_{timestamp}.sqlite3')
        
        try:
            # Use subprocess to copy the file (works on all platforms)
            if os.name == 'nt':  # Windows
                subprocess.run(['copy', db_path, backup_path], shell=True, check=True)
            else:  # Unix/Linux/Mac
                subprocess.run(['cp', db_path, backup_path], check=True)
                
            logger.info(f"Database backup created at {backup_path}")
            return f"Database backup created at {backup_path}"
        except Exception as e:
            logger.error(f"Error backing up database: {e}")
            return f"Error: {str(e)}"
    else:
        # Placeholder for PostgreSQL, MySQL, etc.
        # Would use pg_dump, mysqldump, etc.
        logger.info("Database backup for non-SQLite databases not implemented")
        return "Database backup for non-SQLite databases not implemented"


@shared_task
def create_and_publish_blog(keyword, template_type=None, publish_immediately=False, related_keywords=None):
    """
    Creates and optionally publishes a blog post immediately for a given keyword
    
    Args:
        keyword (str): The keyword/topic to create a blog post for
        template_type (str, optional): The template type to use. If None, will be predicted.
        publish_immediately (bool): Whether to publish immediately or schedule
        related_keywords (list, optional): Related keywords for SEO optimization
        
    Returns:
        str: Status message
    """
    # Create a process logger for this blog creation task
    process_logger = BlogProcessLogger()
    process_logger.info(f"Starting blog creation process for: {keyword}", {
        "keyword": keyword,
        "template_type": template_type,
        "publish_immediately": publish_immediately,
        "related_keywords_count": len(related_keywords) if related_keywords else 0
    })
    
    try:
        # Step 1: Create trending topic entry
        step1 = process_logger.step("CREATE_TRENDING_TOPIC", "Creating trending topic entry")
        
        # Store related keywords as JSON if provided
        related_keywords_json = json.dumps(related_keywords) if related_keywords else None
        
        topic = TrendingTopic.objects.create(
            keyword=keyword,
            rank=1,  # Priority rank
            location='global',
            processed=True,  # Mark as processed
            related_keywords=related_keywords_json
        )
        
        process_logger.complete_step(step1, "CREATE_TRENDING_TOPIC", {
            "topic_id": topic.id,
            "keyword": topic.keyword,
            "related_keywords_count": len(related_keywords) if related_keywords else 0
        })
        
        # Step 2: Determine template type
        step2 = process_logger.step("DETERMINE_TEMPLATE", "Determining blog template type")
        
        # Predict template type if not provided
        if not template_type:
            template_type = predict_template_type(keyword)
            process_logger.info(f"Template type predicted as: {template_type}")
        else:
            process_logger.info(f"Using provided template type: {template_type}")
        
        # Calculate engagement score
        engagement_score = calculate_engagement_potential(keyword)
        
        process_logger.complete_step(step2, "DETERMINE_TEMPLATE", {
            "template_type": template_type,
            "engagement_score": engagement_score
        })
        
        # Step 3: Generate content
        step3 = process_logger.step("GENERATE_CONTENT", "Generating blog content")
        
        # Generate the SEO-optimized prompt for structured JSON content
        prompt = generate_json_seo_prompt(keyword, template_type, related_keywords)
        process_logger.info("Generated SEO prompt", {"prompt_length": len(prompt)})
        
        # Generate content using Gemini
        json_content = generate_content_with_gemini(prompt)
        
        if not json_content:
            error_msg = f"Failed to generate content for topic: {keyword}"
            process_logger.fail_step(step3, "GENERATE_CONTENT", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return error_msg
        
        process_logger.info("Content generated successfully", {"content_length": len(json_content)})
        
        # Parse the generated JSON content
        content_data = parse_json_content(json_content, template_type)
        
        if not content_data:
            error_msg = f"Failed to parse JSON content for topic: {keyword}"
            process_logger.fail_step(step3, "GENERATE_CONTENT", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return error_msg
        
        process_logger.complete_step(step3, "GENERATE_CONTENT", {
            "title": content_data.get('title'),
            "sections_count": len(content_data.get("table_of_contents", []))
        })
        
        # Step 4: Create blog post
        step4 = process_logger.step("CREATE_BLOG_POST", "Creating and publishing blog post")
        
        # Create formatted HTML content from JSON structure
        title = content_data.get('title', keyword)
        meta_description = content_data.get('meta_description', f"Learn about {keyword}")
        html_content = format_json_to_html(content_data, template_type)
        
        process_logger.info("HTML content formatted", {"html_length": len(html_content)})
        
        # Create blog post
        blog_post = BlogPost(
            title=title,
            content=html_content,
            meta_description=meta_description,
            template_type=template_type,
            trending_topic=topic
        )
        
        if publish_immediately:
            # Publish immediately
            blog_post.status = 'published'
            blog_post.published_at = timezone.now()
            status = "published"
        else:
            # Schedule for publication
            blog_post.status = 'scheduled'
            blog_post.scheduled_at = timezone.now() + timedelta(minutes=10)
            status = "scheduled"
        
        blog_post.save()
        
        process_logger.complete_step(step4, "CREATE_BLOG_POST", {
            "blog_id": str(blog_post.id),
            "blog_title": blog_post.title,
            "blog_status": blog_post.status,
            "blog_url": blog_post.slug
        })
        
        process_logger.success(f"Successfully {status} blog post: {blog_post.title}")
        process_logger.end_process("COMPLETED", {
            "blog_id": str(blog_post.id),
            "blog_title": blog_post.title,
            "topic": keyword,
            "template_type": template_type,
            "status": status
        })
        
        return f"Successfully {status} blog post: {blog_post.title} (ID: {blog_post.id})"
        
    except Exception as e:
        process_logger.error(f"Error creating blog for keyword '{keyword}': {str(e)}")
        process_logger.end_process("FAILED", {"error": str(e)})
        return f"Error: {str(e)}" 