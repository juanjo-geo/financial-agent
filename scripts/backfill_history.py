import os
import pandas as pd
import yfinance as yf

OUTPUT_FILE = "data/historical/market_history.csv"


def fetch_history(symbol, indicator_name, unit, source="yfinance", period="90d", interval="1d"):
    try:
        print(f"Descargando {indicator_name} ({symbol})...")

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            print(f"  -> Sin datos para {indicator_name}")
            return None

        hist = hist.copy()

        # Convertir índice temporal a serie de fechas segura
        hist["timestamp"] = pd.to_datetime(hist.index, errors="coerce", utc=True)
        hist["timestamp"] = hist["timestamp"].dt.tz_convert(None)
        hist["timestamp"] = hist["timestamp"].dt.strftime("%Y-%m-%d")

        hist["indicator"] = indicator_name
        hist["value"] = pd.to_numeric(hist["Close"], errors="coerce")
        hist["open_value"] = pd.to_numeric(hist["Open"], errors="coerce")
        hist["change_abs"] = hist["value"] - hist["open_value"]
        hist["change_pct"] = (hist["change_abs"] / hist["open_value"]) * 100

        hist["unit"] = unit
        hist["source"] = source
        hist["status"] = "ok"

        result = hist[
            [
                "indicator",
                "timestamp",
                "value",
                "open_value",
                "change_abs",
                "change_pct",
                "unit",
                "source",
                "status",
            ]
        ].reset_index(drop=True)

        print(f"  -> {len(result)} filas para {indicator_name}")
        return result

    except Exception as e:
        print(f"  -> Error en {indicator_name}: {e}")
        return None


def main():
    os.makedirs("data/historical", exist_ok=True)

    indicators = [
        {"symbol": "BZ=F",     "name": "brent",  "unit": "USD/bbl"},
        {"symbol": "BTC-USD",  "name": "btc",    "unit": "USD"},
        {"symbol": "DX-Y.NYB", "name": "dxy",    "unit": "index"},
        {"symbol": "COP=X",    "name": "usdcop", "unit": "COP per USD"},
        {"symbol": "GC=F",     "name": "gold",   "unit": "USD/oz"},
    ]

    all_data = []

    for item in indicators:
        df = fetch_history(
            symbol=item["symbol"],
            indicator_name=item["name"],
            unit=item["unit"],
        )

        if df is not None and not df.empty:
            all_data.append(df)

    if not all_data:
        print("No se pudo descargar histórico")
        return

    final_df = pd.concat(all_data, ignore_index=True)

    inflation_dates = sorted(final_df["timestamp"].dropna().unique().tolist())

    inflation_df = pd.DataFrame({
        "indicator": ["global_inflation_proxy"] * len(inflation_dates),
        "timestamp": inflation_dates,
        "value": [3.0] * len(inflation_dates),
        "open_value": [3.0] * len(inflation_dates),
        "change_abs": [0.0] * len(inflation_dates),
        "change_pct": [0.0] * len(inflation_dates),
        "unit": ["%"] * len(inflation_dates),
        "source": ["manual_proxy"] * len(inflation_dates),
        "status": ["ok"] * len(inflation_dates),
    })

    final_df = pd.concat([final_df, inflation_df], ignore_index=True)

    final_df = final_df.dropna(subset=["timestamp"])
    final_df = final_df.drop_duplicates(subset=["indicator", "timestamp"], keep="last")
    final_df = final_df.sort_values(["indicator", "timestamp"]).reset_index(drop=True)

    final_df.to_csv(OUTPUT_FILE, index=False)

    print("\nBackfill histórico completado.")
    print(f"Archivo actualizado: {OUTPUT_FILE}")

    print("\nFilas por indicador:")
    print(final_df.groupby("indicator").size())


if __name__ == "__main__":
    main()