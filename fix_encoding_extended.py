import os
import codecs

def find_problematic_byte(filepath, position=31802):
    try:
        with open(filepath, 'rb') as file:
            content = file.read()
            if len(content) >= position:
                problematic_byte = content[position]
                print(f"Byte at position {position} in {filepath}: 0x{problematic_byte:02x}")
                
                # Check some bytes around the problematic position
                start = max(0, position - 20)
                end = min(len(content), position + 20)
                surrounding = content[start:end]
                
                try:
                    # Try to decode surrounding text
                    print(f"Context around problematic byte (Latin-1 encoding):")
                    print(surrounding.decode('latin-1'))
                except:
                    print("Could not decode surrounding bytes with Latin-1")
                
                return True
            else:
                print(f"File {filepath} is too short (length {len(content)}, needed {position})")
                return False
    except Exception as e:
        print(f"Error examining {filepath}: {str(e)}")
        return False

def fix_encoding_with_ignore(filepath):
    try:
        # Read the file in binary mode
        with open(filepath, 'rb') as file:
            content = file.read()
        
        # Decode with 'replace' error handler to replace invalid chars
        decoded = content.decode('utf-8', errors='replace')
        
        # Replace the Unicode replacement character with appropriate substitutes
        decoded = decoded.replace('\ufffd', '') 
        
        # Write back with UTF-8 encoding
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(decoded)
        
        print(f"Fixed encoding for {filepath} using 'replace' method")
        return True
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
    
    # First, try to find the problematic byte in all files
    for template_file in template_files:
        if os.path.exists(template_file):
            print(f"Examining {template_file} for problematic byte...")
            find_problematic_byte(template_file)
    
    # Then fix all files
    for template_file in template_files:
        if os.path.exists(template_file):
            print(f"Processing {template_file}...")
            fix_encoding_with_ignore(template_file)
        else:
            print(f"File not found: {template_file}")

if __name__ == "__main__":
    main() 