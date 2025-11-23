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
echo Checking for local changes...
git diff --quiet
if %errorlevel%==0 (
    echo ------------------------------------------
    echo No local changes detected. Nothing to push.
    echo ------------------------------------------
    echo.
    pause
    goto END
)

echo ------------------------------------------
echo Local changes detected:
echo ------------------------------------------
git status
echo.

echo Staging all changed files...
git add .

echo.
echo Creating auto-commit message...
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do (
    set YYYY=%%c
    set MM=%%a
    set DD=%%b
)
for /f "tokens=1 delims= " %%a in ("%time%") do set HHMMSS=%%a

set COMMIT_MSG=Auto-commit %YYYY%-%MM%-%DD% %HHMMSS%

echo Commit message:
echo   %COMMIT_MSG%
echo.

echo Committing...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo.
    echo Commit failed (maybe nothing to commit).
    echo.
    pause
    goto END
)

echo.
echo Pushing to origin/main...
git push origin main

echo.
echo ==========================================
echo   AUTO PUSH COMPLETE
echo ==========================================
echo.
pause

:END
endlocal
