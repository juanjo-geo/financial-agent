@echo off
:: send_email.bat
:: Envia el reporte diario de mercado por Gmail SMTP.
:: Configurar en Windows Task Scheduler a las 7:40 AM (lunes a viernes).

cd /d "C:\Users\Juan Jose\financial-agent"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul 2>&1
call .venv\Scripts\activate.bat
python -m scripts.send_email_report >> logs\email_send.log 2>&1
