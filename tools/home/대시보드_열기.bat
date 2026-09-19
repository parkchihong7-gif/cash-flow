@echo off
chcp 65001 > nul
REM ============================================================
REM  통합 관리자 대시보드 열기 — 실제로 쓰는 화면입니다.
REM
REM  이 창을 띄워 둔 채로 쓰세요. 창을 닫으면 화면도 닫힙니다.
REM  같은 집 안(같은 공유기)에서는 다른 기기로도 들어올 수 있습니다.
REM ============================================================
setlocal
cd /d "%~dp0\..\.."

if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" > nul
        echo   [i] .env 를 만들었습니다. Claude API 키는 나중에 넣으셔도 됩니다.
    )
)

echo.
echo   대시보드를 띄웁니다. 잠시만요...
echo.
echo   이 컴퓨터에서 : http://127.0.0.1:8000
for /f "tokens=14" %%i in ('ipconfig ^| findstr /c:"IPv4"') do (
    echo   같은 집 안에서: http://%%i:8000
    goto :done
)
:done
echo.
echo   창을 닫으면 화면도 닫힙니다.
echo.
start "" http://127.0.0.1:8000
python -m dashboard
pause
endlocal
