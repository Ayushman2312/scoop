import os
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from django.conf import settings

class BlogProcessLogger:
    """
    Process logger for blog automation process
    Provides structured logging with steps, timing, and error handling
    """
    
    def __init__(self):
        self.logger = logging.getLogger('blog_automation')
        self.process_logger = logging.getLogger('blog.process')
        self.process_id = str(int(time.time()))
        self.start_time = time.time()
        self.steps = {}
        self.current_step = None
        
        # Create logs directory if it doesn't exist
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        
        # Create automation_structured.log for backward compatibility
        self.json_log_path = logs_dir / 'automation_structured.log'
        
        # Create process specific log file
        process_log_dir = logs_dir / 'blog_process'
        process_log_dir.mkdir(exist_ok=True)
        self.process_log_path = process_log_dir / f'blog_process_{self.process_id}.log'
        
        self.process_logger.info(f"PROCESS STARTED\nData: {{\n  \"process_id\": \"{self.process_id}\",\n  \"timestamp\": \"{datetime.now().isoformat()}\"\n}}")
    
    def _log_to_json(self, log_entry):
        """
        Append a log entry to the JSON log file
        """
        try:
            log_entry['timestamp'] = datetime.now().isoformat()
            log_entry['process_id'] = self.process_id
            
            with open(self.json_log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
                
            # Also log to process-specific file
            with open(self.process_log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            self.logger.error(f"Error writing to JSON log: {e}")
    
    def info(self, message, data=None):
        """
        Log an info message
        """
        self.logger.info(f"[{self.process_id}] {message}")
        
        # Format data as JSON string if present
        data_str = ""
        if data:
            data_str = f"\nData: {{\n  " + ",\n  ".join([f"\"{k}\": {json.dumps(v)}" for k, v in data.items()]) + "\n}}"
        
        self.process_logger.info(f"{message}{data_str}")
        
        log_entry = {
            'level': 'INFO',
            'message': message
        }
        
        if data:
            log_entry['data'] = data
            
        self._log_to_json(log_entry)
    
    def warning(self, message, data=None):
        """
        Log a warning message
        """
        self.logger.warning(f"[{self.process_id}] {message}")
        
        # Format data as JSON string if present
        data_str = ""
        if data:
            data_str = f"\nData: {{\n  " + ",\n  ".join([f"\"{k}\": {json.dumps(v)}" for k, v in data.items()]) + "\n}}"
        
        self.process_logger.warning(f"{message}{data_str}")
        
        log_entry = {
            'level': 'WARNING',
            'message': message
        }
        
        if data:
            log_entry['data'] = data
            
        self._log_to_json(log_entry)
    
    def error(self, message, data=None):
        """
        Log an error message
        """
        self.logger.error(f"[{self.process_id}] {message}")
        
        # Format data as JSON string if present
        data_str = ""
        if data:
            data_str = f"\nData: {{\n  " + ",\n  ".join([f"\"{k}\": {json.dumps(v)}" for k, v in data.items()]) + "\n}}"
        
        self.process_logger.error(f"{message}{data_str}")
        
        log_entry = {
            'level': 'ERROR',
            'message': message
        }
        
        if data:
            log_entry['data'] = data
            
        self._log_to_json(log_entry)
    
    def step(self, step_id, step_name):
        """
        Begin a new step in the process
        
        Returns:
            str: The step ID for use with complete_step
        """
        self.current_step = step_id
        step_start_time = time.time()
        
        self.steps[step_id] = {
            'name': step_name,
            'start_time': step_start_time,
            'status': 'IN_PROGRESS'
        }
        
        self.info(f"Starting step: {step_name}", {
            'step_id': step_id,
            'step_name': step_name
        })
        
        return step_id
    
    def complete_step(self, step_id, step_name, data=None):
        """
        Complete a step
        """
        if step_id in self.steps:
            step = self.steps[step_id]
            step['end_time'] = time.time()
            step['duration'] = step['end_time'] - step['start_time']
            step['status'] = 'COMPLETED'
            
            if data:
                step['data'] = data
            
            self.info(f"Completed step: {step_name} in {step['duration']:.2f}s", {
                'step_id': step_id,
                'step_name': step_name,
                'duration': step['duration'],
                'data': data
            })
            
            if step_id == self.current_step:
                self.current_step = None
    
    def fail_step(self, step_id, step_name, error_message):
        """
        Mark a step as failed
        """
        if step_id in self.steps:
            step = self.steps[step_id]
            step['end_time'] = time.time()
            step['duration'] = step['end_time'] - step['start_time']
            step['status'] = 'FAILED'
            step['error'] = error_message
            
            self.error(f"Failed step: {step_name} - {error_message}", {
                'step_id': step_id,
                'step_name': step_name,
                'duration': step['duration'],
                'error': error_message
            })
            
            if step_id == self.current_step:
                self.current_step = None
    
    def success(self, message, data=None):
        """
        Log a success message
        """
        self.logger.info(f"[{self.process_id}] SUCCESS: {message}")
        
        log_entry = {
            'level': 'SUCCESS',
            'message': message
        }
        
        if data:
            log_entry['data'] = data
            
        self._log_to_json(log_entry)
    
    def end_process(self, status, data=None):
        """
        End the current process
        """
        duration = time.time() - self.start_time
        
        log_message = f"Process {self.process_id} {status} in {duration:.2f}s"
        if status == 'COMPLETED':
            self.success(log_message, data)
        else:
            self.error(log_message, data)
        
        # Log a summary of all steps
        steps_summary = {}
        for step_id, step in self.steps.items():
            steps_summary[step_id] = {
                'name': step.get('name'),
                'status': step.get('status'),
                'duration': step.get('duration')
            }
        
        self._log_to_json({
            'level': 'SUMMARY',
            'message': f"Process summary for {self.process_id}",
            'process_id': self.process_id,
            'duration': duration,
            'status': status,
            'steps': steps_summary,
            'data': data
        }) 