import os
import base64
from pathlib import Path
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

# Rutas absolutas desde la raíz del repo — funciona local y en Streamlit Cloud
ROOT          = Path(__file__).parent.parent
CLEAN_FILE    = ROOT / "data/processed/market_clean.csv"
SNAPSHOT_FILE = ROOT / "data/processed/latest_snapshot.csv"
HISTORY_FILE  = ROOT / "data/historical/market_history.csv"
REPORT_FILE   = ROOT / "reports/daily_report.txt"
LOGO_FILE     = ROOT / "logo.png"

BRAND_CSS = """
<style>
/* ── Base ───────────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] { background-color: #F7FAFB; }
[data-testid="stSidebar"]          { background-color: #EBF7F8; }

/* Remove Streamlit top padding */
[data-testid="stAppViewBlockContainer"],
[data-testid="stMainBlockContainer"],
.block-container {
    padding-top: 0 !important;
    margin-top: 0 !important;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.fa-header {
    display: flex;
    align-items: center;
    gap: 32px;
    padding: 20px 0 16px 0;
    border-bottom: 4px solid #3DB860;
    margin-bottom: 32px;
}
.fa-header img  { height: 120px; width: auto; flex-shrink: 0; }
.fa-title       { line-height: 1.1; }
.fa-title h1    {
    margin: 0; color: #1E7A8C;
    font-size: 6rem; font-weight: 800; letter-spacing: -2px;
}
.fa-title span  { color: #3DB860; font-size: 3rem; font-weight: 500; }
.fa-subtitle    {
    color: #5A8A95; font-size: 1rem;
    margin-top: 6px; font-style: italic;
}

/* ── Section titles ─────────────────────────────────────────────────────── */
h2, h3 { color: #1E7A8C !important; }
hr     { border-color: #3DB860 !important; opacity: 0.25; }

/* ── Snapshot metric cards ──────────────────────────────────────────────── */
.metric-card {
    background: #FFFFFF;
    border: 1px solid #D9EEF1;
    border-radius: 12px;
    padding: 20px 16px 16px 16px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(30,122,140,0.07);
    height: 100%;
}
.metric-card .mc-label {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #5A8A95;
    margin-bottom: 8px;
}
.metric-card .mc-value {
    font-size: 1.35rem;
    font-weight: 800;
    color: #1E7A8C;
    word-break: break-word;
    line-height: 1.2;
}
.metric-card .mc-delta {
    font-size: 0.85rem;
    font-weight: 600;
    margin-top: 6px;
}
.mc-delta.pos { color: #1A9E50; }
.mc-delta.neg { color: #D94040; }
.mc-delta.neu { color: #8A9BA8; }

/* ── Historical variation cards ─────────────────────────────────────────── */
.hist-card {
    background: #FFFFFF;
    border: 1px solid #D9EEF1;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 2px 8px rgba(30,122,140,0.07);
    height: 100%;
}
.hist-card .hc-title {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #5A8A95;
    margin-bottom: 12px;
    border-bottom: 2px solid #EBF7F8;
    padding-bottom: 6px;
}
.hist-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
    border-bottom: 1px solid #F0F6F7;
    font-size: 0.9rem;
}
.hist-row:last-child { border-bottom: none; }
.hist-row .hr-period { color: #8A9BA8; font-weight: 500; }
.hist-row .hr-value  { color: #1E2B36; font-weight: 700; }
.hist-row .hr-delta  { font-weight: 700; font-size: 0.82rem; padding: 2px 7px;
                       border-radius: 20px; }
.hr-delta.pos { background: #E6F9EE; color: #1A9E50; }
.hr-delta.neg { background: #FDECEC; color: #D94040; }
.hr-delta.neu { background: #F0F4F6; color: #8A9BA8; }

/* ── News cards ─────────────────────────────────────────────────────────── */
.news-section-title {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #1E7A8C;
    margin-bottom: 8px;
    padding-bottom: 4px;
    border-bottom: 2px solid #3DB860;
}
.news-item {
    padding: 8px 0;
    border-bottom: 1px solid #EEF3F4;
    line-height: 1.4;
}
.news-item:last-child { border-bottom: none; }
.news-item a {
    font-size: 0.88rem;
    font-weight: 600;
    color: #1E2B36;
    text-decoration: none;
}
.news-item a:hover { color: #1E7A8C; }
.news-meta {
    font-size: 0.75rem;
    color: #8A9BA8;
    margin-top: 2px;
}

/* ── st.metric delta icon hide ──────────────────────────────────────────── */
[data-testid="stMetricDelta"] svg { display: none; }

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
    .fa-title h1 { font-size: 3rem; }
    .fa-title span { font-size: 1.6rem; }
    .fa-header img { height: 72px; }
    .metric-card .mc-value { font-size: 1.1rem; }
}
</style>
"""

NEWS_QUERIES = {
    "Brent":   "brent crude oil price",
    "BTC":     "bitcoin BTC crypto",
    "DXY":     "US dollar DXY index",
    "USD/COP": "peso colombiano dolar Colombia",
}


def get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key)


@st.cache_data
def load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return pd.DataFrame()
    return pd.read_csv(SNAPSHOT_FILE)


def load_report():
    if not os.path.exists(REPORT_FILE):
        return "Aún no existe reporte generado."
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def format_metric_value(value, unit):
    try:
        value = float(value)
        return f"{value:,.2f} {unit}"
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


@st.cache_data(ttl=3600)
def load_historical_comparison():
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()

    df = pd.read_csv(HISTORY_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp", "value"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    today = df["timestamp"].max().normalize()
    d7    = today - pd.Timedelta(days=7)
    d30   = today - pd.Timedelta(days=30)

    def closest(grp, target):
        sub = grp[grp["timestamp"].dt.normalize() <= target]
        if sub.empty:
            return None
        return sub.sort_values("timestamp").iloc[-1]

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
            "fecha_hoy": r_now["timestamp"].date() if r_now is not None else None,
        })

    return pd.DataFrame(rows)


def fetch_headlines(indicator, query, api_key, max_results=3):
    if indicator == "USD/COP":
        return fetch_headlines_rss(
            "peso colombiano dolar TRM Colombia",
            lang="es-CO", gl="CO", ceid="CO:es",
            max_results=max_results,
        )
    if api_key:
        results = fetch_headlines_newsapi(query, api_key, max_results)
        if results:
            return results
    return fetch_headlines_rss(query, lang="en-US", gl="US", ceid="US:en", max_results=max_results)


def _img_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ── Página principal del dashboard ───────────────────────────────────────────
def run_dashboard():
    st.markdown(BRAND_CSS, unsafe_allow_html=True)

    if LOGO_FILE.exists():
        logo_b64 = _img_b64(LOGO_FILE)
        st.markdown(f"""
<div class="fa-header">
  <img src="data:image/png;base64,{logo_b64}" />
  <div class="fa-title">
    <h1>Agente Financiero Autónomo <span>· Juanjo</span></h1>
    <div class="fa-subtitle">Monitoreo de indicadores financieros en tiempo real</div>
  </div>
</div>
""", unsafe_allow_html=True)
    else:
        st.markdown(
            "# Agente Financiero Autónomo <span style='font-size:0.5em;color:#2DBD6E;'>· Juanjo</span>",
            unsafe_allow_html=True,
        )
        st.caption("Monitoreo de indicadores financieros en tiempo real")

    snapshot_df  = load_snapshot()
    report_text  = load_report()
    hist_df      = load_historical_comparison()
    news_api_key = get_secret("NEWS_API_KEY")

    # ── Snapshot ─────────────────────────────────────────────────────────────
    st.subheader("Último snapshot")
    if snapshot_df.empty:
        st.warning("No hay datos en latest_snapshot.csv")
    else:
        cols = st.columns(len(snapshot_df))
        for i, (_, row) in enumerate(snapshot_df.iterrows()):
            indicator  = str(row["indicator"]).upper()
            value_str  = format_metric_value(row["value"], row["unit"])
            try:
                chg = float(row["change_pct"])
                delta_str   = f"{'▲' if chg >= 0 else '▼'} {chg:+.2f}%"
                delta_class = "pos" if chg >= 0 else "neg"
            except Exception:
                delta_str, delta_class = "N/A", "neu"
            cols[i].markdown(f"""
<div class="metric-card">
  <div class="mc-label">{indicator}</div>
  <div class="mc-value">{value_str}</div>
  <div class="mc-delta {delta_class}">{delta_str}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Variación histórica ──────────────────────────────────────────────────
    st.subheader("Variación histórica — Hoy vs 7d vs 30d")

    if hist_df.empty:
        st.warning("No hay datos en market_history.csv")
    else:
        hist_cols = st.columns(len(hist_df))
        for col, (_, row) in zip(hist_cols, hist_df.iterrows()):
            def fmt_val(v):
                return f"{v:,.2f}" if pd.notna(v) else "—"
            def fmt_delta(d):
                if not pd.notna(d):
                    return "—", "neu"
                cls = "pos" if d >= 0 else "neg"
                return f"{'▲' if d >= 0 else '▼'} {d:+.2f}%", cls

            d7s,  d7cls  = fmt_delta(row["Δ 7d (%)"])
            d30s, d30cls = fmt_delta(row["Δ 30d (%)"])
            with col:
                st.markdown(f"""
<div class="hist-card">
  <div class="hc-title">{row['Indicador']} <span style="font-weight:400;text-transform:none;font-size:0.72rem">{row['Unidad']}</span></div>
  <div class="hist-row">
    <span class="hr-period">Hoy</span>
    <span class="hr-value">{fmt_val(row['Hoy'])}</span>
  </div>
  <div class="hist-row">
    <span class="hr-period">Hace 7d</span>
    <span class="hr-value">{fmt_val(row['Hace 7d'])}</span>
    <span class="hr-delta {d7cls}">{d7s}</span>
  </div>
  <div class="hist-row">
    <span class="hr-period">Hace 30d</span>
    <span class="hr-value">{fmt_val(row['Hace 30d'])}</span>
    <span class="hr-delta {d30cls}">{d30s}</span>
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Titulares de noticias ────────────────────────────────────────────────
    st.subheader("Titulares recientes por indicador")

    if not news_api_key:
        st.warning("NEWS_API_KEY no configurada.")
    else:
        indicator_cols = st.columns(len(NEWS_QUERIES))
        for col, (label, query) in zip(indicator_cols, NEWS_QUERIES.items()):
            headlines = fetch_headlines(label, query, news_api_key)
            with col:
                st.markdown(f'<div class="news-section-title">{label}</div>', unsafe_allow_html=True)
                if not headlines:
                    st.caption("Sin titulares disponibles.")
                else:
                    items_html = ""
                    for h in headlines:
                        title = h["title"].replace("<", "&lt;").replace(">", "&gt;")
                        link  = h.get("url", "")
                        meta  = f"{h['source']}  ·  {h['publishedAt']}"
                        linked = f'<a href="{link}" target="_blank">{title}</a>' if link else title
                        items_html += f'<div class="news-item">{linked}<div class="news-meta">{meta}</div></div>'
                    st.markdown(items_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Gráficas históricas ──────────────────────────────────────────────────
    st.subheader("Gráficas históricas")
    if not HISTORY_FILE.exists():
        st.warning("No hay datos en market_history.csv")
    else:
        hist_raw = pd.read_csv(HISTORY_FILE)
        hist_raw["timestamp"] = pd.to_datetime(hist_raw["timestamp"], errors="coerce")
        hist_raw["value"]     = pd.to_numeric(hist_raw["value"], errors="coerce")
        hist_raw = hist_raw.dropna(subset=["timestamp", "value"]).sort_values(["indicator", "timestamp"])

        indicators = hist_raw["indicator"].dropna().unique().tolist()
        selected   = st.selectbox("Selecciona un indicador", indicators)
        filtered   = hist_raw[hist_raw["indicator"] == selected].copy()

        if filtered.empty:
            st.warning("No hay datos para el indicador seleccionado.")
        else:
            st.write(f"Registros disponibles para **{selected.upper()}**: {len(filtered)}")
            fig = px.line(filtered, x="timestamp", y="value",
                          title=f"Histórico de {selected.upper()}", markers=True,
                          color_discrete_sequence=["#1E7A8C"])
            fig.update_layout(xaxis_title="Fecha", yaxis_title="Valor",
                              hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("**Últimos 20 registros**")
            st.dataframe(
                filtered.tail(20)[["timestamp", "indicator", "value", "open_value",
                                    "change_abs", "change_pct", "unit", "source", "status"]],
                use_container_width=True, hide_index=True,
            )

    st.divider()

    # ── Reporte IA ───────────────────────────────────────────────────────────
    st.subheader("Reporte diario generado por IA")
    st.text(report_text)


# ── Navegación ───────────────────────────────────────────────────────────────
pg = st.navigation([
    st.Page(run_dashboard, title="Dashboard", icon="📊", default=True),
    st.Page("pages/admin.py", title="Panel de Control", icon="⚙️"),
])
pg.run()
