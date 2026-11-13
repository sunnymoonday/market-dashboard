@echo off
cd /d "%~dp0"
python update_data.py
start "" "%~dp0index.html"
