import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('template_fixer')

def fix_template_encoding(template_path):
    """
    Fix encoding issues in template files by replacing problematic bytes
    
    Args:
        template_path: Path to the template file
    """
    if not os.path.exists(template_path):
        logger.error(f"Template file not found: {template_path}")
        return False
    
    try:
        # Read file in binary mode to identify problematic bytes
        with open(template_path, 'rb') as file:
            content = file.read()
        
        # Process content byte by byte
        new_content = bytearray()
        problems_found = 0
        
        # Track positions of problematic bytes
        problematic_positions = []
        
        for i, byte in enumerate(content):
            # Check for problematic bytes (0x9d is a Windows-specific character)
            if byte == 0x9d:
                # Replace with a standard quote character
                new_content.append(ord('"'))
                problems_found += 1
                problematic_positions.append(i)
            else:
                new_content.append(byte)
        
        if problems_found > 0:
            logger.info(f"Found {problems_found} problematic bytes at positions: {problematic_positions}")
            
            # Try different encodings to decode the content properly
            encodings_to_try = ['cp1252', 'latin-1', 'iso-8859-1']
            decoded_content = None
            
            for encoding in encodings_to_try:
                try:
                    decoded_content = new_content.decode(encoding)
                    logger.info(f"Successfully decoded using {encoding}")
                    break
                except UnicodeDecodeError:
                    continue
            
            if decoded_content:
                # Write corrected content back with UTF-8-SIG encoding
                with open(template_path, 'w', encoding='utf-8-sig') as file:
                    file.write(decoded_content)
                logger.info(f"Successfully fixed {problems_found} encoding issues in {template_path}")
                return True
            else:
                # If no encoding worked, just write back the binary
                with open(template_path, 'wb') as file:
                    file.write(new_content)
                logger.info(f"Wrote back fixed binary content for {template_path}")
                return True
        else:
            logger.info(f"No problematic bytes found in {template_path}")
            return False
            
    except Exception as e:
        logger.error(f"Error processing {template_path}: {str(e)}")
        return False

def scan_for_problematic_bytes(directory, extension='.html'):
    """
    Scan all files with the given extension in the directory for problematic bytes
    
    Args:
        directory: Directory to scan
        extension: File extension to look for
    """
    found_issues = False
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(extension):
                file_path = os.path.join(root, file)
                logger.info(f"Checking {file_path}...")
                
                if fix_template_encoding(file_path):
                    found_issues = True
    
    return found_issues

def main():
    logger.info("Template Encoding Fixer - Scanning for 0x9d bytes")
    logger.info("=================================================")
    
    # Scan all template directories
    directories_to_scan = [
        os.path.join('templates'),
        os.path.join('templates', 'blog_templates'),
        os.path.join('templates', 'blog'),
        os.path.join('templates', 'admin')
    ]
    
    issues_found = False
    
    for directory in directories_to_scan:
        if os.path.exists(directory):
            logger.info(f"Scanning directory: {directory}")
            if scan_for_problematic_bytes(directory):
                issues_found = True
        else:
            logger.warning(f"Directory not found: {directory}")
    
    if issues_found:
        logger.info("Fixed encoding issues in one or more files")
    else:
        logger.info("No encoding issues found in any files")

if __name__ == "__main__":
    main() 