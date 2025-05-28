from django.apps import AppConfig
import sys
import io
import os
from django.template import engines
from django.template.loaders.filesystem import Loader as FileSystemLoader

# Patch Django's FileSystemLoader to handle encoding issues
class EncodingAwareFileSystemLoader(FileSystemLoader):
    def get_contents(self, origin):
        try:
            # First try the default behavior
            return super().get_contents(origin)
        except UnicodeDecodeError as e:
            # If that fails, try with different encodings
            for encoding in ['cp1252', 'latin-1', 'iso-8859-1']:
                try:
                    with open(origin.name, encoding=encoding) as fp:
                        return fp.read()
                except UnicodeDecodeError:
                    continue
            
            # If all encodings fail, try with replacement
            with open(origin.name, encoding='utf-8', errors='replace') as fp:
                return fp.read()

class BlogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'blog'
    
    def ready(self):
        """
        Import automation module when Django starts
        This ensures Celery discovers the automation tasks
        Also standardizes blog templates and fixes encoding
        """
        # Set UTF-8 as the default encoding for standard output
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8-sig')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8-sig')
        
        # Patch the template loaders to handle encoding issues
        try:
            for engine in engines.all():
                for loader in engine.engine.template_loaders:
                    if isinstance(loader, FileSystemLoader):
                        # Replace the loader with our encoding-aware version
                        engine.engine.template_loaders[
                            engine.engine.template_loaders.index(loader)
                        ] = EncodingAwareFileSystemLoader(loader.engine, loader.dirs)
        except Exception as e:
            print(f"Error patching template loaders: {e}")
        
        import blog.automation  # noqa
        
        # Standardize blog templates
        from blog.template_utils import standardize_templates
        standardize_templates()
