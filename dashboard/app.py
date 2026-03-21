import os
import sys
import json
import base64
import subprocess
from pathlib import Path
from datetime import datetime
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(
    page_title="Agente Financiero Autónomo",
    page_icon=str(Path(__file__).parent.parent / "logo.png"),
    layout="wide",
)

ROOT          = Path(__file__).parent.parent
SNAPSHOT_FILE = ROOT / "data/processed/latest_snapshot.csv"
HISTORY_FILE  = ROOT / "data/historical/market_history.csv"
REPORT_FILE   = ROOT / "reports/daily_report.txt"
LOGO_FILE     = ROOT / "logo.png"

# ── Catálogo de indicadores (mismo que indicators_catalog.py) ────────────────
_CATALOG = {
    "brent":                  {"label": "Brent",           "news": "brent crude oil price",         "usdcop_rss": False},
    "gold":                   {"label": "Oro (XAU/USD)",   "news": "gold price XAU USD",             "usdcop_rss": False},
    "wti":                    {"label": "WTI",             "news": "WTI crude oil price",            "usdcop_rss": False},
    "silver":                 {"label": "Plata",           "news": "silver price XAG USD",           "usdcop_rss": False},
    "copper":                 {"label": "Cobre",           "news": "copper price commodity",         "usdcop_rss": False},
    "natgas":                 {"label": "Gas Natural",     "news": "natural gas price NG",           "usdcop_rss": False},
    "btc":                    {"label": "BTC",             "news": "bitcoin BTC crypto",             "usdcop_rss": False},
    "dxy":                    {"label": "DXY",             "news": "US dollar DXY index",            "usdcop_rss": False},
    "usdcop":                 {"label": "USD/COP",         "news": "peso colombiano dolar Colombia", "usdcop_rss": True},
    "eurusd":                 {"label": "EUR/USD",         "news": "euro dollar EUR USD",            "usdcop_rss": False},
    "sp500":                  {"label": "S&P 500",         "news": "S&P 500 stock market index",     "usdcop_rss": False},
    "nasdaq":                 {"label": "Nasdaq",          "news": "Nasdaq index stock market",      "usdcop_rss": False},
    "aapl":                   {"label": "Apple (AAPL)",    "news": "Apple stock AAPL",               "usdcop_rss": False},
    "msft":                   {"label": "Microsoft (MSFT)","news": "Microsoft stock MSFT",           "usdcop_rss": False},
    "nvda":                   {"label": "Nvidia (NVDA)",   "news": "Nvidia stock NVDA",              "usdcop_rss": False},
    "amzn":                   {"label": "Amazon (AMZN)",   "news": "Amazon stock AMZN",              "usdcop_rss": False},
    "googl":                  {"label": "Alphabet (GOOGL)","news": "Alphabet Google stock",          "usdcop_rss": False},
    "meta":                   {"label": "Meta (META)",     "news": "Meta Facebook stock META",       "usdcop_rss": False},
    "tsla":                   {"label": "Tesla (TSLA)",    "news": "Tesla stock TSLA",               "usdcop_rss": False},
    "global_inflation_proxy": {"label": "Inflación Global","news": "global inflation CPI",           "usdcop_rss": False},
}

# ── Paleta fintech profesional ────────────────────────────────────────────────
# Azul oscuro #1B2A4A · Verde #00C896 · Rojo #FF4B4B · Acento #3DB860

BRAND_CSS = """
<style>
/* ── Reset / base ───────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] { background: #F8F9FA; }
[data-testid="stSidebar"]          { background: #FFFFFF; border-right: 1px solid #E8EDF2; }
[data-testid="stAppViewBlockContainer"],
[data-testid="stMainBlockContainer"],
.block-container { padding-top: 0 !important; margin-top: 0 !important; }

/* ── Header ─────────────────────────────────────────────────────────────── */
.fa-header {
    display: flex; align-items: center; gap: 24px;
    padding: 24px 0 20px; border-bottom: 2px solid #E8EDF2;
    margin-bottom: 32px; flex-wrap: wrap;
}
.fa-header img  { height: 96px; width: auto; flex-shrink: 0; border-radius: 12px; }
.fa-title-block { flex: 1; min-width: 220px; }
.fa-title h1 {
    margin: 0; color: #1B2A4A; font-size: 2.6rem;
    font-weight: 800; letter-spacing: -1px; line-height: 1.1;
}
.fa-title h1 span { color: #00C896; font-weight: 500; }
.fa-subtitle { color: #8A9BB0; font-size: 0.88rem; margin-top: 4px; }
.fa-badges   { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.fa-badge {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 0.75rem; font-weight: 600;
    padding: 3px 11px; border-radius: 20px; white-space: nowrap;
}
.badge-update { background: #F0F4F8; color: #5A6A7E; border: 1px solid #D8E2EC; }
.badge-ok     { background: #E6FBF4; color: #00875A; border: 1px solid #B3EDD8; }
.badge-dot    { width: 6px; height: 6px; border-radius: 50%; background: #00C896;
                box-shadow: 0 0 0 2px rgba(0,200,150,.25);
                animation: pulse 2s ease-in-out infinite; }
@keyframes pulse {
    0%,100% { box-shadow: 0 0 0 2px rgba(0,200,150,.25); }
    50%      { box-shadow: 0 0 0 5px rgba(0,200,150,.08); }
}

/* ── Section labels ─────────────────────────────────────────────────────── */
.section-label {
    font-size: 0.68rem; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #8A9BB0;
    margin-bottom: 16px; margin-top: 8px;
    display: flex; align-items: center; gap: 8px;
}
.section-label::after {
    content: ""; flex: 1; height: 1px; background: #E8EDF2;
}
h2,h3 { color: #1B2A4A !important; }

/* ── Snapshot metric cards ──────────────────────────────────────────────── */
.metric-card {
    background: #FFFFFF;
    border: 1px solid #EAF0F6;
    border-radius: 16px;
    padding: 20px 16px 16px;
    text-align: center;
    min-height: 130px;
    display: flex; flex-direction: column;
    justify-content: space-between; align-items: center;
    box-shadow: 0 1px 4px rgba(27,42,74,.05), 0 4px 16px rgba(27,42,74,.04);
    transition: box-shadow .2s ease, transform .2s ease;
    position: relative; overflow: hidden;
}
.metric-card::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 16px 16px 0 0;
    background: linear-gradient(90deg,#00C896,#3DB8A0);
    opacity: 0; transition: opacity .2s;
}
.metric-card:hover {
    box-shadow: 0 8px 32px rgba(27,42,74,.12);
    transform: translateY(-3px);
}
.metric-card:hover::before { opacity: 1; }
.mc-label {
    font-size: 0.67rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #8A9BB0;
}
.mc-value {
    font-size: 1.35rem; font-weight: 800; color: #1B2A4A;
    word-break: break-word; line-height: 1.2;
}
.mc-delta {
    font-size: 0.82rem; font-weight: 700;
    display: inline-flex; align-items: center; gap: 3px;
    padding: 3px 10px; border-radius: 20px;
}
.mc-delta.pos { background: #E6FBF4; color: #00875A; }
.mc-delta.neg { background: #FFF0F0; color: #C0392B; }
.mc-delta.neu { background: #F0F4F8; color: #8A9BB0; }
.mc-arrow.up   { animation: up-bounce   1.6s ease-in-out infinite; display:inline-block; }
.mc-arrow.down { animation: down-bounce 1.6s ease-in-out infinite; display:inline-block; }
@keyframes up-bounce   { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)} }
@keyframes down-bounce { 0%,100%{transform:translateY(0)} 50%{transform:translateY(4px)} }

/* ── Historical variation ────────────────────────────────────────────────── */
.hist-card {
    background: #FFFFFF; border: 1px solid #EAF0F6;
    border-radius: 14px; padding: 16px 18px;
    box-shadow: 0 1px 4px rgba(27,42,74,.05);
}
.hc-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 14px; padding-bottom: 10px;
    border-bottom: 1px solid #F0F4F8;
}
.hc-name  { font-size: 0.75rem; font-weight: 700; letter-spacing: .08em;
            text-transform: uppercase; color: #1B2A4A; }
.hc-unit  { font-size: 0.68rem; color: #8A9BB0; font-weight: 500; }
.hist-row {
    display: grid; grid-template-columns: 4rem 1fr auto;
    align-items: center; gap: 6px;
    padding: 5px 0; font-size: 0.85rem;
    border-bottom: 1px solid #F8FAFB;
}
.hist-row:last-child { border-bottom: none; }
.hr-period { color: #8A9BB0; font-size: 0.78rem; font-weight: 500; }
.hr-value  { color: #1B2A4A; font-weight: 700; text-align: right; }
.hr-delta  { font-weight: 700; font-size: 0.74rem;
             padding: 2px 7px; border-radius: 20px; white-space: nowrap; }
.hr-delta.pos { background: #E6FBF4; color: #00875A; }
.hr-delta.neg { background: #FFF0F0; color: #C0392B; }
.hr-delta.neu { background: #F0F4F8; color: #8A9BB0; }

/* ── News ───────────────────────────────────────────────────────────────── */
.news-grid {
    display: grid;
    grid-template-columns: repeat(4,1fr);
    gap: 20px; margin-top: 4px;
}
@media(max-width:1100px){ .news-grid{grid-template-columns:repeat(3,1fr);} }
@media(max-width:768px) { .news-grid{grid-template-columns:repeat(2,1fr);} }
@media(max-width:480px) { .news-grid{grid-template-columns:1fr;} }
.news-block { background:#FFFFFF; border:1px solid #EAF0F6; border-radius:14px;
              padding:16px; box-shadow:0 1px 4px rgba(27,42,74,.05); }
.news-block-title {
    font-size: 0.68rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #00875A;
    padding-bottom: 10px; margin-bottom: 8px;
    border-bottom: 2px solid #00C896;
}
.news-item { padding: 7px 0; border-bottom: 1px solid #F5F7FA; }
.news-item:last-child { border-bottom: none; }
.news-item a {
    font-size: 0.83rem; font-weight: 600; color: #1B2A4A;
    text-decoration: none; line-height: 1.35; display: block;
}
.news-item a:hover { color: #00C896; }
.news-meta { font-size: 0.7rem; color: #A0ADB8; margin-top: 2px; }

/* ── Report card ────────────────────────────────────────────────────────── */
.report-card {
    background: #FFFFFF; border: 1px solid #EAF0F6;
    border-radius: 14px; padding: 28px 32px;
    box-shadow: 0 1px 4px rgba(27,42,74,.05);
    position: relative; overflow: hidden;
}
.report-card::before {
    content: ""; position: absolute; top: 0; left: 0;
    width: 4px; height: 100%;
    background: linear-gradient(180deg,#00C896,#1B2A4A);
}
.report-date {
    font-size: 0.7rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #8A9BB0; margin-bottom: 16px;
}
.report-body {
    font-size: 1rem; line-height: 1.85; color: #2C3E50;
    white-space: pre-wrap; font-family: Georgia,serif;
}

/* ── Signal badges strip ────────────────────────────────────────────────── */
.sig-strip {
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px;
}
.sig-badge {
    flex: 1; min-width: 120px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: #FFFFFF; border: 1px solid #EAF0F6;
    border-radius: 14px; padding: 14px 10px;
    box-shadow: 0 1px 4px rgba(27,42,74,.05);
    text-align: center;
}
.sig-badge-label {
    font-size: 0.6rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #8A9BB0; margin-bottom: 6px;
}
.sig-badge-value { font-size: 0.88rem; font-weight: 800; }
.sig-ok    { border-color: #B3EDD8 !important; }
.sig-ok    .sig-badge-value { color: #00875A; }
.sig-warn  { border-color: #FFE0A0 !important; }
.sig-warn  .sig-badge-value { color: #856404; }
.sig-alert { border-color: #F5C6C6 !important; }
.sig-alert .sig-badge-value { color: #C0392B; }
.sig-neu   { border-color: #D8E2EC !important; }
.sig-neu   .sig-badge-value { color: #5A6A7E; }

/* ── Agent reading card ─────────────────────────────────────────────────── */
.agent-card {
    background: #FFFFFF; border: 1px solid #EAF0F6;
    border-radius: 16px; padding: 24px 28px;
    box-shadow: 0 1px 4px rgba(27,42,74,.05);
    position: relative; overflow: hidden;
}
.agent-card::before {
    content: ""; position: absolute; top: 0; left: 0;
    width: 4px; height: 100%;
    background: linear-gradient(180deg,#00C896,#1B2A4A);
}
.agent-card-header {
    font-size: 0.85rem; font-weight: 800; color: #1B2A4A;
    margin-bottom: 16px; padding-bottom: 12px;
    border-bottom: 1px solid #F0F4F8;
    display: flex; align-items: center; gap: 8px;
}
.agent-field { margin-bottom: 14px; }
.agent-field:last-child { margin-bottom: 0; }
.agent-field-label {
    font-size: 0.62rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #8A9BB0;
    display: block; margin-bottom: 4px;
}
.agent-field-value {
    font-size: 0.88rem; line-height: 1.6; color: #2C3E50;
}
.agent-drivers {
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
    margin-top: 16px; padding-top: 14px;
    border-top: 1px solid #F0F4F8;
}
.agent-driver {
    background: #F8F9FA; border-radius: 10px;
    padding: 10px 14px; font-size: 0.82rem;
    color: #2C3E50; line-height: 1.5;
}
.agent-driver-lbl {
    font-size: 0.6rem; font-weight: 700; letter-spacing: .08em;
    text-transform: uppercase; color: #8A9BB0;
    display: block; margin-bottom: 3px;
}
@media(max-width:900px){ .agent-drivers { grid-template-columns: 1fr; } }

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media(max-width:768px){
    .fa-title h1 { font-size: 1.8rem; }
    .fa-header img { height: 64px; }
    .mc-value { font-size: 1.1rem; }
    .report-card { padding: 18px 16px; }
    .sig-badge { min-width: 90px; padding: 10px 6px; }
    .sig-badge-value { font-size: 0.78rem; }
}
</style>
"""

# Per-indicator color palette for charts: (line_color, fill_rgba)
_IND_COLORS = {
    "brent":  ("#E65C00", "rgba(230,92,0,0.08)"),
    "wti":    ("#CC4400", "rgba(204,68,0,0.08)"),
    "gold":   ("#C8940A", "rgba(200,148,10,0.08)"),
    "silver": ("#7B8FA0", "rgba(123,143,160,0.08)"),
    "copper": ("#B87333", "rgba(184,115,51,0.08)"),
    "natgas": ("#FF8C00", "rgba(255,140,0,0.08)"),
    "btc":    ("#F7931A", "rgba(247,147,26,0.08)"),
    "dxy":    ("#1B2A4A", "rgba(27,42,74,0.10)"),
    "usdcop": ("#FF4B4B", "rgba(255,75,75,0.08)"),
    "eurusd": ("#0066CC", "rgba(0,102,204,0.08)"),
    "sp500":  ("#00C896", "rgba(0,200,150,0.08)"),
    "nasdaq": ("#00875A", "rgba(0,135,90,0.08)"),
    "aapl":   ("#555555", "rgba(85,85,85,0.08)"),
    "msft":   ("#00A4EF", "rgba(0,164,239,0.08)"),
    "nvda":   ("#76B900", "rgba(118,185,0,0.08)"),
    "amzn":   ("#FF9900", "rgba(255,153,0,0.08)"),
    "googl":  ("#4285F4", "rgba(66,133,244,0.08)"),
    "meta":   ("#0668E1", "rgba(6,104,225,0.08)"),
    "tsla":   ("#CC0000", "rgba(204,0,0,0.08)"),
    "global_inflation_proxy": ("#9B59B6", "rgba(155,89,182,0.08)"),
}
_DEFAULT_COLOR = ("#1B2A4A", "rgba(27,42,74,0.08)")

def _build_news_queries():
    """Construye NEWS_QUERIES dinámicamente desde active_indicators."""
    active = _load_active_indicators()
    return {
        _CATALOG[k]["label"]: (_CATALOG[k]["news"], _CATALOG[k]["usdcop_rss"])
        for k in active if k in _CATALOG
    }


def get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key)


def get_file_mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return None


def _load_active_indicators() -> tuple:
    """Lee active_indicators desde config.json. Retorna tuple para poder usarlo como cache key."""
    config_file = ROOT / "config.json"
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            lst = json.load(f).get("active_indicators",
                                   ["brent", "btc", "dxy", "usdcop", "gold"])
        return tuple(lst)
    except Exception:
        return ("brent", "btc", "dxy", "usdcop", "gold")


def load_snapshot(active: tuple):
    if not os.path.exists(SNAPSHOT_FILE):
        return pd.DataFrame()
    df = pd.read_csv(SNAPSHOT_FILE)
    return df[df["indicator"].isin(active)].reset_index(drop=True)


def load_report():
    if not os.path.exists(REPORT_FILE):
        return None
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def load_daily_signals() -> dict:
    signals_file = ROOT / "data/signals/daily_signals.json"
    if not signals_file.exists():
        return {}
    try:
        with open(signals_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def format_metric_value(value, unit):
    try:
        return f"{float(value):,.2f} {unit}"
    except Exception:
        return f"{value} {unit}"


@st.cache_data(ttl=3600)
def fetch_headlines_rss(query, lang="es-CO", gl="CO", ceid="CO:es", max_results=3):
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
            title   = item.findtext("title", "").strip()
            source  = item.findtext("source", "Google News").strip()
            link    = item.findtext("link", "").strip()
            pubdate = item.findtext("pubDate", "")[:16]
            if title:
                results.append({"title": title, "source": source,
                                 "url": link, "publishedAt": pubdate})
        return results
    except Exception:
        return []


@st.cache_data(ttl=3600)
def fetch_headlines_newsapi(query, api_key, max_results=3):
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
                return [
                    {"title": a["title"], "source": a["source"]["name"],
                     "url": a.get("url", ""), "publishedAt": a.get("publishedAt", "")[:10]}
                    for a in articles
                ]
        except Exception:
            pass
    return []


def load_historical_comparison(active: tuple):
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()
    df = pd.read_csv(HISTORY_FILE)
    df = df[df["indicator"].isin(active)]
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    df = df.dropna(subset=["timestamp", "value"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    today = df["timestamp"].max().normalize()
    d7    = today - pd.Timedelta(days=7)
    d30   = today - pd.Timedelta(days=30)

    def closest(grp, target):
        sub = grp[grp["timestamp"].dt.normalize() <= target]
        return sub.sort_values("timestamp").iloc[-1] if not sub.empty else None

    rows = []
    for indicator, grp in df.groupby("indicator"):
        unit  = grp["unit"].iloc[-1]
        r_now = closest(grp, today)
        r7    = closest(grp, d7)
        r30   = closest(grp, d30)
        v_now = r_now["value"] if r_now is not None else None
        v7    = r7["value"]    if r7    is not None else None
        v30   = r30["value"]   if r30   is not None else None

        def chg(a, b):
            if a is None or b is None or b == 0:
                return None
            return ((a - b) / b) * 100

        rows.append({
            "Indicador": indicator.upper(),
            "Hoy":       v_now,
            "Hace 7d":   v7,
            "Δ 7d (%)":  chg(v_now, v7),
            "Hace 30d":  v30,
            "Δ 30d (%)": chg(v_now, v30),
            "Unidad":    unit,
        })
    return pd.DataFrame(rows)


def fetch_headlines(indicator, query, api_key, max_results=3, use_rss=False):
    if use_rss:
        return fetch_headlines_rss(
            query, lang="es-CO", gl="CO", ceid="CO:es", max_results=max_results,
        )
    if api_key:
        results = fetch_headlines_newsapi(query, api_key, max_results)
        if results:
            return results
    return fetch_headlines_rss(query, lang="en-US", gl="US", ceid="US:en", max_results=max_results)


def _img_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ── Dashboard ─────────────────────────────────────────────────────────────────
def run_dashboard():
    st.markdown(BRAND_CSS, unsafe_allow_html=True)

    # Timestamps
    snap_time   = get_file_mtime(SNAPSHOT_FILE)
    report_time = get_file_mtime(REPORT_FILE)
    now_str     = datetime.now().strftime("%d/%m/%Y %H:%M")

    badge_update = f'<span class="fa-badge badge-update">🕐 Última actualización: {snap_time or now_str}</span>'
    if report_time:
        badge_pipeline = f'<span class="fa-badge badge-ok"><span class="badge-dot ok"></span>Pipeline activo · {report_time}</span>'
    else:
        badge_pipeline = '<span class="fa-badge badge-update">⏸ Sin pipeline reciente</span>'

    # Header
    if LOGO_FILE.exists():
        logo_b64 = _img_b64(LOGO_FILE)
        st.markdown(f"""
<div class="fa-header">
  <img src="data:image/png;base64,{logo_b64}" />
  <div class="fa-title-block">
    <div class="fa-title">
      <h1>Agente Financiero Autónomo <span>· Juanjo</span></h1>
    </div>
    <div class="fa-subtitle">Monitoreo de indicadores financieros en tiempo real</div>
    <div class="fa-badges">{badge_update}{badge_pipeline}</div>
  </div>
</div>""", unsafe_allow_html=True)
    else:
        st.markdown(
            "# Agente Financiero Autónomo <span style='font-size:0.5em;color:#00C896'>· Juanjo</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="fa-badges">{badge_update}{badge_pipeline}</div>',
                    unsafe_allow_html=True)

    if st.button("🔄 Actualizar datos", type="secondary"):
        with st.spinner("Recolectando datos del mercado..."):
            # 1. Backfill historical data for any newly activated indicators
            subprocess.run(
                [sys.executable, "-m", "scripts.backfill_history"],
                cwd=str(ROOT), check=False, capture_output=True,
            )
            # 2. Collect today's prices
            subprocess.run(
                [sys.executable, "-m", "scripts.market_collector"],
                cwd=str(ROOT), check=False, capture_output=True,
            )
            # 3. Rebuild snapshot
            subprocess.run(
                [sys.executable, "-m", "scripts.processor"],
                cwd=str(ROOT), check=False, capture_output=True,
            )
        st.cache_data.clear()
        st.rerun()

    active       = _load_active_indicators()
    snapshot_df  = load_snapshot(active)
    hist_df      = load_historical_comparison(active)
    report_text  = load_report()
    news_api_key = get_secret("NEWS_API_KEY")

    # ── Snapshot ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Precios en tiempo real</div>', unsafe_allow_html=True)
    if snapshot_df.empty:
        st.warning("No hay datos en latest_snapshot.csv")
    else:
        rows_data = list(snapshot_df.iterrows())
        # All cards in one row with equal-width columns (config limits to max 5)
        cols = st.columns(len(rows_data))
        for col, (_, row) in zip(cols, rows_data):
            indicator = str(row["indicator"]).upper()
            value_str = format_metric_value(row["value"], row["unit"])
            try:
                chg = float(row["change_pct"])
                arrow_cls   = "up" if chg >= 0 else "down"
                arrow_sym   = "▲" if chg >= 0 else "▼"
                delta_class = "pos" if chg >= 0 else "neg"
                delta_html  = (
                    f'<span class="mc-delta {delta_class}">'
                    f'<span class="mc-arrow {arrow_cls}">{arrow_sym}</span>'
                    f' {chg:+.2f}%</span>'
                )
            except Exception:
                delta_html = '<span class="mc-delta neu">N/A</span>'
            col.markdown(f"""
<div class="metric-card">
  <div class="mc-label">{indicator}</div>
  <div class="mc-value">{value_str}</div>
  {delta_html}
</div>""", unsafe_allow_html=True)

    st.markdown("<div style='margin:28px 0 4px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Variación histórica ──────────────────────────────────────────────────
    st.markdown('<div class="section-label">Variación histórica — hoy vs 7d vs 30d</div>',
                unsafe_allow_html=True)
    if hist_df.empty:
        st.warning("No hay datos en market_history.csv")
    else:
        def fmt_v(v):
            return f"{v:,.2f}" if pd.notna(v) else "—"
        def fmt_d(d):
            if not pd.notna(d):
                return "—", "neu"
            return (f"{'▲' if d >= 0 else '▼'} {d:+.2f}%", "pos" if d >= 0 else "neg")

        hist_rows_data = list(hist_df.iterrows())
        # Equal-width columns for all cards in one row (max 5 per config)
        hist_cols = st.columns(len(hist_rows_data))
        for col, (_, row) in zip(hist_cols, hist_rows_data):
            d7s,  d7c  = fmt_d(row["Δ 7d (%)"])
            d30s, d30c = fmt_d(row["Δ 30d (%)"])
            with col:
                st.markdown(f"""
<div class="hist-card">
  <div class="hc-title">
    {row['Indicador']}
    <span class="hc-unit">{row['Unidad']}</span>
  </div>
  <div class="hist-row">
    <span class="hr-period">Hoy</span>
    <span class="hr-value">{fmt_v(row['Hoy'])}</span>
  </div>
  <div class="hist-row">
    <span class="hr-period">Hace 7d</span>
    <span class="hr-value">{fmt_v(row['Hace 7d'])}</span>
    <span class="hr-delta {d7c}">{d7s}</span>
  </div>
  <div class="hist-row">
    <span class="hr-period">Hace 30d</span>
    <span class="hr-value">{fmt_v(row['Hace 30d'])}</span>
    <span class="hr-delta {d30c}">{d30s}</span>
  </div>
</div>""", unsafe_allow_html=True)


    st.markdown("<div style='margin:28px 0 4px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Titulares ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Titulares recientes por indicador</div>',
                unsafe_allow_html=True)
    if not news_api_key:
        st.warning("NEWS_API_KEY no configurada.")
    else:
        cards_html = ""
        for label, (query, use_rss) in _build_news_queries().items():
            headlines  = fetch_headlines(label, query, news_api_key, use_rss=use_rss)
            if not headlines:
                items_html = '<div class="news-item" style="color:#8A9BA8;font-size:0.85rem">Sin titulares disponibles.</div>'
            else:
                items_html = ""
                for h in headlines:
                    t      = h["title"].replace("<", "&lt;").replace(">", "&gt;")
                    l      = h.get("url", "")
                    m      = f"{h['source']} · {h['publishedAt']}"
                    linked = f'<a href="{l}" target="_blank">{t}</a>' if l else t
                    items_html += f'<div class="news-item">{linked}<div class="news-meta">{m}</div></div>'
            cards_html += (
                f'<div class="news-block">'
                f'<div class="news-block-title">{label}</div>'
                f'{items_html}</div>'
            )
        st.markdown(f'<div class="news-grid">{cards_html}</div>', unsafe_allow_html=True)

    st.markdown("<div style='margin:28px 0 4px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Gráficas históricas ──────────────────────────────────────────────────
    st.markdown('<div class="section-label">Evolución histórica de precios</div>',
                unsafe_allow_html=True)
    if not HISTORY_FILE.exists():
        st.warning("No hay datos en market_history.csv")
    else:
        hist_raw = pd.read_csv(HISTORY_FILE)
        hist_raw["timestamp"] = pd.to_datetime(hist_raw["timestamp"], errors="coerce", format="mixed")
        hist_raw["value"]     = pd.to_numeric(hist_raw["value"], errors="coerce")
        hist_raw = hist_raw.dropna(subset=["timestamp", "value"]).sort_values(["indicator", "timestamp"])
        hist_raw = hist_raw[hist_raw["indicator"].isin(active)]

        indicators = sorted(hist_raw["indicator"].dropna().unique().tolist())
        selected   = st.selectbox(
            "Selecciona un indicador", indicators,
            key=f"chart_sel_{'_'.join(active)}",
        )
        filtered = hist_raw[hist_raw["indicator"] == selected].copy()

        if not filtered.empty:
            line_color, fill_color = _IND_COLORS.get(selected, _DEFAULT_COLOR)
            single_point = len(filtered) == 1

            if single_point:
                fig = px.scatter(filtered, x="timestamp", y="value",
                                 title=f"Histórico — {selected.upper()}")
                fig.update_traces(marker=dict(size=14, color=line_color))
                st.info("Solo 1 día de datos. La gráfica crecerá con el pipeline diario.")
            else:
                fig = px.area(filtered, x="timestamp", y="value",
                              title=f"Histórico — {selected.upper()}")
                fig.update_traces(
                    line=dict(color=line_color, width=2),
                    fillcolor=fill_color,
                    marker=dict(size=4, color=line_color),
                    hovertemplate="<b>%{x|%d %b %Y}</b><br>%{y:,.4f}<extra></extra>",
                )

            label = _CATALOG.get(selected, {}).get("label", selected.upper())
            unit  = filtered["unit"].iloc[-1] if "unit" in filtered.columns else ""
            fig.update_layout(
                title=dict(text=f"<b>{label}</b>  <span style='font-size:13px;color:#8A9BB0'>({unit})</span>",
                           font=dict(size=16, color="#1B2A4A"), x=0),
                xaxis_title="", yaxis_title=unit,
                hovermode="x unified",
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                font=dict(color="#1B2A4A", size=12),
                xaxis=dict(gridcolor="#F0F4F8", showline=False, zeroline=False),
                yaxis=dict(gridcolor="#F0F4F8", showline=False, zeroline=False),
                margin=dict(t=52, b=24, l=60, r=20),
                legend=dict(visible=False),
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("Ver últimos 20 registros"):
                st.dataframe(
                    filtered.tail(20)[["timestamp","indicator","value","open_value",
                                       "change_abs","change_pct","unit","source","status"]],
                    use_container_width=True, hide_index=True,
                )

    st.markdown("<div style='margin:28px 0 4px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Señales del Agente ───────────────────────────────────────────────────
    st.markdown('<div class="section-label">Señales del Agente</div>',
                unsafe_allow_html=True)
    daily_signals = load_daily_signals()
    if not daily_signals:
        st.info("Las señales se generan automáticamente con el pipeline diario.")
    else:
        _s  = daily_signals.get("senales", {})
        _i  = daily_signals.get("interpretacion", {})
        _gen = daily_signals.get("generado_en", "")

        # Color class helpers
        def _sig_cls(key: str, val: str) -> str:
            _map = {
                "riesgo_macro":          {"Bajo": "sig-ok", "Medio": "sig-warn", "Alto": "sig-alert"},
                "sesgo_mercado":         {"Risk-on": "sig-ok", "Mixto": "sig-neu", "Risk-off": "sig-alert"},
                "presion_inflacionaria": {"Bajista": "sig-ok", "Neutral": "sig-neu", "Alcista": "sig-warn"},
                "presion_cop":           {"Favorable COP": "sig-ok", "Neutral": "sig-neu", "Alcista USD/COP": "sig-warn"},
            }
            return _map.get(key, {}).get(val, "sig-neu")

        def _conv_cls(v: int) -> str:
            return "sig-ok" if v >= 7 else ("sig-warn" if v >= 4 else "sig-alert")

        conv = _s.get("conviccion", 0)
        badges = [
            ("Riesgo Macro",          _s.get("riesgo_macro",            "—"), _sig_cls("riesgo_macro",          _s.get("riesgo_macro", ""))),
            ("Sesgo de Mercado",      _s.get("sesgo_mercado",           "—"), _sig_cls("sesgo_mercado",         _s.get("sesgo_mercado", ""))),
            ("Presión Inflacionaria", _s.get("presion_inflacionaria",   "—"), _sig_cls("presion_inflacionaria", _s.get("presion_inflacionaria", ""))),
            ("Presión COP",           _s.get("presion_cop",             "—"), _sig_cls("presion_cop",           _s.get("presion_cop", ""))),
            ("Convicción",            f"{conv}/10",                           _conv_cls(conv)),
        ]

        strip_html = "".join(
            f'<div class="sig-badge {cls}">'
            f'<span class="sig-badge-label">{lbl}</span>'
            f'<span class="sig-badge-value">{val}</span>'
            f'</div>'
            for lbl, val, cls in badges
        )
        st.markdown(
            f'<div style="font-size:0.7rem;color:#8A9BB0;margin-bottom:10px">'
            f'Generado: {_gen}</div>'
            f'<div class="sig-strip">{strip_html}</div>',
            unsafe_allow_html=True,
        )

        # Agent reading card
        cierre   = _i.get("cierre_ejecutivo",  "")
        cruzada  = _i.get("lectura_cruzada",   "")
        driver1  = _i.get("driver_principal",  "")
        driver2  = _i.get("driver_secundario", "")

        def _esc(t: str) -> str:
            return t.replace("<", "&lt;").replace(">", "&gt;")

        st.markdown(f"""
<div class="agent-card">
  <div class="agent-card-header">🤖 Lectura del Agente</div>
  <div class="agent-field">
    <span class="agent-field-label">Cierre ejecutivo</span>
    <span class="agent-field-value">{_esc(cierre)}</span>
  </div>
  <div class="agent-field">
    <span class="agent-field-label">Lectura cruzada</span>
    <span class="agent-field-value">{_esc(cruzada)}</span>
  </div>
  <div class="agent-drivers">
    <div class="agent-driver">
      <span class="agent-driver-lbl">🔷 Driver principal</span>
      {_esc(driver1)}
    </div>
    <div class="agent-driver">
      <span class="agent-driver-lbl">🔶 Driver secundario</span>
      {_esc(driver2)}
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("<div style='margin:28px 0 4px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Reporte del día ──────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Reporte del día — análisis IA</div>',
                unsafe_allow_html=True)
    if report_text:
        date_label = f"Generado el {report_time}" if report_time else ""
        body = report_text.replace("<", "&lt;").replace(">", "&gt;")
        st.markdown(f"""
<div class="report-card">
  <div class="report-date">📄 {date_label}</div>
  <div class="report-body">{body}</div>
</div>""", unsafe_allow_html=True)
    else:
        st.info("El reporte se genera automáticamente cada día a las 7:00 AM (Colombia).")


# ── Navegación ────────────────────────────────────────────────────────────────
pg = st.navigation([
    st.Page(run_dashboard, title="Dashboard", icon="📊", default=True),
    st.Page("pages/admin.py", title="Panel de Control", icon="⚙️"),
])
pg.run()
