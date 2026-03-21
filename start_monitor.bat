@echo off
cd /d C:\financial-agent
start "FinancialAgent_Monitor" /MIN .venv\Scripts\python.exe scripts\alerts_monitor.py >> logs\alerts_monitor.log 2>&1
echo Monitor iniciado. Log: logs\alerts_monitor.log
