"""
Simula una alerta de prueba para verificar los formatos de email y WhatsApp.
Usa señales reales de daily_signals.json y datos ficticios de precio.
NO envía emails ni WhatsApp — solo imprime y guarda en alerts_log.json.
"""

from pathlib import Path
from scripts.alerts_monitor import (
    build_alert_email,
    build_whatsapp_alert,
    load_daily_signals,
    save_alert_log,
)

# ── Datos ficticios de la alerta de prueba ────────────────────────────────────
INDICATOR  = "brent"
CURRENT    = 85.30
OPEN_PRICE = 81.84
CHANGE_PCT = ((CURRENT - OPEN_PRICE) / OPEN_PRICE) * 100   # ≈ +4.1%
UNIT       = "USD/bbl"
NEWS       = "Oil prices surge as OPEC+ signals deeper supply cuts (Reuters)"

CONFIG = {
    "symbol":     "BZ=F",
    "unit":       UNIT,
    "news_query": "oil price crude brent",
}

SEP = "-" * 50


def main():
    signals = load_daily_signals()

    if not signals:
        print("[AVISO] daily_signals.json no encontrado — se simularan senales vacias.")
        signals = {
            "senales": {
                "riesgo_macro":           "Medio",
                "sesgo_mercado":          "Mixto",
                "presion_inflacionaria":  "Alcista",
                "presion_cop":            "Neutral",
                "conviccion":             7,
            },
            "interpretacion": {
                "driver_principal":  "El petroleo Brent registro un avance pronunciado (+4.1%), lo que parece indicar tensiones en la oferta energetica global.",
                "driver_secundario": "El DXY avanzo moderadamente (+0.3%), con cierta apreciacion del dolar a nivel global.",
                "lectura_cruzada":   "Las senales del dia presentan un cuadro mixto, sin un sesgo de riesgo claramente dominante.",
                "cierre_ejecutivo":  "El entorno macro se presenta con un nivel de riesgo moderado, con senales mixtas que aconsejan seguimiento cercano. La presion inflacionaria sugiere que los bancos centrales podrian mantener una postura restrictiva por mas tiempo del esperado. Las senales presentan una conviccion 7/10.",
            },
            "generado_en": "2026-03-21 07:05:12",
        }

    subject, email_body = build_alert_email(
        INDICATOR, CURRENT, OPEN_PRICE, CHANGE_PCT, UNIT, NEWS, signals
    )
    wa_msg = build_whatsapp_alert(INDICATOR, CHANGE_PCT, signals)

    print()
    print("=" * 60)
    print("SIMULACION DE ALERTA - SOLO IMPRESION, SIN ENVIO")
    print("=" * 60)

    print()
    print("-- EMAIL --------------------------------------------------")
    print(f"Asunto : {subject}")
    print(SEP)
    print(email_body)

    print()
    print("-- WHATSAPP -----------------------------------------------")
    print(wa_msg)
    print(f"\n({len(wa_msg)} caracteres)")

    # Guarda en alerts_log.json con canal "simulacion"
    save_alert_log(
        INDICATOR, CHANGE_PCT, CURRENT, OPEN_PRICE,
        UNIT, signals, NEWS, ["simulacion"],
    )

    print()
    print("-" * 60)
    print("Alerta guardada en data/signals/alerts_log.json")


if __name__ == "__main__":
    main()
