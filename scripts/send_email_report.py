"""
send_email_report.py
--------------------
Lee reports/daily_report.txt y lo envía por email vía Gmail SMTP.
Requiere GMAIL_APP_PASSWORD en el archivo .env del proyecto.

Uso: python -m scripts.send_email_report
     (desde la raíz del proyecto: C:\\Users\\Juan Jose\\financial-agent)
"""

import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ── Configuración ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GMAIL_USER     = "jjgrillom98@gmail.com"
GMAIL_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")  # App Password (espacios ignorados)

RECIPIENTS = [
    "jjgrillom98@gmail.com",
    "juan.grillo@atento.com",
]

REPORT_PATH = BASE_DIR / "reports" / "daily_report.txt"

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_report() -> str:
    """Lee el reporte generado por Claude."""
    if not REPORT_PATH.exists():
        raise FileNotFoundError(f"No se encontró el reporte en {REPORT_PATH}")
    return REPORT_PATH.read_text(encoding="utf-8")


def build_message(body: str) -> MIMEMultipart:
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"Reporte Diario de Mercado — {today}"

    msg = MIMEMultipart("alternative")
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(RECIPIENTS)
    msg["Subject"] = subject

    # Versión texto plano
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Versión HTML básica (preserva saltos de línea)
    html_body = "<html><body><pre style='font-family:Arial,sans-serif;font-size:14px;line-height:1.6'>"
    html_body += body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_body += "</pre></body></html>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    return msg


def send_email(msg: MIMEMultipart) -> None:
    """Envía el email vía Gmail SMTP con TLS."""
    if not GMAIL_PASSWORD:
        raise ValueError(
            "GMAIL_APP_PASSWORD no encontrada en .env. "
            "Genera una App Password en https://myaccount.google.com/apppasswords"
        )

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENTS, msg.as_string())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Iniciando envío de reporte...")

    try:
        body = read_report()
        print(f"  ✓ Reporte leído ({len(body)} caracteres)")

        msg = build_message(body)
        print(f"  ✓ Email preparado para: {', '.join(RECIPIENTS)}")

        send_email(msg)
        print(f"  ✓ Email enviado exitosamente a {len(RECIPIENTS)} destinatarios")

    except FileNotFoundError as e:
        print(f"  ✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"  ✗ Configuración: {e}", file=sys.stderr)
        sys.exit(1)
    except smtplib.SMTPAuthenticationError:
        print("  ✗ Error de autenticación. Verifica que GMAIL_APP_PASSWORD sea correcta.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"  ✗ Error inesperado: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
