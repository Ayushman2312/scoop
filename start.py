#!/usr/bin/env python
"""
Startup script for Blogify
Runs all required components (Django server, Celery worker, Celery beat)
"""
import os
import sys
import time
import signal
import subprocess
import atexit
from pathlib import Path

# Define colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Initialize process list
processes = []

def log(message, color=Colors.BLUE):
    """Print a colored message to the console"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"{color}[{timestamp}] {message}{Colors.ENDC}")

def cleanup():
    """Terminate all running processes"""
    log("Shutting down all processes...", Colors.YELLOW)
    for process in processes:
        if process.poll() is None:  # If process is still running
            process.terminate()
            log(f"Terminated process PID: {process.pid}", Colors.YELLOW)
    log("All processes terminated", Colors.GREEN)

def signal_handler(sig, frame):
    """Handle Ctrl+C"""
    log("Received interrupt signal, shutting down...", Colors.RED)
    cleanup()
    sys.exit(0)

def check_redis():
    """Check if Redis is running"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        return True
    except:
        return False

def check_requirements():
    """Check if all required components are available"""
    # Check if virtual environment is activated
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        log("Virtual environment not activated! Please activate your virtual environment first.", Colors.RED)
        log("Example: source venv/bin/activate (Linux/Mac) or venv\\Scripts\\activate (Windows)", Colors.YELLOW)
        return False
    
    # Check if Redis is running
    if not check_redis():
        log("Redis is not running! Please start Redis before running this script.", Colors.RED)
        log("You can start Redis with: redis-server", Colors.YELLOW)
        return False
    
    # Check if .env file exists
    if not Path('.env').exists():
        log(".env file not found! Please create a .env file with your API keys.", Colors.RED)
        log("See README.md for instructions.", Colors.YELLOW)
        return False
    
    # Check if migrations are applied
    try:
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings')
        django.setup()
        from django.db import connections
        from django.db.utils import OperationalError
        conn = connections['default']
        try:
            conn.cursor()
        except OperationalError:
            log("Database connection failed! Please check your database settings.", Colors.RED)
            return False
    except Exception as e:
        log(f"Django setup error: {e}", Colors.RED)
        return False
    
    return True

def start_django():
    """Start the Django development server"""
    log("Starting Django development server...", Colors.GREEN)
    process = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "0.0.0.0:8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    processes.append(process)
    return process

def start_celery_worker():
    """Start the Celery worker"""
    log("Starting Celery worker...", Colors.GREEN)
    process = subprocess.Popen(
        ["celery", "-A", "blogify", "worker", "--loglevel=info"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    processes.append(process)
    return process

def start_celery_beat():
    """Start the Celery beat scheduler"""
    log("Starting Celery beat scheduler...", Colors.GREEN)
    process = subprocess.Popen(
        ["celery", "-A", "blogify", "beat", "--loglevel=info"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    processes.append(process)
    return process

def monitor_processes():
    """Monitor the output of all processes"""
    process_outputs = {
        'django': {'process': start_django(), 'name': 'Django', 'color': Colors.GREEN},
        'worker': {'process': start_celery_worker(), 'name': 'Celery Worker', 'color': Colors.BLUE},
        'beat': {'process': start_celery_beat(), 'name': 'Celery Beat', 'color': Colors.YELLOW}
    }
    
    log("All processes started! Monitoring output...", Colors.GREEN)
    log(f"{Colors.BOLD}Press Ctrl+C to stop all processes{Colors.ENDC}", Colors.YELLOW)
    
    # Create directories if they don't exist
    Path('logs').mkdir(exist_ok=True)
    
    try:
        while True:
            for key, details in process_outputs.items():
                process = details['process']
                if process.poll() is not None:
                    log(f"{details['name']} process exited with code {process.returncode}!", Colors.RED)
                    return
                
                while True:
                    output = process.stdout.readline()
                    if output:
                        timestamp = time.strftime("%H:%M:%S")
                        print(f"{details['color']}[{timestamp}][{details['name']}] {output.strip()}{Colors.ENDC}")
                    else:
                        break
            
            time.sleep(0.1)
    except KeyboardInterrupt:
        log("Received keyboard interrupt", Colors.YELLOW)
        cleanup()

def main():
    """Main function"""
    log(f"{Colors.BOLD}Starting Blogify{Colors.ENDC}", Colors.HEADER)
    
    # Register cleanup handlers
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Check requirements
    if not check_requirements():
        log("Requirements check failed. Please fix the issues and try again.", Colors.RED)
        return
    
    # Start all processes and monitor them
    monitor_processes()

if __name__ == "__main__":
    main() 