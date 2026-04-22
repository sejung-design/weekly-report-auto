@echo off
cd /d "C:\Users\Sejung Oh\Downloads\2026\01_BMS\12_Design Center\Weekly Report Auto"
python scripts\preview_report.py
if %errorlevel% neq 0 (
    echo.
    echo 오류가 발생했습니다. 위 메시지를 확인해주세요.
    pause
)
