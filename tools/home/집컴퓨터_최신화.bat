@echo off
chcp 65001 > nul
REM ============================================================
REM  집 컴퓨터 최신화 — 밖에서 고친 것을 받아 옵니다.
REM
REM  바탕화면에 바로가기를 만들어 두고 집에 오시면 한 번 누르세요.
REM  받아 오기 → 라이브러리 맞추기 → 확인용 화면 다시 만들기 까지 합니다.
REM
REM  고객 자료(data\dashboard.db)는 **건드리지 않습니다.**
REM  그 파일은 이 컴퓨터에만 있고 저장소에 올라가지 않습니다.
REM ============================================================
setlocal
cd /d "%~dp0\..\.."

echo.
echo   [1/4] 밖에서 고친 것을 받아 옵니다
echo   ----------------------------------------
git fetch origin
if errorlevel 1 goto :net

REM 내 컴퓨터에서 고친 것이 있으면 덮어쓰지 않고 멈춘다.
git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
    echo.
    echo   [!] 이 컴퓨터에서 고친 것이 있습니다.
    echo       덮어쓰면 사라지므로 멈춥니다.
    echo.
    git status --short
    echo.
    echo       그대로 두시려면  : git stash
    echo       버리셔도 되면    : git checkout .
    echo.
    goto :end
)

for /f "tokens=*" %%b in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%b
git pull --ff-only origin %BRANCH%
if errorlevel 1 (
    echo.
    echo   [!] 자동으로 합칠 수 없습니다. 갈라진 것 같습니다.
    echo       Claude 에게 "집 컴퓨터가 갈라졌어" 라고 말씀하세요.
    goto :end
)

echo.
echo   [2/4] 라이브러리를 맞춥니다
echo   ----------------------------------------
python -m pip install -q -r requirements.txt
if errorlevel 1 echo   [!] 라이브러리 설치에 실패했습니다. 파이썬이 깔려 있는지 보세요.

echo.
echo   [3/4] 확인용 화면을 다시 만듭니다
echo   ----------------------------------------
python -m dashboard.snapshot --out dashboard-snapshot --single "대시보드_확인용.html"
if errorlevel 1 echo   [!] 화면 만들기에 실패했습니다.

echo.
echo   [4/4] 끝났습니다
echo   ----------------------------------------
echo.
echo   확인용 한 장  : 대시보드_확인용.html  (더블클릭)
echo   실제로 쓰시려면: 대시보드_열기.bat
echo.
goto :end

:net
echo.
echo   [!] 인터넷에 못 붙었습니다. 연결을 확인하고 다시 눌러 주세요.

:end
pause
endlocal
