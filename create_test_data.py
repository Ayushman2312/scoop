import os
import django
import datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings')
django.setup()

from django.utils import timezone
from blog.models import TrendingTopic, BlogPost, AdPlacement, ContentPerformanceLog

def create_test_data():
    print("Creating test data...")

    # Create trending topics
    for i in range(1, 6):
        topic, created = TrendingTopic.objects.get_or_create(
            keyword=f"Test Trending Topic {i}",
            rank=i,
            location='in',
            defaults={
                'processed': i % 2 == 0,
                'filtered_out': i % 3 == 0
            }
        )
        if created:
            print(f"Created trending topic: {topic}")
        else:
            print(f"Topic already exists: {topic}")

    # Create blog posts
    template_types = ['how_to', 'listicle', 'news', 'review', 'opinion']
    status_types = ['draft', 'scheduled', 'published', 'archived']
    
    for i in range(1, 6):
        topic = TrendingTopic.objects.all()[i-1]
        template_type = template_types[i-1]
        status = status_types[i % 4]
        
        title = f"Test Blog Post {i}: {topic.keyword}"
        
        try:
            post, created = BlogPost.objects.get_or_create(
                title=title,
                defaults={
                    'content': f"This is test content for {title}. It's a {template_type} article.",
                    'meta_description': f"Meta description for {title}",
                    'template_type': template_type,
                    'trending_topic': topic,
                    'status': status,
                    'view_count': i * 10
                }
            )
            
            if created:
                print(f"Created blog post: {post}")
            else:
                print(f"Blog post already exists: {post}")
                
            # If published, set published_at
            if status == 'published' and not post.published_at:
                post.published_at = timezone.now() - datetime.timedelta(days=i)
                post.save()
                print(f"Updated published_at for {post}")
            
            # Create performance log
            if status == 'published':
                log, log_created = ContentPerformanceLog.objects.get_or_create(
                    blog_post=post,
                    defaults={
                        'views': i * 25,
                        'avg_time_on_page': i * 1.5,
                        'bounce_rate': 60 - (i * 5),
                        'conversion_rate': i * 0.5
                    }
                )
                if log_created:
                    print(f"Created performance log for {post}")
                else:
                    print(f"Performance log already exists for {post}")
                
        except Exception as e:
            print(f"Error creating blog post {title}: {e}")

    # Create ad placements
    placements = ['header', 'mid-content', 'footer', 'sidebar']
    for i, placement in enumerate(placements):
        ad, created = AdPlacement.objects.get_or_create(
            name=f"Test {placement.title()} Ad",
            defaults={
                'placement': placement,
                'ad_code': f'<div class="ad-{placement}">Test Ad {i+1}</div>',
                'is_active': i < 3  # First 3 are active
            }
        )
        if created:
            print(f"Created ad placement: {ad}")
        else:
            print(f"Ad placement already exists: {ad}")

    print("Test data creation complete!")

if __name__ == "__main__":
    create_test_data() 