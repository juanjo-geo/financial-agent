"""
onchain_collector.py
--------------------
Descarga métricas on-chain de Bitcoin desde la API pública de blockchain.com.
No requiere API key. Guarda los datos en data/historical/onchain_history.csv.

Métricas descargadas:
  - onchain_active_addr   : Direcciones únicas activas por día
  - onchain_tx_count      : Transacciones confirmadas por día
  - onchain_hashrate      : Hash rate de la red (EH/s)
  - onchain_mempool_size  : Tamaño del mempool (MB)
  - onchain_tx_volume_usd : Volumen estimado transaccionado en USD

Uso:
  python -m scripts.onchain_collector              # descarga últimos 2 años
  python -m scripts.onchain_collector --period 1y  # descarga 1 año
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT         = Path(__file__).parent.parent
ONCHAIN_FILE = ROOT / "data/historical/onchain_history.csv"

# Endpoints públicos de blockchain.com (sin API key)
CHARTS = {
    "onchain_active_addr": {
        "url":   "https://api.blockchain.info/charts/n-unique-addresses",
        "unit":  "addresses",
        "label": "Direcciones activas BTC",
    },
    "onchain_tx_count": {
        "url":   "https://api.blockchain.info/charts/n-transactions",
        "unit":  "transactions",
        "label": "Transacciones BTC/día",
    },
    "onchain_hashrate": {
        "url":   "https://api.blockchain.info/charts/hash-rate",
        "unit":  "EH/s",
        "label": "Hash rate BTC",
    },
    "onchain_mempool_size": {
        "url":   "https://api.blockchain.info/charts/mempool-size",
        "unit":  "MB",
        "label": "Mempool size BTC",
    },
    "onchain_tx_volume_usd": {
        "url":   "https://api.blockchain.info/charts/estimated-transaction-volume-usd",
        "unit":  "USD",
        "label": "Volumen transacciones BTC (USD)",
    },
}


def fetch_chart(key: str, info: dict, timespan: str = "2years") -> pd.DataFrame | None:
    """Descarga una métrica on-chain y retorna DataFrame normalizado."""
    url = f"{info['url']}?timespan={timespan}&format=json&cors=true"
    try:
        print(f"  [{key}] Descargando {timespan}...", end=" ", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "financial-agent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        values = data.get("values", [])
        if not values:
            print("sin datos")
            return None

        df = pd.DataFrame(values, columns=["x", "y"])
        df["timestamp"] = pd.to_datetime(df["x"], unit="s").dt.strftime("%Y-%m-%d")
        df["value"]     = pd.to_numeric(df["y"], errors="coerce")

        # Calcular change_pct día a día
        df = df.sort_values("timestamp").reset_index(drop=True)
        df["open_value"] = df["value"].shift(1)
        df["change_abs"] = df["value"] - df["open_value"]
        df["change_pct"] = (
            df["change_abs"] / df["open_value"].replace(0, float("nan")) * 100
        )

        df["indicator"] = key
        df["unit"]      = info["unit"]
        df["source"]    = "blockchain.com"
        df["status"]    = "ok"

        result = df[[
            "indicator", "timestamp", "value", "open_value",
            "change_abs", "change_pct", "unit", "source", "status",
        ]].dropna(subset=["timestamp", "value"]).reset_index(drop=True)

        print(f"{len(result)} filas  ({result['timestamp'].min()} → {result['timestamp'].max()})")
        return result

    except Exception as e:
        print(f"ERROR: {e}")
        return None


def run_onchain_collector(timespan: str = "2years") -> None:
    """Descarga todas las métricas on-chain y las fusiona con el archivo existente."""
    print("=" * 60)
    print(f"ON-CHAIN COLLECTOR — timespan: {timespan}")
    print(f"Inicio: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    # Cargar historia existente
    if ONCHAIN_FILE.exists():
        existing = pd.read_csv(ONCHAIN_FILE)
        print(f"\nHistoria on-chain actual: {len(existing)} filas")
    else:
        existing = pd.DataFrame()
        print("\nCreando onchain_history.csv desde cero...")

    new_frames = []
    for key, info in CHARTS.items():
        df = fetch_chart(key, info, timespan)
        if df is not None:
            new_frames.append(df)
        time.sleep(0.5)   # respetar rate limits de la API

    if not new_frames:
        print("\n¡No se descargó ningún dato! Verifica tu conexión.")
        return

    # Fusionar con historia existente
    combined = pd.concat([existing] + new_frames, ignore_index=True)
    combined = combined.dropna(subset=["indicator", "timestamp"])
    combined = combined.sort_values(["indicator", "timestamp"])
    combined = combined.drop_duplicates(subset=["indicator", "timestamp"], keep="last")
    combined = combined.reset_index(drop=True)

    ONCHAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(ONCHAIN_FILE, index=False)

    print("\n" + "=" * 60)
    print("ON-CHAIN COMPLETADO")
    print("=" * 60)
    print(f"\nTotal filas en onchain_history.csv: {len(combined)}")
    print("\nFilas por métrica:")
    summary = combined.groupby("indicator").agg(
        filas=("value", "count"),
        desde=("timestamp", "min"),
        hasta=("timestamp", "max"),
    )
    print(summary.to_string())
    print(f"\nFin: {datetime.now():%Y-%m-%d %H:%M:%S}")


def main():
    timespan = "2years"
    for arg in sys.argv[1:]:
        if arg.startswith("--period="):
            timespan = arg.split("=", 1)[1]
        elif arg == "--period" and len(sys.argv) > sys.argv.index(arg) + 1:
            timespan = sys.argv[sys.argv.index(arg) + 1]

    run_onchain_collector(timespan)


if __name__ == "__main__":
    main()
