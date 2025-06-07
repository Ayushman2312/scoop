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
from .models import TrendingTopic, BlogPost, ContentPerformanceLog, TopicFreshnessLog
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
    Fetches top 10 trending topics from the past 4 hours using SerpAPI (Google Trends)
    Improved to ensure reliable results and handle multiple API response formats
    """
    process_logger = BlogProcessLogger()
    process_logger.info("Starting enhanced trending topics fetch (past 4 hours)")

    if not hasattr(settings, 'SERPAPI_API_KEY') or not settings.SERPAPI_API_KEY:
        error_msg = "SERPAPI_API_KEY not configured in settings"
        process_logger.error(error_msg)
        process_logger.end_process("FAILED", {"reason": error_msg})
        return f"Error: {error_msg}"

    region = getattr(settings, 'SERP_API_REGION', 'US').lower()
    
    # By default, skip non-Latin script topics to avoid encoding issues
    skip_non_latin = getattr(settings, 'SKIP_NON_LATIN_TOPICS', True)
    process_logger.info(f"Non-Latin script topics will be {'skipped' if skip_non_latin else 'included'}")

    try:
        # Step 1: Configure API for real-time trending searches
        step1 = process_logger.step("CONFIGURE_SERPAPI", "Configuring SerpAPI search parameters")

        # Primary configuration for trending_searches (real-time)
        primary_params = {
            "engine": "google_trends_trending_now",
            "geo": region.upper(),  # SerpAPI requires uppercase geo codes
            "hl": "en",  # Force English language
            "hours": 4,  # Focus on past 4 hours as requested
            "category": "all",
            "api_key": settings.SERPAPI_API_KEY
        }

        # Secondary configuration for daily_searches (fallback)
        secondary_params = {
            "engine": "google_trends",
            "data_type": "TIMESERIES",
            "geo": region.upper(),
            "date": "now 1-d",  # Last 24 hours
            "hl": "en",  # Force English language
            "api_key": settings.SERPAPI_API_KEY
        }

        # Tertiary configuration for trending searches on web (extra fallback)
        tertiary_params = {
            "engine": "google_trends_trending_now",
            "geo": "US",  # Force US region as safe fallback
            "hl": "en",  # Force English language
            "api_key": settings.SERPAPI_API_KEY, 
            "hours": 4,
        }

        process_logger.complete_step(step1, "CONFIGURE_SERPAPI", {"region": region, "time_range": "4 hours"})

        # Step 2: Execute the search with multiple fallbacks
        step2 = process_logger.step("EXECUTE_SERPAPI", "Executing SerpAPI search with fallbacks")
        
        # Try primary search first (real-time trending)
        primary_search = GoogleSearch(primary_params)
        results = primary_search.get_dict()
        trending_stories = results.get("trending_searches", [])
        search_method = "trending_searches"
        
        # If primary search yielded no results, try daily searches
        if not trending_stories and "daily_searches" in results:
            daily_searches = results.get("daily_searches", [])
            if daily_searches and len(daily_searches) > 0:
                trending_stories = daily_searches[0].get("searches", [])
                search_method = "daily_searches"
        
        # If still no results, try secondary approach
        if not trending_stories:
            process_logger.info("No results from primary search, trying secondary approach")
            secondary_search = GoogleSearch(secondary_params)
            secondary_results = secondary_search.get_dict()
            
            # Extract from interest over time if available
            if "interest_over_time" in secondary_results:
                interest_data = secondary_results.get("interest_over_time", {}).get("timeline_data", [])
                if interest_data:
                    # Reconstruct trending stories from interest over time data
                    trending_stories = []
                    for data_point in interest_data:
                        if "values" in data_point:
                            for value in data_point.get("values", []):
                                trending_stories.append({
                                    "query": value.get("query", ""),
                                    "value": value.get("value", 0)
                                })
                    search_method = "interest_over_time"
        
        # Last resort: try tertiary approach
        if not trending_stories:
            process_logger.info("No results from secondary search, trying tertiary approach")
            tertiary_search = GoogleSearch(tertiary_params)
            tertiary_results = tertiary_search.get_dict()
            
            # Extract from related queries if available
            if "related_queries" in tertiary_results:
                related_queries = tertiary_results.get("related_queries", [])
                trending_stories = [{"query": query.get("query", "")} for query in related_queries]
                search_method = "related_queries"
        
        # Ensure we limit to top 10 as specified
        trending_stories = trending_stories[:10]
        
        process_logger.complete_step(step2, "EXECUTE_SERPAPI", {
            "stories_count": len(trending_stories),
            "search_method": search_method
        })

        # Step 3: Store the topics
        step3 = process_logger.step("STORE_TOPICS", "Storing top 10 trending topics in database")
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
                traffic = str(story.get("search_volume", "") or story.get("value", ""))
                articles = story.get("articles", [])
                
                # For the new API format that includes trend_breakdown
                related_keywords = []
                if "trend_breakdown" in story:
                    related_keywords = story.get("trend_breakdown", [])
                elif "related_queries" in story:
                    related_keywords = [q.get("query", "") for q in story.get("related_queries", []) if q.get("query")]
                
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
            
            # Check if this topic contains non-English characters and if it's using a non-Latin alphabet
            # This helps to filter out topics that might cause encoding issues
            is_non_latin = bool(re.search(r'[^\x00-\x7F\u00C0-\u00FF]', keyword))
            
            if is_non_latin and region.upper() != 'US':
                # For non-Latin alphabet, replace with transliterated version or skip if configured to do so
                if skip_non_latin:
                    process_logger.info(f"Skipping non-Latin alphabet topic: {keyword} (use SKIP_NON_LATIN_TOPICS=False to include)")
                    continue
                else:
                    # Try to transliterate if it's a non-Latin script
                    try:
                        import unidecode
                        transliterated = unidecode.unidecode(keyword)
                        if transliterated != keyword:
                            process_logger.info(f"Transliterating non-Latin topic: '{keyword}' -> '{transliterated}'")
                            keyword = transliterated
                    except ImportError:
                        # If unidecode is not available, just use the original keyword
                        pass
            
            # Ensure keyword length is reasonable to avoid excessively long keywords that might be errors
            if len(keyword) > 100:
                process_logger.info(f"Truncating excessively long keyword ({len(keyword)} chars)")
                keyword = keyword[:100]
                
            # Convert related keywords to JSON
            related_keywords_json = json.dumps(related_keywords) if related_keywords else None

            # Check if this topic already exists from recent fetch (avoid duplicates)
            existing_topic = TrendingTopic.objects.filter(
                keyword=keyword,
                timestamp__gte=timezone.now() - timedelta(hours=4)
            ).first()
            
            if existing_topic:
                # Update the existing topic with fresh data
                existing_topic.rank = rank
                existing_topic.search_volume = traffic
                existing_topic.timestamp = timezone.now()
                if related_keywords_json:
                    existing_topic.related_keywords = related_keywords_json
                existing_topic.save()
                
                topic = existing_topic
                process_logger.info(f"Updated existing topic: {keyword}")
            else:
                # Create a new trending topic
                try:
                    topic = TrendingTopic.objects.create(
                        keyword=keyword,
                        rank=rank,
                        location=region,
                        search_volume=traffic,
                        category=category_names,
                        related_keywords=related_keywords_json
                    )
                    process_logger.info(f"Created new topic: {keyword}")
                except Exception as e:
                    process_logger.error(f"Error creating topic: {str(e)}")
                    # Try again with a sanitized keyword
                    safe_keyword = re.sub(r'[^\w\s-]', '', keyword)
                    if safe_keyword != keyword:
                        try:
                            topic = TrendingTopic.objects.create(
                                keyword=safe_keyword,
                                rank=rank,
                                location=region,
                                search_volume=traffic,
                                category=category_names,
                                related_keywords=related_keywords_json
                            )
                            process_logger.info(f"Created topic with sanitized keyword: {safe_keyword}")
                        except Exception as e2:
                            process_logger.error(f"Failed to create topic even with sanitized keyword: {str(e2)}")
                            continue
                    else:
                        continue

            count += 1
            stored_topics.append({
                "id": topic.id,
                "keyword": keyword,
                "rank": rank,
                "traffic": traffic,
                "categories": category_names
            })
            
            # Limit to exactly 10 topics
            if count >= 10:
                break

        process_logger.complete_step(step3, "STORE_TOPICS", {
            "topics_count": count,
            "topics": stored_topics[:5] if stored_topics else []  # Show top 5 for brevity
        })

        # If we didn't get enough topics, add some fallback evergreen topics
        if count < 5:
            process_logger.info(f"Only found {count} topics, adding fallback evergreen topics")
            fallback_count = add_fallback_topics(process_logger, 10 - count)
            process_logger.info(f"Added {fallback_count} fallback topics")
            count += fallback_count

        process_logger.success(f"Successfully fetched {count} trending topics for the past 4 hours")
        process_logger.end_process("COMPLETED", {
            "topics_count": count, 
            "region": region,
            "search_method": search_method
        })
        return f"Successfully fetched {count} trending topics for the past 4 hours using {search_method}"

    except Exception as e:
        error_msg = f"Error fetching trending topics: {str(e)}"
        process_logger.error(error_msg)
        process_logger.end_process("FAILED", {"error": str(e)})
        
        # If the fetch fails, add fallback topics to ensure the system keeps running
        fallback_count = add_fallback_topics(process_logger, 10)
        if fallback_count > 0:
            return f"Error fetching trends, but added {fallback_count} fallback topics"
        
        return f"Error: {str(e)}"

def add_fallback_topics(process_logger, count=5):
    """
    Add fallback evergreen topics when trend fetching fails or returns insufficient results
    
    Args:
        process_logger: Logger instance
        count: Number of fallback topics to add
    
    Returns:
        int: Number of fallback topics added
    """
    fallback_topics = [
        {"keyword": "Digital Marketing Trends", "category": "Business"},
        {"keyword": "AI Tools for Productivity", "category": "Technology"},
        {"keyword": "Health and Wellness Tips", "category": "Health"},
        {"keyword": "Personal Finance Strategies", "category": "Finance"},
        {"keyword": "Work-Life Balance", "category": "Lifestyle"},
        {"keyword": "Home Office Setup Ideas", "category": "Home"},
        {"keyword": "SEO Best Practices", "category": "Marketing"},
        {"keyword": "Remote Work Tools", "category": "Business"},
        {"keyword": "Mental Health Tips", "category": "Health"},
        {"keyword": "Content Creation Strategies", "category": "Marketing"},
        {"keyword": "Sustainable Living", "category": "Lifestyle"},
        {"keyword": "Fitness for Beginners", "category": "Health"},
        {"keyword": "Email Marketing Tips", "category": "Marketing"},
        {"keyword": "Cooking Basics", "category": "Food"},
        {"keyword": "Career Development", "category": "Business"}
    ]
    
    # Shuffle the list to get different topics each time
    import random
    random.shuffle(fallback_topics)
    
    # Take only the number of topics we need
    topics_to_add = fallback_topics[:count]
    
    added_count = 0
    for rank, topic in enumerate(topics_to_add, 1):
        # Check if this topic was used in the last 7 days to avoid repetition
        existing = TrendingTopic.objects.filter(
            keyword=topic["keyword"],
            timestamp__gte=timezone.now() - timedelta(days=7)
        ).exists()
        
        if not existing:
            try:
                TrendingTopic.objects.create(
                    keyword=topic["keyword"],
                    rank=rank,
                    location="global",
                    category=topic["category"],
                    is_fallback=True
                )
                process_logger.info(f"Added fallback topic: {topic['keyword']}")
                added_count += 1
            except Exception as e:
                process_logger.error(f"Error adding fallback topic: {str(e)}")
    
    return added_count


@shared_task
def process_trending_topics(limit=None):
    """
    Processes unprocessed trending topics by filtering and categorizing them
    
    Args:
        limit: Optional limit on the number of topics to process in this run
    """
    logger.info(f"Processing new trending topics{' (limited to ' + str(limit) + ')' if limit else ''}")
    
    # Get unprocessed topics
    topics = TrendingTopic.objects.filter(processed=False, filtered_out=False).order_by('-timestamp')
    
    if not topics.exists():
        logger.info("No unprocessed trending topics found")
        return "No unprocessed trending topics found"
    
    # Apply limit if specified
    if limit and limit > 0:
        topics = topics[:limit]
        logger.info(f"Limited processing to {limit} topics")
    
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
    
    Returns one of: 'evergreen', 'trend', 'comparison', 'local', or 'how_to'
    """
    keyword = keyword.lower()
    
    # Template 5: How-to guide
    if keyword.startswith('how to') or 'step by step' in keyword or 'guide' in keyword or 'tutorial' in keyword:
        return 'how_to'
    
    # Check for explicit comparison markers first
    if 'vs' in keyword or 'versus' in keyword or 'comparison' in keyword or 'compared' in keyword:
        return 'comparison'
    
    # Template 4: Local SEO
    if (any(word in keyword for word in ['near me', 'local', 'city', 'state', 'region', 'country', 'restaurant', 'café', 'store', 'shop']) or
        'best places' in keyword or 
        'things to do in' in keyword or
        any(city in keyword.lower() for city in ['new york', 'chicago', 'london', 'tokyo', 'paris', 'berlin', 'sydney'])):
        return 'local'
    
    # Template 3: General Comparison/Review that doesn't use explicit comparison terms
    if 'best' in keyword or 'top' in keyword or 'review' in keyword or 'ranking' in keyword:
        return 'comparison'
    
    # Template 2: Trending content
    if any(word in keyword for word in ['breaking', 'news', 'announced', 'launches', 'update', 'released', 'latest']):
        return 'trend'
    
    # Template 1: Evergreen content (default for most other topics)
    if any(word in keyword for word in ['what is', 'guide to', 'understanding', 'complete', 'ultimate']):
        return 'evergreen'
    
    # Default to how_to if nothing else matches
    return 'how_to'


@shared_task
def generate_blog_for_topic(topic_id, template_type, engagement_score=50, fresh_content_strategy=None):
    """
    Generates a blog post for a specific trending topic and publishes it immediately
    """
    try:
        # Get the topic
        topic = TrendingTopic.objects.get(id=topic_id)
        logger.info(f"Generating blog for topic: {topic.keyword} using {template_type} template")
        
        # Ensure template_type is one of the allowed values
        allowed_templates = ['evergreen', 'trend', 'comparison', 'local', 'how_to']
        if template_type not in allowed_templates:
            logger.warning(f"Invalid template_type: {template_type}. Defaulting to 'how_to'")
            template_type = 'how_to'
        
        # Load related keywords if available
        related_keywords = None
        if topic.related_keywords:
            try:
                related_keywords = json.loads(topic.related_keywords)
                logger.info(f"Loaded {len(related_keywords)} related keywords for SEO optimization")
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse related keywords JSON for topic: {topic.keyword}")
        
        # Check if this is a duplicate topic that needs fresh content
        is_fresh_variant = False
        if fresh_content_strategy:
            logger.info(f"Using fresh content strategy: {fresh_content_strategy} for duplicate topic")
            is_fresh_variant = True
            
        # Generate the SEO-optimized prompt for structured JSON content
        prompt = generate_json_seo_prompt(topic.keyword, template_type, related_keywords, fresh_content_strategy)
        
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
        
        # If the content includes a template_type field, validate it matches our allowed templates
        if 'template_type' in content_data:
            suggested_template = content_data.get('template_type')
            if suggested_template in allowed_templates:
                used_template_type = suggested_template
                logger.info(f"Using suggested template type from content: {used_template_type}")
            else:
                used_template_type = template_type
                logger.info(f"Ignoring invalid suggested template: {suggested_template}, using original: {template_type}")
        else:
            used_template_type = template_type
        
        logger.info(f"Using template type: {used_template_type} (original suggestion: {template_type})")
        
        # Create formatted HTML content from JSON structure
        title = content_data.get('title', topic.keyword)
        meta_description = content_data.get('meta_description', f"Learn about {topic.keyword}")
        html_content = format_json_to_html(content_data, used_template_type)
        
        # Create blog post
        blog_post = BlogPost(
            title=title,
            content=html_content,
            meta_description=meta_description,
            template_type=used_template_type,
            trending_topic=topic,
            status='published',  # Publish immediately
            published_at=timezone.now(),  # Set publication time to now
            is_fresh_variant=is_fresh_variant,
            fresh_approach=fresh_content_strategy
        )
        blog_post.save()
        
        # Generate a slug from the title if not already set
        if not blog_post.slug:
            slug = title.lower()
            # Replace spaces with dashes and remove special characters
            slug = re.sub(r'[^\w\s-]', '', slug)
            slug = re.sub(r'[\s-]+', '-', slug)
            blog_post.slug = slug
            blog_post.save()
        
        # Mark the topic as processed
        topic.processed = True
        topic.save()
        
        # Update or create a TopicFreshnessLog entry if this is a fresh variant
        if is_fresh_variant:
            # Update or create a log for this topic
            log, created = TopicFreshnessLog.objects.get_or_create(
                keyword=topic.keyword.lower(),
                defaults={
                    'occurrence_count': 1,
                    'strategy_applied': fresh_content_strategy or 'different_angle',
                    'strategy_notes': f"Created fresh variant using template: {used_template_type}"
                }
            )
            
            if not created:
                # Update existing log
                log.increment_occurrence()
                log.strategy_applied = fresh_content_strategy or 'different_angle'
                log.strategy_notes = f"{log.strategy_notes}\nCreated fresh variant using template: {used_template_type} on {timezone.now().strftime('%Y-%m-%d %H:%M')}"
                log.save()
                
            # Add this blog post to the log's related posts
            log.related_blog_posts.add(blog_post)
            
            logger.info(f"Updated TopicFreshnessLog for '{topic.keyword}' with strategy: {fresh_content_strategy}")
        
        logger.info(f"Successfully created and published blog post: {blog_post.title} using template {used_template_type}")
        return f"Successfully created and published blog post: {blog_post.title}"
        
    except TrendingTopic.DoesNotExist:
        logger.error(f"Topic with ID {topic_id} not found")
        return f"Error: Topic with ID {topic_id} not found"
    except Exception as e:
        logger.error(f"Error generating blog for topic ID {topic_id}: {e}")
        return f"Error: {str(e)}"


def generate_json_seo_prompt(keyword, template_type=None, related_keywords=None, fresh_content_strategy=None):
    """
    Generates an SEO-optimized prompt for JSON content generation
    
    Args:
        keyword: The keyword to generate content for
        template_type: Optional suggested template type (Gemini may override)
        related_keywords: Optional list of related keywords for SEO optimization
        fresh_content_strategy: Optional fresh content strategy for duplicate topics
        
    Returns:
        str: The generated prompt
    """
    if not template_type:
        template_type = predict_template_type(keyword)
        
    # Create base prompt
    prompt = f"""Create a comprehensive, SEO-optimized blog post about "{keyword}" using the {template_type} template.

Your content must be structured as valid JSON following this exact format:

```json
{{
  "title": "SEO-optimized title with '{keyword}' included",
  "meta_description": "Engaging meta description under 160 characters with keyword",
  "template_type": "{template_type}",
  "introduction": "2-3 paragraph introduction that hooks the reader",
  "table_of_contents": ["Section 1", "Section 2", "Section 3"],
  "sections": [
    {{
      "heading": "H2 Section Heading",
      "content": "Detailed, valuable content for this section",
      "subsections": [
        {{
          "heading": "H3 Subsection Heading",
          "content": "Content for this subsection"
        }}
      ]
    }}
  ],
  "conclusion": "Summary paragraph with call to action",
  "faq": [
    {{
      "question": "Frequently asked question about {keyword}?",
      "answer": "Comprehensive answer (at least 100 words)"
    }}
  ]
}}
```

IMPORTANT REQUIREMENTS:
1. Create at least 5 detailed sections with H2 headings
2. Include subsections with H3 headings where appropriate
3. Write comprehensive, valuable content (at least 2000 words total)
4. Include relevant statistics, examples, and actionable advice
5. Optimize naturally for the keyword '{keyword}'
6. Create at least 5 relevant FAQ items with thorough answers
7. Use a conversational but authoritative tone
8. Ensure all JSON is properly formatted with no errors
9. Include the template_type field with value "{template_type}" (must be one of: 'evergreen', 'trend', 'comparison', 'local', 'how_to')
"""
    
    # Add fresh content instructions if specified
    if fresh_content_strategy:
        if fresh_content_strategy == 'different_angle':
            fresh_prompt = f"""
CRITICAL INSTRUCTION: This topic has been covered before, so you MUST create FRESH CONTENT with a COMPLETELY DIFFERENT ANGLE:

1. Focus on a different aspect of '{keyword}' than what's typically covered
2. Use a unique structure or format that differentiates this content
3. Target a different audience segment or intent (e.g., beginners vs experts)
4. Include the latest data, statistics, quotes, or trends that weren't available before
5. Provide a unique perspective or contrarian viewpoint on the topic
6. Focus on novel examples, case studies, or applications that haven't been widely discussed
7. If appropriate, use a different tone or style (e.g., more casual, more technical, more storytelling)

Your content MUST feel completely fresh and provide NEW VALUE even to readers who have read other content on this topic.
"""
        elif fresh_content_strategy == 'new_template':
            fresh_prompt = f"""
CRITICAL INSTRUCTION: This topic has been covered before using a different template, so you MUST create FRESH CONTENT with a COMPLETELY DIFFERENT STRUCTURE:

1. Utilize the full potential of the {template_type} template format to present information differently
2. Organize information in a different hierarchy or order than typical content on this topic
3. Include unique sections that wouldn't appear in other template types
4. Use different content elements (lists, tables, quotes, examples) than what's commonly used
5. Focus on answering different user questions or serving different search intent

Your content MUST feel structurally distinct from other content on this topic.
"""
        elif fresh_content_strategy == 'latest_data':
            fresh_prompt = f"""
CRITICAL INSTRUCTION: This topic has been covered before, so you MUST create FRESH CONTENT with the LATEST DATA AND TRENDS:

1. Focus heavily on the most recent statistics, studies, and data about '{keyword}'
2. Highlight what has changed or evolved in this topic area recently
3. Include references to current events, news, or developments related to the topic
4. Compare current trends with previous approaches or understanding
5. Discuss future predictions or where this topic is heading next

Your content MUST feel timely and current, providing value through up-to-date information.
"""
        else:
            # Default fresh content instructions
            fresh_prompt = f"""
CRITICAL INSTRUCTION: This topic has been covered before, so you MUST create FRESH CONTENT that offers new value:

1. Take a different approach to '{keyword}' than what's typically covered
2. Include unique insights, examples, or perspectives not commonly found
3. Organize information in a way that feels fresh and engaging
4. Focus on providing value that differentiates this content from existing resources

Your content MUST stand out from other blog posts on this topic.
"""
        
        # Add the fresh content instructions to the prompt
        prompt = f"{prompt}\n\n{fresh_prompt}"
    
    # Add related keywords if available
    if related_keywords and isinstance(related_keywords, list):
        related_keywords_str = ", ".join(related_keywords[:10])  # Limit to 10 keywords
        prompt += f"\n\nAdditionally, incorporate these related keywords naturally throughout the content: {related_keywords_str}"
    
    # Add template-specific instructions
    if template_type == 'how_to':
        prompt += """
For the how-to guide template, include:
- A clear step-by-step process with numbered steps
- Required tools or prerequisites
- Common challenges and solutions
- Tips for success
- Expected outcomes or results
"""
    elif template_type == 'trend':
        prompt += """
For the trending topic template, include:
- Recent developments and their context
- Expert quotes or perspectives (real or hypothetical)
- Impact analysis and current relevance
- Future implications
- Why this trend matters to the reader
"""
    elif template_type == 'comparison':
        prompt += """
For the comparison/review template, include:
- Clear pros and cons
- Detailed evaluation criteria
- Performance metrics or ratings
- Comparisons to alternatives
- Final verdict and recommendations
"""
    elif template_type == 'local':
        prompt += """
For the local SEO template, include:
- Location-specific information and relevance
- Local statistics or data when available
- Regional context and application
- Local examples or case studies
- Location-based call to action
"""
    elif template_type == 'evergreen':
        prompt += """
For the evergreen pillar content template, include:
- Comprehensive coverage of the topic
- Foundational concepts and definitions
- Best practices and industry standards
- Common misconceptions
- Future-proof information that won't quickly become outdated
"""
    
    return prompt


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
        
        # Validate template_type - ensure it's one of the allowed values
        allowed_templates = ['how_to', 'listicle', 'news', 'review', 'opinion']
        if 'template_type' in data:
            if data['template_type'] not in allowed_templates:
                logger.warning(f"Invalid template_type: {data['template_type']}. Defaulting to {template_type}")
                data['template_type'] = template_type
        else:
            logger.warning(f"Missing template_type in JSON content. Defaulting to {template_type}")
            data['template_type'] = template_type
        
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
        
        # Add featured image if present
        if 'featured_image' in content_data and content_data['featured_image']:
            featured_image = content_data['featured_image']
            alt_text = featured_image.get('alt_text', title).encode('utf-8', 'ignore').decode('utf-8')
            search_terms = featured_image.get('search_terms', title).encode('utf-8', 'ignore').decode('utf-8')
            
            # Create placeholder image tag with data attributes for frontend processing
            html += f'<div class="featured-image-container">\n'
            html += f'  <img class="unsplash-image" data-search-terms="{search_terms}" alt="{alt_text}" data-placeholder="featured" />\n'
            html += f'  <noscript>Featured image: {alt_text}</noscript>\n'
            html += f'</div>\n\n'
        
        # Add template-specific styling and structure
        if template_type == 'evergreen':
            # Add a table of contents for evergreen content
            toc_items = content_data.get('table_of_contents', [])
            if toc_items:
                html += '<div class="table-of-contents-container">\n'
                html += '<h2>Table of Contents</h2>\n'
                html += '<ul class="table-of-contents">\n'
                for item in toc_items:
                    item_text = item.encode('utf-8', 'ignore').decode('utf-8')
                    # Create anchor link from item text
                    anchor = item_text.lower().replace(' ', '-').replace(',', '').replace('.', '')
                    html += f'<li><a href="#{anchor}">{item_text}</a></li>\n'
                html += '</ul>\n'
                html += '</div>\n\n'
                
        elif template_type == 'how_to':
            # Add a "What You'll Need" section if it's in the data
            if 'prerequisites' in content_data:
                html += '<div class="prerequisites-container">\n'
                html += '<h2>What You\'ll Need</h2>\n'
                html += '<ul class="prerequisites-list">\n'
                for item in content_data.get('prerequisites', []):
                    item_text = item.encode('utf-8', 'ignore').decode('utf-8')
                    html += f'<li>{item_text}</li>\n'
                html += '</ul>\n'
                html += '</div>\n\n'
                
        elif template_type == 'comparison':
            # Add a comparison table if it's in the data
            if 'comparison_table' in content_data:
                html += '<div class="comparison-table-container">\n'
                html += '<h2>Comparison At A Glance</h2>\n'
                html += '<table class="comparison-table">\n'
                
                # Add table header
                html += '<thead><tr>\n'
                for header in content_data['comparison_table'].get('headers', []):
                    header_text = header.encode('utf-8', 'ignore').decode('utf-8')
                    html += f'<th>{header_text}</th>\n'
                html += '</tr></thead>\n'
                
                # Add table body
                html += '<tbody>\n'
                for row in content_data['comparison_table'].get('rows', []):
                    html += '<tr>\n'
                    for cell in row:
                        cell_text = cell.encode('utf-8', 'ignore').decode('utf-8')
                        html += f'<td>{cell_text}</td>\n'
                    html += '</tr>\n'
                html += '</tbody>\n'
                html += '</table>\n'
                html += '</div>\n\n'
                
        elif template_type == 'local':
            # Add a local information box if available
            if 'local_info' in content_data:
                local_info = content_data['local_info']
                html += '<div class="local-info-container">\n'
                html += f'<h2>Local Information: {local_info.get("location", "")}</h2>\n'
                html += '<div class="local-info-content">\n'
                html += f'<p>{local_info.get("description", "")}</p>\n'
                html += '</div>\n'
                html += '</div>\n\n'
        
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
                
                # Add section image if present
                if 'image' in section and section['image']:
                    html = add_section_image(html, section['image'])
            
            elif section_type == 'conclusion':
                # Conclusion section
                h2 = section.get('h2', 'Conclusion').encode('utf-8', 'ignore').decode('utf-8')
                content_text = section.get('content', '').encode('utf-8', 'ignore').decode('utf-8')
                html += f"<h2>{h2}</h2>\n"
                html += f"<p>{content_text}</p>\n\n"
                
                # Add section image if present
                if 'image' in section and section['image']:
                    html = add_section_image(html, section['image'])
            
            else:
                # Regular section
                if 'h2' in section:
                    h2 = section.get('h2', '').encode('utf-8', 'ignore').decode('utf-8')
                    # For evergreen content, add anchors for TOC
                    if template_type == 'evergreen':
                        anchor = h2.lower().replace(' ', '-').replace(',', '').replace('.', '')
                        html += f'<h2 id="{anchor}">{h2}</h2>\n'
                    else:
                        html += f"<h2>{h2}</h2>\n"
                
                # Add section image with appropriate placement
                if 'image' in section and section['image']:
                    placement = section['image'].get('placement', 'center')
                    if placement == 'left':
                        html = add_section_image(html, section['image'], "float-left mr-4 mb-4")
                    elif placement == 'right':
                        html = add_section_image(html, section['image'], "float-right ml-4 mb-4")
                    else:  # center
                        html = add_section_image(html, section['image'], "mx-auto my-4 block")
                
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
                    
                    # Add subsection image if present
                    if 'image' in subsection and subsection['image']:
                        placement = subsection['image'].get('placement', 'center')
                        if placement == 'left':
                            html = add_section_image(html, subsection['image'], "float-left mr-4 mb-4")
                        elif placement == 'right':
                            html = add_section_image(html, subsection['image'], "float-right ml-4 mb-4")
                        else:  # center
                            html = add_section_image(html, subsection['image'], "mx-auto my-4 block")
                    
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
        
        # Add call to action for all templates
        if 'call_to_action' in content_data:
            cta = content_data['call_to_action']
            cta_text = cta.get('text', 'Learn More').encode('utf-8', 'ignore').decode('utf-8')
            cta_url = cta.get('url', '#').encode('utf-8', 'ignore').decode('utf-8')
            
            html += f'<div class="call-to-action-container">\n'
            html += f'<a href="{cta_url}" class="cta-button">{cta_text}</a>\n'
            html += f'</div>\n\n'
        
        # Append these CSS styles to the existing style block in format_json_to_html
        html += """
<style>
.float-left {
    float: left;
    margin-right: 1.5rem;
    margin-bottom: 1rem;
    max-width: 40%;
}
.float-right {
    float: right;
    margin-left: 1.5rem;
    margin-bottom: 1rem;
    max-width: 40%;
}
.mx-auto {
    margin-left: auto;
    margin-right: auto;
}
.my-4 {
    margin-top: 1rem;
    margin-bottom: 1rem;
}
.block {
    display: block;
}
.featured-image-container {
    margin-bottom: 2rem;
    text-align: center;
}
.featured-image-container img {
    max-width: 100%;
    height: auto;
    border-radius: 0.5rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}
.unsplash-image {
    min-height: 200px;
    background-color: #f3f4f6;
    border: 1px solid #e5e7eb;
    display: block;
}
.table-of-contents-container {
    background-color: #f9f9f9;
    padding: 1.5rem;
    margin-bottom: 2rem;
    border-radius: 0.5rem;
    border: 1px solid #e5e7eb;
}
.table-of-contents {
    list-style-type: none;
    padding-left: 1rem;
}
.table-of-contents li {
    margin-bottom: 0.5rem;
}
.table-of-contents a {
    text-decoration: none;
    color: #4f46e5;
}
.table-of-contents a:hover {
    text-decoration: underline;
}
.comparison-table-container {
    margin: 2rem 0;
    overflow-x: auto;
}
.comparison-table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.5rem 0;
}
.comparison-table th, .comparison-table td {
    border: 1px solid #e5e7eb;
    padding: 0.75rem;
    text-align: left;
}
.comparison-table th {
    background-color: #f3f4f6;
    font-weight: bold;
}
.local-info-container {
    background-color: #f0f7ff;
    padding: 1.5rem;
    margin-bottom: 2rem;
    border-radius: 0.5rem;
    border: 1px solid #cce5ff;
}
.prerequisites-container {
    background-color: #f7f7f7;
    padding: 1.5rem;
    margin-bottom: 2rem;
    border-radius: 0.5rem;
    border: 1px solid #e5e7eb;
}
.faq-section {
    margin-top: 2rem;
}
.faq-item {
    margin-bottom: 1.5rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
}
.faq-item h3 {
    font-weight: bold;
    margin-bottom: 0.75rem;
}
.call-to-action-container {
    margin: 2rem 0;
    text-align: center;
}
.cta-button {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    background-color: #4f46e5;
    color: white;
    font-weight: bold;
    border-radius: 0.375rem;
    text-decoration: none;
    transition: background-color 0.2s;
}
.cta-button:hover {
    background-color: #4338ca;
}
</style>
"""
        
        return html
    except Exception as e:
        logger.error(f"Error formatting JSON to HTML: {e}")
        return ""


def add_section_image(html, image_data, css_classes=""):
    """Helper function to add an image to the HTML content"""
    try:
        alt_text = image_data.get('alt_text', '').encode('utf-8', 'ignore').decode('utf-8')
        search_terms = image_data.get('search_terms', '').encode('utf-8', 'ignore').decode('utf-8')
        
        # Create image tag with data attributes for frontend processing
        image_html = f'<div class="section-image-container">\n'
        image_html += f'  <img class="unsplash-image {css_classes}" data-search-terms="{search_terms}" alt="{alt_text}" data-placeholder="section" />\n'
        image_html += f'  <noscript>Image: {alt_text}</noscript>\n'
        image_html += f'</div>\n\n'
        
        return html + image_html
    except Exception as e:
        logger.error(f"Error adding section image: {e}")
        return html


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
def generate_blog_content(limit_lookback=24):
    """
    Main task that orchestrates the blog content generation pipeline
    Runs every 5 minutes to select a trending topic and generate content
    
    Args:
        limit_lookback: How many hours back to look for unprocessed topics (default: 24)
    """
    logger.info(f"Starting blog content generation pipeline (lookback: {limit_lookback} hours)")
    
    try:
        # Get the best trending topics
        trending_topics = TrendingTopic.objects.filter(
            processed=False,
            filtered_out=False,
            timestamp__gte=timezone.now() - timedelta(hours=limit_lookback)
        ).order_by('-rank')
        
        if not trending_topics.exists():
            logger.info("No unprocessed trending topics available, fetching new ones")
            fetch_trending_topics.delay()
            return "No unprocessed trending topics available, fetching new ones"
        
        # Check for duplicate trending topics (same topics appearing in consecutive runs)
        # For 5-minute runs, we'll look back 30 minutes (6 cycles) for duplicates
        recent_hours = min(1, limit_lookback)  # At most 1 hour lookback
        topics_last_period = TrendingTopic.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=recent_hours),
            processed=True
        ).order_by('-timestamp')
        
        # Extract unique keywords from recent topics
        recent_keywords = list(set([t.keyword.lower() for t in topics_last_period]))
        
        # Track duplicates and their occurrence counts
        duplicate_topics = {}
        for keyword in recent_keywords:
            # Count how many times this topic appeared in the recent period
            count = topics_last_period.filter(keyword__iexact=keyword).count()
            if count >= 2:  # Topic appeared in 2 or more consecutive runs
                duplicate_topics[keyword] = count
                logger.info(f"Detected duplicate trending topic: {keyword} (appeared {count} times in last {recent_hours} hours)")
        
        # If we have duplicates, check if blogs were already created for these topics recently
        fresh_content_strategy = None
        if duplicate_topics:
            logger.info(f"Found {len(duplicate_topics)} topics that have been trending for consecutive runs")
            
            # Check for blogs created in the last 2 hours for these duplicate topics
            # For 5-minute runs, we're more aggressive with the recency check
            recent_blog_hours = 2
            topics_with_recent_blogs = []
            
            for keyword in duplicate_topics.keys():
                # Find blogs for this topic in the recent hours
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
                logger.info(f"Found {len(topics_with_recent_blogs)} topics with recent blogs in the last {recent_blog_hours} hours")
                
                # We need to handle this situation specially
                # 1. Try to select a different topic that hasn't been covered recently
                # 2. If we must use a duplicate topic, generate with a fresh angle
                
                # Filter out topics that already have recent blogs
                recent_topic_keywords = [t["keyword"].lower() for t in topics_with_recent_blogs]
                alternative_topics = trending_topics.exclude(keyword__iregex=r'(' + '|'.join(recent_topic_keywords) + ')')
                
                if alternative_topics.exists():
                    # We found alternative topics that haven't been covered recently
                    logger.info(f"Found {alternative_topics.count()} alternative topics that haven't been covered recently")
                    selected_topic = alternative_topics.first()
                else:
                    # No alternative topics, must use a duplicate but with fresh content
                    logger.info("No alternative topics found, will create fresh content for a duplicate topic")
                    selected_topic = trending_topics.first()
                    fresh_content_strategy = "different_angle"
                    
                    # Log information about the duplicate topic we're using
                    for topic_data in topics_with_recent_blogs:
                        if topic_data["keyword"].lower() == selected_topic.keyword.lower():
                            logger.info(f"Will create fresh content for '{selected_topic.keyword}' with different angle")
                            logger.info(f"Previous templates used: {topic_data['blog_templates']}")
                            break
            else:
                # Topics are duplicates but no blogs have been created yet
                selected_topic = trending_topics.first()
        else:
            # No duplicate trending topics, select the top trending topic as usual
            selected_topic = trending_topics.first()
        
        # Predict the best template type for this topic
        template_type = predict_template_type(selected_topic.keyword)
        
        # If we're using a fresh content strategy for a duplicate topic,
        # avoid using the same template as before
        if fresh_content_strategy == "different_angle":
            # Get previously used templates for this topic
            for topic_data in topics_with_recent_blogs:
                if topic_data["keyword"].lower() == selected_topic.keyword.lower():
                    used_templates = topic_data["blog_templates"]
                    # Choose a different template type
                    template_options = ['how_to', 'listicle', 'news', 'review', 'opinion']
                    available_templates = [t for t in template_options if t not in used_templates]
                    if available_templates:
                        template_type = available_templates[0]
                    logger.info(f"Selected different template type: {template_type} (previously used: {used_templates})")
                    break
        
        # Generate and publish a blog post
        logger.info(f"Generating blog for topic: {selected_topic.keyword} with template: {template_type}")
        
        if fresh_content_strategy:
            # Use our customized prompt with instructions for fresh content
            from .blog_ai import GeminiChatbot
            
            # Create prompt with fresh content instructions
            fresh_content_instructions = """
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
            # Generate content with custom instructions for freshness
            logger.info("Using fresh content strategy with different angle")
            
            # Add this topic to a log of duplicate topics for analysis
            with open("duplicate_topics_log.json", "a") as f:
                log_entry = {
                    "timestamp": timezone.now().isoformat(),
                    "topic": selected_topic.keyword,
                    "strategy": fresh_content_strategy,
                    "template": template_type
                }
                f.write(json.dumps(log_entry) + "\n")
        
        # Mark this topic as processed
        selected_topic.processed = True
        selected_topic.save()
        
        # Generate the blog
        generate_blog_for_topic.delay(selected_topic.id, template_type, engagement_score=calculate_engagement_potential(selected_topic.keyword), fresh_content_strategy=fresh_content_strategy)
        
        return f"Blog generation started for topic: {selected_topic.keyword}"
        
    except Exception as e:
        logger.error(f"Error in blog content generation pipeline: {e}")
        return f"Error: {str(e)}"


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
def create_and_publish_blog(keyword, template_type=None, publish_immediately=True, related_keywords=None):
    """
    Creates and publishes a blog post immediately for a given keyword
    
    Args:
        keyword: The main keyword for the blog post
        template_type: Optional template type to use
        publish_immediately: Whether to publish immediately (default True)
        related_keywords: Optional list of related keywords
    """
    # Create a process logger for this task
    process_logger = BlogProcessLogger()
    process_logger.info(f"Starting blog creation process for: {keyword}")
    
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
        
        # Ensure template_type is one of the allowed values
        allowed_templates = ['evergreen', 'trend', 'comparison', 'local', 'how_to']
        if template_type not in allowed_templates:
            process_logger.warning(f"Invalid template_type: {template_type}. Defaulting to 'how_to'")
            template_type = 'how_to'
        
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
        
        # Validate and use the template type from the JSON response if it's valid
        if 'template_type' in content_data:
            suggested_template = content_data.get('template_type')
            if suggested_template in allowed_templates:
                used_template_type = suggested_template
                process_logger.info(f"Using suggested template type from content: {used_template_type}")
            else:
                used_template_type = template_type
                process_logger.info(f"Ignoring invalid suggested template: {suggested_template}, using original: {template_type}")
        else:
            used_template_type = template_type
        
        process_logger.info(f"Using template type: {used_template_type} (original suggestion: {template_type})")
        
        process_logger.complete_step(step3, "GENERATE_CONTENT", {
            "title": content_data.get('title'),
            "sections_count": len(content_data.get("table_of_contents", [])),
            "template_type": used_template_type
        })
        
        # Step 4: Create blog post
        step4 = process_logger.step("CREATE_BLOG_POST", "Creating and publishing blog post")
        
        # Create formatted HTML content from JSON structure
        title = content_data.get('title', keyword)
        meta_description = content_data.get('meta_description', f"Learn about {keyword}")
        html_content = format_json_to_html(content_data, used_template_type)
        
        process_logger.info("HTML content formatted", {"html_length": len(html_content)})
        
        # Create blog post - always published immediately
        blog_post = BlogPost(
            title=title,
            content=html_content,
            meta_description=meta_description,
            template_type=used_template_type,
            trending_topic=topic,
            status='published',
            published_at=timezone.now()
        )
        blog_post.save()
        
        process_logger.info(f"Successfully created blog post: {blog_post.title} using template {used_template_type}")
        
        # Generate a slug from the title if not already set
        if not blog_post.slug:
            slug = title.lower()
            # Replace spaces with dashes and remove special characters
            slug = re.sub(r'[^\w\s-]', '', slug)
            slug = re.sub(r'[\s-]+', '-', slug)
            blog_post.slug = slug
            blog_post.save()
        
        process_logger.complete_step(step4, "CREATE_BLOG_POST", {
            "blog_id": str(blog_post.id),
            "blog_title": blog_post.title,
            "blog_status": blog_post.status,
            "blog_url": blog_post.slug,
            "template_type": used_template_type
        })
        
        process_logger.success(f"Successfully published blog post: {blog_post.title}")
        process_logger.end_process("COMPLETED", {
            "blog_id": str(blog_post.id),
            "blog_title": blog_post.title,
            "topic": keyword,
            "template_type": used_template_type,
            "status": "published"
        })
        
        return f"Successfully created and published blog post: {blog_post.title}"
        
    except Exception as e:
        error_msg = f"Error creating blog post: {str(e)}"
        process_logger.error(error_msg)
        process_logger.end_process("FAILED", {"error": str(e)})
        return error_msg


@shared_task
def ensure_trending_topics_available():
    """
    Ensures there are always trending topics available for blog creation
    by adding fallback topics if needed. This prevents the blog automation
    pipeline from failing when SerpAPI doesn't return any topics.
    """
    logger.info("Checking if we need to add fallback trending topics")
    
    # Check if we have any unprocessed topics from the last 4 hours
    recent_topics = TrendingTopic.objects.filter(
        timestamp__gte=timezone.now() - timedelta(hours=4),
        processed=False,
        filtered_out=False
    ).count()
    
    if recent_topics == 0:
        logger.info("No recent trending topics available. Adding fallback topics.")
        
        # List of evergreen topics that always work well for blogs
        fallback_topics = [
            {"keyword": "Digital Marketing Trends", "category": "Business"},
            {"keyword": "AI Tools for Productivity", "category": "Technology"},
            {"keyword": "Health and Wellness Tips", "category": "Health"},
            {"keyword": "Personal Finance Strategies", "category": "Finance"},
            {"keyword": "Work-Life Balance", "category": "Lifestyle"},
            {"keyword": "Home Office Setup Ideas", "category": "Home"},
            {"keyword": "SEO Best Practices", "category": "Marketing"},
            {"keyword": "Remote Work Tools", "category": "Business"},
            {"keyword": "Mental Health Tips", "category": "Health"},
            {"keyword": "Content Creation Strategies", "category": "Marketing"}
        ]
        
        # Add these topics to the database
        for rank, topic in enumerate(fallback_topics, 1):
            # Check if this topic already exists and was used in the last 7 days
            existing_recent = TrendingTopic.objects.filter(
                keyword=topic["keyword"],
                timestamp__gte=timezone.now() - timedelta(days=7)
            ).exists()
            
            if not existing_recent:
                TrendingTopic.objects.create(
                    keyword=topic["keyword"],
                    rank=rank,
                    location="global",
                    category=topic["category"],
                    is_fallback=True
                )
                logger.info(f"Added fallback topic: {topic['keyword']}")
        
        # Return the count of added topics
        return f"Added fallback trending topics"
    else:
        logger.info(f"Found {recent_topics} recent unprocessed topics. No need for fallback topics.")
        return f"Found {recent_topics} existing topics, no fallback needed"


@shared_task
def update_freshness_metrics():
    """
    Updates the TopicFreshnessLog with performance metrics based on blog posts
    This task implements the reinforcement learning logic for content freshness
    """
    logger.info("Updating topic freshness metrics for reinforcement learning")
    
    try:
        # Get all topics that have multiple occurrences (potential duplicates)
        from .models import TopicFreshnessLog, BlogPost
        from django.db.models import Avg, Count, F, Q
        
        # Get logs that have multiple occurrences
        duplicate_logs = TopicFreshnessLog.objects.filter(
            occurrence_count__gte=2,  # Topics that appeared multiple times
            strategy_applied__in=['different_angle', 'new_template', 'latest_data', 'audience_shift']  # Only where a freshness strategy was applied
        )
        
        logger.info(f"Found {duplicate_logs.count()} topics with multiple occurrences and freshness strategies")
        
        metrics_updated = 0
        
        for log in duplicate_logs:
            # Get the related blog posts
            related_posts = log.related_blog_posts.filter(is_fresh_variant=True)
            
            if not related_posts.exists():
                continue
                
            # Calculate performance metrics based on engagement
            avg_view_count = related_posts.aggregate(Avg('view_count'))['view_count__avg'] or 0
            avg_time_on_page = related_posts.aggregate(Avg('avg_time_on_page'))['avg_time_on_page__avg'] or 0
            
            # Get regular (non-fresh) posts for the same keyword for comparison
            regular_posts = BlogPost.objects.filter(
                trending_topic__keyword__iexact=log.keyword,
                is_fresh_variant=False
            )
            
            # If we have regular posts to compare against
            engagement_lift = 0
            if regular_posts.exists():
                regular_avg_views = regular_posts.aggregate(Avg('view_count'))['view_count__avg'] or 1
                regular_avg_time = regular_posts.aggregate(Avg('avg_time_on_page'))['avg_time_on_page__avg'] or 1
                
                # Calculate lift percentages (avoid division by zero)
                if regular_avg_views > 0:
                    view_lift = ((avg_view_count / regular_avg_views) - 1) * 100
                else:
                    view_lift = 0
                    
                if regular_avg_time > 0:
                    time_lift = ((avg_time_on_page / regular_avg_time) - 1) * 100
                else:
                    time_lift = 0
                    
                # Combined engagement lift
                engagement_lift = (view_lift + time_lift) / 2
            
            # Calculate success score (0-100)
            # This is a simplified approach - you could use a more sophisticated algorithm
            success_score = min(max(int(50 + engagement_lift / 2), 0), 100)
            
            # Estimate SEO impact (simplified)
            seo_impact = min(max(int(engagement_lift), -100), 100)
            
            # Update the log with these metrics
            log.update_performance_metrics(
                success_score=success_score,
                seo_impact=seo_impact,
                engagement_lift=engagement_lift
            )
            
            logger.info(f"Updated metrics for topic '{log.keyword}': Score={success_score}, SEO Impact={seo_impact}, Engagement Lift={engagement_lift:.2f}%")
            metrics_updated += 1
        
        # Now update the occurrence counts for trending topics
        from datetime import timedelta
        from django.utils import timezone
        from .models import TrendingTopic
        
        # Find topics that have appeared in the last 24 hours
        recent_topics = TrendingTopic.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=24)
        )
        
        # Group by keyword and count occurrences
        keyword_counts = {}
        for topic in recent_topics:
            keyword = topic.keyword.lower()
            if keyword in keyword_counts:
                keyword_counts[keyword] += 1
            else:
                keyword_counts[keyword] = 1
        
        # Update or create TopicFreshnessLog entries
        logs_created = 0
        logs_updated = 0
        
        for keyword, count in keyword_counts.items():
            if count >= 2:  # Only track keywords that appear multiple times
                # Check if a log already exists
                log, created = TopicFreshnessLog.objects.get_or_create(
                    keyword=keyword,
                    defaults={
                        'occurrence_count': count,
                        'strategy_applied': 'none'
                    }
                )
                
                if created:
                    logs_created += 1
                else:
                    # Update existing log
                    log.occurrence_count = max(log.occurrence_count, count)  # Keep the higher count
                    log.save()
                    logs_updated += 1
                
                # Link related blog posts if not already linked
                related_posts = BlogPost.objects.filter(
                    trending_topic__keyword__iexact=keyword
                )
                
                for post in related_posts:
                    if post not in log.related_blog_posts.all():
                        log.related_blog_posts.add(post)
        
        logger.info(f"Updated metrics for {metrics_updated} topic logs")
        logger.info(f"Created {logs_created} new topic freshness logs and updated {logs_updated} existing logs")
        
        return f"Updated freshness metrics for {metrics_updated} topics, created {logs_created} new logs"
        
    except Exception as e:
        logger.error(f"Error updating freshness metrics: {str(e)}")
        return f"Error: {str(e)}" 