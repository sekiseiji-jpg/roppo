@echo off
cd /d "%~dp0"
echo.
echo   六法全書 を起動しました
echo   ---------------------------------------------
echo   このPC:  http://localhost:8770/
echo   終了するにはこのウィンドウを閉じてください
echo   ---------------------------------------------
echo.
start "" "http://localhost:8770/"
python -m http.server 8770
