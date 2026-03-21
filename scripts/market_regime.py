import os
from datetime import datetime
import pandas as pd

SIGNALS_FILE = "data/signals/latest_signals.csv"
OUTPUT_FILE = "data/signals/market_regime.txt"


def load_signals():
    if not os.path.exists(SIGNALS_FILE):
        raise FileNotFoundError(f"No existe el archivo: {SIGNALS_FILE}")
    return pd.read_csv(SIGNALS_FILE)


def get_signal(signals_df, indicator_name):
    row = signals_df[signals_df["indicator"] == indicator_name]
    if row.empty:
        return None
    return row.iloc[0]


def detect_regimes(signals_df):
    regimes = []
    explanations = []

    btc = get_signal(signals_df, "btc")
    brent = get_signal(signals_df, "brent")
    dxy = get_signal(signals_df, "dxy")
    usdcop = get_signal(signals_df, "usdcop")

    if dxy is not None and dxy["direction"] == "up" and dxy["severity"] in ["medium", "high"]:
        regimes.append("Dollar Strength")
        explanations.append("El dólar global muestra fortaleza relevante por el avance del DXY.")

    if btc is not None and btc["direction"] == "up" and btc["severity"] in ["low", "medium", "high"]:
        regimes.append("Risk Appetite")
        explanations.append("Bitcoin sube, señal de apetito por riesgo y demanda especulativa.")

    if btc is not None and btc["direction"] == "down" and btc["severity"] in ["medium", "high"]:
        regimes.append("Risk Off")
        explanations.append("Bitcoin cae con fuerza, indicando menor apetito por riesgo.")

    if brent is not None and brent["direction"] == "up" and brent["severity"] in ["medium", "high"]:
        regimes.append("Inflation Pressure")
        explanations.append("El petróleo sube con intensidad, aumentando presión inflacionaria energética.")

    if brent is not None and brent["direction"] == "down" and brent["severity"] in ["low", "medium", "high"]:
        regimes.append("Energy Disinflation")
        explanations.append("El petróleo cae, reduciendo presión inflacionaria vía energía.")

    if usdcop is not None and usdcop["direction"] == "up" and usdcop["severity"] in ["low", "medium", "high"]:
        regimes.append("EM FX Pressure")
        explanations.append("USD/COP sube, señal de presión sobre la moneda colombiana.")

    if usdcop is not None and usdcop["direction"] == "down" and usdcop["severity"] in ["low", "medium", "high"]:
        regimes.append("EM FX Relief")
        explanations.append("USD/COP cae, señal de alivio relativo para la moneda colombiana.")

    # Combinaciones más interesantes
    if (
        dxy is not None and btc is not None
        and dxy["direction"] == "up"
        and btc["direction"] == "up"
    ):
        regimes.append("Mixed Macro")
        explanations.append("Dólar fuerte y Bitcoin al alza sugieren un entorno macro mixto.")

    if (
        dxy is not None and usdcop is not None
        and dxy["direction"] == "up"
        and usdcop["direction"] == "up"
    ):
        regimes.append("Dollar Pressure on COP")
        explanations.append("La fortaleza del dólar coincide con depreciación del peso colombiano.")

    if not regimes:
        regimes.append("Neutral")
        explanations.append("No se detecta un régimen macro dominante en esta sesión.")

    # quitar duplicados preservando orden
    unique_regimes = []
    unique_explanations = []

    for r, e in zip(regimes, explanations):
        if r not in unique_regimes:
            unique_regimes.append(r)
            unique_explanations.append(e)

    return unique_regimes, unique_explanations


def build_report(signals_df):
    regimes, explanations = detect_regimes(signals_df)

    lines = []
    lines.append("MARKET REGIME REPORT")
    lines.append("------------------------------")
    lines.append(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("REGÍMENES DETECTADOS")
    lines.append("------------------------------")

    for regime in regimes:
        lines.append(f"- {regime}")

    lines.append("")
    lines.append("EXPLICACIÓN")
    lines.append("------------------------------")

    for explanation in explanations:
        lines.append(f"- {explanation}")

    lines.append("")
    lines.append("SEÑALES BASE")
    lines.append("------------------------------")

    for _, row in signals_df.iterrows():
        lines.append(
            f"- {row['indicator'].upper()}: {row['change_pct']:.2f}% | "
            f"{row['direction']} | {row['severity']}"
        )

    return "\n".join(lines)


def save_report(text):
    os.makedirs("data/signals", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    print("Detectando régimen de mercado...")

    signals_df = load_signals()
    report = build_report(signals_df)
    save_report(report)

    print("\nReporte de régimen generado:\n")
    print(report)
    print(f"\nArchivo guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()