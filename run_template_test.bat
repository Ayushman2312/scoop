@echo off
echo Running Template Selection Test...
echo.

python test_template_selection.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Template Selection Test Completed Successfully!
) else (
    echo.
    echo Template Selection Test Failed with Error Code: %ERRORLEVEL%
)

echo.
echo Press any key to close...
pause > nul 