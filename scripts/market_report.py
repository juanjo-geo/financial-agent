import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

SNAPSHOT_FILE = "data/processed/latest_snapshot.csv"
REPORTS_DIR   = "reports"
REPORT_FILE   = os.path.join(REPORTS_DIR, "daily_report.txt")

NEWS_QUERIES = {
    "brent":               "brent crude oil price",
    "btc":                 "bitcoin BTC crypto",
    "dxy":                 "US dollar DXY index",
    "usdcop":              "peso colombiano dolar COP Colombia",
    "global_inflation_proxy": "global inflation CPI",
}


def load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        raise FileNotFoundError(f"No existe el archivo snapshot: {SNAPSHOT_FILE}")
    return pd.read_csv(SNAPSHOT_FILE)


def fetch_news_google_rss(query, max_headlines=2):
    """Busca titulares via Google News RSS (sin API key, cobertura en español)."""
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=es-CO&gl=CO&ceid=CO:es"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")[:max_headlines]
        results = []
        for item in items:
            title  = item.findtext("title", "").strip()
            source = item.findtext("source", "Google News").strip()
            if title:
                results.append(f"- {title} ({source})")
        return results
    except Exception as e:
        print(f"  [rss] Error Google News RSS: {e}")
        return []


def fetch_news(indicator, api_key, max_headlines=2):
    """Retorna titulares para el indicador.
    - usdcop: usa Google News RSS en español (mejor cobertura Colombia).
    - otros: NewsAPI con fallback a Google News RSS.
    """
    query = NEWS_QUERIES.get(indicator, indicator)

    if indicator == "usdcop":
        return fetch_news_google_rss("peso colombiano dolar TRM Colombia", max_headlines)

    if api_key:
        for url, params in [
            ("https://newsapi.org/v2/top-headlines", {"q": query, "language": "en", "pageSize": max_headlines}),
            ("https://newsapi.org/v2/everything",    {"q": query, "language": "en", "sortBy": "publishedAt", "pageSize": max_headlines}),
        ]:
            try:
                params["apiKey"] = api_key
                resp     = requests.get(url, params=params, timeout=10)
                articles = resp.json().get("articles", [])
                if articles:
                    return [f"- {a['title']} ({a['source']['name']})" for a in articles]
            except Exception as e:
                print(f"  [news] Error en {url} para {indicator}: {e}")

    # Fallback: Google News RSS en inglés
    return fetch_news_google_rss(query, max_headlines)


def build_market_context(df, news_api_key):
    """Construye el contexto de mercado + titulares de noticias por indicador."""
    market_lines = []
    news_lines   = []

    for _, row in df.iterrows():
        indicator  = row.get("indicator", "unknown")
        value      = row.get("value", "N/A")
        open_value = row.get("open_value", "N/A")
        change_abs = row.get("change_abs", "N/A")
        change_pct = row.get("change_pct", "N/A")
        unit       = row.get("unit", "")
        status     = row.get("status", "")

        market_lines.append(
            f"Indicador: {indicator} | "
            f"Valor actual: {value} {unit} | "
            f"Apertura: {open_value} {unit} | "
            f"Cambio absoluto: {change_abs} | "
            f"Cambio porcentual: {change_pct}% | "
            f"Estado: {status}"
        )

        headlines = fetch_news(indicator, news_api_key)
        if headlines:
            news_lines.append(f"{indicator.upper()}:")
            news_lines.extend(headlines)
        else:
            news_lines.append(f"{indicator.upper()}: sin titulares disponibles")

    market_context = "\n".join(market_lines)
    news_context   = "\n".join(news_lines)

    return market_context, news_context


def generate_report_with_ai(market_context, news_context, openai_key):
    client = OpenAI(api_key=openai_key)

    prompt = f"""
Actúa como un analista financiero ejecutivo.

Tienes dos fuentes de información:

1. DATOS DE MERCADO:
{market_context}

2. TITULARES DE NOTICIAS DE LAS ÚLTIMAS 24 HORAS:
{news_context}

Redacta un reporte financiero diario en español con DOS secciones claramente separadas:

SECCIÓN 1 — ANÁLISIS DE MERCADO:
Resume el comportamiento de los indicadores. Máximo 200 palabras.
Solo comenta lo que se observa en los datos. No inventes causas que no estén en las noticias.

SECCIÓN 2 — NOTICIAS RELEVANTES:
Lista los titulares más importantes del día relacionados con los indicadores.
Si un titular es relevante para explicar el movimiento de un indicador, indícalo brevemente.
Máximo 200 palabras.

Total máximo: 400 palabras.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": "Eres un analista financiero preciso, ejecutivo y claro."},
            {"role": "user",   "content": prompt},
        ],
    )

    return response.choices[0].message.content.strip()


def save_report(report_text):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_text = (
        f"REPORTE DIARIO DE MERCADO\n"
        f"Generado: {timestamp}\n"
        f"{'-' * 50}\n\n"
        f"{report_text}\n"
    )
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(final_text)
    return final_text


def main():
    load_dotenv()

    openai_key  = os.getenv("OPENAI_API_KEY")
    news_api_key = os.getenv("NEWS_API_KEY")

    print("Key OpenAI termina en:", openai_key[-6:] if openai_key else "None")
    print("Buscando noticias y generando reporte...")

    df = load_snapshot()
    market_context, news_context = build_market_context(df, news_api_key)

    print("\n--- Titulares obtenidos ---")
    print(news_context)
    print("-" * 30)

    report_text = generate_report_with_ai(market_context, news_context, openai_key)
    final_text  = save_report(report_text)

    print("\nReporte generado correctamente:\n")
    print(final_text)
    print(f"\nArchivo guardado en: {REPORT_FILE}")


if __name__ == "__main__":
    main()
