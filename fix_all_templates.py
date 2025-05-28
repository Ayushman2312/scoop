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
        except UnicodeDecodeError as e:
            print(f"  UTF-8 decode error in {filepath}: {str(e)}")
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

def find_template_files():
    """Find all HTML template files in the project"""
    template_files = []
    for root, _, files in os.walk('templates'):
        for file in files:
            if file.endswith('.html'):
                template_files.append(os.path.join(root, file))
    return template_files

def main():
    print("Comprehensive Template Encoding Fixer")
    print("===================================")
    
    # Find all template files
    template_files = find_template_files()
    print(f"Found {len(template_files)} template files to process")
    
    # Process each template file
    for template_file in template_files:
        process_template_file(template_file)
    
    print("\nEncoding fix complete. Try running your Django server again.")

if __name__ == "__main__":
    main() 