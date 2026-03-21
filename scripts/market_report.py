import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

SNAPSHOT_FILE  = "data/processed/latest_snapshot.csv"
HISTORY_FILE   = "data/historical/market_history.csv"
REPORTS_DIR    = "reports"
REPORT_FILE    = os.path.join(REPORTS_DIR, "daily_report.txt")

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


def build_historical_context():
    """Compara el valor de cierre más reciente vs hace 7 y 30 días."""
    if not os.path.exists(HISTORY_FILE):
        return ""

    df = pd.read_csv(HISTORY_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp", "value"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    today    = df["timestamp"].max().normalize()
    d7       = today - pd.Timedelta(days=7)
    d30      = today - pd.Timedelta(days=30)

    def closest_value(indicator_df, target_date):
        subset = indicator_df[indicator_df["timestamp"].dt.normalize() <= target_date]
        if subset.empty:
            return None
        return subset.sort_values("timestamp").iloc[-1]["value"]

    lines = ["COMPARACION HISTORICA (valor de cierre):"]
    lines.append(f"{'Indicador':<25} {'Hoy':>12} {'Hace 7d':>12} {'Var7d%':>8} {'Hace 30d':>12} {'Var30d%':>8} {'Unidad'}")
    lines.append("-" * 85)

    for indicator, grp in df.groupby("indicator"):
        unit    = grp["unit"].iloc[-1]
        v_today = closest_value(grp, today)
        v7      = closest_value(grp, d7)
        v30     = closest_value(grp, d30)

        def pct(a, b):
            if a is None or b is None or b == 0:
                return "N/A"
            return f"{((a - b) / b) * 100:+.2f}%"

        v_today_s = f"{v_today:,.2f}" if v_today is not None else "N/A"
        v7_s      = f"{v7:,.2f}"      if v7      is not None else "N/A"
        v30_s     = f"{v30:,.2f}"     if v30     is not None else "N/A"

        lines.append(
            f"{indicator:<25} {v_today_s:>12} {v7_s:>12} {pct(v_today, v7):>8} "
            f"{v30_s:>12} {pct(v_today, v30):>8}  {unit}"
        )

    return "\n".join(lines)


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


def generate_report_with_ai(market_context, news_context, historical_context, openai_key):
    client = OpenAI(api_key=openai_key)

    prompt = f"""
Eres un analista financiero colombiano que escribe el resumen diario de mercados para un grupo de WhatsApp de empresarios. Tu tono es directo, conversacional y claro — como si le explicaras a un colega inteligente, no a un académico. Usas español colombiano natural, sin jerga innecesaria ni frases rimbombantes.

Datos de hoy:
{market_context}

Contexto histórico (hoy vs hace 7 y 30 días):
{historical_context}

Noticias relevantes:
{news_context}

Escribe el reporte en tres bloques sin títulos de sección, separados por salto de línea:

BLOQUE 1 — QUÉ PASÓ HOY (máx. 100 palabras):
Cuenta qué hicieron los mercados hoy de forma natural. Varía el vocabulario: el dólar "se fortaleció", "cedió terreno", "se mantuvo quieto"; el petróleo "subió con fuerza", "retrocedió", "cerró plano"; el bitcoin "arrancó bien", "perdió impulso", etc. Cuando el dólar sube, menciona el impacto directo en Colombia (importaciones, deuda en dólares, poder adquisitivo).

BLOQUE 2 — LA TENDENCIA (máx. 80 palabras):
Sin repetir los números del bloque 1, comenta si los movimientos de hoy son parte de una tendencia o un movimiento aislado. ¿Algo viene cambiando en las últimas semanas?

BLOQUE 3 — EN CONTEXTO (máx. 70 palabras):
Una lectura general del ambiente de mercado. Termina con una frase corta y directa que resuma el momento, como si cerraras una conversación.

Máximo 250 palabras en total. Sin asteriscos, sin negritas, sin viñetas. Solo texto corrido.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=800,
        temperature=0.7,
        messages=[
            {"role": "system", "content": "Eres un analista financiero colombiano. Escribes en español natural, directo y sin tecnicismos innecesarios."},
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
    historical_context = build_historical_context()

    print("\n--- Titulares obtenidos ---")
    print(news_context)
    print("-" * 30)
    print("\n--- Contexto histórico ---")
    print(historical_context)
    print("-" * 30)

    report_text = generate_report_with_ai(market_context, news_context, historical_context, openai_key)
    final_text  = save_report(report_text)

    print("\nReporte generado correctamente:\n")
    print(final_text)
    print(f"\nArchivo guardado en: {REPORT_FILE}")


if __name__ == "__main__":
    main()
