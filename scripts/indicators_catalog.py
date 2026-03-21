"""
Catálogo completo de indicadores disponibles para el agente financiero.
Fuente única de verdad para todos los módulos.
"""

MAX_ACTIVE = 5

DEFAULT_ACTIVE = ["brent", "btc", "dxy", "usdcop", "gold"]

# Orden de grupos en el panel de administración
GROUP_ORDER = ["Commodities", "Crypto", "Divisas", "Índices", "Las 7 Magníficas", "Macro"]

# Catálogo completo
# symbol=None → proxy manual (no se descarga de yfinance)
CATALOG = {
    # ── Commodities ───────────────────────────────────────────────────────────
    "brent":  {"symbol": "BZ=F",     "unit": "USD/bbl",   "label": "Brent",           "group": "Commodities",      "news": "brent crude oil price"},
    "gold":   {"symbol": "GC=F",     "unit": "USD/oz",    "label": "Oro (XAU/USD)",   "group": "Commodities",      "news": "gold price XAU USD"},
    "wti":    {"symbol": "CL=F",     "unit": "USD/bbl",   "label": "WTI",             "group": "Commodities",      "news": "WTI crude oil price"},
    "silver": {"symbol": "SI=F",     "unit": "USD/oz",    "label": "Plata (XAG/USD)", "group": "Commodities",      "news": "silver price XAG USD"},
    "copper": {"symbol": "HG=F",     "unit": "USD/lb",    "label": "Cobre",           "group": "Commodities",      "news": "copper price commodity"},
    "natgas": {"symbol": "NG=F",     "unit": "USD/MMBtu", "label": "Gas Natural",     "group": "Commodities",      "news": "natural gas price NG"},
    # ── Crypto ────────────────────────────────────────────────────────────────
    "btc":    {"symbol": "BTC-USD",  "unit": "USD",       "label": "Bitcoin (BTC)",   "group": "Crypto",           "news": "bitcoin BTC crypto"},
    # ── Divisas ───────────────────────────────────────────────────────────────
    "dxy":    {"symbol": "DX-Y.NYB", "unit": "index",     "label": "DXY",             "group": "Divisas",          "news": "US dollar DXY index"},
    "usdcop": {"symbol": "COP=X",    "unit": "COP/USD",   "label": "USD/COP",         "group": "Divisas",          "news": "peso colombiano dolar Colombia"},
    "eurusd": {"symbol": "EURUSD=X", "unit": "USD",       "label": "EUR/USD",         "group": "Divisas",          "news": "euro dollar EUR USD"},
    # ── Índices ───────────────────────────────────────────────────────────────
    "sp500":  {"symbol": "^GSPC",    "unit": "USD",       "label": "S&P 500",         "group": "Índices",          "news": "S&P 500 stock market index"},
    "nasdaq": {"symbol": "^IXIC",    "unit": "USD",       "label": "Nasdaq",          "group": "Índices",          "news": "Nasdaq index stock market"},
    # ── Las 7 Magníficas ──────────────────────────────────────────────────────
    "aapl":   {"symbol": "AAPL",     "unit": "USD",       "label": "Apple (AAPL)",    "group": "Las 7 Magníficas", "news": "Apple stock AAPL"},
    "msft":   {"symbol": "MSFT",     "unit": "USD",       "label": "Microsoft (MSFT)","group": "Las 7 Magníficas", "news": "Microsoft stock MSFT"},
    "nvda":   {"symbol": "NVDA",     "unit": "USD",       "label": "Nvidia (NVDA)",   "group": "Las 7 Magníficas", "news": "Nvidia stock NVDA"},
    "amzn":   {"symbol": "AMZN",     "unit": "USD",       "label": "Amazon (AMZN)",   "group": "Las 7 Magníficas", "news": "Amazon stock AMZN"},
    "googl":  {"symbol": "GOOGL",    "unit": "USD",       "label": "Alphabet (GOOGL)","group": "Las 7 Magníficas", "news": "Alphabet Google stock"},
    "meta":   {"symbol": "META",     "unit": "USD",       "label": "Meta (META)",     "group": "Las 7 Magníficas", "news": "Meta Facebook stock META"},
    "tsla":   {"symbol": "TSLA",     "unit": "USD",       "label": "Tesla (TSLA)",    "group": "Las 7 Magníficas", "news": "Tesla stock TSLA"},
    # ── Macro ─────────────────────────────────────────────────────────────────
    "global_inflation_proxy": {"symbol": None, "unit": "%", "label": "Inflación Global (proxy)", "group": "Macro", "news": "global inflation CPI"},
}
