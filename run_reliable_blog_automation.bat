@echo off
setlocal enabledelayedexpansion

REM Set UTF-8 console mode
chcp 65001 > nul

echo.
echo ======================================================
echo    RELIABLE BLOG AUTOMATION SYSTEM
echo ======================================================
echo This will run a robust blog publishing system that
echo creates a new blog every 5 minutes with error handling
echo.
echo Available blog templates:
echo  - Evergreen: comprehensive pillar content
echo  - Trend: timely content on trending topics
echo  - Comparison: reviews and product comparisons
echo  - Local: location-specific content
echo  - How-To: step-by-step tutorials and guides
echo.

REM Change to the project directory
cd /d %~dp0

REM Check if the virtual environment exists
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo No virtual environment found, using system Python
)

REM Kill any existing Celery processes to ensure clean start
echo Stopping any existing Celery processes...
taskkill /f /im celery.exe 2>nul
timeout /t 2 /nobreak >nul

REM Verify required API keys are set
echo Checking required API keys...
python -c "import os; from django.conf import settings; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings'); import django; django.setup(); missing = []; gemini_key = getattr(settings, 'GEMINI_API_KEY', None); serp_key = getattr(settings, 'SERPAPI_API_KEY', None); if not gemini_key: missing.append('GEMINI_API_KEY'); if not serp_key: missing.append('SERPAPI_API_KEY'); print(','.join(missing))" > api_check.txt

set /p MISSING_KEYS=<api_check.txt
del api_check.txt

if not "!MISSING_KEYS!"=="" (
    echo ERROR: Missing required API keys: !MISSING_KEYS!
    echo Please configure these keys in your settings.py file
    echo and try again.
    pause
    exit /b 1
)

echo All required API keys are configured.

REM Verify database connection
echo Checking database connection...
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings'); import django; django.setup(); from blog.models import TrendingTopic; print(TrendingTopic.objects.count())" > db_check.txt

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Database connection failed. Please check your database settings.
    pause
    exit /b 1
)

echo Database connection successful.
del db_check.txt

REM Create separate console windows for each component (with UTF-8 encoding)
echo Starting Celery worker with increased concurrency...
start "Celery Worker" cmd /k "chcp 65001 > nul && celery -A blogify worker --loglevel=INFO --concurrency=6 -O fair"

REM Wait for worker to initialize
timeout /t 5 /nobreak >nul

echo Starting Celery beat scheduler...
start "Celery Beat" cmd /k "chcp 65001 > nul && celery -A blogify beat --loglevel=INFO"

REM Wait for beat to initialize
timeout /t 2 /nobreak >nul

echo.
echo ======================================================
echo Blog automation system is now running!
echo.
echo - Celery worker is processing tasks with 6 workers
echo - Celery beat is scheduling tasks every 5 minutes
echo.
echo To force generate a blog on a specific topic, run:
echo python force_generate_blog.py --topic "Your Topic" --template "evergreen|trend|comparison|local|how_to"
echo.
echo DO NOT CLOSE THIS WINDOW or the processes will continue
echo running in the background. Press Ctrl+C to stop all
echo processes when you want to shut down the system.
echo ======================================================
echo.

REM Monitor for problems and restart if needed
:monitor_loop
timeout /t 30 /nobreak >nul

REM Check if worker is still running
tasklist /fi "windowtitle eq Celery Worker" | find "cmd.exe" > nul
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Celery worker appears to have stopped. Restarting...
    start "Celery Worker" cmd /k "chcp 65001 > nul && celery -A blogify worker --loglevel=INFO --concurrency=6 -O fair"
)

REM Check if beat is still running
tasklist /fi "windowtitle eq Celery Beat" | find "cmd.exe" > nul
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Celery beat appears to have stopped. Restarting...
    start "Celery Beat" cmd /k "chcp 65001 > nul && celery -A blogify beat --loglevel=INFO"
)

goto monitor_loop

REM This section will run when the user presses Ctrl+C
:end
echo Stopping all Celery processes...
taskkill /f /im celery.exe
echo Blog automation stopped.
pause
endlocal 