import json
import os
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

from scripts.news_collector import get_headlines

SNAPSHOT_FILE  = "data/processed/latest_snapshot.csv"
HISTORY_FILE   = "data/historical/market_history.csv"
REPORTS_DIR    = "reports"
REPORT_FILE    = os.path.join(REPORTS_DIR, "daily_report.txt")
SIGNALS_FILE   = "data/signals/daily_signals.json"
CONTEXT_FILE   = "data/processed/report_context.json"


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

    today = df["timestamp"].max().normalize()
    d7    = today - pd.Timedelta(days=7)
    d30   = today - pd.Timedelta(days=30)

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


def fetch_news(indicator, api_key, max_headlines=2):
    """Retorna titulares para el indicador usando news_collector centralizado."""
    return get_headlines(indicator, api_key, max_results=max_headlines)


def build_market_context(df, news_api_key):
    """Construye el contexto de mercado + titulares de noticias por indicador."""
    market_lines      = []
    news_lines        = []
    news_by_indicator = {}

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
        news_by_indicator[indicator] = headlines
        if headlines:
            news_lines.append(f"{indicator.upper()}:")
            news_lines.extend(headlines)
        else:
            news_lines.append(f"{indicator.upper()}: sin titulares disponibles")

    return "\n".join(market_lines), "\n".join(news_lines), news_by_indicator


def build_signals_sections() -> str:
    """Construye las secciones 5 y 6 del reporte desde daily_signals.json."""
    if not os.path.exists(SIGNALS_FILE):
        return ""
    try:
        with open(SIGNALS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""

    s   = data.get("senales", {})
    i   = data.get("interpretacion", {})
    gen = data.get("generado_en", "")

    lines = [
        "",
        "=" * 55,
        "SECCIÓN 5 — SEÑALES ACCIONABLES",
        f"Generado: {gen}",
        "=" * 55,
        f"  Riesgo Macro           : {s.get('riesgo_macro',            'N/A')}",
        f"  Sesgo de Mercado       : {s.get('sesgo_mercado',           'N/A')}",
        f"  Presión Inflacionaria  : {s.get('presion_inflacionaria',   'N/A')}",
        f"  Presión COP            : {s.get('presion_cop',             'N/A')}",
        f"  Convicción             : {s.get('conviccion',              'N/A')}/10",
        "",
        "=" * 55,
        "SECCIÓN 6 — INTERPRETACIÓN CAUSAL",
        "=" * 55,
        "",
        "Driver principal:",
        f"  {i.get('driver_principal',  'N/A')}",
        "",
        "Driver secundario:",
        f"  {i.get('driver_secundario', 'N/A')}",
        "",
        "Lectura cruzada:",
        f"  {i.get('lectura_cruzada',   'N/A')}",
        "",
        "Cierre ejecutivo:",
        f"  {i.get('cierre_ejecutivo',  'N/A')}",
    ]
    return "\n".join(lines)


def save_report_context(market_context, news_context, historical_context, news_by_indicator):
    """
    Guarda todo el contexto necesario para que Claude genere el reporte.
    Este archivo es leído por la tarea programada de Cowork (claude-daily-report).
    """
    os.makedirs("data/processed", exist_ok=True)

    signals_data = {}
    signals_age_days = None
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, encoding="utf-8") as f:
                signals_data = json.load(f)
            # Calcular antigüedad de las señales
            sig_date_str = signals_data.get("fecha", "")
            if sig_date_str:
                sig_date = datetime.strptime(sig_date_str, "%Y-%m-%d")
                signals_age_days = (datetime.now() - sig_date).days
                if signals_age_days > 1:
                    print(f"  [AVISO] Señales del agente tienen {signals_age_days} días de antigüedad ({sig_date_str})")
        except Exception as e:
            print(f"  [AVISO] Error leyendo señales: {e}")

    # Conteo de indicadores con/sin noticias
    news_count = sum(1 for v in news_by_indicator.values() if v)
    news_total = len(news_by_indicator)

    context = {
        "generado_en":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fecha":                datetime.now().strftime("%Y-%m-%d"),
        "market_context":       market_context,
        "historical_context":   historical_context,
        "news_context":         news_context,
        "news_by_indicator":    news_by_indicator,
        "news_coverage":        f"{news_count}/{news_total} indicadores con noticias",
        "signals":              signals_data,
        "signals_age_days":     signals_age_days,
        "signals_sections_text": build_signals_sections(),
    }

    with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    print(f"Contexto guardado en: {CONTEXT_FILE}")
    return context


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

    news_api_key = os.getenv("NEWS_API_KEY")

    print("Recolectando datos de mercado y noticias...")

    df = load_snapshot()
    market_context, news_context, news_by_indicator = build_market_context(df, news_api_key)
    historical_context = build_historical_context()

    print("\n--- Titulares obtenidos ---")
    print(news_context)
    print("-" * 30)
    print("\n--- Contexto histórico ---")
    print(historical_context)
    print("-" * 30)

    save_report_context(market_context, news_context, historical_context, news_by_indicator)

    print("\nContexto listo. El reporte será generado por Claude (tarea programada de Cowork).")


if __name__ == "__main__":
    main()
