from django.core.management.base import BaseCommand
from blog.tasks import fetch_trending_topics, process_trending_topics

class Command(BaseCommand):
    help = 'Fetch trending topics from Google Trends using SerpAPI'

    def add_arguments(self, parser):
        parser.add_argument(
            '--process',
            action='store_true',
            help='Also process the fetched trends after fetching',
        )

    def handle(self, *args, **options):
        self.stdout.write("Fetching trending topics...")
        result = fetch_trending_topics()
        self.stdout.write(self.style.SUCCESS(result))
        
        # Process trends if requested
        if options.get('process'):
            self.stdout.write("Processing trending topics...")
            process_result = process_trending_topics()
            self.stdout.write(self.style.SUCCESS(process_result)) 