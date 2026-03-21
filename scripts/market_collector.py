from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
import yfinance as yf
import os

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
        latest_open = hist["Open"].iloc[-1]

        change_abs = latest_close - latest_open

        if latest_open != 0:
            change_pct = (change_abs / latest_open) * 100
        else:
            change_pct = None

        return {
            "indicator": indicator_name,
            "timestamp": datetime.now().isoformat(),
            "value": round(float(latest_close), 4),
            "open_value": round(float(latest_open), 4),
            "change_abs": round(float(change_abs), 4),
            "change_pct": round(float(change_pct), 4) if change_pct is not None else None,
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
    indicators = [
        {"symbol": "BZ=F",     "name": "brent",  "unit": "USD/bbl"},
        {"symbol": "BTC-USD",  "name": "btc",    "unit": "USD"},
        {"symbol": "DX-Y.NYB", "name": "dxy",    "unit": "index"},
        {"symbol": "COP=X",    "name": "usdcop", "unit": "COP per USD"},
        {"symbol": "GC=F",     "name": "gold",   "unit": "USD/oz"},
        {"symbol": "^GSPC",    "name": "sp500",  "unit": "USD"},
        {"symbol": "CL=F",     "name": "wti",    "unit": "USD/bbl"},
    ]

    records = []

    for item in indicators:
        record = fetch_ticker_data(
            symbol=item["symbol"],
            indicator_name=item["name"],
            unit=item["unit"]
        )
        records.append(record)

    inflation_proxy = {
        "indicator": "global_inflation_proxy",
        "timestamp": datetime.now().isoformat(),
        "value": 3.0,
        "open_value": 3.0,
        "change_abs": 0.0,
        "change_pct": 0.0,
        "unit": "%",
        "source": "manual_proxy",
        "status": "ok"
    }

    records.append(inflation_proxy)

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