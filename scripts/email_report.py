import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv
from scripts.load_config import load_config

REPORT_FILE = "reports/daily_report.txt"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def load_report():
    if not os.path.exists(REPORT_FILE):
        raise FileNotFoundError(f"No existe el reporte: {REPORT_FILE}")
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def send_email(subject, body, email_user, email_password, email_to):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = email_to

    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(email_user, email_password)
        server.sendmail(email_user, email_to, msg.as_string())


def main():
    load_dotenv()
    cfg = load_config()

    if not cfg.get("email_enabled", True):
        print("Email desactivado en config.json — omitiendo.")
        return

    email_user     = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_to       = cfg.get("email_to") or os.getenv("EMAIL_TO")

    if not all([email_user, email_password, email_to]):
        raise ValueError("Faltan credenciales (EMAIL_USER, EMAIL_PASSWORD) o email_to en config.json")

    print(f"Enviando reporte a: {email_to}")
    report_body = load_report()
    date_str    = datetime.now().strftime("%Y-%m-%d")
    subject     = f"Reporte Diario de Mercado — {date_str}"
    send_email(subject, report_body, email_user, email_password, email_to)
    print("Email enviado correctamente.")


if __name__ == "__main__":
    main()
