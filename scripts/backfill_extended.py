"""
backfill_extended.py
--------------------
Descarga hasta 2 años de historia para todos los indicadores activos
usando yfinance y la fusiona con market_history.csv existente.

Ejecutar UNA SOLA VEZ desde la raíz del proyecto para enriquecer el
dataset del modelo ML antes de que el pipeline diario acumule suficientes datos.

Uso:
  python -m scripts.backfill_extended              # 2 años (por defecto)
  python -m scripts.backfill_extended --period 1y  # 1 año
  python -m scripts.backfill_extended --period max # todo lo disponible

Indicadores descargados: todos los que tengan symbol en indicators_catalog.py
  btc, brent, gold, silver, dxy, sp500, usdcop, eurusd, nasdaq, wti, ...
  (global_inflation_proxy se omite — no tiene ticker yfinance)
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

# Agregar raíz al path para imports relativos
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.indicators_catalog import CATALOG

HISTORY_FILE = ROOT / "data/historical/market_history.csv"
DEFAULT_PERIOD = "2y"


# ── Descarga ──────────────────────────────────────────────────────────────────

def fetch_indicator(key: str, symbol: str, unit: str, period: str) -> pd.DataFrame | None:
    """Descarga historial diario para un símbolo vía yfinance."""
    try:
        print(f"  [{key}] Descargando {period} desde {symbol}...", end=" ", flush=True)
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=period, interval="1d")

        if hist.empty:
            print("sin datos")
            return None

        hist = hist.copy()
        hist["timestamp"]  = (
            pd.to_datetime(hist.index, utc=True)
            .tz_convert(None)
            .strftime("%Y-%m-%d")
        )
        hist["indicator"]  = key
        hist["value"]      = pd.to_numeric(hist["Close"],  errors="coerce")
        hist["open_value"] = pd.to_numeric(hist["Open"],   errors="coerce")
        hist["change_abs"] = hist["value"] - hist["open_value"]
        hist["change_pct"] = (
            hist["change_abs"]
            / hist["open_value"].replace(0, float("nan"))
            * 100
        )
        hist["unit"]   = unit
        hist["source"] = "yfinance"
        hist["status"] = "ok"

        result = hist[[
            "indicator", "timestamp", "value", "open_value",
            "change_abs", "change_pct", "unit", "source", "status",
        ]].dropna(subset=["timestamp", "value"]).reset_index(drop=True)

        print(f"{len(result)} filas  ({result['timestamp'].min()} → {result['timestamp'].max()})")

        # Para BTC: guardar también el volumen como indicador separado (btc_volume)
        if key == "btc" and "Volume" in hist.columns:
            vol = hist.copy()
            vol["indicator"]  = "btc_volume"
            vol["value"]      = pd.to_numeric(hist["Volume"], errors="coerce")
            vol["open_value"] = vol["value"].shift(1)
            vol["change_abs"] = vol["value"] - vol["open_value"]
            vol["change_pct"] = (
                vol["change_abs"]
                / vol["open_value"].replace(0, float("nan"))
                * 100
            )
            vol["unit"]   = "BTC"
            vol["source"] = "yfinance"
            vol["status"] = "ok"
            vol_result = vol[[
                "indicator", "timestamp", "value", "open_value",
                "change_abs", "change_pct", "unit", "source", "status",
            ]].dropna(subset=["timestamp", "value"]).reset_index(drop=True)
            # Retornar tupla (precio, volumen) cuando es BTC
            return result, vol_result

        return result, None

    except Exception as e:
        print(f"ERROR: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Leer período desde argumento
    period = DEFAULT_PERIOD
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--period" and i + 1 < len(sys.argv) - 1:
            period = sys.argv[i + 2]
        elif arg.startswith("--period="):
            period = arg.split("=", 1)[1]

    print("=" * 60)
    print(f"BACKFILL EXTENDIDO — período: {period}")
    print(f"Inicio: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    # Cargar historia existente
    if HISTORY_FILE.exists():
        hist_df = pd.read_csv(HISTORY_FILE)
        print(f"\nHistoria actual: {len(hist_df)} filas")
        print(hist_df.groupby("indicator").size().rename("filas_actuales").to_string())
    else:
        hist_df = pd.DataFrame()
        print("\nNo existe market_history.csv — se creará desde cero.")

    # Descargar todos los indicadores con symbol válido
    print(f"\nDescargando {period} para todos los indicadores...\n")
    new_frames = []
    skipped    = []

    for key, info in sorted(CATALOG.items()):
        symbol = info.get("symbol")
        if symbol is None:
            skipped.append(key)
            continue
        df, vol_df = fetch_indicator(key, symbol, info["unit"], period)
        if df is not None:
            new_frames.append(df)
        if vol_df is not None:
            new_frames.append(vol_df)   # btc_volume como indicador separado

    if skipped:
        print(f"\n  Omitidos (sin ticker): {skipped}")

    if not new_frames:
        print("\n¡No se descargó ningún dato! Verifica tu conexión a internet.")
        return

    # Fusionar con historia existente
    combined = pd.concat([hist_df] + new_frames, ignore_index=True)
    combined = combined.dropna(subset=["indicator", "timestamp"])
    combined = combined.sort_values(["indicator", "timestamp"])
    combined = combined.drop_duplicates(subset=["indicator", "timestamp"], keep="last")
    combined = combined.reset_index(drop=True)

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(HISTORY_FILE, index=False)

    # Resumen final
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETADO")
    print("=" * 60)
    print(f"\nTotal filas en market_history.csv: {len(combined)}")
    print("\nFilas por indicador:")
    summary = combined.groupby("indicator").agg(
        filas=("value", "count"),
        desde=("timestamp", "min"),
        hasta=("timestamp", "max"),
    )
    print(summary.to_string())

    btc_rows = len(combined[combined["indicator"] == "btc"])
    print(f"\n→ BTC: {btc_rows} días de datos disponibles para el modelo ML")
    print(f"  (antes: {len(hist_df[hist_df['indicator']=='btc']) if not hist_df.empty else 0} días)")
    print(f"\nAhora re-entrena el modelo ML con:")
    print(f"  .venv\\Scripts\\python.exe -m intelligence.ml_predictor")
    print(f"\nFin: {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
