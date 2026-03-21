import os
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Financial Agent Dashboard", layout="wide")

CLEAN_FILE    = "data/processed/market_clean.csv"
SNAPSHOT_FILE = "data/processed/latest_snapshot.csv"
REPORT_FILE   = "reports/daily_report.txt"

NEWS_QUERIES = {
    "Brent":   "brent crude oil price",
    "BTC":     "bitcoin BTC crypto",
    "DXY":     "US dollar DXY index",
    "USD/COP": "peso colombiano dolar Colombia",
}


def get_secret(key):
    """Lee desde st.secrets (Streamlit Cloud) o variables de entorno (local)."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key)


@st.cache_data
def load_clean_data():
    if not os.path.exists(CLEAN_FILE):
        return pd.DataFrame()
    df = pd.read_csv(CLEAN_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values(["indicator", "timestamp"]).reset_index(drop=True)
    return df


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
def fetch_headlines(indicator, query, api_key, max_results=3):
    """Busca titulares en NewsAPI. Cache de 1 hora."""
    if not api_key:
        return []
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


# ── Encabezado ──────────────────────────────────────────────────────────────
st.markdown(
    "# Financial Agent Dashboard <span style='font-size:0.5em; font-weight:400;'>Juanjo</span>",
    unsafe_allow_html=True,
)
st.caption("Monitoreo de indicadores financieros del MVP")

snapshot_df = load_snapshot()
clean_df    = load_clean_data()
report_text = load_report()
news_api_key = get_secret("NEWS_API_KEY")

# ── Snapshot ─────────────────────────────────────────────────────────────────
st.subheader("Último snapshot")
if snapshot_df.empty:
    st.warning("No hay datos en latest_snapshot.csv")
else:
    cols = st.columns(len(snapshot_df))
    for i, (_, row) in enumerate(snapshot_df.iterrows()):
        indicator  = str(row["indicator"]).upper()
        value      = row["value"]
        unit       = row["unit"]
        change_pct = row["change_pct"]
        delta_text = "N/A"
        try:
            delta_text = f"{float(change_pct):.2f}%"
        except Exception:
            pass
        cols[i].metric(
            label=indicator,
            value=format_metric_value(value, unit),
            delta=delta_text,
        )

st.divider()

# ── Titulares de noticias ────────────────────────────────────────────────────
st.subheader("Titulares recientes por indicador")

if not news_api_key:
    st.warning("NEWS_API_KEY no configurada. Agrega la clave en Streamlit Secrets o en .env")
else:
    indicator_cols = st.columns(len(NEWS_QUERIES))
    for col, (label, query) in zip(indicator_cols, NEWS_QUERIES.items()):
        headlines = fetch_headlines(label, query, news_api_key)
        with col:
            st.markdown(f"**{label}**")
            if not headlines:
                st.caption("Sin titulares disponibles.")
            else:
                for h in headlines:
                    with st.container(border=True):
                        if h["url"]:
                            st.markdown(f"[{h['title']}]({h['url']})")
                        else:
                            st.markdown(h["title"])
                        st.caption(f"{h['source']}  ·  {h['publishedAt']}")

st.divider()

# ── Gráficas históricas ──────────────────────────────────────────────────────
st.subheader("Gráficas históricas")
if clean_df.empty:
    st.warning("No hay datos en market_clean.csv")
else:
    indicators = clean_df["indicator"].dropna().unique().tolist()
    selected   = st.selectbox("Selecciona un indicador", indicators)
    filtered   = clean_df[clean_df["indicator"] == selected].copy().sort_values("timestamp")

    if filtered.empty:
        st.warning("No hay datos para el indicador seleccionado.")
    else:
        st.write(f"Registros disponibles para **{selected.upper()}**: {len(filtered)}")
        fig = px.line(filtered, x="timestamp", y="value",
                      title=f"Histórico de {selected.upper()}", markers=True)
        fig.update_layout(xaxis_title="Fecha y hora", yaxis_title="Valor",
                          hovermode="x unified")
        st.plotly_chart(fig, width="stretch")

        st.markdown("**Últimos registros del indicador seleccionado**")
        st.dataframe(
            filtered.tail(20)[["timestamp", "indicator", "value", "open_value",
                                "change_abs", "change_pct", "unit", "source", "status"]],
            width="stretch",
        )

st.divider()

# ── Reporte IA ───────────────────────────────────────────────────────────────
st.subheader("Reporte diario generado por IA")
st.text(report_text)
