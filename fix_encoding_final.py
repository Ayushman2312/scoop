import os
import sys

def process_template_file(filepath):
    """Process a template file to fix encoding issues"""
    print(f"Processing {filepath}...")
    
    try:
        # First try to read with utf-8 to see if it's already valid
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            print(f"  File {filepath} is already valid UTF-8")
            return True
        except UnicodeDecodeError:
            # If UTF-8 fails, try Windows cp1252 encoding
            pass
            
        # Read in binary mode
        with open(filepath, 'rb') as file:
            binary_content = file.read()
            
        # Try to decode with cp1252 (Windows encoding)
        try:
            content = binary_content.decode('cp1252')
            print(f"  Successfully decoded {filepath} with cp1252")
            
            # Write back with UTF-8 encoding
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(content)
                
            print(f"  Converted {filepath} from cp1252 to UTF-8")
            return True
        except UnicodeDecodeError:
            # If cp1252 fails, use 'replace' to substitute invalid characters
            content = binary_content.decode('utf-8', errors='replace')
            print(f"  Used error replacement to decode {filepath}")
            
            # Write back with UTF-8 encoding
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(content)
                
            print(f"  Fixed {filepath} using replacement characters")
            return True
            
    except Exception as e:
        print(f"  Error processing {filepath}: {str(e)}")
        return False
        
def update_django_settings():
    """Update Django settings.py to ensure file encoding settings are correct"""
    settings_path = os.path.join('blogify', 'settings.py')
    if not os.path.exists(settings_path):
        print(f"Settings file not found at {settings_path}")
        return False
        
    try:
        with open(settings_path, 'r', encoding='utf-8') as file:
            content = file.read()
            
        # Check if FILE_CHARSET is already defined
        if 'FILE_CHARSET' not in content:
            # Find the right place to add the setting - after USE_TZ
            if 'USE_TZ = True' in content:
                content = content.replace(
                    'USE_TZ = True',
                    'USE_TZ = True\n\n# File encoding settings\nFILE_CHARSET = \'utf-8\'\nDEFAULT_CHARSET = \'utf-8\''
                )
                
                with open(settings_path, 'w', encoding='utf-8') as file:
                    file.write(content)
                    
                print(f"Updated {settings_path} with explicit charset settings")
                return True
            else:
                print(f"Could not find appropriate place to add charset settings in {settings_path}")
                return False
        else:
            print(f"FILE_CHARSET already defined in {settings_path}")
            return True
            
    except Exception as e:
        print(f"Error updating settings file: {str(e)}")
        return False

def main():
    print("Template Encoding Fixer")
    print("======================")
    
    # List of template files to process
    template_dir = os.path.join('templates', 'blog_templates')
    template_files = [
        os.path.join(template_dir, 'template1.html'),
        os.path.join(template_dir, 'template2.html'),
        os.path.join(template_dir, 'template3.html'),
        os.path.join(template_dir, 'template5.html'),
        os.path.join(template_dir, 'header.html'),
        os.path.join(template_dir, 'footer.html')
    ]
    
    # Process each template file
    for template_file in template_files:
        if os.path.exists(template_file):
            process_template_file(template_file)
        else:
            print(f"File not found: {template_file}")
    
    # Update Django settings
    update_django_settings()
    
    print("\nEncoding fix complete. Try running your Django server again.")

if __name__ == "__main__":
    main() 