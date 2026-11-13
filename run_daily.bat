@echo off
rem 작업 스케줄러용: 데이터만 갱신하고 결과를 update.log 에 남깁니다 (브라우저는 열지 않음)
chcp 65001 >nul
cd /d "%~dp0"
echo ==== %date% %time% ==== >> update.log
"C:\Users\carfe\AppData\Local\Programs\Python\Python312\python.exe" update_data.py >> update.log 2>&1
