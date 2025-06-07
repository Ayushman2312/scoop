#!/usr/bin/env python
"""Django views for interacting with the Gemini chatbot and blog display."""
import json
import logging
import time
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from blog.blog_ai import GeminiChatbot
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from celery import shared_task
from .models import BlogPost, AdPlacement, ContentPerformanceLog, TrendingTopic
from .tasks import update_blog_analytics, create_and_publish_blog
from django.utils import timezone
from datetime import timedelta
from .automation import BlogProcessLogger
from django.conf import settings
import os
from django.db import models

# Configure logging
logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)

# Homepage and blog list view
def index(request):
    """
    Display the homepage with latest blog posts
    """
    # Get filter parameters
    category = request.GET.get('category')
    sort = request.GET.get('sort', 'newest')
    
    # Base query for published posts
    posts_query = BlogPost.objects.filter(status='published')
    
    # Apply category filter if specified
    if category:
        posts_query = posts_query.filter(template_type=category)
    
    # Apply sorting
    if sort == 'popular':
        posts_query = posts_query.order_by('-view_count', '-published_at')
    elif sort == 'trending':
        # For trending, we consider recent views (could be refined with analytics data)
        posts_query = posts_query.filter(
            published_at__gte=timezone.now() - timedelta(days=7)
        ).order_by('-view_count', '-published_at')
    else:  # newest is default
        posts_query = posts_query.order_by('-published_at')
    
    # Get trending topics
    trending_topics = TrendingTopic.objects.filter(
        filtered_out=False
    ).order_by('-timestamp')[:4]
    
    # Paginate the results
    paginator = Paginator(posts_query, 9)  # Show 9 posts per page (3x3 grid)
    page = request.GET.get('page')
    
    try:
        posts = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page
        posts = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver last page
        posts = paginator.page(paginator.num_pages)
    
    # Get header ads
    header_ads = AdPlacement.objects.filter(placement='header', is_active=True)
    
    return render(request, 'blog/index.html', {
        'posts': posts,
        'trending_topics': trending_topics,
        'current_category': category,
        'current_sort': sort,
        'header_ads': header_ads,
    })

def blog_detail(request, slug):
    """
    Display a single blog post
    """
    # Get the blog post
    post = get_object_or_404(BlogPost, slug=slug, status='published')
    
    # Record the view
    post.view_count += 1
    post.save()
    
    # Log performance data asynchronously
    log_blog_performance.delay(post.id, request.META.get('HTTP_USER_AGENT', ''))
    
    # Check if post.content is in JSON format
    content_data = None
    try:
        # Attempt to parse the content as JSON
        content_data = json.loads(post.content)
        # If JSON has a template_type field, use that
        template_type = content_data.get('template_type', post.template_type)
    except (json.JSONDecodeError, TypeError):
        # If post.content is not valid JSON, use the default template type
        template_type = post.template_type
        # For non-JSON content, leave content_data as None
    
    # Select template based on the determined template type
    template_name = f"blog/{template_type}.html"
    
    # Get ads for the template
    ads = {
        'header': AdPlacement.objects.filter(placement='header', is_active=True).first(),
        'mid_content': AdPlacement.objects.filter(placement='mid-content', is_active=True).first(),
        'footer': AdPlacement.objects.filter(placement='footer', is_active=True).first(),
        'sidebar': AdPlacement.objects.filter(placement='sidebar', is_active=True).first(),
    }
    
    # Get related posts
    related_posts = BlogPost.objects.filter(
        status='published', 
        template_type=template_type  # Use the determined template type for related posts
    ).exclude(id=post.id).order_by('-published_at')[:4]
    
    return render(request, template_name, {
        'post': post,
        'related_posts': related_posts,
        'ads': ads,
        'content_data': content_data  # Pass JSON content if available (None otherwise)
    })

@shared_task
def log_blog_performance(post_id, user_agent):
    """
    Log blog post performance metrics
    """
    try:
        post = BlogPost.objects.get(id=post_id)
        
        # Create performance log
        ContentPerformanceLog.objects.create(
            blog_post=post,
            views=1,
            # Other metrics would be populated by a background process
        )
    except Exception as e:
        logger.error(f"Error logging blog performance: {e}")

# Admin dashboard view
@login_required
def admin_dashboard(request):
    """
    Admin dashboard showing statistics and content management
    """
    # Get post statistics
    stats = {
        'total_posts': BlogPost.objects.count(),
        'published_posts': BlogPost.objects.filter(status='published').count(),
        'draft_posts': BlogPost.objects.filter(status='draft').count(),
        'scheduled_posts': BlogPost.objects.filter(status='scheduled').count(),
        'total_views': BlogPost.objects.aggregate(models.Sum('view_count'))['view_count__sum'] or 0,
    }
    
    # Get recent and trending posts with error handling
    try:
        recent_posts = BlogPost.objects.order_by('-created_at')[:5]
    except Exception as e:
        logger.error(f"Error fetching recent posts: {e}")
        recent_posts = []
        
    try:
        trending_posts = BlogPost.objects.filter(status='published').order_by('-view_count')[:5]
    except Exception as e:
        logger.error(f"Error fetching trending posts: {e}")
        trending_posts = []
    
    return render(request, 'admin/dashboard.html', {
        'stats': stats,
        'recent_posts': recent_posts,
        'trending_posts': trending_posts,
    })

@login_required
def home(request):
    """
    Render the home page with the chatbot interface.
    """
    return render(request, 'chatbot.html')

# Initialize the chatbot with default settings
# This creates a singleton instance shared across requests
chatbot = GeminiChatbot()

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def chat_view(request):
    """
    Handle chat requests from users.
    
    Expects a JSON payload with:
    - message: The user's input text
    - conversation_id: (Optional) ID to continue an existing conversation
    
    Returns a JSON response with:
    - response: The chatbot's response
    - conversation_id: ID for continuing the conversation
    - processing_time: Time taken to generate the response
    """
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        
        # Validate input
        if not user_message:
            return JsonResponse({
                'error': 'Message is required'
            }, status=400)
        
        # Associate conversation with the current user
        if conversation_id is None:
            # Create a new conversation ID that includes the user ID for security
            user_id = request.user.id
            conversation_id = f"user_{user_id}_{int(time.time())}"
        
        # Process the message
        response_data = chatbot.chat(user_message, conversation_id)
        
        # Return the chatbot response
        return JsonResponse({
            'response': response_data['response'],
            'conversation_id': response_data['conversation_id'],
            'processing_time': response_data['processing_time']
        })
    
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    
    except Exception as e:
        return JsonResponse({
            'error': f'An error occurred: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def clear_conversation(request):
    """
    Clear a specific conversation from the cache.
    
    Expects a JSON payload with:
    - conversation_id: ID of the conversation to clear
    
    Returns a success message or error.
    """
    try:
        data = json.loads(request.body)
        conversation_id = data.get('conversation_id')
        
        if not conversation_id:
            return JsonResponse({
                'error': 'Conversation ID is required'
            }, status=400)
        
        # Ensure the conversation belongs to the current user
        user_id = request.user.id
        if not conversation_id.startswith(f"user_{user_id}_"):
            return JsonResponse({
                'error': 'Unauthorized access to this conversation'
            }, status=403)
        
        # Clear the conversation
        chatbot.clear_conversation(conversation_id)
        
        return JsonResponse({
            'success': True,
            'message': 'Conversation cleared successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    
    except Exception as e:
        return JsonResponse({
            'error': f'An error occurred: {str(e)}'
        }, status=500)

@login_required
def get_conversation_history(request, conversation_id):
    """
    Retrieve the conversation history for a specific conversation.
    
    Args:
        conversation_id: ID of the conversation to retrieve
        
    Returns the conversation history or an error.
    """
    try:
        # Ensure the conversation belongs to the current user
        user_id = request.user.id
        if not conversation_id.startswith(f"user_{user_id}_"):
            return JsonResponse({
                'error': 'Unauthorized access to this conversation'
            }, status=403)
        
        # Get the conversation history
        history = chatbot.get_conversation_history(conversation_id)
        
        # Filter out system messages as they're not meant for users
        user_visible_history = [
            msg for msg in history 
            if msg.get('role') in ('user', 'assistant')
        ]
        
        return JsonResponse({
            'conversation_id': conversation_id,
            'history': user_visible_history
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f'An error occurred: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def generate_blog_outline(request):
    """
    Generate a blog post outline based on a title and keywords.
    
    Expects a JSON payload with:
    - title: The blog post title
    - keywords: (Optional) List of keywords to include
    
    Returns a JSON response with the generated outline.
    """
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        keywords = data.get('keywords', [])
        
        if not title:
            return JsonResponse({
                'error': 'Title is required'
            }, status=400)
        
        # Create a specialized prompt for outline generation
        prompt = f"Generate a detailed outline for a blog post titled '{title}'."
        
        if keywords:
            prompt += f" Include the following keywords: {', '.join(keywords)}."
            
        prompt += " Format the outline with main sections (using ## headers) and subsections (using bullet points)."
        
        # Generate the outline
        conversation_id = f"outline_{request.user.id}_{int(time.time())}"
        response_data = chatbot.chat(prompt, conversation_id)
        
        return JsonResponse({
            'title': title,
            'outline': response_data['response'],
            'processing_time': response_data['processing_time']
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    
    except Exception as e:
        return JsonResponse({
            'error': f'An error occurred: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def improve_blog_content(request):
    """
    Improve existing blog content with suggestions.
    
    Expects a JSON payload with:
    - content: The existing blog content
    - focus: (Optional) What to focus on (SEO, readability, etc.)
    
    Returns a JSON response with the improved content.
    """
    try:
        data = json.loads(request.body)
        content = data.get('content', '').strip()
        focus = data.get('focus', 'general').lower()
        
        if not content:
            return JsonResponse({
                'error': 'Content is required'
            }, status=400)
        
        # Create a specialized prompt based on the focus
        if focus == 'seo':
            prompt = f"""Improve the following blog content to make it more SEO-friendly. 
            Add appropriate headings, improve keyword usage, and enhance readability. 
            Keep the core message intact but optimize for search engines.
            
            Original content:
            {content}"""
        elif focus == 'readability':
            prompt = f"""Improve the following blog content to enhance readability. 
            Simplify complex sentences, use clear language, add bullet points where appropriate, 
            and ensure a good flow. Keep the core message intact.
            
            Original content:
            {content}"""
        elif focus == 'engagement':
            prompt = f"""Improve the following blog content to make it more engaging. 
            Add hooks, improve the introduction and conclusion, use more compelling language, 
            and enhance the overall storytelling. Keep the core message intact.
            
            Original content:
            {content}"""
        else:  # general
            prompt = f"""Improve the following blog content for overall quality. 
            Enhance readability, fix any grammatical issues, improve structure, 
            and make it more engaging and professional. Keep the core message intact.
            
            Original content:
            {content}"""
        
        # Generate the improved content
        conversation_id = f"improve_{request.user.id}_{int(time.time())}"
        response_data = chatbot.chat(prompt, conversation_id)
        
        return JsonResponse({
            'improved_content': response_data['response'],
            'focus': focus,
            'processing_time': response_data['processing_time']
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON payload'
        }, status=400)
    
    except Exception as e:
        return JsonResponse({
            'error': f'An error occurred: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def create_blog_api(request):
    """
    Create and optionally publish a new blog post via API
    
    Expects a JSON payload with:
    - keyword: The keyword/topic for the blog post (required)
    - template_type: The template type to use (optional)
    - publish_immediately: Whether to publish immediately (optional, defaults to False)
    
    Returns a JSON response with status and message
    """
    # Create a process logger for this API request
    process_logger = BlogProcessLogger()
    process_logger.info("API request to create blog post", {
        "user_id": request.user.id,
        "username": request.user.username
    })
    
    try:
        # Step 1: Parse request data
        step1 = process_logger.step("PARSE_REQUEST", "Parsing and validating request data")
        
        data = json.loads(request.body)
        keyword = data.get('keyword', '').strip()
        template_type = data.get('template_type')
        publish_immediately = data.get('publish_immediately', False)
        
        process_logger.info("Request data parsed", {
            "keyword": keyword,
            "template_type": template_type,
            "publish_immediately": publish_immediately
        })
        
        # Validate input
        if not keyword:
            error_msg = "Keyword is required"
            process_logger.fail_step(step1, "PARSE_REQUEST", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return JsonResponse({
                'status': 'error',
                'message': error_msg
            }, status=400)
        
        # Valid template types
        valid_templates = ['how_to', 'listicle', 'news', 'review', 'opinion']
        if template_type and template_type not in valid_templates:
            error_msg = f'Invalid template type. Must be one of: {", ".join(valid_templates)}'
            process_logger.fail_step(step1, "PARSE_REQUEST", error_msg)
            process_logger.end_process("FAILED", {"reason": error_msg})
            return JsonResponse({
                'status': 'error',
                'message': error_msg
            }, status=400)
        
        process_logger.complete_step(step1, "PARSE_REQUEST", {
            "keyword": keyword,
            "template_type": template_type,
            "publish_immediately": publish_immediately
        })
        
        # Step 2: Queue the blog creation task
        step2 = process_logger.step("QUEUE_TASK", "Queuing blog creation task")
        
        # Queue the task
        task = create_and_publish_blog.delay(
            keyword=keyword,
            template_type=template_type,
            publish_immediately=publish_immediately
        )
        
        process_logger.complete_step(step2, "QUEUE_TASK", {
            "task_id": task.id
        })
        
        process_logger.success("Blog creation task queued successfully")
        process_logger.end_process("COMPLETED", {
            "task_id": task.id,
            "keyword": keyword
        })
        
        return JsonResponse({
            'status': 'success',
            'message': f'Blog creation task queued with ID: {task.id}',
            'task_id': task.id
        })
    
    except json.JSONDecodeError:
        error_msg = "Invalid JSON payload"
        process_logger.error(error_msg)
        process_logger.end_process("FAILED", {"reason": error_msg})
        return JsonResponse({
            'status': 'error',
            'message': error_msg
        }, status=400)
    
    except Exception as e:
        error_msg = f"Error in create_blog_api: {str(e)}"
        process_logger.error(error_msg)
        process_logger.end_process("FAILED", {"error": str(e)})
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred: {str(e)}'
        }, status=500)

@require_http_methods(["GET"])
@login_required
def check_blog_task_status(request, task_id):
    """
    Check the status of a blog creation task
    
    Args:
        task_id: The ID of the task to check
        
    Returns a JSON response with the task status
    """
    try:
        from celery.result import AsyncResult
        
        # Get the task result
        task_result = AsyncResult(task_id)
        
        # Return the task status
        response = {
            'task_id': task_id,
            'status': task_result.status,
        }
        
        # Check if there are logs for this task
        logs_dir = os.path.join(settings.BASE_DIR, 'logs', 'blog_process')
        if os.path.exists(logs_dir):
            # The log file might have a timestamp format or task_id format
            possible_log_files = [
                os.path.join(logs_dir, f'blog_process_{task_id}.log'),
                # Also try looking for logs with timestamps that might match this task
                *[os.path.join(logs_dir, f) for f in os.listdir(logs_dir) if f.endswith('.log')]
            ]
            
            # Find the log file
            log_file = None
            for file_path in possible_log_files:
                if os.path.exists(file_path):
                    try:
                        # Check if file contains the task ID
                        with open(file_path, 'r') as f:
                            content = f.read()
                            if task_id in content:
                                log_file = file_path
                                break
                    except:
                        continue
            
            if log_file:
                # Read the last 10 log entries
                try:
                    with open(log_file, 'r') as f:
                        log_lines = f.readlines()
                        response['log_entries'] = log_lines[-10:] if len(log_lines) > 10 else log_lines
                        response['log_file'] = os.path.basename(log_file)
                except Exception as e:
                    logger.error(f"Error reading log file: {e}")
        
        # If the task is successful, return the result
        if task_result.successful():
            response['result'] = task_result.result
            
            # If the result contains a blog post ID, get the URL
            if isinstance(task_result.result, str) and "ID:" in task_result.result:
                # Extract the UUID from the result string
                import re
                uuid_match = re.search(r'ID: ([0-9a-f-]+)', task_result.result)
                if uuid_match:
                    blog_id = uuid_match.group(1)
                    try:
                        blog = BlogPost.objects.get(id=blog_id)
                        response['blog_url'] = f"/blog/{blog.slug}/"
                        response['blog_title'] = blog.title
                        response['blog_status'] = blog.status
                    except BlogPost.DoesNotExist:
                        pass
        
        # If the task failed, return the error
        elif task_result.failed():
            response['error'] = str(task_result.result)
        
        return JsonResponse(response)
    
    except Exception as e:
        logger.error(f"Error checking task status: {e}")
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred: {str(e)}'
        }, status=500)

@login_required
def view_process_logs(request, log_file=None):
    """
    View detailed process logs for blog creation
    
    Args:
        log_file: Optional specific log file to view
        
    Returns rendered template with log data
    """
    if not request.user.is_staff:
        return render(request, 'admin/error.html', {
            'error': 'You do not have permission to view logs'
        })
    
    logs_dir = os.path.join(settings.BASE_DIR, 'logs', 'blog_process')
    
    # Check if logs directory exists
    if not os.path.exists(logs_dir):
        return render(request, 'admin/error.html', {
            'error': 'Logs directory not found'
        })
    
    # Get list of log files
    log_files = [f for f in os.listdir(logs_dir) if f.endswith('.log')]
    log_files.sort(key=lambda x: os.path.getmtime(os.path.join(logs_dir, x)), reverse=True)
    
    # If no specific log file is requested, use the latest
    if not log_file and log_files:
        log_file = log_files[0]
    
    log_content = []
    selected_log_path = None
    
    if log_file and log_file in log_files:
        selected_log_path = os.path.join(logs_dir, log_file)
        try:
            with open(selected_log_path, 'r') as f:
                for line in f:
                    try:
                        # Try to parse as JSON for structured logs
                        entry = json.loads(line.strip())
                        log_content.append(entry)
                    except json.JSONDecodeError:
                        # If not JSON, add as plain text
                        log_content.append({
                            'timestamp': '',
                            'level': 'INFO',
                            'message': line.strip()
                        })
        except Exception as e:
            return render(request, 'admin/error.html', {
                'error': f'Error reading log file: {str(e)}'
            })
    
    # Group logs by process ID if possible
    processes = {}
    for entry in log_content:
        if isinstance(entry, dict) and 'message' in entry:
            # Try to extract process ID from the message or data
            process_id = None
            message = entry.get('message', '')
            
            # Check if there's a process_id in the message
            if 'process_id' in message and isinstance(message, dict):
                process_id = message.get('process_id')
            elif 'PROCESS STARTED' in message and 'Data:' in message:
                # Try to extract from the data part
                try:
                    data_start = message.find('Data:') + 5
                    data_json = message[data_start:].strip()
                    data = json.loads(data_json)
                    process_id = data.get('process_id')
                except:
                    pass
            
            if process_id:
                if process_id not in processes:
                    processes[process_id] = []
                processes[process_id].append(entry)
            else:
                # For entries without process ID, use 'unknown'
                if 'unknown' not in processes:
                    processes['unknown'] = []
                processes['unknown'].append(entry)
    
    return render(request, 'admin/process_logs.html', {
        'log_files': log_files,
        'selected_log': log_file,
        'log_content': log_content,
        'processes': processes
    })

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def publish_post(request, post_id):
    """
    Publish a blog post via AJAX
    """
    try:
        post = get_object_or_404(BlogPost, id=post_id)
        post.publish()
        return JsonResponse({
            'success': True,
            'message': f'Post "{post.title}" has been published successfully.',
            'post_id': str(post.id),
            'post_url': f'/blog/{post.slug}/'
        })
    except Exception as e:
        logger.error(f"Error publishing post {post_id}: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error publishing post: {str(e)}'
        }, status=500) 