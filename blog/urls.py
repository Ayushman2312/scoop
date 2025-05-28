from django.urls import path
from .views import *

urlpatterns = [
    # Blog public routes
    path('', index, name='index'),
    path('blog/<slug:slug>/', blog_detail, name='blog_detail'),
    
    # Admin and dashboard routes
    path('dashboard/', admin_dashboard, name='admin_dashboard'),
    path('logs/', view_process_logs, name='view_process_logs'),
    path('logs/<str:log_file>/', view_process_logs, name='view_specific_log'),
    
    # Chatbot routes
    path('chatbot/', home, name='chatbot_home'),
    path('chat/', chat_view, name='chat_view'),
    path('chat/clear/', clear_conversation, name='clear_conversation'),
    path('chat/history/<str:conversation_id>/', get_conversation_history, name='get_conversation_history'),
    path('chat/outline/', generate_blog_outline, name='generate_blog_outline'),
    path('chat/improve/', improve_blog_content, name='improve_blog_content'),
    
    # Blog API routes
    path('api/create-blog/', create_blog_api, name='create_blog_api'),
    path('api/task-status/<str:task_id>/', check_blog_task_status, name='check_blog_task_status'),
] 