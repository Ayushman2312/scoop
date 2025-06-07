# Blogify - Automated Blog Generator

Blogify is an AI-powered blog automation platform that generates high-quality, SEO-optimized blog posts based on trending topics. The system automatically fetches trending topics from Google using the SerpAPI, selects the best topic using Google's Gemini AI, generates content, and publishes it on your blog.

## Features

- **Automated Trending Topic Fetching**: Every 4 hours, Blogify fetches trending topics from Google using SerpAPI.
- **AI-Powered Topic Selection**: Gemini AI selects the most engaging and relevant topic for your audience.
- **Template Selection**: Gemini automatically selects the most appropriate blog template based on the topic.
- **SEO-Optimized Content Generation**: Generates comprehensive, human-like blog content optimized for search engines.
- **Automatic Publication**: Published blogs are immediately available on your site.
- **Detailed Logging**: Comprehensive logging system to track the automation process.

## Setup Instructions

### Prerequisites

- Python 3.8+
- Django 3.2+
- Redis (for Celery task queue)
- SerpAPI Account (for trending topics)
- Google Gemini API Key (for AI content generation)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/blogify.git
   cd blogify
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root with the following variables:
   ```
   DEBUG=True
   SECRET_KEY=your_django_secret_key
   ALLOWED_HOSTS=localhost,127.0.0.1
   
   # Database settings (if using PostgreSQL)
   # DATABASE_URL=postgres://user:password@localhost:5432/blogify
   
   # SerpAPI settings
   SERPAPI_API_KEY=your_serpapi_api_key
   SERP_API_REGION=us
   SERP_API_CATEGORY=all
   
   # Gemini AI settings
   GEMINI_API_KEY=your_gemini_api_key
   GEMINI_MODEL=gemini-1.5-pro
   ```

5. Apply migrations:
   ```
   python manage.py migrate
   ```

6. Create a superuser:
   ```
   python manage.py createsuperuser
   ```

7. Create required directories:
   ```
   mkdir -p logs cache
   ```

8. Create the template context file:
   ```
   cp template_context_example.json cache/template_context.json
   ```

### Running the Application

1. Start Redis (required for Celery):
   ```
   redis-server
   ```

2. Start the Django development server:
   ```
   python manage.py runserver
   ```

3. Start the Celery worker:
   ```
   celery -A blogify worker -l info
   ```

4. Start the Celery beat scheduler:
   ```
   celery -A blogify beat -l info
   ```

## How It Works

1. **Trending Topic Fetching**: Every 4 hours, the system fetches trending topics from Google using SerpAPI.
2. **Topic Processing**: The system filters and processes the fetched topics to ensure quality.
3. **Topic Selection**: Gemini AI selects the best topic based on engagement potential and relevance.
4. **Template Selection**: Gemini selects the most appropriate blog template for the chosen topic based on the templates defined in `cache/template_context.json`.
5. **Content Generation**: Gemini generates comprehensive, SEO-optimized content in JSON format according to the selected template.
6. **Content Rendering**: The JSON content is rendered to HTML based on the selected template.
7. **Blog Publication**: The finished blog post is published on the site.

## Logging

The system maintains detailed logs of the entire automation process in the `logs` directory:
- `logs/automation.log`: General application logs
- `logs/automation_structured.log`: Structured JSON logs for detailed process tracking

## Customization

### Blog Templates

Templates are defined in `cache/template_context.json`. Each template includes:
- Template ID and name
- Purpose and use cases
- Structure information
- Example topics

The system comes with five pre-defined templates:
1. **Evergreen Pillar Page Structure**: Comprehensive guides on broad topics
2. **Trend-Based SEO Blog Structure**: Content based on trending topics
3. **Comparison Blog Structure**: Product or service comparisons
4. **Local SEO Blog Template**: Location-specific content
5. **How-To Guide SEO Blog Template**: Step-by-step guides

### Template Selection Process

The template selection process uses Google's Gemini AI to analyze the trending topic and determine which template would be most effective:

1. After selecting the best trending topic, Gemini analyzes the topic's characteristics.
2. Gemini evaluates each template in `cache/template_context.json` to determine the best match based on:
   - Search intent (informational, commercial, etc.)
   - Content structure needs (comparison, how-to, news, etc.)
   - SEO requirements for the topic
   - Target audience expectations
3. Gemini returns a structured response identifying the selected template as "Template 1", "Template 2", etc., along with detailed reasoning.
4. Each template requires a specific JSON structure with template-appropriate SEO elements.
5. The content generation process then uses the selected template to create a properly structured blog post with all required SEO elements.

The five templates are designed for different types of content:
- **Template 1**: Best for comprehensive evergreen pillar content for broad topics
- **Template 2**: Best for recent trending topics that need timely coverage
- **Template 3**: Best for comparison/review content between products or services
- **Template 4**: Best for location-specific content targeting local audiences
- **Template 5**: Best for step-by-step instructional guides and tutorials

### Scheduling

The automation schedule can be customized in `blogify/celery.py`. By default:
- Trending topics are fetched every 4 hours
- Blog posts are generated every 4 hours
- Scheduled blogs are published every 10 minutes

## Troubleshooting

If you encounter issues with the automation process, check the logs at:
- `logs/automation.log`
- `logs/automation_structured.log`

Common issues:
- Missing API keys in `.env` file
- Redis not running (required for Celery)
- Incorrect template format in `cache/template_context.json`

## License

This project is licensed under the MIT License.