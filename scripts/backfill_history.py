"""
Descarga datos históricos para indicadores activos en market_history.csv.

Modo normal   : rellena indicadores con < MIN_HISTORY_DAYS entradas (~30 dias).
Modo completo : --full  → descarga 6 meses para TODOS los activos (fuerza 90+ dias).

Se ejecuta automáticamente como primer paso del pipeline (run_daily.py).
"""

import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime
from pathlib import Path

from scripts.load_config import load_config
from scripts.indicators_catalog import CATALOG

HISTORY_FILE     = "data/historical/market_history.csv"
MIN_HISTORY_DAYS = 30   # si tiene menos filas que esto, se hace backfill
FULL_PERIOD      = "6mo"  # ~130 dias calendario = ~90 dias de mercado


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_history() -> pd.DataFrame:
    if os.path.exists(HISTORY_FILE):
        return pd.read_csv(HISTORY_FILE)
    return pd.DataFrame()


def _days_in_history(indicator: str, hist_df: pd.DataFrame) -> int:
    """Cuenta días distintos con datos válidos para el indicador."""
    if hist_df.empty:
        return 0
    rows = hist_df[hist_df["indicator"] == indicator]
    if rows.empty:
        return 0
    # Normalize timestamps to date-only to count unique calendar days
    ts = pd.to_datetime(rows["timestamp"], errors="coerce", format="mixed")
    return ts.dt.normalize().dropna().nunique()


def _fetch_history(key: str, symbol: str, unit: str,
                   period: str = "3mo") -> pd.DataFrame | None:
    """Descarga historial diario para un símbolo yfinance."""
    try:
        print(f"  Descargando {period} para {key} ({symbol})...")
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=period, interval="1d")

        if hist.empty:
            print(f"  [WARN] Sin datos para {key}")
            return None

        hist = hist.copy()
        hist["timestamp"]  = pd.to_datetime(hist.index, utc=True).tz_convert(None).strftime("%Y-%m-%d")
        hist["indicator"]  = key
        hist["value"]      = pd.to_numeric(hist["Close"], errors="coerce")
        hist["open_value"] = pd.to_numeric(hist["Open"],  errors="coerce")
        hist["change_abs"] = hist["value"] - hist["open_value"]
        hist["change_pct"] = hist["change_abs"] / hist["open_value"].replace(0, float("nan")) * 100
        hist["unit"]       = unit
        hist["source"]     = "yfinance"
        hist["status"]     = "ok"

        result = hist[["indicator","timestamp","value","open_value",
                        "change_abs","change_pct","unit","source","status"]
                      ].dropna(subset=["timestamp","value"]).reset_index(drop=True)

        print(f"  -> {len(result)} filas para {key}")
        return result

    except Exception as e:
        print(f"  [ERROR] {key}: {e}")
        return None


# Keep old name for backward compatibility
def _fetch_90d(key: str, symbol: str, unit: str) -> pd.DataFrame | None:
    return _fetch_history(key, symbol, unit, period="3mo")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_backfill(force: bool = False) -> None:
    """
    Detecta indicadores activos con histórico insuficiente y los rellena.
    force=True descarga para TODOS los activos independientemente del conteo.
    """
    cfg    = load_config()
    active = cfg.get("active_indicators", [])

    hist_df = _load_history()

    indicators_to_fill = []
    for key in active:
        info = CATALOG.get(key)
        if info is None or info["symbol"] is None:
            continue
        days = _days_in_history(key, hist_df)
        if force or days < MIN_HISTORY_DAYS:
            indicators_to_fill.append((key, info, days))

    if not indicators_to_fill:
        print("Backfill: todos los indicadores activos tienen histórico suficiente.")
        return

    print(f"Backfill necesario para: {[k for k,_,_ in indicators_to_fill]}")

    period = FULL_PERIOD if force else "3mo"
    new_frames = []
    for key, info, days in indicators_to_fill:
        print(f"  {key}: {days} dias actuales -> descargando {period}...")
        df = _fetch_history(key, info["symbol"], info["unit"], period=period)
        if df is not None:
            new_frames.append(df)

    if not new_frames:
        print("Backfill: no se obtuvo ningún dato nuevo.")
        return

    # Merge con histórico existente y deduplicar por (indicator, timestamp)
    combined = pd.concat([hist_df] + new_frames, ignore_index=True)
    combined = combined.dropna(subset=["indicator","timestamp"])
    combined = combined.sort_values(["indicator","timestamp"])
    combined = combined.drop_duplicates(subset=["indicator","timestamp"], keep="last")
    combined = combined.reset_index(drop=True)

    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    combined.to_csv(HISTORY_FILE, index=False)
    print(f"Backfill completo. Filas en market_history.csv: {len(combined)}")
    print("Filas por indicador:")
    print(combined.groupby("indicator").size().to_string())


def main():
    full_mode = "--full" in sys.argv
    if full_mode:
        print("Modo completo: descargando 6 meses para todos los indicadores activos...")
        run_backfill(force=True)
    else:
        run_backfill()


if __name__ == "__main__":
    main()
