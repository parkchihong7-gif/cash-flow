@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   셀럽오르빗 설치
echo ================================================
set PY=
py -3.11 --version >nul 2>nul && set PY=py -3.11
if not defined PY py -3 --version >nul 2>nul && set PY=py -3
if not defined PY python --version >nul 2>nul && set PY=python
if not defined PY (
  echo [!] 파이썬이 없습니다. python.org 에서 3.11 이상을 설치하고
  echo     설치 첫 화면의 "Add python.exe to PATH" 를 꼭 체크하세요.
  pause
  exit /b 1
)
echo 사용할 파이썬: %PY%
if not exist .venv (
  echo 가상환경을 만듭니다...
  %PY% -m venv .venv || goto fail
)
echo 필요한 프로그램을 설치합니다 (몇 분 걸립니다)...
.venv\Scripts\python -m pip install --upgrade pip >nul
.venv\Scripts\python -m pip install -r ..\..\requirements.txt -r requirements.txt || goto fail
if not exist ..\..\.env if exist .env.example copy .env.example ..\..\.env >nul
where ffmpeg >nul 2>nul
if not %errorlevel%==0 (
  echo [참고] FFmpeg 가 아직 없습니다. 영상 만들기 단계에서 필요합니다.
  echo        winget install Gyan.FFmpeg  로 설치할 수 있습니다.
)
echo.
echo 설치가 끝났습니다. 실행.bat 을 더블클릭하세요.
pause
exit /b 0
:fail
echo [!] 설치 중 오류가 났습니다. 위 메시지를 캡처해 보내 주세요.
pause
exit /b 1
