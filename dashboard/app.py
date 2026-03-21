import os
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Financial Agent Dashboard", layout="wide")

CLEAN_FILE = "data/processed/market_clean.csv"
SNAPSHOT_FILE = "data/processed/latest_snapshot.csv"
REPORT_FILE = "reports/daily_report.txt"


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


st.title("Financial Agent Dashboard")
st.caption("Monitoreo de indicadores financieros del MVP")

snapshot_df = load_snapshot()
clean_df = load_clean_data()
report_text = load_report()

st.subheader("Último snapshot")
if snapshot_df.empty:
    st.warning("No hay datos en latest_snapshot.csv")
else:
    cols = st.columns(len(snapshot_df))
    for i, (_, row) in enumerate(snapshot_df.iterrows()):
        indicator = str(row["indicator"]).upper()
        value = row["value"]
        unit = row["unit"]
        change_pct = row["change_pct"]

        delta_text = "N/A"
        try:
            delta_text = f"{float(change_pct):.2f}%"
        except Exception:
            pass

        cols[i].metric(
            label=indicator,
            value=format_metric_value(value, unit),
            delta=delta_text
        )

st.divider()

st.subheader("Gráficas históricas")
if clean_df.empty:
    st.warning("No hay datos en market_clean.csv")
else:
    indicators = clean_df["indicator"].dropna().unique().tolist()
    selected = st.selectbox("Selecciona un indicador", indicators)

    filtered = clean_df[clean_df["indicator"] == selected].copy()
    filtered = filtered.sort_values("timestamp")

    if filtered.empty:
        st.warning("No hay datos para el indicador seleccionado.")
    else:
        st.write(f"Registros disponibles para **{selected.upper()}**: {len(filtered)}")

        fig = px.line(
            filtered,
            x="timestamp",
            y="value",
            title=f"Histórico de {selected.upper()}",
            markers=True
        )

        fig.update_layout(
            xaxis_title="Fecha y hora",
            yaxis_title="Valor",
            hovermode="x unified"
        )

        st.plotly_chart(fig, width="stretch")

        st.markdown("**Últimos registros del indicador seleccionado**")
        st.dataframe(
            filtered.tail(20)[
                ["timestamp", "indicator", "value", "open_value", "change_abs", "change_pct", "unit", "source", "status"]
            ],
            width="stretch"
        )

st.divider()

st.subheader("Reporte diario generado por IA")
st.text(report_text)