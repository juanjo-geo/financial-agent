"""
news_collector.py — Recolector de titulares para todos los indicadores.
Usado como utilidad por market_report.py y desde scripts independientes.
"""
import requests
import xml.etree.ElementTree as ET

NEWS_QUERIES = {
    "brent":                  "brent crude oil price",
    "btc":                    "bitcoin BTC crypto",
    "dxy":                    "US dollar DXY index",
    "usdcop":                 "peso colombiano dolar TRM Colombia",
    "global_inflation_proxy": "global inflation CPI",
    "gold":                   "gold price XAU USD",
}

# Indicadores que usan Google News RSS en español (mejor cobertura local)
_RSS_ES = {"usdcop"}


def fetch_rss(query, lang="en-US", gl="US", ceid="US:en", max_results=3):
    url = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&hl={lang}&gl={gl}&ceid={ceid}"
    )
    try:
        resp  = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        root  = ET.fromstring(resp.content)
        items = root.findall(".//item")[:max_results]
        results = []
        for item in items:
            title  = item.findtext("title", "").strip()
            source = item.findtext("source", "Google News").strip()
            if title:
                results.append(f"- {title} ({source})")
        return results
    except Exception as e:
        print(f"  [rss] Error: {e}")
        return []


def fetch_newsapi(query, api_key, max_results=3):
    for endpoint in (
        "https://newsapi.org/v2/top-headlines",
        "https://newsapi.org/v2/everything",
    ):
        try:
            resp = requests.get(
                endpoint,
                params={"q": query, "language": "en", "sortBy": "publishedAt",
                        "pageSize": max_results, "apiKey": api_key},
                timeout=10,
            )
            articles = resp.json().get("articles", [])
            if articles:
                return [f"- {a['title']} ({a['source']['name']})" for a in articles]
        except Exception as e:
            print(f"  [newsapi] Error: {e}")
    return []


def get_headlines(indicator, api_key=None, max_results=3):
    """Retorna lista de strings '- Titular (Fuente)' para el indicador dado."""
    query = NEWS_QUERIES.get(indicator, indicator)

    if indicator in _RSS_ES:
        return fetch_rss(query, lang="es-CO", gl="CO", ceid="CO:es",
                         max_results=max_results)

    if api_key:
        results = fetch_newsapi(query, api_key, max_results)
        if results:
            return results

    return fetch_rss(query, max_results=max_results)


def main():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("NEWS_API_KEY")

    for indicator in NEWS_QUERIES:
        print(f"\n{indicator.upper()}:")
        headlines = get_headlines(indicator, api_key)
        if headlines:
            print("\n".join(headlines))
        else:
            print("  Sin titulares.")


if __name__ == "__main__":
    main()
