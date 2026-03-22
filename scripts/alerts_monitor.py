import json
import os
import smtplib
import time
import requests
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from twilio.rest import Client
import yfinance as yf

from scripts.load_config import load_config

ROOT            = Path(__file__).parent.parent
SIGNALS_FILE    = ROOT / "data/signals/daily_signals.json"
ALERTS_LOG_FILE = ROOT / "data/signals/alerts_log.json"

SYMBOLS = {
    "brent":  {"symbol": "BZ=F",    "unit": "USD/bbl", "news_query": "oil price crude brent"},
    "btc":    {"symbol": "BTC-USD", "unit": "USD",     "news_query": "bitcoin BTC crypto"},
    "usdcop": {"symbol": "COP=X",   "unit": "COP/USD", "news_query": "peso colombiano dolar COP"},
    "gold":   {"symbol": "GC=F",    "unit": "USD/oz",  "news_query": "gold price XAU"},
}

CHECK_INTERVAL = 30 * 60   # segundos
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587

_SEP = "-" * 50


# ── Precio e noticias ─────────────────────────────────────────────────────────

def fetch_price(symbol):
    """Retorna (precio_actual, precio_apertura) usando datos intradía de 1 minuto."""
    ticker = yf.Ticker(symbol)
    hist   = ticker.history(period="1d", interval="1m")
    if hist.empty:
        return None, None
    return float(hist["Close"].iloc[-1]), float(hist["Open"].iloc[0])


def fetch_news(query, api_key):
    """Busca el titular más reciente. Intenta español primero, luego inglés."""
    if not api_key:
        return None
    url = "https://newsapi.org/v2/everything"
    for lang in ("es", "en"):
        try:
            params = {
                "q": query, "language": lang,
                "sortBy": "publishedAt", "pageSize": 1, "apiKey": api_key,
            }
            resp     = requests.get(url, params=params, timeout=10)
            articles = resp.json().get("articles", [])
            if articles:
                a = articles[0]
                return f"{a['title']} — {a['source']['name']}"
        except Exception:
            pass
    return None


# ── Señales del agente ────────────────────────────────────────────────────────

def load_daily_signals() -> dict:
    """Lee daily_signals.json. Retorna {} si no existe o falla."""
    if not SIGNALS_FILE.exists():
        return {}
    try:
        with open(SIGNALS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── Constructores de mensaje ──────────────────────────────────────────────────

def build_alert_email(
    indicator: str,
    current: float,
    open_price: float,
    change_pct: float,
    unit: str,
    news: str | None,
    signals: dict,
) -> tuple[str, str]:
    """
    Retorna (subject, body) del email de alerta con contexto de señales.
    """
    sign      = "+" if change_pct >= 0 else ""
    direction = "SUBE" if change_pct > 0 else "BAJA"
    ind_upper = indicator.upper()

    s    = signals.get("senales", {})
    i    = signals.get("interpretacion", {})
    gen  = signals.get("generado_en", "")

    riesgo    = s.get("riesgo_macro",           "N/A")
    sesgo     = s.get("sesgo_mercado",          "N/A")
    inflacion = s.get("presion_inflacionaria",  "N/A")
    cop       = s.get("presion_cop",            "N/A")
    conv      = s.get("conviccion",             "N/A")

    driver_p  = i.get("driver_principal",  "")
    lect_cruz = i.get("lectura_cruzada",   "")
    cierre    = i.get("cierre_ejecutivo",  "")

    subject = (
        f"Alerta {ind_upper} {sign}{change_pct:.1f}% | "
        f"Riesgo {riesgo} | Sesgo {sesgo}"
    )

    body_parts = [
        f"ALERTA FINANCIERA - {ind_upper} {sign}{change_pct:.1f}%",
        f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "VARIACION DE MERCADO",
        _SEP,
        f"{ind_upper} {direction} {sign}{change_pct:.2f}% vs apertura del dia",
        f"Valor actual    : {current:,.2f} {unit}",
        f"Precio apertura : {open_price:,.2f} {unit}",
    ]

    if signals:
        body_parts += [
            "",
            f"SENALES DEL AGENTE (generadas: {gen})",
            _SEP,
            f"  Riesgo Macro          : {riesgo}",
            f"  Sesgo de Mercado      : {sesgo}",
            f"  Presion Inflacionaria : {inflacion}",
            f"  Presion COP           : {cop}",
            f"  Conviccion            : {conv}/10",
        ]

    if driver_p or lect_cruz or cierre:
        body_parts += ["", "LECTURA DEL AGENTE", _SEP]
        if driver_p:
            body_parts += ["Driver principal:", f"  {driver_p}", ""]
        if lect_cruz:
            body_parts += ["Lectura cruzada:", f"  {lect_cruz}", ""]
        if cierre:
            body_parts += ["Cierre ejecutivo:", f"  {cierre}"]

    if news:
        body_parts += ["", "NOTICIA RELACIONADA", _SEP, f"  {news}"]

    return subject, "\n".join(body_parts)


def build_whatsapp_alert(
    indicator: str,
    change_pct: float,
    signals: dict,
) -> str:
    """
    Mensaje compacto para WhatsApp de alerta con contexto de señales.
    Formato de ejemplo:
        Alerta BRENT +4.2%
        Riesgo: Medio | Sesgo: Mixto
        Driver: El Brent subio...
        El entorno macro se presenta...
    """
    sign     = "+" if change_pct >= 0 else ""
    ind_up   = indicator.upper()

    s = signals.get("senales", {})
    i = signals.get("interpretacion", {})

    riesgo = s.get("riesgo_macro",  "N/A")
    sesgo  = s.get("sesgo_mercado", "N/A")
    driver = i.get("driver_principal", "")
    cierre = i.get("cierre_ejecutivo", "")

    # Truncar driver a ~110 chars para mantener el mensaje compacto
    if len(driver) > 110:
        driver = driver[:107].rstrip() + "..."

    # Primera oracion del cierre ejecutivo
    cierre_short = cierre.split(".")[0].strip() + "." if cierre else ""
    if len(cierre_short) > 120:
        cierre_short = cierre_short[:117].rstrip() + "..."

    lines = [f"Alerta {ind_up} {sign}{change_pct:.1f}%"]

    if riesgo != "N/A" or sesgo != "N/A":
        lines.append(f"Riesgo: {riesgo} | Sesgo: {sesgo}")

    if driver:
        lines.append(f"Driver: {driver}")

    if cierre_short:
        lines.append(cierre_short)

    return "\n".join(lines)


# ── Log de alertas ────────────────────────────────────────────────────────────

def save_alert_log(
    indicator: str,
    change_pct: float,
    current: float,
    open_price: float,
    unit: str,
    signals: dict,
    news: str | None,
    channels_ok: list[str],
) -> None:
    """Agrega la alerta al final de alerts_log.json (lista de objetos)."""
    s = signals.get("senales", {})
    i = signals.get("interpretacion", {})

    entry = {
        "timestamp":             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indicator":             indicator,
        "change_pct":            round(change_pct, 2),
        "current":               round(current, 4),
        "open_price":            round(open_price, 4),
        "unit":                  unit,
        "riesgo_macro":          s.get("riesgo_macro",           ""),
        "sesgo_mercado":         s.get("sesgo_mercado",          ""),
        "presion_inflacionaria": s.get("presion_inflacionaria",  ""),
        "presion_cop":           s.get("presion_cop",            ""),
        "conviccion":            s.get("conviccion",             0),
        "driver_principal":      i.get("driver_principal",       ""),
        "cierre_ejecutivo":      i.get("cierre_ejecutivo",       ""),
        "news":                  news or "",
        "channels":              channels_ok,
    }

    ALERTS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if ALERTS_LOG_FILE.exists():
        try:
            with open(ALERTS_LOG_FILE, encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []
    else:
        log = []

    log.append(entry)

    with open(ALERTS_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


# ── Envío ─────────────────────────────────────────────────────────────────────

def send_email(subject, body, email_user, email_password, email_to):
    msg            = MIMEMultipart("alternative")
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


# ── Despacho ──────────────────────────────────────────────────────────────────

def dispatch_alert(indicator, current, open_price, change_pct, config, env):
    news    = fetch_news(config["news_query"], env["news_api_key"])
    signals = load_daily_signals()

    subject, email_body = build_alert_email(
        indicator, current, open_price, change_pct, config["unit"], news, signals
    )
    wa_msg = build_whatsapp_alert(indicator, change_pct, signals)

    channels_ok: list[str] = []

    # Email
    try:
        send_email(subject, email_body, env["email_user"], env["email_password"], env["email_to"])
        print(f"    [OK] Email enviado a {env['email_to']}")
        channels_ok.append("email")
    except Exception as e:
        print(f"    [ERR] Email: {e}")

    # WhatsApp
    if env.get("account_sid") and env.get("from_number") and env.get("to_number"):
        try:
            send_whatsapp(
                wa_msg,
                env["account_sid"], env["auth_token"],
                env["from_number"], f"+{env['to_number']}",
            )
            print(f"    [OK] WhatsApp enviado a +{env['to_number']}")
            channels_ok.append("whatsapp")
        except Exception as e:
            print(f"    [ERR] WhatsApp: {e}")

    save_alert_log(
        indicator, change_pct, current, open_price,
        config["unit"], signals, news, channels_ok,
    )
    print(f"    [OK] Alerta guardada en alerts_log.json")


# ── Env ───────────────────────────────────────────────────────────────────────

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


# ── Monitor loop ──────────────────────────────────────────────────────────────

def main():
    env = load_env()
    cfg = load_config()

    if not cfg.get("alerts_enabled", True):
        print("Alertas desactivadas en config.json — monitor no iniciado.")
        return

    alert_threshold = cfg.get("alert_threshold", 4.0)

    # indicator -> fecha en que se envio la ultima alerta (1 por indicador por dia)
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

        next_check = datetime.now().strftime("%H:%M:%S")
        print(f"\n  Proxima revision en 30 min. (ahora son las {next_check})\n")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
