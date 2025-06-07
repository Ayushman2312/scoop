@echo off
setlocal enabledelayedexpansion

echo.
echo ======================================================
echo    BLOG AUTOMATION DIAGNOSTIC AND REPAIR TOOL
echo ======================================================
echo This tool will diagnose and fix common issues with 
echo the blog automation system.
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

REM Install required packages
echo Checking and installing required packages...
pip install -r requirements.txt > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install required packages. Please check your internet connection.
    goto :end
) else (
    echo Required packages installed successfully.
)

REM Check API keys
echo Checking API keys...
python -c "import os; from django.conf import settings; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings'); import django; django.setup(); missing = []; gemini_key = getattr(settings, 'GEMINI_API_KEY', None); serp_key = getattr(settings, 'SERPAPI_API_KEY', None); if not gemini_key: missing.append('GEMINI_API_KEY'); if not serp_key: missing.append('SERPAPI_API_KEY'); print(','.join(missing))" > api_check.txt

set /p MISSING_KEYS=<api_check.txt
del api_check.txt

if not "!MISSING_KEYS!"=="" (
    echo ERROR: Missing required API keys: !MISSING_KEYS!
    echo.
    echo Please configure these keys in your settings.py file:
    echo.
    
    if "!MISSING_KEYS!"=="GEMINI_API_KEY" (
        echo 1. Get a Gemini API key from: https://ai.google.dev/
        echo 2. Add this line to your settings.py file:
        echo    GEMINI_API_KEY = 'your_api_key_here'
    )
    
    if "!MISSING_KEYS!"=="SERPAPI_API_KEY" (
        echo 1. Get a SerpAPI key from: https://serpapi.com/
        echo 2. Add this line to your settings.py file:
        echo    SERPAPI_API_KEY = 'your_api_key_here'
    )
    
    if "!MISSING_KEYS!"=="GEMINI_API_KEY,SERPAPI_API_KEY" (
        echo 1. Get a Gemini API key from: https://ai.google.dev/
        echo 2. Get a SerpAPI key from: https://serpapi.com/
        echo 3. Add these lines to your settings.py file:
        echo    GEMINI_API_KEY = 'your_gemini_api_key_here'
        echo    SERPAPI_API_KEY = 'your_serpapi_key_here'
    )
    
    goto :ask_continue
) else (
    echo All required API keys are configured.
)

REM Check database connection
echo Checking database connection...
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings'); import django; django.setup(); from blog.models import TrendingTopic; print(TrendingTopic.objects.count())" > db_check.txt

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Database connection failed. 
    echo Please check your database settings in settings.py.
    goto :ask_continue
) else (
    echo Database connection successful.
    del db_check.txt
)

REM Kill any existing Celery processes
echo Stopping any existing Celery processes...
taskkill /f /im celery.exe 2>nul
timeout /t 2 /nobreak >nul

REM Check for trending topics
echo Checking for trending topics...
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings'); import django; django.setup(); from blog.models import TrendingTopic; from django.utils import timezone; from datetime import timedelta; recent = TrendingTopic.objects.filter(timestamp__gte=timezone.now()-timedelta(hours=24)).count(); print(recent)" > topics_check.txt

set /p RECENT_TOPICS=<topics_check.txt
del topics_check.txt

if "%RECENT_TOPICS%"=="0" (
    echo No recent trending topics found. Attempting to fetch new topics...
    python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings'); import django; django.setup(); from blog.tasks import fetch_trending_topics; fetch_trending_topics()"
    
    REM Check if fetch was successful
    python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blogify.settings'); import django; django.setup(); from blog.models import TrendingTopic; from django.utils import timezone; from datetime import timedelta; recent = TrendingTopic.objects.filter(timestamp__gte=timezone.now()-timedelta(hours=24)).count(); print(recent)" > topics_check.txt
    
    set /p RECENT_TOPICS=<topics_check.txt
    del topics_check.txt
    
    if "%RECENT_TOPICS%"=="0" (
        echo WARNING: Failed to fetch trending topics. 
        echo This could be due to API limits or network issues.
        echo The system will fall back to default topics.
    ) else (
        echo Successfully fetched %RECENT_TOPICS% trending topics.
    )
) else (
    echo Found %RECENT_TOPICS% recent trending topics.
)

:ask_fix
echo.
echo What would you like to do?
echo 1. Run diagnostics only
echo 2. Try to generate a blog post now (test pipeline)
echo 3. Start reliable blog automation system
echo 4. Exit
echo.

set /p ACTION=Enter your choice (1-4): 

if "%ACTION%"=="1" (
    echo Running full diagnostics...
    python diagnose_automation.py
    goto :ask_continue
)

if "%ACTION%"=="2" (
    echo Attempting to generate a blog post...
    python force_generate_blog.py
    goto :ask_continue
)

if "%ACTION%"=="3" (
    echo Starting reliable blog automation system...
    start cmd /k run_reliable_blog_automation.bat
    echo Blog automation system started in a new window.
    goto :end
)

if "%ACTION%"=="4" (
    goto :end
) else (
    echo Invalid choice. Please try again.
    goto :ask_fix
)

:ask_continue
echo.
echo Would you like to return to the main menu? (Y/N)
set /p CONTINUE=

if /i "%CONTINUE%"=="Y" goto :ask_fix

:end
echo.
echo Diagnostic and repair completed.
pause
endlocal 