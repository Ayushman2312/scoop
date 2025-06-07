import os
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from django.conf import settings
import sys

# Force UTF-8 encoding for all file operations
if sys.platform == 'win32':
    # Windows-specific fix for console output
    import codecs
    # Change console code page to UTF-8
    os.system('chcp 65001 > nul')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def safe_message(message):
    """Make message safe for any console by replacing problematic characters"""
    if isinstance(message, str):
        # Replace non-ASCII chars with ASCII approximations for console display
        try:
            return message.encode('ascii', 'replace').decode('ascii')
        except:
            return "[Complex Unicode Content]"
    return str(message)

class SafeFormatter(logging.Formatter):
    """Formatter that handles Unicode characters safely"""
    def format(self, record):
        # Save original message
        original_msg = record.getMessage()
        
        # Replace message with safe version for formatting
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = safe_message(record.msg)
            if record.args:
                record.args = tuple(safe_message(arg) if isinstance(arg, str) else arg 
                                  for arg in record.args)
        
        # Get formatted message
        formatted = super().format(record)
        
        # Restore original for file loggers that can handle Unicode
        record.msg = original_msg
        
        return formatted

def get_safe_console_handler():
    """Create a console handler that safely handles Unicode characters"""
    handler = logging.StreamHandler()
    formatter = SafeFormatter('%(asctime)s [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    return handler

def get_utf8_file_handler(filename):
    """Create a file handler with UTF-8 encoding"""
    try:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Create handler with explicit UTF-8 encoding
        handler = logging.FileHandler(filename, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        return handler
    except Exception as e:
        print(f"Error creating log file {filename}: {e}")
        # Fallback to a local logs directory
        try:
            if not os.path.exists('logs'):
                os.makedirs('logs')
            handler = logging.FileHandler(f"logs/fallback_{datetime.now().strftime('%Y%m%d')}.log", 
                                         encoding='utf-8')
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            return handler
        except:
            # Last resort: create a null handler that doesn't log anything
            return logging.NullHandler()

class BlogProcessLogger:
    """
    Logger class for tracking and logging the blog generation process with proper Unicode handling
    """
    def __init__(self):
        self.process_id = uuid.uuid4().hex[:10]
        self.start_time = datetime.now()
        self.steps = []
        
        # Create log directory if it doesn't exist
        logs_dir = getattr(settings, 'LOGS_DIR', Path('logs'))
        os.makedirs(logs_dir, exist_ok=True)
        
        # Main logger for console output
        self.logger = logging.getLogger(f'blog_automation_{self.process_id}')
        self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers to avoid duplication
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Add safe console handler
        self.logger.addHandler(get_safe_console_handler())
        
        # Add UTF-8 file handler
        log_file = Path(logs_dir) / f'blog_process_{datetime.now().strftime("%Y%m%d")}.log'
        self.logger.addHandler(get_utf8_file_handler(str(log_file)))
        
        # Detailed process logger (file only)
        process_log_dir = getattr(settings, 'PROCESS_LOG_DIR', Path('logs/processes'))
        os.makedirs(process_log_dir, exist_ok=True)
        
        self.process_log_path = Path(process_log_dir) / f'process_{self.process_id}.log'
        self.process_logger = logging.getLogger(f'process_{self.process_id}')
        self.process_logger.setLevel(logging.INFO)
        
        # Clear existing handlers to avoid duplication
        if self.process_logger.handlers:
            self.process_logger.handlers.clear()
        
        # Add UTF-8 file handler
        self.process_logger.addHandler(get_utf8_file_handler(str(self.process_log_path)))
        
        # Start logging
        self.info("Process started", {"process_id": self.process_id})
    
    def _safe_json_dumps(self, data):
        """Convert data to JSON string safely"""
        try:
            return json.dumps(data, ensure_ascii=False)
        except:
            # If JSON serialization fails, use a simpler representation
            try:
                # Try with ASCII encoding
                return json.dumps(data, ensure_ascii=True)
            except:
                # Last resort: convert to string
                return str(data)
    
    def info(self, message, data=None):
        """Log an info message with optional data"""
        try:
            # Create safe versions for console display
            safe_msg = safe_message(message)
            
            # Log to main logger (will handle Unicode safely via formatter)
            self.logger.info(f"[{self.process_id}] {message}")
            
            # For process logger (file), use full Unicode support
            if data:
                data_str = f" - {self._safe_json_dumps(data)}"
                self.process_logger.info(f"{message}{data_str}")
            else:
                self.process_logger.info(message)
                
        except Exception as e:
            # Fallback logging in case of errors
            print(f"Logging error: {str(e)} - Message: {safe_message(message)}")
    
    def warning(self, message, data=None):
        """Log a warning message with optional data"""
        try:
            # Log to main logger
            self.logger.warning(f"[{self.process_id}] {message}")
            
            # For process logger (file)
            if data:
                data_str = f" - {self._safe_json_dumps(data)}"
                self.process_logger.warning(f"{message}{data_str}")
            else:
                self.process_logger.warning(message)
                
        except Exception as e:
            # Fallback logging
            print(f"Logging error: {str(e)} - Message: {safe_message(message)}")
    
    def error(self, message, data=None):
        """Log an error message with optional data"""
        try:
            # Log to main logger
            self.logger.error(f"[{self.process_id}] {message}")
            
            # For process logger (file)
            if data:
                data_str = f" - {self._safe_json_dumps(data)}"
                self.process_logger.error(f"{message}{data_str}")
            else:
                self.process_logger.error(message)
                
        except Exception as e:
            # Fallback logging
            print(f"Logging error: {str(e)} - Message: {safe_message(message)}")
    
    def success(self, message, data=None):
        """Log a success message with optional data"""
        try:
            # Log to main logger
            self.logger.info(f"[{self.process_id}] SUCCESS: {message}")
            
            # For process logger (file)
            if data:
                data_str = f" - {self._safe_json_dumps(data)}"
                self.process_logger.info(f"SUCCESS: {message}{data_str}")
            else:
                self.process_logger.info(f"SUCCESS: {message}")
                
        except Exception as e:
            # Fallback logging
            print(f"Logging error: {str(e)} - Message: {safe_message(message)}")
    
    def step(self, step_id, step_name):
        """Start a new step in the process and return the step ID"""
        step = {
            'id': step_id,
            'name': step_name,
            'start_time': datetime.now().isoformat(),
            'status': 'IN_PROGRESS'
        }
        self.steps.append(step)
        self.info(f"Starting step: {step_name}", {'step_id': step_id})
        return step_id
    
    def complete_step(self, step_id, step_name, data=None):
        """Mark a step as completed"""
        for step in self.steps:
            if step['id'] == step_id:
                step['end_time'] = datetime.now().isoformat()
                step['status'] = 'COMPLETED'
                step['data'] = data
                break
        
        self.info(f"Completed step: {step_name}", {'step_id': step_id, 'data': data})
    
    def fail_step(self, step_id, step_name, reason):
        """Mark a step as failed"""
        for step in self.steps:
            if step['id'] == step_id:
                step['end_time'] = datetime.now().isoformat()
                step['status'] = 'FAILED'
                step['reason'] = reason
                break
        
        self.error(f"Failed step: {step_name}", {'step_id': step_id, 'reason': reason})
    
    def end_process(self, status, data=None):
        """End the process with a status and optional data"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        self.info(f"Process ended with status: {status}", {
            'duration_seconds': duration,
            'data': data
        })
        
        # Save final process state to JSON
        process_state = {
            'process_id': self.process_id,
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration,
            'status': status,
            'steps': self.steps,
            'data': data
        }
        
        # Save as JSON
        try:
            logs_dir = getattr(settings, 'LOGS_DIR', Path('logs'))
            os.makedirs(logs_dir, exist_ok=True)
            
            json_path = Path(logs_dir) / f'process_{self.process_id}.json'
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(process_state, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            self.error(f"Failed to save process state: {str(e)}") 