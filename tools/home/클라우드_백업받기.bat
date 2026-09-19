@echo off
chcp 65001 > nul
REM ============================================================
REM  클라우드 → 집 컴퓨터 백업
REM
REM  클라우드에 올린 대시보드에서 고객 DB 를 한 벌 받아
REM  이 컴퓨터의 data\backup\ 에 날짜를 붙여 저장합니다.
REM
REM  왜 필요한가
REM    고객 이름·이메일·발급한 키가 전부 클라우드에만 있습니다.
REM    호스팅 계정이 잠기거나 디스크를 잘못 지우면 판 키의 목록이
REM    통째로 사라집니다. 받아 둔 파일이 있으면 되살릴 수 있습니다.
REM
REM  처음 한 번만
REM    같은 폴더의 클라우드주소.txt 에 두 줄을 적어 두세요.
REM      1줄: https://내주소.onrender.com
REM      2줄: 접속 코드
REM    이 파일은 저장소에 올라가지 않습니다(.gitignore).
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0\..\.."

set "CONF=tools\home\클라우드주소.txt"
if not exist "%CONF%" goto :noconf

set /a N=0
for /f "usebackq delims=" %%L in ("%CONF%") do (
    set /a N+=1
    if !N!==1 set "URL=%%L"
    if !N!==2 set "CODE=%%L"
)
if "%URL%"=="" goto :noconf
if "%CODE%"=="" goto :noconf

REM 끝에 붙은 / 를 떼어 낸다. 안 그러면 주소가 //backup.db 가 된다.
if "%URL:~-1%"=="/" set "URL=%URL:~0,-1%"

for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set "STAMP=%%T"
set "OUT=data\backup\dashboard-%STAMP%.db"
if not exist "data\backup" mkdir "data\backup"

echo.
echo   클라우드에서 받아 옵니다
echo   ----------------------------------------
echo   주소 : %URL%
echo   저장 : %OUT%
echo.

REM 접속 코드로 먼저 들어가서 쿠키를 받고, 그 쿠키로 파일을 받는다.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "try {" ^
  "  $s = New-Object Microsoft.PowerShell.Commands.WebRequestSession;" ^
  "  Invoke-WebRequest -Uri '%URL%/login' -Method Post -WebSession $s" ^
  "    -Body @{code='%CODE%'} -UseBasicParsing | Out-Null;" ^
  "  Invoke-WebRequest -Uri '%URL%/backup.db' -WebSession $s" ^
  "    -OutFile '%OUT%' -UseBasicParsing;" ^
  "  exit 0" ^
  "} catch { Write-Host ('   [!] ' + $_.Exception.Message); exit 1 }"

if errorlevel 1 goto :failed
if not exist "%OUT%" goto :failed

REM SQLite 파일은 'SQLite format 3' 으로 시작한다. 로그인 화면(HTML)을
REM 받아 놓고 백업받았다고 믿는 일이 없게 여기서 확인한다.
powershell -NoProfile -Command ^
  "$b=[System.IO.File]::ReadAllBytes('%OUT%');" ^
  "if ($b.Length -lt 100 -or [Text.Encoding]::ASCII.GetString($b[0..12]) -ne 'SQLite format') { exit 1 }"
if errorlevel 1 goto :notdb

for %%F in ("%OUT%") do set "SIZE=%%~zF"
echo   받았습니다. %SIZE% 바이트
echo.
echo   되살리실 때는 이 파일을 data\dashboard.db 로 덮어쓰시면 됩니다.
echo   (덮어쓰기 전에 대시보드를 꺼 주세요)
echo.
goto :end

:noconf
echo.
echo   [!] tools\home\클라우드주소.txt 가 없거나 비어 있습니다.
echo.
echo       메모장으로 그 이름의 파일을 만들고 두 줄을 적으세요.
echo         1줄: https://내주소.onrender.com
echo         2줄: 접속 코드
echo.
goto :end

:notdb
echo.
echo   [!] 받은 파일이 DB 가 아닙니다. 접속 코드가 틀렸을 때 이렇게 됩니다.
echo       클라우드주소.txt 의 2줄을 확인해 주세요.
echo.
del "%OUT%" 2> nul
goto :end

:failed
echo.
echo   [!] 받지 못했습니다. 주소가 맞는지, 클라우드가 켜져 있는지 보세요.
echo.

:end
pause
endlocal
