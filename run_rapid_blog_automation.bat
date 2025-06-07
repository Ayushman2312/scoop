@echo off
echo Starting Rapid Blog Automation System...
echo This will run the Celery worker and beat scheduler to publish a new blog every 5 minutes
echo.

REM Change to the project directory if needed
cd /d %~dp0

REM Activate virtual environment if using one
REM call venv\Scripts\activate.bat

REM Run the automation script
python run_blog_automation.py

echo.
echo Blog automation stopped.
pause 