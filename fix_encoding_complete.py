import os
import sys

def fix_encoding_issues(filepath):
    """Fix encoding issues in a file by reading in binary and writing as UTF-8"""
    try:
        # Read file in binary mode
        with open(filepath, 'rb') as file:
            content = file.read()
            
        # Try to decode with different encodings
        for encoding in ['utf-8', 'cp1252', 'latin-1']:
            try:
                decoded = content.decode(encoding)
                print(f"  Successfully decoded {filepath} with {encoding}")
                
                # Replace problematic characters
                decoded = decoded.replace('\u2018', "'")  # Left single quote
                decoded = decoded.replace('\u2019', "'")  # Right single quote
                decoded = decoded.replace('\u201c', '"')  # Left double quote
                decoded = decoded.replace('\u201d', '"')  # Right double quote
                decoded = decoded.replace('\u2013', '-')  # En dash
                decoded = decoded.replace('\u2014', '--')  # Em dash
                decoded = decoded.replace('\u2026', '...')  # Ellipsis
                
                # Write back with UTF-8 encoding
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(decoded)
                    
                print(f"  Fixed encoding for {filepath}")
                return True
            except UnicodeDecodeError:
                continue
                
        # If no encoding worked, try using 'replace' error handler
        try:
            decoded = content.decode('utf-8', errors='replace')
            
            # Write back with UTF-8 encoding
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(decoded)
                
            print(f"  Fixed {filepath} using replacement characters")
            return True
        except Exception as e:
            print(f"  Error using replacement method: {str(e)}")
            return False
            
    except Exception as e:
        print(f"  Error processing {filepath}: {str(e)}")
        return False

def fix_specific_positions(filepath, positions=[31802, 32890]):
    """Fix specific problematic bytes at the given positions"""
    try:
        filesize = os.path.getsize(filepath)
        smallest_pos = min(positions)
        if filesize < smallest_pos:
            return False  # File too small
            
        with open(filepath, 'rb') as file:
            content = file.read()
            
        fixed = False
        for pos in positions:
            if filesize >= pos:
                # Check byte at position
                byte_value = content[pos-1]
                if byte_value == 0x9d:
                    print(f"  Found problematic byte 0x9d at position {pos} in {filepath}")
                    # Replace with space
                    content = content[:pos-1] + b' ' + content[pos:]
                    fixed = True
                    
        if fixed:
            # Write back the modified content
            with open(filepath, 'wb') as file:
                file.write(content)
                
            print(f"  Fixed specific problematic bytes in {filepath}")
            return True
            
        return False
        
    except Exception as e:
        print(f"  Error fixing specific positions in {filepath}: {str(e)}")
        return False

def find_template_files():
    """Find all HTML template files in the project"""
    template_files = []
    
    # Search in templates directory
    for root, _, files in os.walk('templates'):
        for file in files:
            if file.endswith('.html'):
                template_files.append(os.path.join(root, file))
                
    # Also check static directory if it exists
    if os.path.exists('static'):
        for root, _, files in os.walk('static'):
            for file in files:
                if file.endswith('.html'):
                    template_files.append(os.path.join(root, file))
    
    return template_files

def update_django_settings():
    """Update Django settings.py to ensure proper encoding and fix any syntax issues"""
    settings_path = os.path.join('blogify', 'settings.py')
    if not os.path.exists(settings_path):
        print("Settings file not found")
        return False
        
    try:
        with open(settings_path, 'r', encoding='utf-8') as file:
            content = file.read()
            
        # Check if FILE_CHARSET is already defined
        if 'FILE_CHARSET' not in content:
            # Add encoding settings after USE_TZ
            if 'USE_TZ = True' in content:
                content = content.replace(
                    'USE_TZ = True',
                    'USE_TZ = True\n\n# File encoding settings\nFILE_CHARSET = \'utf-8\'\nDEFAULT_CHARSET = \'utf-8\''
                )
                
                with open(settings_path, 'w', encoding='utf-8') as file:
                    file.write(content)
                    
                print("Added explicit charset settings to Django settings")
                
        # Fix Gemini API key if needed
        if 'GEMINI_API_KEY =' in content and 'os.environ.get' not in content:
            content = content.replace(
                'GEMINI_API_KEY =',
                'GEMINI_API_KEY = os.environ.get(\'GEMINI_API_KEY\', \'\')'
            )
            
            with open(settings_path, 'w', encoding='utf-8') as file:
                file.write(content)
                
            print("Fixed GEMINI_API_KEY setting")
            
        return True
            
    except Exception as e:
        print(f"Error updating settings file: {str(e)}")
        return False

def main():
    print("Comprehensive Encoding and Template Fixer")
    print("=======================================")
    
    # Update Django settings
    update_django_settings()
    
    # Find template files
    template_files = find_template_files()
    print(f"Found {len(template_files)} template files to process")
    
    # Process each file
    for template_file in template_files:
        print(f"Processing {template_file}...")
        
        # First try to fix encoding issues
        fix_encoding_issues(template_file)
        
        # Then check and fix specific byte positions
        fix_specific_positions(template_file)
    
    print("\nFix complete. Try running your Django server again.")

if __name__ == "__main__":
    main() 