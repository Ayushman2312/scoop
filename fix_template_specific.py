import os
import logging
import re
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('template_fixer')

def fix_specific_template_encoding(template_path, problematic_positions=None):
    """
    Fix specific encoding issues in template files
    
    Args:
        template_path: Path to the template file
        problematic_positions: List of specific byte positions known to be problematic
    """
    if not os.path.exists(template_path):
        logger.error(f"Template file not found: {template_path}")
        return False
    
    try:
        # Read file in binary mode to identify problematic bytes
        with open(template_path, 'rb') as file:
            content = file.read()
        
        # If we know specific problematic positions, check them
        if problematic_positions:
            for pos in problematic_positions:
                if pos < len(content) and content[pos] == 0x9d:
                    logger.info(f"Found problematic byte 0x9d at position {pos} in {template_path}")
        
        # Process content byte by byte
        new_content = bytearray()
        problems_found = 0
        
        for i, byte in enumerate(content):
            # Check for problematic bytes (0x9d is a Windows-specific character)
            if byte == 0x9d:
                # Replace with a standard quote character
                new_content.append(ord('"'))
                problems_found += 1
                logger.info(f"Replaced byte 0x9d at position {i} with double quote")
            else:
                new_content.append(byte)
        
        if problems_found > 0:
            # Write corrected content back with UTF-8-SIG encoding
            with open(template_path, 'wb') as file:
                # First try to decode with cp1252 and encode as UTF-8
                try:
                    decoded = new_content.decode('cp1252')
                    file.write(decoded.encode('utf-8-sig'))
                    logger.info(f"Successfully fixed {problems_found} encoding issues in {template_path}")
                except UnicodeDecodeError:
                    # If cp1252 fails, just write back the modified binary
                    file.write(new_content)
                    logger.info(f"Wrote back fixed binary content for {template_path}")
            return True
        else:
            logger.info(f"No problematic bytes found in {template_path}")
            return False
            
    except Exception as e:
        logger.error(f"Error processing {template_path}: {str(e)}")
        return False

def main():
    logger.info("Template Specific Encoding Fixer")
    logger.info("==============================")
    
    # Base directory for templates
    template_dir = os.path.join('templates', 'blog_templates')
    
    # Process all template files with possible problematic positions
    templates_to_fix = {
        os.path.join(template_dir, 'template1.html'): [33439],
        os.path.join(template_dir, 'template2.html'): [33439],
        os.path.join(template_dir, 'template3.html'): [33439],
        os.path.join(template_dir, 'template5.html'): [33439]
    }
    
    for template_path, positions in templates_to_fix.items():
        if os.path.exists(template_path):
            fix_specific_template_encoding(template_path, positions)
        else:
            logger.error(f"Template file not found: {template_path}")
    
    logger.info("Specific encoding fix completed")

if __name__ == "__main__":
    main() 