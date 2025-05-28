import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Setup API keys for SerpAPI and Gemini API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--serpapi-key',
            dest='serpapi_key',
            type=str,
            help='SerpAPI key for fetching trending topics',
        )
        parser.add_argument(
            '--gemini-key',
            dest='gemini_key',
            type=str,
            help='Google Gemini API key for content generation',
        )
        parser.add_argument(
            '--region',
            type=str,
            help='Region for trending topics (default: us)',
            default='us',
        )
        parser.add_argument(
            '--category',
            type=str,
            help='Category for trending topics (default: all)',
            choices=['all', 'business', 'entertainment', 'health', 'sci/tech', 'sports', 'top stories'],
            default='all',
        )

    def handle(self, *args, **options):
        env_path = Path(settings.BASE_DIR) / '.env'
        
        # Check if .env file exists
        if env_path.exists():
            self.stdout.write("Existing .env file found. Updating keys...")
            with open(env_path, 'r') as f:
                env_content = f.read()
        else:
            self.stdout.write("Creating new .env file...")
            env_content = """# Django Settings
SECRET_KEY={secret_key}
DEBUG=True

# API Keys
SERPAPI_API_KEY=
GEMINI_API_KEY=

# Google Trends Settings
SERP_API_REGION=us
SERP_API_CATEGORY=all

# Gemini Model Settings
GEMINI_MODEL=gemini-1.5-pro

# Celery / Redis Settings
REDIS_URL=redis://localhost:6379/0
""".format(secret_key=settings.SECRET_KEY)

        # Update SerpAPI key if provided
        serpapi_key = options.get('serpapi_key')
        if serpapi_key:
            if 'SERPAPI_API_KEY=' in env_content:
                env_content = env_content.replace(
                    f"SERPAPI_API_KEY={env_content.split('SERPAPI_API_KEY=')[1].split('\n')[0]}",
                    f"SERPAPI_API_KEY={serpapi_key}"
                )
            else:
                env_content += f"\nSERPAPI_API_KEY={serpapi_key}"
        else:
            serpapi_key = input("Enter your SerpAPI key: ")
            if serpapi_key:
                if 'SERPAPI_API_KEY=' in env_content:
                    env_content = env_content.replace(
                        f"SERPAPI_API_KEY={env_content.split('SERPAPI_API_KEY=')[1].split('\n')[0]}",
                        f"SERPAPI_API_KEY={serpapi_key}"
                    )
                else:
                    env_content += f"\nSERPAPI_API_KEY={serpapi_key}"

        # Update Gemini API key if provided
        gemini_key = options.get('gemini_key')
        if gemini_key:
            if 'GEMINI_API_KEY=' in env_content:
                env_content = env_content.replace(
                    f"GEMINI_API_KEY={env_content.split('GEMINI_API_KEY=')[1].split('\n')[0]}",
                    f"GEMINI_API_KEY={gemini_key}"
                )
            else:
                env_content += f"\nGEMINI_API_KEY={gemini_key}"
        else:
            gemini_key = input("Enter your Gemini API key: ")
            if gemini_key:
                if 'GEMINI_API_KEY=' in env_content:
                    env_content = env_content.replace(
                        f"GEMINI_API_KEY={env_content.split('GEMINI_API_KEY=')[1].split('\n')[0]}",
                        f"GEMINI_API_KEY={gemini_key}"
                    )
                else:
                    env_content += f"\nGEMINI_API_KEY={gemini_key}"

        # Update region if provided
        region = options.get('region')
        if region and region != 'us':
            if 'SERP_API_REGION=' in env_content:
                env_content = env_content.replace(
                    f"SERP_API_REGION={env_content.split('SERP_API_REGION=')[1].split('\n')[0]}",
                    f"SERP_API_REGION={region}"
                )
            else:
                env_content += f"\nSERP_API_REGION={region}"

        # Update category if provided
        category = options.get('category')
        if category and category != 'all':
            if 'SERP_API_CATEGORY=' in env_content:
                env_content = env_content.replace(
                    f"SERP_API_CATEGORY={env_content.split('SERP_API_CATEGORY=')[1].split('\n')[0]}",
                    f"SERP_API_CATEGORY={category}"
                )
            else:
                env_content += f"\nSERP_API_CATEGORY={category}"

        # Write to .env file
        with open(env_path, 'w') as f:
            f.write(env_content)

        self.stdout.write(self.style.SUCCESS("API keys have been set up successfully!"))
        self.stdout.write("You can now run the following to test your configuration:")
        self.stdout.write("  python manage.py fetch_trends")
        self.stdout.write("Or generate content with:")
        self.stdout.write("  python manage.py generate_blog") 