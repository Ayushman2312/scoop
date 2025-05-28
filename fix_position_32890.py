import os
import sys

def find_and_fix_byte_at_position(filepath, position=32890):
    """Find and fix the problematic byte at a specific position"""
    try:
        filesize = os.path.getsize(filepath)
        if filesize < position:
            # File is too small to have a character at this position
            return False
            
        with open(filepath, 'rb') as file:
            content = file.read()
            
        # Check the byte at the specified position
        problem_byte = content[position - 1]
        print(f"Byte at position {position} in {filepath}: 0x{problem_byte:02x}")
        
        # Check if it's a problematic byte (0x9d)
        if problem_byte == 0x9d:
            print(f"Found problematic byte 0x9d at position {position} in {filepath}")
            
            # Replace with a space
            content = content[:position-1] + b' ' + content[position:]
            
            with open(filepath, 'wb') as file:
                file.write(content)
                
            print(f"Fixed problematic byte in {filepath}")
            return True
            
        return False
        
    except Exception as e:
        print(f"Error processing {filepath}: {str(e)}")
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

def main():
    print("Problematic Byte Fixer for Position 32890")
    print("=======================================")
    
    # Find all template files
    template_files = find_template_files()
    print(f"Found {len(template_files)} template files to check")
    
    # Track files with issues
    fixed_files = []
    
    # Process each template file
    for template_file in template_files:
        print(f"Checking {template_file}...")
        if find_and_fix_byte_at_position(template_file):
            fixed_files.append(template_file)
    
    # Report results
    if fixed_files:
        print(f"\nFixed {len(fixed_files)} files:")
        for file in fixed_files:
            print(f"  - {file}")
    else:
        print("\nNo files needed fixing at position 32890.")
    
    print("\nProcess complete. Try running your Django server again.")

if __name__ == "__main__":
    main() 