import os
from dotenv import load_dotenv
from openai import OpenAI
from twilio.rest import Client
from scripts.load_config import load_config

REPORT_FILE = "reports/daily_report.txt"


def load_report():
    if not os.path.exists(REPORT_FILE):
        raise FileNotFoundError(f"No existe el reporte: {REPORT_FILE}")
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def summarize_report(report_text, api_key):
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=600,
        messages=[
            {
                "role": "system",
                "content": "Eres un analista financiero. Resume reportes de mercado de forma clara y concisa."
            },
            {
                "role": "user",
                "content": (
                    "Resume el siguiente reporte financiero en máximo 400 palabras. "
                    "Mantén los datos clave (valores, porcentajes) y la lectura general del mercado.\n\n"
                    f"{report_text}"
                )
            }
        ],
    )

    return response.choices[0].message.content.strip()


def send_whatsapp(message, account_sid, auth_token, from_number, to_number):
    client = Client(account_sid, auth_token)

    msg = client.messages.create(
        from_=f"whatsapp:{from_number}",
        to=f"whatsapp:{to_number}",
        body=message
    )

    return msg.sid


def main():
    load_dotenv()
    cfg = load_config()

    if not cfg.get("whatsapp_enabled", True):
        print("WhatsApp desactivado en config.json — omitiendo.")
        return

    openai_key  = os.getenv("OPENAI_API_KEY")
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM")
    to_number   = cfg.get("whatsapp_to") or os.getenv("WHATSAPP_TO")

    if not all([account_sid, auth_token, from_number, to_number]):
        raise ValueError("Faltan credenciales Twilio o whatsapp_to en config.json")

    print("Cargando reporte...")
    report_text = load_report()

    print("Resumiendo reporte con IA...")
    summary = summarize_report(report_text, openai_key)

    print(f"Enviando WhatsApp a +{to_number}...")
    sid = send_whatsapp(summary, account_sid, auth_token, from_number, f"+{to_number}")

    print(f"WhatsApp enviado correctamente. SID: {sid}")
    print(f"\nMensaje enviado:\n{summary}")


if __name__ == "__main__":
    main()
