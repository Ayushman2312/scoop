@echo off
REM Set UTF-8 console mode
chcp 65001 > nul

echo ======================================================
echo    FIXING AND STARTING BLOG AUTOMATION SYSTEM
echo ======================================================
echo.

REM Change to the project directory
cd /d %~dp0

REM Install required packages including the new ones
echo Installing required packages...
pip install -r requirements.txt

REM Create logs directory if it doesn't exist
if not exist logs mkdir logs

REM Kill any existing Celery processes
echo Stopping any existing Celery processes...
taskkill /f /im celery.exe 2>nul
timeout /t 2 /nobreak >nul

REM Run the diagnostic script to verify the setup
echo Running diagnostics...
python diagnose_automation.py

echo.
echo Press any key to start the blog automation system...
pause >nul

REM Start the improved blog automation system
echo Starting the reliable blog automation system...
start cmd /k "chcp 65001 > nul && run_reliable_blog_automation.bat"

echo.
echo Blog automation system is now running in a separate window.
echo.
echo REMEMBER: If you want to manually test blog generation, you can run:
echo python force_generate_blog.py
echo.

pause 