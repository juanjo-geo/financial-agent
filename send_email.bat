@echo off
cd /d "C:\Users\Juan Jose\financial-agent"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul 2>&1
.venv\Scripts\python.exe -m scripts.send_email_report >> logs\email_send.log 2>&1
