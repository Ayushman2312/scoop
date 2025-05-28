import os
import re

def fix_encoding(filepath):
    try:
        # Read the file in binary mode
        with open(filepath, 'rb') as file:
            content = file.read()
        
        # Try to decode using different encodings
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                # Decode using the encoding
                decoded = content.decode(encoding)
                print(f"Successfully decoded {filepath} with {encoding}")
                
                # Replace problematic characters - smart quotes and other special characters
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
                
                print(f"Fixed encoding for {filepath}")
                return True
            except UnicodeDecodeError:
                continue
        
        print(f"Could not decode {filepath} with any of the attempted encodings")
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {str(e)}")
        return False

def main():
    template_dir = os.path.join('templates', 'blog_templates')
    template_files = [
        os.path.join(template_dir, 'template1.html'),
        os.path.join(template_dir, 'template2.html'),
        os.path.join(template_dir, 'template3.html'),
        os.path.join(template_dir, 'template5.html'),
        os.path.join(template_dir, 'header.html'),
        os.path.join(template_dir, 'footer.html')
    ]
    
    for template_file in template_files:
        if os.path.exists(template_file):
            print(f"Processing {template_file}...")
            fix_encoding(template_file)
        else:
            print(f"File not found: {template_file}")

if __name__ == "__main__":
    main() 