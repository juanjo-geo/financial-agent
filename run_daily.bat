@echo off
cd /d C:\financial-agent
.venv\Scripts\python.exe scripts\run_daily.py >> logs\run_daily.log 2>&1
