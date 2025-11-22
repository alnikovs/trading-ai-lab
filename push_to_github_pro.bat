@echo off
setlocal
TITLE Push Local Changes to GitHub (AI Quant Fund)

cd /d C:\Bot\trading-ai-lab

echo ==========================================
echo   Push Local Changes to GitHub
echo ==========================================
echo.

git status

echo.
set /p COMMIT_MSG=Enter commit message (empty = cancel): 

if "%COMMIT_MSG%"=="" (
    echo.
    echo No commit message. Aborting.
    echo.
    pause
    goto :END
)

echo.
echo Adding all changes...
git add .

echo.
echo Committing...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo.
    echo Commit failed (maybe nothing to commit).
    echo.
    pause
    goto :END
)

echo.
echo Pushing to origin/main...
git push

echo.
echo Done.
pause

:END
endlocal
