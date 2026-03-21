import pandas as pd
import os
from datetime import datetime

SIGNALS_FILE = "data/signals/latest_signals.csv"
OUTPUT_FILE = "data/signals/macro_report.txt"


def load_signals():
    if not os.path.exists(SIGNALS_FILE):
        raise FileNotFoundError("No existe latest_signals.csv")

    return pd.read_csv(SIGNALS_FILE)


def get_indicator(signals, name):
    rows = signals.loc[signals.indicator == name]
    if rows.empty:
        return None
    return rows.iloc[0]


def interpret_macro(signals):

    messages = []

    btc = get_indicator(signals, "btc")
    brent = get_indicator(signals, "brent")
    dxy = get_indicator(signals, "dxy")
    usdcop = get_indicator(signals, "usdcop")

    # dólar fuerte
    if dxy is not None and dxy.direction == "up" and dxy.severity in ["medium", "high"]:
        messages.append(
            "El dólar muestra fortaleza global (DXY en subida significativa)."
        )

    # petróleo
    if brent is not None and brent.direction == "up":
        messages.append(
            "El petróleo sube, lo que puede aumentar presiones inflacionarias globales."
        )

    if brent is not None and brent.direction == "down":
        messages.append(
            "El petróleo cae, reduciendo presiones inflacionarias energéticas."
        )

    # bitcoin
    if btc is not None and btc.direction == "up" and btc.severity != "none":
        messages.append(
            "Bitcoin muestra demanda especulativa positiva."
        )

    if btc is not None and btc.direction == "down":
        messages.append(
            "Bitcoin cae, indicando menor apetito por riesgo."
        )

    # moneda emergente
    if usdcop is not None and usdcop.direction == "up":
        messages.append(
            "El peso colombiano se debilita frente al dólar."
        )

    if usdcop is not None and usdcop.direction == "down":
        messages.append(
            "El peso colombiano muestra fortaleza relativa."
        )

    if len(messages) == 0:
        messages.append("No se detectan cambios macro relevantes.")

    return messages


def build_report(signals):

    report = []

    report.append("MACRO MARKET REPORT")
    report.append("-------------------------")
    report.append(f"Generado: {datetime.now()}")
    report.append("")

    for _, row in signals.iterrows():

        line = f"{row.indicator.upper()} | {row.change_pct:.2f}% | {row.direction} | {row.severity}"
        report.append(line)

    report.append("")
    report.append("INTERPRETACIÓN MACRO")
    report.append("-------------------------")

    interpretations = interpret_macro(signals)

    for msg in interpretations:
        report.append(f"- {msg}")

    return "\n".join(report)


def save_report(text):

    os.makedirs("data/signals", exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(text)


def main():

    signals = load_signals()

    report = build_report(signals)

    save_report(report)

    print("\nMacro report generado:\n")
    print(report)


if __name__ == "__main__":
    main()