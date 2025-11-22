@echo off
TITLE Push Local Changes to GitHub (PRO)

echo ==========================================
echo   Push Local Changes to GitHub (PRO)
echo   Project: AI Quant Fund
echo ==========================================
echo.

REM Переходим в папку проекта
cd /d C:\Bot\trading-ai-lab

REM Проверяем, что это git-репозиторий
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo Ошибка: это не git-репозиторий.
    echo Проверь путь C:\Bot\trading-ai-lab
    echo.
    pause
    exit /b 1
)

echo Текущий статус репозитория:
echo ------------------------------------------
git status
echo ------------------------------------------
echo.

REM Показываем текущую ветку
for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD') do set CURRENT_BRANCH=%%B
echo Текущая ветка: %CURRENT_BRANCH%
echo.

echo Выберите режим:
echo   1 ^) Commit + push в текущую ветку (%CURRENT_BRANCH%)
echo   2 ^) Создать новую ветку и push туда (для PR)
echo.

set /p mode=Введите номер режима (1 или 2) и нажмите Enter: 

if "%mode%"=="2" goto create_branch
if "%mode%"=="1" goto same_branch

echo Неверный выбор. По умолчанию: режим 1 (текущая ветка).
goto same_branch


:ask_commit_msg
echo.
set /p commitmsg=Введите сообщение коммита (или оставьте пустым для авто): 

if "%commitmsg%"=="" (
    echo Сообщение не задано, генерирую авто-коммит...
    for /f "tokens=1-4 delims=.:-/ " %%a in ("%date% %time%") do (
        set YY=%%d
        set MM=%%b
        set DD=%%c
        set HH=%%e
        set MI=%%f
    )
    set commitmsg=Auto: update %YY%-%MM%-%DD% %HH%:%MI%
)

echo.
echo Используется сообщение коммита:
echo   "%commitmsg%"
echo.
goto do_commit


:same_branch
echo.
echo Режим: commit + push в текущую ветку: %CURRENT_BRANCH%
goto ask_commit_msg


:create_branch
echo.
echo Режим: создать новую ветку от %CURRENT_BRANCH% и push туда.
set /p NEWBRANCH=Введите имя новой ветки (например: devflow-simple-ma-1): 

if "%NEWBRANCH%"=="" (
    echo Имя ветки не задано. Отмена.
    echo.
    pause
    exit /b 1
)

echo.
echo Создаю новую ветку: %NEWBRANCH%
git checkout -b "%NEWBRANCH%"
if errorlevel 1 (
    echo Ошибка при создании ветки. Отмена.
    echo.
    pause
    exit /b 1
)
set CURRENT_BRANCH=%NEWBRANCH%
goto ask_commit_msg


:do_commit
echo Добавляю все изменения: git add .
git add .

echo.
echo Делаю commit...
git commit -m "%commitmsg%"
if errorlevel 1 (
    echo.
    echo ВОЗМОЖНО: нет изменений для коммита ^(nothing to commit^).
    echo Проверяю статус...
    echo.
    git status
    echo.
    pause
    exit /b 1
)

echo.
echo Отправляю ветку "%CURRENT_BRANCH%" на origin: git push -u origin %CURRENT_BRANCH%
git push -u origin %CURRENT_BRANCH%
if errorlevel 1 (
    echo.
    echo Ошибка при git push.
    echo Проверь подключение к интернету и права к репозиторию.
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   ГОТОВО! Изменения отправлены.
echo ==========================================
echo.

echo Текущая ветка: %CURRENT_BRANCH%
echo Репозиторий: https://github.com/alnikovs/trading-ai-lab
echo.

if not "%CURRENT_BRANCH%"=="main" (
    echo Ветка НЕ main. Можно открыть PR:
    echo   Ссылка для PR (сравнение с main):
    echo   https://github.com/alnikovs/trading-ai-lab/compare/main...%CURRENT_BRANCH%?expand=1
    echo.
) else (
    echo Изменения в main. На сервере достаточно сделать:
    echo   cd C:\Bot\trading-ai-lab
    echo   git pull
    echo   restart_orchestrator.bat  ^(или вручную uvicorn^)
    echo.
)

pause
exit /b 0
