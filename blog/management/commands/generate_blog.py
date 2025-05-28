import logging
from django.core.management.base import BaseCommand
from blog.tasks import select_best_trending_topic, generate_blog_for_topic
from blog.models import TrendingTopic
from django.utils import timezone

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generate a blog post from the most engaging trending topic'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Optional topic ID to generate content for. If not provided, will select the best topic.',
        )
        parser.add_argument(
            '--template',
            type=str,
            choices=['how_to', 'listicle', 'news', 'review', 'opinion'],
            help='Optional template type to use.',
        )
        parser.add_argument(
            '--publish',
            action='store_true',
            help='Whether to immediately publish the blog post instead of scheduling it.',
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        template = options.get('template')
        publish = options.get('publish', False)
        
        if topic_id:
            try:
                topic = TrendingTopic.objects.get(id=topic_id)
                self.stdout.write(self.style.SUCCESS(f"Found topic: {topic.keyword}"))
                
                # If template not specified, auto-detect
                from blog.tasks import predict_template_type
                template_type = template or predict_template_type(topic.keyword)
                
                # Generate blog
                self.stdout.write(f"Generating blog for topic: {topic.keyword} using template: {template_type}")
                result = generate_blog_for_topic(topic_id, template_type)
                
                # Handle publish flag
                if publish and "Successfully created blog post" in result:
                    # Get the latest blog post for this topic
                    from blog.models import BlogPost
                    blog_post = BlogPost.objects.filter(trending_topic=topic).order_by('-created_at').first()
                    if blog_post:
                        blog_post.status = 'published'
                        blog_post.published_at = timezone.now()
                        blog_post.save()
                        self.stdout.write(self.style.SUCCESS(f"Published blog post: {blog_post.title}"))
                
                self.stdout.write(self.style.SUCCESS(result))
            except TrendingTopic.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Topic with ID {topic_id} not found"))
                return
        else:
            # Select the best topic for content generation
            self.stdout.write("Selecting the best trending topic for content generation...")
            result = select_best_trending_topic()
            
            if "Selected best topic" in result:
                self.stdout.write(self.style.SUCCESS(result))
                
                # Handle publish flag - find the newly created post
                if publish:
                    # Give some time for the blog post to be created
                    import time
                    time.sleep(5)
                    
                    # Get the latest blog post
                    from blog.models import BlogPost
                    blog_post = BlogPost.objects.all().order_by('-created_at').first()
                    if blog_post and blog_post.status == 'scheduled':
                        blog_post.status = 'published'
                        blog_post.published_at = timezone.now()
                        blog_post.save()
                        self.stdout.write(self.style.SUCCESS(f"Published blog post: {blog_post.title}"))
            else:
                self.stdout.write(self.style.WARNING(result)) 