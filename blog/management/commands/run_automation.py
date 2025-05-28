from django.core.management.base import BaseCommand, CommandError
from blog.automation import run_blog_automation_pipeline


class Command(BaseCommand):
    help = 'Runs the blog automation pipeline that selects topics and generates content'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force execution even if there are recent blog posts',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting blog automation pipeline...'))
        
        try:
            # Run the pipeline synchronously (not as a Celery task)
            result = run_blog_automation_pipeline()
            
            if result.startswith('Success'):
                self.stdout.write(self.style.SUCCESS(result))
            else:
                self.stdout.write(self.style.WARNING(result))
                
        except Exception as e:
            raise CommandError(f'Blog automation pipeline failed: {e}') 