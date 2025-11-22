@echo off
TITLE Push Local Changes to GitHub (SAFE - Never closes)

echo ==========================================
echo   Push Local Changes to GitHub (SAFE MODE)
echo ==========================================
echo.

REM Prevent auto-close on any exit
setlocal EnableExtensions

REM Go to project folder
cd /d C:\Bot\trading-ai-lab

echo Checking Git repository...
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: This folder is NOT a Git repository.
    echo Path checked: C:\Bot\trading-ai-lab
    echo.
    goto END
)

echo.
echo Current repo status:
echo ------------------------------------------
git status
echo ------------------------------------------
echo.

for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD') do set CURRENT_BRANCH=%%B
echo Current branch: %CURRENT_BRANCH%
echo.

echo Choose mode:
echo   1 ) Commit + push to current branch (%CURRENT_BRANCH%)
echo   2 ) Create a new branch and push it (PR flow)
echo.

set /p mode=Enter mode number (1 or 2): 

if "%mode%"=="2" goto CREATE_BRANCH
if "%mode%"=="1" goto SAME_BRANCH

echo Invalid choice. Using option 1 by default.
goto SAME_BRANCH


:SAME_BRANCH
echo.
echo Mode: commit + push to %CURRENT_BRANCH%
goto ASK_COMMIT


:CREATE_BRANCH
echo.
set /p NEWBRANCH=Enter new branch name: 
if "%NEWBRANCH%"=="" (
    echo Empty branch name. Aborting.
    goto END
)

git checkout -b "%NEWBRANCH%"
if errorlevel 1 (
    echo ERROR: Failed to create new branch.
    goto END
)
set CURRENT_BRANCH=%NEWBRANCH%
goto ASK_COMMIT


:ASK_COMMIT
echo.
set /p commitmsg=Enter commit message (leave empty for auto): 
if "%commitmsg%"=="" (
    set commitmsg=Auto commit %date% %time%
)

echo Using commit message:
echo "%commitmsg%"
echo.

echo Adding files...
git add .

echo Committing...
git commit -m "%commitmsg%"
if errorlevel 1 (
    echo.
    echo WARNING: Nothing to commit or commit failed.
    echo.
    goto END
)

echo.
echo Pushing changes...
git push -u origin %CURRENT_BRANCH%
if errorlevel 1 (
    echo.
    echo ERROR: Git push failed.
    echo Check your network, SSH keys or permissions.
    echo.
    goto END
)

echo.
echo ==========================================
echo   SUCCESS! Changes pushed to GitHub.
echo ==========================================
echo.
goto END


:END
echo.
echo Press ANY KEY to close this window...
pause >nul
exit /b 0
