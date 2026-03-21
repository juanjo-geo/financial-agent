import os
import pandas as pd

HISTORICAL_FILE = "data/historical/market_history.csv"
PROCESSED_DIR = "data/processed"
CLEAN_FILE = os.path.join(PROCESSED_DIR, "market_clean.csv")
SNAPSHOT_FILE = os.path.join(PROCESSED_DIR, "latest_snapshot.csv")


def load_historical_data():
    if not os.path.exists(HISTORICAL_FILE):
        raise FileNotFoundError(f"No existe el archivo histórico: {HISTORICAL_FILE}")
    return pd.read_csv(HISTORICAL_FILE)


def parse_timestamp_safe(value):
    try:
        ts = pd.to_datetime(str(value), errors="coerce", utc=True)
        if pd.isna(ts):
            return pd.NaT
        return ts.tz_convert(None).floor("D")
    except Exception:
        return pd.NaT


def clean_market_data(df):
    clean_df = df.copy()

    clean_df["indicator"] = clean_df["indicator"].astype(str).str.strip().str.lower()
    clean_df["timestamp"] = clean_df["timestamp"].apply(parse_timestamp_safe)

    numeric_cols = ["value", "open_value", "change_abs", "change_pct"]
    for col in numeric_cols:
        clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")

    clean_df["unit"] = clean_df["unit"].astype(str).str.strip()
    clean_df["source"] = clean_df["source"].astype(str).str.strip().str.lower()
    clean_df["status"] = clean_df["status"].astype(str).str.strip().str.lower()

    clean_df = clean_df.dropna(subset=["indicator", "timestamp"])
    clean_df = clean_df.sort_values(["indicator", "timestamp"])
    clean_df = clean_df.drop_duplicates(subset=["indicator", "timestamp"], keep="last")
    clean_df = clean_df.reset_index(drop=True)

    # Recalculate change_abs/change_pct for rows where they are NaN
    # but value and open_value are valid (e.g. NaN open from yfinance off-hours)
    mask = (
        clean_df["change_pct"].isna()
        & clean_df["value"].notna()
        & clean_df["open_value"].notna()
        & (clean_df["open_value"] != 0)
    )
    clean_df.loc[mask, "change_abs"] = (
        clean_df.loc[mask, "value"] - clean_df.loc[mask, "open_value"]
    )
    clean_df.loc[mask, "change_pct"] = (
        clean_df.loc[mask, "change_abs"] / clean_df.loc[mask, "open_value"] * 100
    )

    return clean_df


def build_latest_snapshot(clean_df):
    # Only consider rows with a valid value so a failed fetch
    # never overwrites a previously good entry in the snapshot.
    valid = clean_df[clean_df["value"].notna()]
    snapshot_df = (
        valid.sort_values("timestamp")
        .groupby("indicator", as_index=False)
        .tail(1)
        .sort_values("indicator")
        .reset_index(drop=True)
    )
    return snapshot_df


def save_processed_files(clean_df, snapshot_df):
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    clean_df.to_csv(CLEAN_FILE, index=False)
    snapshot_df.to_csv(SNAPSHOT_FILE, index=False)


def main():
    print("Procesando datos de mercado...")

    df = load_historical_data()
    clean_df = clean_market_data(df)
    snapshot_df = build_latest_snapshot(clean_df)
    save_processed_files(clean_df, snapshot_df)

    print("\nIndicadores en histórico limpio:")
    print(sorted(clean_df["indicator"].unique().tolist()))

    print("\nÚltimo snapshot por indicador:")
    print(snapshot_df[["indicator", "timestamp", "value", "change_pct", "unit", "source", "status"]])

    print(f"\nArchivo limpio guardado en: {CLEAN_FILE}")
    print(f"Snapshot guardado en: {SNAPSHOT_FILE}")


if __name__ == "__main__":
    main()