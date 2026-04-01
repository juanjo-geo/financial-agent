"""
news_collector.py — Recolector de titulares para todos los indicadores.

Fuente principal: Google News RSS (gratis, sin API key).
Fuente secundaria: NewsAPI (cuando la clave esté disponible).

Usado por market_report.py y como script independiente.
"""
import time
import requests
import xml.etree.ElementTree as ET

NEWS_QUERIES = {
    "brent":                  "brent crude oil price",
    "btc":                    "bitcoin BTC crypto price",
    "dxy":                    "US dollar DXY index",
    "usdcop":                 "peso colombiano dolar TRM Colombia",
    "global_inflation_proxy": "global inflation CPI consumer prices",
    "gold":                   "gold price XAU USD",
    "silver":                 "silver price XAG USD",
    "sp500":                  "S&P 500 stock market index",
}

# Indicadores que usan Google News RSS en español (mejor cobertura local)
_RSS_ES = {"usdcop"}

# Headers para evitar bloqueo de bots
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}


def fetch_rss(query, lang="en-US", gl="US", ceid="US:en", max_results=3):
    """Busca titulares via Google News RSS (sin API key)."""
    url = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&hl={lang}&gl={gl}&ceid={ceid}"
    )
    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=15, headers=_HEADERS)
            if resp.status_code != 200:
                print(f"  [rss] HTTP {resp.status_code} para '{query}' (intento {attempt+1})")
                if attempt == 0:
                    time.sleep(2)
                    continue
                return []
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")[:max_results]
            results = []
            for item in items:
                title = item.findtext("title", "").strip()
                source = item.findtext("source", "Google News").strip()
                if title:
                    results.append(f"- {title} ({source})")
            if results:
                return results
            # Si no hay resultados, intentar con query simplificada
            if attempt == 0 and " " in query:
                simplified = " ".join(query.split()[:2])
                url = (
                    f"https://news.google.com/rss/search"
                    f"?q={requests.utils.quote(simplified)}&hl={lang}&gl={gl}&ceid={ceid}"
                )
                time.sleep(1)
                continue
            return []
        except Exception as e:
            print(f"  [rss] Error (intento {attempt+1}): {e}")
            if attempt == 0:
                time.sleep(2)
    return []


def fetch_newsapi(query, api_key, max_results=3):
    """Busca titulares via NewsAPI (requiere API key)."""
    for endpoint in (
        "https://newsapi.org/v2/everything",
        "https://newsapi.org/v2/top-headlines",
    ):
        try:
            resp = requests.get(
                endpoint,
                params={"q": query, "language": "en", "sortBy": "publishedAt",
                        "pageSize": max_results, "apiKey": api_key},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "error":
                print(f"  [newsapi] {data.get('code', '?')}: {data.get('message', '?')}")
                return []
            articles = data.get("articles", [])
            if articles:
                return [f"- {a['title']} ({a['source']['name']})" for a in articles
                        if a.get("title")]
        except Exception as e:
            print(f"  [newsapi] Error: {e}")
    return []


def get_headlines(indicator, api_key=None, max_results=3):
    """
    Retorna lista de strings '- Titular (Fuente)' para el indicador dado.
    Estrategia: RSS primero (gratis), NewsAPI como refuerzo si RSS falla.
    """
    query = NEWS_QUERIES.get(indicator, indicator)

    # Para USD/COP siempre usar RSS en español
    if indicator in _RSS_ES:
        results = fetch_rss(query, lang="es-CO", gl="CO", ceid="CO:es",
                            max_results=max_results)
        if results:
            return results

    # 1. Intentar Google News RSS primero (gratis, siempre disponible)
    results = fetch_rss(query, max_results=max_results)
    if results:
        return results

    # 2. Fallback a NewsAPI si hay API key
    if api_key:
        results = fetch_newsapi(query, api_key, max_results)
        if results:
            return results

    # 3. Último intento: RSS con query en español
    results = fetch_rss(query, lang="es-419", gl="CO", ceid="CO:es",
                        max_results=max_results)
    return results


def main():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("NEWS_API_KEY")

    print("=== Test de recolección de noticias ===\n")
    total_ok = 0
    total = len(NEWS_QUERIES)

    for indicator in NEWS_QUERIES:
        print(f"{indicator.upper()}:")
        headlines = get_headlines(indicator, api_key)
        if headlines:
            print("\n".join(headlines))
            total_ok += 1
        else:
            print("  Sin titulares.")
        print()

    print(f"=== Resultado: {total_ok}/{total} indicadores con noticias ===")


if __name__ == "__main__":
    main()
