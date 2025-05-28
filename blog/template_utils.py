"""
Utility functions for blog template standardization and processing.
"""
import os
import logging
import re
from django.conf import settings
from django.template.loader import get_template
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)

def convert_content_to_template(content, template_type):
    """
    Converts JSON content data to HTML using the appropriate template
    
    Args:
        content (dict): Content data in dictionary format
        template_type (str): The template type (how_to, listicle, etc.)
        
    Returns:
        str: HTML content
    """
    try:
        template_name = f"blog/{template_type}.html"
        template = get_template(template_name)
        
        # Transform the content data into format expected by template
        context = {
            'post': {
                'title': content.get('title', ''),
                'meta_description': content.get('meta_description', ''),
                'content': format_content_to_html(content, template_type),
                'template_type': template_type,
            }
        }
        
        return template.render(context)
    except Exception as e:
        logger.error(f"Error converting content to template: {e}")
        return ""

def format_content_to_html(content, template_type):
    """
    Formats the structured content data into HTML based on template type
    
    Args:
        content (dict): Content data in dictionary format
        template_type (str): The template type (how_to, listicle, etc.)
        
    Returns:
        str: HTML content
    """
    html = []
    
    # Add intro section
    if 'intro' in content:
        html.append(content['intro'])
    
    # Add table of contents if present
    if 'table_of_contents' in content and content['table_of_contents']:
        toc_html = ['<div class="table-of-contents my-6 p-5 bg-gray-50 border border-gray-200 rounded-lg">',
                   '<h2 class="text-xl font-semibold mb-3">Table of Contents</h2>',
                   '<ul class="space-y-2">']
        
        for item in content['table_of_contents']:
            item_id = item.get('id', '')
            item_title = item.get('title', '')
            if item_id and item_title:
                toc_html.append(f'<li><a href="#{item_id}" class="text-primary-600 hover:text-primary-800 transition">{item_title}</a></li>')
        
        toc_html.append('</ul></div>')
        html.append(''.join(toc_html))
    
    # Add main content based on template type
    if template_type == 'how_to':
        if 'steps' in content:
            for step in content['steps']:
                step_id = step.get('id', '')
                step_title = step.get('title', '')
                step_content = step.get('content', '')
                
                if step_id and step_title:
                    html.append(f'<h2 id="{step_id}" class="text-2xl font-bold mt-8 mb-4">{step_title}</h2>')
                    html.append(step_content)
    
    elif template_type == 'listicle':
        if 'list_items' in content:
            for item in content['list_items']:
                item_id = item.get('id', '')
                item_number = item.get('number', '')
                item_title = item.get('title', '')
                item_content = item.get('content', '')
                
                if item_id and item_title:
                    html.append(f'<h2 id="{item_id}" class="text-2xl font-bold mt-8 mb-4">{item_number}. {item_title}</h2>')
                    html.append(item_content)
    
    else:  # news, review, opinion
        if 'sections' in content:
            for section in content['sections']:
                section_id = section.get('id', '')
                section_title = section.get('title', '')
                section_content = section.get('content', '')
                
                if section_id and section_title:
                    html.append(f'<h2 id="{section_id}" class="text-2xl font-bold mt-8 mb-4">{section_title}</h2>')
                    html.append(section_content)
    
    # Add special sections for review template
    if template_type == 'review' and 'pros' in content and 'cons' in content:
        html.append('<div class="pros-cons-container my-8 grid grid-cols-1 md:grid-cols-2 gap-6">')
        
        # Pros section
        html.append('<div class="pros bg-green-50 border border-green-200 rounded-lg p-5">')
        html.append('<h3 class="text-xl font-semibold text-green-800 mb-3">Pros</h3>')
        html.append('<ul class="space-y-2">')
        for pro in content['pros']:
            html.append(f'<li class="flex items-start"><svg class="h-5 w-5 text-green-500 mr-2 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>{pro}</li>')
        html.append('</ul></div>')
        
        # Cons section
        html.append('<div class="cons bg-red-50 border border-red-200 rounded-lg p-5">')
        html.append('<h3 class="text-xl font-semibold text-red-800 mb-3">Cons</h3>')
        html.append('<ul class="space-y-2">')
        for con in content['cons']:
            html.append(f'<li class="flex items-start"><svg class="h-5 w-5 text-red-500 mr-2 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>{con}</li>')
        html.append('</ul></div>')
        
        html.append('</div>')
        
        # Verdict
        if 'verdict' in content:
            html.append('<div class="verdict my-8 bg-blue-50 border border-blue-200 rounded-lg p-5">')
            html.append('<h3 class="text-xl font-semibold text-blue-800 mb-3">Our Verdict</h3>')
            html.append(content['verdict'])
            html.append('</div>')
    
    # Add conclusion
    if 'conclusion' in content:
        html.append('<h2 class="text-2xl font-bold mt-8 mb-4">Conclusion</h2>')
        html.append(content['conclusion'])
    
    # Add FAQs if present
    if 'faqs' in content and content['faqs']:
        html.append('<h2 class="text-2xl font-bold mt-10 mb-6">Frequently Asked Questions</h2>')
        html.append('<div class="faqs space-y-6">')
        
        for faq in content['faqs']:
            question = faq.get('question', '')
            answer = faq.get('answer', '')
            
            if question and answer:
                html.append('<div class="faq-item bg-white rounded-lg shadow-sm p-5">')
                html.append(f'<h3 class="text-lg font-semibold mb-2">{question}</h3>')
                html.append(f'<div class="text-gray-700">{answer}</div>')
                html.append('</div>')
        
        html.append('</div>')
    
    # Return the combined HTML with proper marks_safe for Django templates
    return mark_safe('\n'.join(html))

def standardize_templates():
    """
    Standardizes all blog templates in the blog_templates folder
    to use the header and footer includes
    """
    templates_dir = os.path.join(settings.BASE_DIR, 'templates', 'blog_templates')
    
    try:
        # Skip the header and footer templates themselves
        template_files = [f for f in os.listdir(templates_dir) 
                         if f.endswith('.html') and f not in ['header.html', 'footer.html']]
        
        for template_file in template_files:
            template_path = os.path.join(templates_dir, template_file)
            
            try:
                with open(template_path, 'r', encoding='utf-8-sig') as file:
                    content = file.read()
                
                # Check if the template already includes header.html
                if '{% include "blog_templates/header.html"' in content:
                    logger.info(f"Template already standardized: {template_file}")
                    continue
                
                # Extract the content section (between opening body and closing body tags)
                body_pattern = re.compile(r'<body.*?>(.*?)</body>', re.DOTALL)
                body_match = body_pattern.search(content)
                
                if body_match:
                    body_content = body_match.group(1).strip()
                    
                    # Create standardized template with header and footer includes
                    standardized_template = (
                        '{% include "blog_templates/header.html" with \n'
                        '    title=title|default:"Blog Template" \n'
                        '    meta_description=meta_description|default:"" \n'
                        '    page_url=page_url|default:"" \n'
                        '    featured_image=featured_image|default:"" \n'
                        '    schema_type="Article"\n'
                        '    published_date=published_date|default:"" \n'
                        '    modified_date=modified_date|default:"" \n'
                        '%}\n\n'
                        f'<!-- Main Content -->\n{body_content}\n\n'
                        '{% include "blog_templates/footer.html" %}'
                    )
                    
                    # Write the standardized template back to the file
                    with open(template_path, 'w', encoding='utf-8-sig') as file:
                        file.write(standardized_template)
                    
                    logger.info(f"Standardized template: {template_file}")
                else:
                    # If there's no body tag but the template doesn't include header.html,
                    # assume it's a raw content template and wrap it with header/footer
                    standardized_template = (
                        '{% include "blog_templates/header.html" with \n'
                        '    title=title|default:"Blog Template" \n'
                        '    meta_description=meta_description|default:"" \n'
                        '    page_url=page_url|default:"" \n'
                        '    featured_image=featured_image|default:"" \n'
                        '    schema_type="Article"\n'
                        '    published_date=published_date|default:"" \n'
                        '    modified_date=modified_date|default:"" \n'
                        '%}\n\n'
                        f'<!-- Main Content -->\n{content}\n\n'
                        '{% include "blog_templates/footer.html" %}'
                    )
                    
                    # Write the standardized template back to the file
                    with open(template_path, 'w', encoding='utf-8-sig') as file:
                        file.write(standardized_template)
                    
                    logger.info(f"Wrapped template with header/footer: {template_file}")
            except UnicodeDecodeError as ude:
                logger.error(f"Encoding error with {template_file}: {ude}")
                # Try with different encodings
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        with open(template_path, 'r', encoding=encoding) as file:
                            content = file.read()
                        
                        # Check if the template already includes header.html
                        if '{% include "blog_templates/header.html"' in content:
                            logger.info(f"Template already standardized: {template_file}")
                            break
                            
                        # Extract body content and convert to standardized template
                        body_pattern = re.compile(r'<body.*?>(.*?)</body>', re.DOTALL)
                        body_match = body_pattern.search(content)
                        
                        if body_match:
                            body_content = body_match.group(1).strip()
                            
                            # Create standardized template
                            standardized_template = (
                                '{% include "blog_templates/header.html" with \n'
                                '    title=title|default:"Blog Template" \n'
                                '    meta_description=meta_description|default:"" \n'
                                '    page_url=page_url|default:"" \n'
                                '    featured_image=featured_image|default:"" \n'
                                '    schema_type="Article"\n'
                                '    published_date=published_date|default:"" \n'
                                '    modified_date=modified_date|default:"" \n'
                                '%}\n\n'
                                f'<!-- Main Content -->\n{body_content}\n\n'
                                '{% include "blog_templates/footer.html" %}'
                            )
                        else:
                            # If there's no body tag, wrap the entire content
                            standardized_template = (
                                '{% include "blog_templates/header.html" with \n'
                                '    title=title|default:"Blog Template" \n'
                                '    meta_description=meta_description|default:"" \n'
                                '    page_url=page_url|default:"" \n'
                                '    featured_image=featured_image|default:"" \n'
                                '    schema_type="Article"\n'
                                '    published_date=published_date|default:"" \n'
                                '    modified_date=modified_date|default:"" \n'
                                '%}\n\n'
                                f'<!-- Main Content -->\n{content}\n\n'
                                '{% include "blog_templates/footer.html" %}'
                            )
                            
                        # Write with utf-8-sig encoding
                        with open(template_path, 'w', encoding='utf-8-sig') as file:
                            file.write(standardized_template)
                        
                        logger.info(f"Fixed encoding and standardized template: {template_file}")
                        break
                    except Exception as e:
                        continue
    except Exception as e:
        logger.error(f"Error standardizing templates: {e}") 