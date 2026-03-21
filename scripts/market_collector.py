from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
import yfinance as yf
import os
from scripts.load_config import load_config
from scripts.indicators_catalog import CATALOG

def fetch_ticker_data(symbol, indicator_name, unit, source="yfinance"):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d", interval="1d")

        if hist.empty:
            return {
                "indicator": indicator_name,
                "timestamp": datetime.now().isoformat(),
                "value": None,
                "open_value": None,
                "change_abs": None,
                "change_pct": None,
                "unit": unit,
                "source": source,
                "status": "no_data"
            }

        latest_close = hist["Close"].iloc[-1]
        latest_open  = hist["Open"].iloc[-1]

        # Guard against NaN open (futures off-hours) — fall back to previous close
        if pd.isna(latest_open) or latest_open == 0:
            prev_rows = hist[hist["Open"].notna() & (hist["Open"] != 0)]
            latest_open = prev_rows["Open"].iloc[-1] if not prev_rows.empty else latest_close

        change_abs = latest_close - latest_open
        change_pct = (change_abs / latest_open) * 100 if latest_open != 0 else None

        return {
            "indicator": indicator_name,
            "timestamp": datetime.now().isoformat(),
            "value":      round(float(latest_close), 4),
            "open_value": round(float(latest_open),  4),
            "change_abs": round(float(change_abs),   4),
            "change_pct": round(float(change_pct),   4) if change_pct is not None else None,
            "unit": unit,
            "source": source,
            "status": "ok"
        }

    except Exception as e:
        return {
            "indicator": indicator_name,
            "timestamp": datetime.now().isoformat(),
            "value": None,
            "open_value": None,
            "change_abs": None,
            "change_pct": None,
            "unit": unit,
            "source": source,
            "status": f"error: {str(e)}"
        }

def get_market_data():
    cfg = load_config()
    active = cfg.get("active_indicators", ["brent", "btc", "dxy", "usdcop", "gold"])

    records = []
    for key in active:
        info = CATALOG.get(key)
        if info is None:
            print(f"  [WARN] Indicador desconocido en config: {key}")
            continue

        # Proxy manual (no yfinance)
        if info["symbol"] is None:
            records.append({
                "indicator": key,
                "timestamp": datetime.now().isoformat(),
                "value": 3.0, "open_value": 3.0,
                "change_abs": 0.0, "change_pct": 0.0,
                "unit": info["unit"], "source": "manual_proxy", "status": "ok",
            })
        else:
            records.append(fetch_ticker_data(
                symbol=info["symbol"],
                indicator_name=key,
                unit=info["unit"],
            ))

    return pd.DataFrame(records)

def save_market_data(df):
    os.makedirs("data/historical", exist_ok=True)
    file_path = "data/historical/market_history.csv"

    if os.path.exists(file_path):
        existing_df = pd.read_csv(file_path)
        updated_df = pd.concat([existing_df, df], ignore_index=True)
    else:
        updated_df = df.copy()

    updated_df.to_csv(file_path, index=False)

def main():
    load_dotenv()

    print("Recolectando datos de mercado...")
    df = get_market_data()
    save_market_data(df)

    print(df)
    print("\nDatos guardados en data/historical/market_history.csv")

if __name__ == "__main__":
    main()