import os
import json
import base64
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
/* ── Base ───────────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] { background-color: #F0F4F8; }
[data-testid="stSidebar"]          { background-color: #E8F1F8; }
[data-testid="stAppViewBlockContainer"],
[data-testid="stMainBlockContainer"],
.block-container { padding-top: 0 !important; margin-top: 0 !important; }

/* ── Header ─────────────────────────────────────────────────────────────── */
.fa-header {
    display: flex;
    align-items: center;
    gap: 28px;
    padding: 20px 0 16px 0;
    border-bottom: 3px solid #00C896;
    margin-bottom: 28px;
    flex-wrap: wrap;
}
.fa-header img  { height: 110px; width: auto; flex-shrink: 0; }
.fa-title-block { flex: 1; min-width: 220px; }
.fa-title       { line-height: 1.05; }
.fa-title h1    { margin: 0; color: #1B2A4A; font-size: 6rem;
                  font-weight: 800; letter-spacing: -2px; }
.fa-title span  { color: #00C896; font-size: 3rem; font-weight: 500; }
.fa-subtitle    { color: #6B7C93; font-size: 0.95rem;
                  margin-top: 6px; font-style: italic; }
.fa-badges      { display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.fa-badge {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 0.78rem; font-weight: 600;
    padding: 4px 12px; border-radius: 20px; white-space: nowrap;
}
.badge-update { background: #E8F1F8; color: #1B2A4A; border: 1px solid #C8D8E8; }
.badge-ok     { background: #E0FAF3; color: #008A68; border: 1px solid #A0E8D0; }
.badge-dot    { width: 7px; height: 7px; border-radius: 50%; }
.badge-dot.ok  { background: #00C896;
                 box-shadow: 0 0 0 2px rgba(0,200,150,0.3);
                 animation: pulse 2s ease-in-out infinite; }
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 2px rgba(0,200,150,0.3); }
    50%       { box-shadow: 0 0 0 5px rgba(0,200,150,0.1); }
}

/* ── Section headings ───────────────────────────────────────────────────── */
h2, h3 { color: #1B2A4A !important; }
hr     { border-color: #00C896 !important; opacity: 0.2; }
.section-label {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #6B7C93;
    margin-bottom: 14px; margin-top: 4px;
}

/* ── Snapshot metric cards ──────────────────────────────────────────────── */
.metric-card {
    background: #FFFFFF;
    border: 1px solid #E2EAF0;
    border-radius: 14px;
    padding: 22px 18px 18px 18px;
    text-align: center;
    box-shadow: 0 2px 12px rgba(27,42,74,0.07);
    transition: box-shadow 0.2s;
}
.metric-card:hover { box-shadow: 0 6px 20px rgba(27,42,74,0.12); }
.mc-label {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #6B7C93; margin-bottom: 10px;
}
.mc-value {
    font-size: 1.4rem; font-weight: 800; color: #1B2A4A;
    word-break: break-word; line-height: 1.2; margin-bottom: 8px;
}
.mc-delta {
    font-size: 0.88rem; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 20px;
}
.mc-delta.pos { background: #E0FAF3; color: #008A68; }
.mc-delta.neg { background: #FFF0F0; color: #CC3333; }
.mc-delta.neu { background: #F0F4F6; color: #8A9BA8; }
.mc-arrow { display: inline-block; }
.mc-arrow.up   { animation: bounce-up   1.4s ease-in-out infinite; }
.mc-arrow.down { animation: bounce-down 1.4s ease-in-out infinite; }
@keyframes bounce-up {
    0%, 100% { transform: translateY(0); }
    50%       { transform: translateY(-4px); }
}
@keyframes bounce-down {
    0%, 100% { transform: translateY(0); }
    50%       { transform: translateY(4px); }
}

/* ── Historical variation cards ─────────────────────────────────────────── */
.hist-card {
    background: #FFFFFF; border: 1px solid #E2EAF0;
    border-radius: 14px; padding: 18px;
    box-shadow: 0 2px 12px rgba(27,42,74,0.07);
}
.hc-title {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #1B2A4A;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 2px solid #F0F4F8;
    display: flex; justify-content: space-between; align-items: baseline;
}
.hc-unit { font-size: 0.7rem; font-weight: 400;
           text-transform: none; color: #6B7C93; }
.hist-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 0; border-bottom: 1px solid #F5F8FA; font-size: 0.9rem;
}
.hist-row:last-child { border-bottom: none; }
.hr-period { color: #6B7C93; font-weight: 500; }
.hr-value  { color: #1B2A4A; font-weight: 700; }
.hr-delta  { font-weight: 700; font-size: 0.8rem;
             padding: 2px 8px; border-radius: 20px; }
.hr-delta.pos { background: #E0FAF3; color: #008A68; }
.hr-delta.neg { background: #FFF0F0; color: #CC3333; }
.hr-delta.neu { background: #F0F4F6; color: #8A9BA8; }

/* ── News ───────────────────────────────────────────────────────────────── */
.news-col-wrap {
    background: #FFFFFF; border: 1px solid #E2EAF0;
    border-radius: 14px; padding: 16px 16px 10px 16px;
    box-shadow: 0 2px 12px rgba(27,42,74,0.07);
}
.news-col-title {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #1B2A4A;
    padding-bottom: 8px; margin-bottom: 8px;
    border-bottom: 2px solid #00C896;
}
.news-item { padding: 8px 0; border-bottom: 1px solid #F0F4F8; line-height: 1.4; }
.news-item:last-child { border-bottom: none; }
.news-item a { font-size: 0.86rem; font-weight: 600; color: #1B2A4A;
               text-decoration: none; }
.news-item a:hover { color: #00C896; }
.news-meta { font-size: 0.73rem; color: #8A9BA8; margin-top: 2px; }

/* ── Report card ────────────────────────────────────────────────────────── */
.report-card {
    background: #FFFFFF; border: 1px solid #E2EAF0;
    border-radius: 14px; padding: 28px 32px;
    box-shadow: 0 2px 12px rgba(27,42,74,0.07);
    position: relative; overflow: hidden;
}
.report-card::before {
    content: ""; position: absolute; top: 0; left: 0;
    width: 4px; height: 100%; background: linear-gradient(180deg, #00C896, #3DB860);
}
.report-date {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #6B7C93; margin-bottom: 16px;
}
.report-body {
    font-size: 1.02rem; line-height: 1.8; color: #2C3E50;
    white-space: pre-wrap; font-family: Georgia, serif;
}

/* ── News grid (4 + 3 layout) ───────────────────────────────────────────── */
.news-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 18px;
    margin-top: 4px;
}
@media (max-width: 1100px) { .news-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 768px)  { .news-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px)  { .news-grid { grid-template-columns: 1fr; } }

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
    .fa-title h1 { font-size: 3rem; }
    .fa-title span { font-size: 1.6rem; }
    .fa-header img { height: 72px; }
    .mc-value { font-size: 1.1rem; }
    .report-card { padding: 18px 16px; }
}
</style>
"""

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

@st.cache_data
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


@st.cache_data
def load_historical_comparison(active: tuple):
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()
    df = pd.read_csv(HISTORY_FILE)
    df = df[df["indicator"].isin(active)]
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
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
        # Display in rows of 4
        for row_start in range(0, len(rows_data), 4):
            chunk = rows_data[row_start:row_start + 4]
            cols  = st.columns(len(chunk))
            for col, (_, row) in zip(cols, chunk):
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
        for row_start in range(0, len(hist_rows_data), 4):
            chunk     = hist_rows_data[row_start:row_start + 4]
            hist_cols = st.columns(len(chunk))
            for col, (_, row) in zip(hist_cols, chunk):
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
                f'<div class="news-col-wrap">'
                f'<div class="news-col-title">{label}</div>'
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
        hist_raw["timestamp"] = pd.to_datetime(hist_raw["timestamp"], errors="coerce")
        hist_raw["value"]     = pd.to_numeric(hist_raw["value"], errors="coerce")
        hist_raw = hist_raw.dropna(subset=["timestamp", "value"]).sort_values(["indicator", "timestamp"])
        hist_raw = hist_raw[hist_raw["indicator"].isin(active)]

        indicators = sorted(hist_raw["indicator"].dropna().unique().tolist())
        selected   = st.selectbox("Selecciona un indicador", indicators)
        filtered   = hist_raw[hist_raw["indicator"] == selected].copy()

        if not filtered.empty:
            single_point = len(filtered) == 1
            fig = px.scatter(filtered, x="timestamp", y="value",
                             title=f"Histórico de {selected.upper()}",
                             color_discrete_sequence=["#1B2A4A"]) \
                  if single_point else \
                  px.line(filtered, x="timestamp", y="value",
                          title=f"Histórico de {selected.upper()}",
                          color_discrete_sequence=["#1B2A4A"],
                          markers=True)
            if not single_point:
                fig.update_traces(line_width=2, marker_size=5)
            else:
                fig.update_traces(marker_size=12)
                st.info("Este indicador tiene solo 1 día de datos. La gráfica se completará a medida que el pipeline acumule histórico.")
            fig.update_layout(
                xaxis_title="Fecha", yaxis_title="Valor",
                hovermode="x unified",
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                font_color="#1B2A4A",
                xaxis=dict(gridcolor="#F0F4F8"),
                yaxis=dict(gridcolor="#F0F4F8"),
                title_font_size=15,
                margin=dict(t=48, b=32),
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("**Últimos 20 registros**")
            st.dataframe(
                filtered.tail(20)[["timestamp", "indicator", "value", "open_value",
                                    "change_abs", "change_pct", "unit", "source", "status"]],
                use_container_width=True, hide_index=True,
            )

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
