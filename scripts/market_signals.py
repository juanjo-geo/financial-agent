import os
from datetime import datetime
import pandas as pd

SNAPSHOT_FILE = "data/processed/latest_snapshot.csv"
SIGNALS_DIR = "data/signals"
SIGNALS_FILE = os.path.join(SIGNALS_DIR, "latest_signals.csv")
SIGNALS_TXT_FILE = os.path.join(SIGNALS_DIR, "latest_signals.txt")


def load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        raise FileNotFoundError(f"No existe el archivo snapshot: {SNAPSHOT_FILE}")

    df = pd.read_csv(SNAPSHOT_FILE)
    return df


def classify_signal(indicator, change_pct):
    """
    Devuelve severidad, dirección y mensaje base.
    Ajustamos umbrales por indicador.
    """
    abs_change = abs(change_pct)

    # Umbrales por indicador
    thresholds = {
        "btc":                    {"low": 1.5, "medium": 3.0, "high": 5.0},
        "brent":                  {"low": 1.0, "medium": 2.5, "high": 4.0},
        "dxy":                    {"low": 0.4, "medium": 0.8, "high": 1.5},
        "usdcop":                 {"low": 0.5, "medium": 1.0, "high": 2.0},
        "global_inflation_proxy": {"low": 0.1, "medium": 0.2, "high": 0.5},
        "gold":                   {"low": 0.5, "medium": 1.5, "high": 3.0},
        "sp500":                  {"low": 0.5, "medium": 1.5, "high": 3.0},
        "wti":                    {"low": 1.0, "medium": 2.5, "high": 4.0},
    }

    t = thresholds.get(indicator, {"low": 1.0, "medium": 2.0, "high": 4.0})

    if abs_change >= t["high"]:
        severity = "high"
    elif abs_change >= t["medium"]:
        severity = "medium"
    elif abs_change >= t["low"]:
        severity = "low"
    else:
        severity = "none"

    if change_pct > 0:
        direction = "up"
    elif change_pct < 0:
        direction = "down"
    else:
        direction = "flat"

    return severity, direction


def build_signal_message(indicator, direction, severity, change_pct, value, unit):
    indicator_name_map = {
        "btc":                    "Bitcoin",
        "brent":                  "Brent",
        "dxy":                    "DXY",
        "usdcop":                 "USD/COP",
        "global_inflation_proxy": "inflación global proxy",
        "gold":                   "Oro (XAU/USD)",
        "sp500":                  "S&P 500",
        "wti":                    "WTI",
    }

    display_name = indicator_name_map.get(indicator, indicator.upper())

    if severity == "none":
        return f"Sin señal relevante en {display_name}."

    direction_text = {
        "up": "sube",
        "down": "cae",
        "flat": "permanece estable"
    }.get(direction, "se mueve")

    severity_text = {
        "low": "movimiento leve relevante",
        "medium": "movimiento relevante",
        "high": "movimiento fuerte"
    }.get(severity, "movimiento")

    return (
        f"{display_name} {direction_text} {abs(change_pct):.2f}% "
        f"({severity_text}). Valor actual: {value:,.2f} {unit}"
    )


def generate_signals(snapshot_df):
    rows = []

    for _, row in snapshot_df.iterrows():
        indicator = str(row["indicator"]).strip().lower()
        value = pd.to_numeric(row["value"], errors="coerce")
        change_pct = pd.to_numeric(row["change_pct"], errors="coerce")
        unit = str(row["unit"]).strip()

        if pd.isna(change_pct):
            continue

        severity, direction = classify_signal(indicator, change_pct)
        message = build_signal_message(indicator, direction, severity, change_pct, value, unit)

        rows.append({
            "timestamp_generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "indicator": indicator,
            "value": value,
            "change_pct": change_pct,
            "unit": unit,
            "direction": direction,
            "severity": severity,
            "message": message,
        })

    signals_df = pd.DataFrame(rows)
    return signals_df


def save_signals(signals_df):
    os.makedirs(SIGNALS_DIR, exist_ok=True)

    signals_df.to_csv(SIGNALS_FILE, index=False)

    relevant_signals = signals_df[signals_df["severity"] != "none"].copy()

    with open(SIGNALS_TXT_FILE, "w", encoding="utf-8") as f:
        f.write("SEÑALES DE MERCADO\n")
        f.write(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 50 + "\n\n")

        if relevant_signals.empty:
            f.write("No se detectaron señales relevantes.\n")
        else:
            for _, row in relevant_signals.iterrows():
                f.write(f"- {row['message']}\n")

    return relevant_signals


def main():
    print("Generando señales de mercado...")

    snapshot_df = load_snapshot()
    signals_df = generate_signals(snapshot_df)
    relevant_signals = save_signals(signals_df)

    print("\nTodas las señales:")
    print(signals_df[["indicator", "change_pct", "severity", "direction", "message"]])

    print("\nSeñales relevantes:")
    if relevant_signals.empty:
        print("No se detectaron señales relevantes.")
    else:
        print(relevant_signals[["indicator", "change_pct", "severity", "message"]])

    print(f"\nArchivo CSV guardado en: {SIGNALS_FILE}")
    print(f"Archivo TXT guardado en: {SIGNALS_TXT_FILE}")


if __name__ == "__main__":
    main()