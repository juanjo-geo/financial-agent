import os
import time
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
from dotenv import load_dotenv
import yfinance as yf
from twilio.rest import Client
from scripts.load_config import load_config

SYMBOLS = {
    "brent": {"symbol": "BZ=F",     "unit": "USD/bbl", "news_query": "oil price crude brent"},
    "btc":   {"symbol": "BTC-USD",  "unit": "USD",     "news_query": "bitcoin BTC crypto"},
    "usdcop":{"symbol": "COP=X",    "unit": "COP/USD", "news_query": "peso colombiano dolar COP"},
}

CHECK_INTERVAL  = 30 * 60  # segundos

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def fetch_price(symbol):
    """Retorna (precio_actual, precio_apertura) usando datos intradía de 1 minuto."""
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d", interval="1m")
    if hist.empty:
        return None, None
    current    = float(hist["Close"].iloc[-1])
    open_price = float(hist["Open"].iloc[0])
    return current, open_price


def fetch_news(query, api_key):
    """Busca la noticia más reciente relacionada. Intenta español primero, luego inglés."""
    if not api_key:
        return None
    url = "https://newsapi.org/v2/everything"
    for lang in ("es", "en"):
        try:
            params = {
                "q": query,
                "language": lang,
                "sortBy": "publishedAt",
                "pageSize": 1,
                "apiKey": api_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            articles = resp.json().get("articles", [])
            if articles:
                a = articles[0]
                return f"{a['title']} — {a['source']['name']}"
        except Exception:
            pass
    return None


def build_alert_message(indicator, current, open_price, change_pct, unit, news):
    direction = "SUBE" if change_pct > 0 else "BAJA"
    sign = "+" if change_pct > 0 else ""
    lines = [
        f"ALERTA FINANCIERA — {indicator.upper()}",
        f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"{indicator.upper()} {direction} {sign}{change_pct:.2f}% vs apertura del dia",
        f"Valor actual : {current:,.2f} {unit}",
        f"Precio apertura: {open_price:,.2f} {unit}",
    ]
    if news:
        lines += ["", "Noticia relacionada:", news]
    return "\n".join(lines)


def send_email(subject, body, email_user, email_password, email_to):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = email_user
    msg["To"]      = email_to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(email_user, email_password)
        server.sendmail(email_user, email_to, msg.as_string())


def send_whatsapp(message, account_sid, auth_token, from_number, to_number):
    client = Client(account_sid, auth_token)
    client.messages.create(
        from_=f"whatsapp:{from_number}",
        to=f"whatsapp:{to_number}",
        body=message,
    )


def dispatch_alert(indicator, current, open_price, change_pct, config, env):
    news = fetch_news(config["news_query"], env["news_api_key"])
    body = build_alert_message(indicator, current, open_price, change_pct, config["unit"], news)

    sign    = "+" if change_pct > 0 else ""
    subject = f"ALERTA: {indicator.upper()} {sign}{change_pct:.2f}% vs apertura"

    # Email
    try:
        send_email(subject, body, env["email_user"], env["email_password"], env["email_to"])
        print(f"    [OK] Email enviado a {env['email_to']}")
    except Exception as e:
        print(f"    [ERR] Email: {e}")

    # WhatsApp
    try:
        send_whatsapp(
            body,
            env["account_sid"], env["auth_token"],
            env["from_number"], f"+{env['to_number']}",
        )
        print(f"    [OK] WhatsApp enviado a +{env['to_number']}")
    except Exception as e:
        print(f"    [ERR] WhatsApp: {e}")


def load_env():
    load_dotenv()
    return {
        "email_user":     os.getenv("EMAIL_USER"),
        "email_password": os.getenv("EMAIL_PASSWORD"),
        "email_to":       os.getenv("EMAIL_TO"),
        "news_api_key":   os.getenv("NEWS_API_KEY"),
        "account_sid":    os.getenv("TWILIO_ACCOUNT_SID"),
        "auth_token":     os.getenv("TWILIO_AUTH_TOKEN"),
        "from_number":    os.getenv("TWILIO_WHATSAPP_FROM"),
        "to_number":      os.getenv("WHATSAPP_TO"),
    }


def main():
    env = load_env()
    cfg = load_config()

    if not cfg.get("alerts_enabled", True):
        print("Alertas desactivadas en config.json — monitor no iniciado.")
        return

    alert_threshold = cfg.get("alert_threshold", 4.0)

    # indicator -> fecha en que se envió la última alerta (1 alerta por indicador por día)
    alerted_today: dict[str, date] = {}

    print("=" * 50)
    print("FINANCIAL AGENT — MONITOR DE ALERTAS EN TIEMPO REAL")
    print("=" * 50)
    print(f"Indicadores : {', '.join(SYMBOLS.keys())}")
    print(f"Umbral      : +/- {alert_threshold}%")
    print(f"Intervalo   : cada 30 minutos")
    print(f"Inicio      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50 + "\n")

    while True:
        today = date.today()
        # Limpiar alertas de días anteriores
        alerted_today = {k: v for k, v in alerted_today.items() if v == today}

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Revisando precios...")

        for indicator, config in SYMBOLS.items():
            if alerted_today.get(indicator) == today:
                print(f"  {indicator:8s}: alerta ya enviada hoy, omitiendo.")
                continue

            try:
                current, open_price = fetch_price(config["symbol"])

                if current is None or open_price is None or open_price == 0:
                    print(f"  {indicator:8s}: sin datos disponibles.")
                    continue

                change_pct = ((current - open_price) / open_price) * 100
                sign = "+" if change_pct >= 0 else ""
                print(f"  {indicator:8s}: {current:>12,.2f} {config['unit']}  |  {sign}{change_pct:.2f}% vs apertura")

                if abs(change_pct) >= alert_threshold:
                    print(f"  {'':8s}  *** ALERTA DETECTADA — despachando notificaciones ***")
                    dispatch_alert(indicator, current, open_price, change_pct, config, env)
                    alerted_today[indicator] = today

            except Exception as e:
                print(f"  {indicator:8s}: ERROR — {e}")

        next_check = datetime.now().strftime('%H:%M:%S')
        print(f"\n  Próxima revisión en 30 min. (ahora son las {next_check})\n")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
