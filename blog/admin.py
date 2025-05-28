from django.contrib import admin
from .models import TrendingTopic, BlogPost, AdPlacement, ContentPerformanceLog

@admin.register(TrendingTopic)
class TrendingTopicAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'rank', 'location', 'timestamp', 'processed', 'filtered_out')
    list_filter = ('location', 'processed', 'filtered_out', 'timestamp')
    search_fields = ('keyword',)
    date_hierarchy = 'timestamp'

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'template_type', 'status', 'created_at', 'published_at', 'view_count')
    list_filter = ('status', 'template_type', 'created_at', 'published_at')
    search_fields = ('title', 'content', 'meta_description')
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'created_at'
    readonly_fields = ('id', 'created_at', 'updated_at', 'view_count', 'avg_time_on_page')
    fieldsets = (
        (None, {
            'fields': ('id', 'title', 'slug', 'content', 'meta_description')
        }),
        ('Publishing', {
            'fields': ('status', 'template_type', 'trending_topic', 'published_at', 'scheduled_at')
        }),
        ('Analytics', {
            'fields': ('view_count', 'avg_time_on_page', 'seo_score', 'keyword_density')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    actions = ['publish_posts', 'archive_posts']
    
    def publish_posts(self, request, queryset):
        for post in queryset:
            post.publish()
        self.message_user(request, f"{queryset.count()} posts were published successfully.")
    publish_posts.short_description = "Publish selected posts"
    
    def archive_posts(self, request, queryset):
        queryset.update(status='archived')
        self.message_user(request, f"{queryset.count()} posts were archived successfully.")
    archive_posts.short_description = "Archive selected posts"

@admin.register(AdPlacement)
class AdPlacementAdmin(admin.ModelAdmin):
    list_display = ('name', 'placement', 'is_active', 'created_at')
    list_filter = ('placement', 'is_active')
    search_fields = ('name', 'ad_code')

@admin.register(ContentPerformanceLog)
class ContentPerformanceLogAdmin(admin.ModelAdmin):
    list_display = ('blog_post', 'timestamp', 'views', 'avg_time_on_page', 'bounce_rate')
    list_filter = ('timestamp',)
    date_hierarchy = 'timestamp'
    readonly_fields = ('blog_post', 'timestamp', 'views', 'avg_time_on_page', 'bounce_rate', 'conversion_rate')
