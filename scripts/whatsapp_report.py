import json
import os
from datetime import datetime

from dotenv import load_dotenv
from twilio.rest import Client

from scripts.load_config import load_config

REPORT_FILE  = "reports/daily_report.txt"
SIGNALS_FILE = "data/signals/daily_signals.json"


# ── Construcción determinística del mensaje ───────────────────────────────────

def _icon_riesgo(v: str) -> str:
    return {"Bajo": "✅", "Medio": "⚠️", "Alto": "🔴"}.get(v, "⚠️")

def _icon_sesgo(v: str) -> str:
    return {"Risk-on": "📈", "Mixto": "↔️", "Risk-off": "📉"}.get(v, "↔️")

def _icon_infl(v: str) -> str:
    return {"Bajista": "🟢", "Neutral": "⚪", "Alcista": "🔺"}.get(v, "⚪")

def _icon_cop(v: str) -> str:
    return {"Favorable COP": "🟢", "Neutral": "⚪", "Alcista USD/COP": "🔺"}.get(v, "⚪")


def build_whatsapp_from_signals(data: dict) -> str:
    """
    Construye un mensaje WhatsApp compacto (< 400 caracteres) desde daily_signals.json.
    Formato: fecha · 4 señales · top 2 drivers · resumen ejecutivo en 1 línea.
    """
    s       = data.get("senales", {})
    changes = data.get("variaciones_mercado", {})
    fecha   = data.get("fecha", datetime.now().strftime("%Y-%m-%d"))

    try:
        date_str = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m")
    except Exception:
        date_str = fecha

    riesgo    = s.get("riesgo_macro",           "N/A")
    sesgo     = s.get("sesgo_mercado",          "N/A")
    inflacion = s.get("presion_inflacionaria",  "N/A")
    cop       = s.get("presion_cop",            "N/A")
    conv      = s.get("conviccion",             0)

    # Top 2 movers por magnitud
    sorted_chg = sorted(changes.items(), key=lambda x: abs(x[1]), reverse=True)[:2]
    drivers_str = " · ".join(
        f"{k.upper()} {v:+.1f}%" for k, v in sorted_chg if abs(v) >= 0.1
    ) or "Sin variaciones relevantes"

    # Resumen en 1 línea
    parts: list[str] = []
    if riesgo == "Alto":
        parts.append("Riesgo elevado.")
    elif riesgo == "Bajo":
        parts.append("Entorno estable.")
    else:
        parts.append("Entorno moderado.")

    if inflacion == "Alcista":
        parts.append("Presion inflacionaria activa.")
    elif inflacion == "Bajista":
        parts.append("Desinflacion en curso.")

    if cop == "Alcista USD/COP":
        parts.append("Peso bajo presion.")
    elif cop == "Favorable COP":
        parts.append("Peso favorecido.")

    if conv >= 7:
        parts.append(f"Conviccion {conv}/10.")
    elif conv >= 4:
        parts.append(f"Conviccion moderada ({conv}/10).")
    else:
        parts.append(f"Senales inconclusas ({conv}/10).")

    summary = " ".join(parts)

    msg = (
        f"📊 *Agente Financiero* · {date_str}\n"
        f"{'─' * 16}\n"
        f"{_icon_riesgo(riesgo)} Riesgo: {riesgo}\n"
        f"{_icon_sesgo(sesgo)} Sesgo: {sesgo}\n"
        f"{_icon_infl(inflacion)} Inflacion: {inflacion}\n"
        f"{_icon_cop(cop)} COP: {cop} · 🎯 {conv}/10\n"
        f"{'─' * 16}\n"
        f"📌 {drivers_str}\n"
        f"{summary}"
    )
    return msg


def load_signals() -> dict:
    if not os.path.exists(SIGNALS_FILE):
        return {}
    try:
        with open(SIGNALS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def send_whatsapp(message: str, account_sid: str, auth_token: str,
                  from_number: str, to_number: str) -> str:
    client = Client(account_sid, auth_token)
    msg = client.messages.create(
        from_=f"whatsapp:{from_number}",
        to=f"whatsapp:{to_number}",
        body=message,
    )
    return msg.sid


def main():
    load_dotenv()
    cfg = load_config()

    if not cfg.get("whatsapp_enabled", True):
        print("WhatsApp desactivado en config.json — omitiendo.")
        return

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM")
    to_number   = cfg.get("whatsapp_to") or os.getenv("WHATSAPP_TO")

    if not all([account_sid, auth_token, from_number, to_number]):
        raise ValueError("Faltan credenciales Twilio o whatsapp_to en config.json")

    signals = load_signals()
    if signals:
        print("Construyendo mensaje desde señales del agente...")
        message = build_whatsapp_from_signals(signals)
    else:
        # Fallback: primer párrafo del reporte diario (si existe)
        print("Señales no disponibles — usando extracto del reporte diario...")
        if not os.path.exists(REPORT_FILE):
            raise FileNotFoundError(f"No existe el reporte ni las señales.")
        with open(REPORT_FILE, encoding="utf-8") as f:
            content = f.read()
        # Tomar las primeras 350 chars del cuerpo del reporte como fallback
        body = content.split("-" * 50)[-1].strip() if "-" * 50 in content else content
        message = body[:350].strip()

    print(f"\nMensaje a enviar ({len(message)} chars):\n{message}\n")

    print(f"Enviando WhatsApp a +{to_number}...")
    sid = send_whatsapp(message, account_sid, auth_token, from_number, f"+{to_number}")
    print(f"WhatsApp enviado correctamente. SID: {sid}")


if __name__ == "__main__":
    main()
