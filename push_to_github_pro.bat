@echo off
setlocal
TITLE AI Quant Fund - AUTO PUSH

cd /d C:\Bot\trading-ai-lab

echo ==========================================
echo   AI Quant Fund - AUTO PUSH LOCAL CHANGES
echo ==========================================
echo.

echo Checking Git status...
git status

echo.
echo Switching to main branch...
git checkout main >nul 2>&1

echo.
echo Pulling latest main from origin...
git pull origin main

echo.
echo Staging all changed files...
git add .

echo.
echo Creating auto-commit message...

for /f "tokens=1-3 delims=./ " %%a in ("%date%") do (
    set DD=%%a
    set MM=%%b
    set YYYY=%%c
)

for /f "tokens=1 delims=." %%a in ("%time%") do set HHMMSS=%%a

set COMMIT_MSG=Auto-commit %YYYY%-%MM%-%DD% %HHMMSS%

echo Commit message:
echo   %COMMIT_MSG%
echo.

echo Committing (if there is something new)...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo.
    echo No new changes to commit OR commit failed.
    echo Continuing to push any existing local commits...
    echo.
)

echo.
echo Pushing to origin/main...
git push origin main

echo.
echo ==========================================
echo   AUTO PUSH COMPLETE
echo ==========================================
echo.

echo Press any key to exit...
pause >nul

endlocal
