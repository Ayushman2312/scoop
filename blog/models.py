from django.db import models
from django.utils.text import slugify
from django.utils import timezone
import uuid

class TrendingTopic(models.Model):
    """
    Model to store trending topics fetched from SerpAPI
    """
    LOCATION_CHOICES = (
        ('global', 'Global'),
        ('us', 'United States'),
        ('uk', 'United Kingdom'),
        ('ca', 'Canada'),
        ('au', 'Australia'),
        ('in', 'India'),
    )

    keyword = models.CharField(max_length=255)
    rank = models.IntegerField()
    location = models.CharField(max_length=20, choices=LOCATION_CHOICES, default='global')
    timestamp = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    filtered_out = models.BooleanField(default=False)
    filter_reason = models.CharField(max_length=255, blank=True, null=True)
    search_volume = models.IntegerField(default=0)
    increase_percentage = models.IntegerField(default=0)
    category = models.CharField(max_length=255, blank=True, null=True)
    related_keywords = models.JSONField(null=True, blank=True)
    is_fallback = models.BooleanField(default=False, help_text="Indicates if this is a manually added fallback topic")
    
    class Meta:
        ordering = ['-timestamp', 'rank']
        unique_together = ('keyword', 'timestamp', 'location')
    
    def __str__(self):
        return f"{self.keyword} (#{self.rank} in {self.location})"


class BlogPost(models.Model):
    """
    Model to store generated blog posts
    """
    TEMPLATE_CHOICES = (
        ('evergreen', 'Evergreen Pillar Content'),
        ('trend', 'Trending Topic Content'),
        ('comparison', 'Comparison/Review Content'),
        ('local', 'Local SEO Content'),
        ('how_to', 'How-To Guide'),
    )
    
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    content = models.TextField()
    meta_description = models.CharField(max_length=160)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_CHOICES)
    trending_topic = models.ForeignKey(TrendingTopic, on_delete=models.SET_NULL, null=True, blank=True, related_name='blog_posts')
    
    # Publishing metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    
    # Analytics
    view_count = models.IntegerField(default=0)
    avg_time_on_page = models.FloatField(null=True, blank=True)
    
    # SEO metrics
    seo_score = models.IntegerField(null=True, blank=True)
    keyword_density = models.FloatField(null=True, blank=True)
    
    # Content freshness tracking
    is_fresh_variant = models.BooleanField(default=False, help_text="Indicates if this post is a fresh variant of a duplicate topic")
    fresh_approach = models.CharField(max_length=50, blank=True, null=True, help_text="The approach used for creating fresh content")
    
    class Meta:
        ordering = ['-published_at', '-created_at']
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        # Auto-generate slug if not provided
        if not self.slug:
            self.slug = slugify(self.title)
        
        # Set published_at when status changes to published
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
            
        super().save(*args, **kwargs)
    
    def publish(self):
        """Publish this blog post"""
        self.status = 'published'
        self.published_at = timezone.now()
        self.save()
        
    @property
    def is_published(self):
        return self.status == 'published'
    
    @property
    def reading_time(self):
        """Estimate reading time in minutes"""
        words_per_minute = 200
        word_count = len(self.content.split())
        return max(1, round(word_count / words_per_minute))


class AdPlacement(models.Model):
    """
    Model to store AdSense ad placement configuration
    """
    PLACEMENT_CHOICES = (
        ('header', 'Header'),
        ('mid-content', 'Mid-Content'),
        ('footer', 'Footer'),
        ('sidebar', 'Sidebar'),
    )
    
    name = models.CharField(max_length=100)
    placement = models.CharField(max_length=20, choices=PLACEMENT_CHOICES)
    ad_code = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.placement})"


class ContentPerformanceLog(models.Model):
    """
    Model to track performance of generated content for learning
    """
    blog_post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='performance_logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    views = models.IntegerField(default=0)
    avg_time_on_page = models.FloatField(null=True, blank=True)
    bounce_rate = models.FloatField(null=True, blank=True)
    conversion_rate = models.FloatField(null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Performance log for {self.blog_post.title} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class TopicFreshnessLog(models.Model):
    """
    Model to track topic duplication and content freshness strategies
    This helps with reinforcement learning for the content generation system
    """
    FRESHNESS_STRATEGY_CHOICES = (
        ('different_angle', 'Different Angle/Perspective'),
        ('new_template', 'New Template Type'),
        ('alternative_topic', 'Alternative Topic Selected'),
        ('latest_data', 'Latest Data/Trends/Statistics'),
        ('audience_shift', 'Different Audience Targeting'),
        ('none', 'No Strategy Applied'),
    )
    
    keyword = models.CharField(max_length=255)
    first_occurrence = models.DateTimeField(auto_now_add=True, help_text="When the topic was first seen")
    last_occurrence = models.DateTimeField(auto_now=True, help_text="When the topic was most recently seen")
    occurrence_count = models.IntegerField(default=1, help_text="How many times this topic has appeared")
    
    # Blog posts generated for this topic
    related_blog_posts = models.ManyToManyField(BlogPost, blank=True, related_name='freshness_logs')
    
    # Strategy applied
    strategy_applied = models.CharField(max_length=50, choices=FRESHNESS_STRATEGY_CHOICES, default='none')
    strategy_notes = models.TextField(blank=True, null=True)
    
    # Performance metrics for adaptive learning
    strategy_success_score = models.IntegerField(default=0, help_text="Score indicating how successful the strategy was (0-100)")
    seo_impact = models.IntegerField(default=0, help_text="Impact on SEO performance (-100 to 100)")
    engagement_lift = models.FloatField(default=0.0, help_text="Percentage lift in engagement compared to previous content")
    
    class Meta:
        ordering = ['-last_occurrence']
        indexes = [
            models.Index(fields=['keyword']),
            models.Index(fields=['last_occurrence']),
        ]
    
    def __str__(self):
        return f"{self.keyword} (Occurred {self.occurrence_count} times)"
    
    def increment_occurrence(self):
        """Increment the occurrence count and update last_occurrence"""
        self.occurrence_count += 1
        self.last_occurrence = timezone.now()
        self.save()
    
    def update_performance_metrics(self, success_score, seo_impact, engagement_lift):
        """Update performance metrics based on content performance"""
        self.strategy_success_score = success_score
        self.seo_impact = seo_impact
        self.engagement_lift = engagement_lift
        self.save()
