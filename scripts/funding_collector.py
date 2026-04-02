"""
funding_collector.py
--------------------
Descarga el historial de Funding Rates de BTC desde la API pública de Binance.
No requiere API key. Guarda los datos en data/historical/funding_history.csv.

¿Qué es el funding rate?
  En futuros perpetuos, cada 8h los longs pagan a shorts (o viceversa).
  - Funding rate ALTO (>0.05%): mercado muy apalancado long → señal bajista (squeeze inminente)
  - Funding rate BAJO/NEGATIVO (<0%): mercado corto → señal alcista (short squeeze)
  - Neutral (~0.01%): sin sesgo direccional

Historia disponible: desde ~2019-09 (lanzamiento de BTCUSDT perpetuo en Binance).
Frecuencia: cada 8h → 3 pagos/día → se agrega a diario (promedio y extremos).

Columnas de salida (por día):
  - date             : fecha (YYYY-MM-DD)
  - fr_mean          : funding rate promedio del día (3 ventanas de 8h)
  - fr_max           : funding rate máximo del día
  - fr_min           : funding rate mínimo del día
  - fr_annualized    : fr_mean anualizado (× 3 × 365, para intuición)
  - fr_7d_mean       : media móvil 7 días del fr_mean
  - fr_extreme_long  : 1 si fr_mean > 0.05% (mercado muy apalancado long)
  - fr_extreme_short : 1 si fr_mean < -0.01% (mercado muy apalancado short)

Uso:
  python -m scripts.funding_collector
"""

import json
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT         = Path(__file__).parent.parent
FUNDING_FILE = ROOT / "data/historical/funding_history.csv"

BINANCE_URL  = "https://fapi.binance.com/fapi/v1/fundingRate"
SYMBOL       = "BTCUSDT"
LIMIT        = 1000   # máximo por request de Binance


def fetch_funding_page(start_ms: int | None = None, end_ms: int | None = None) -> list[dict]:
    """Descarga una página de funding rates desde Binance Futures."""
    params: dict = {"symbol": SYMBOL, "limit": LIMIT}
    if start_ms:
        params["startTime"] = start_ms
    if end_ms:
        params["endTime"] = end_ms

    url = BINANCE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "financial-agent/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_all_funding() -> pd.DataFrame:
    """Descarga todo el historial de funding rates paginando por el límite de Binance.

    Binance devuelve registros en orden ASCENDENTE (más antiguo primero).
    Paginamos hacia adelante usando startTime del registro más reciente + 1ms.
    """
    print("  Descargando funding rates BTC (Binance)...", end=" ", flush=True)
    all_rows = []

    # Inicio: lanzamiento de BTCUSDT perpetuo en Binance (sept 2019)
    start_ms = int(datetime(2019, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    pages    = 0

    while True:
        try:
            page = fetch_funding_page(start_ms=start_ms)
        except Exception as e:
            print(f"\n  ERROR en página {pages}: {e}")
            break

        if not page:
            break

        all_rows.extend(page)
        pages += 1

        # El más reciente de esta página es el nuevo punto de inicio
        newest_ts = max(int(r["fundingTime"]) for r in page)
        start_ms  = newest_ts + 1   # un ms después para no duplicar

        # Si la página tiene menos de LIMIT registros, llegamos al final
        if len(page) < LIMIT:
            break

        time.sleep(0.3)   # respetar rate limits

    if not all_rows:
        print("sin datos")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce") * 100  # a porcentaje
    df["datetime"]    = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["date"]        = df["datetime"].dt.normalize().dt.tz_localize(None)

    # Agregar a nivel diario
    daily = df.groupby("date")["fundingRate"].agg(
        fr_mean="mean",
        fr_max="max",
        fr_min="min",
    ).reset_index()

    # Features derivadas
    daily["fr_annualized"]    = daily["fr_mean"] * 3 * 365
    daily["fr_7d_mean"]       = daily["fr_mean"].rolling(7, min_periods=1).mean()
    daily["fr_extreme_long"]  = (daily["fr_mean"] > 0.05).astype(float)
    daily["fr_extreme_short"] = (daily["fr_mean"] < -0.01).astype(float)
    daily["fr_change"]        = daily["fr_mean"].diff()

    daily = daily.sort_values("date").reset_index(drop=True)
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")

    print(f"{len(daily)} días  ({daily['date'].min()} → {daily['date'].max()})")
    return daily


def run_funding_collector() -> None:
    """Descarga y fusiona el historial de funding rates con el archivo existente."""
    print("=" * 60)
    print("FUNDING RATE COLLECTOR (Binance BTCUSDT Perpetual)")
    print(f"Inicio: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    df_new = fetch_all_funding()
    if df_new.empty:
        print("\nNo se pudieron descargar funding rates.")
        return

    if FUNDING_FILE.exists():
        df_old = pd.read_csv(FUNDING_FILE)
        print(f"  Historia existente: {len(df_old)} filas")
        combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        print("  Creando funding_history.csv desde cero...")
        combined = df_new

    combined = combined.drop_duplicates(subset=["date"], keep="last")
    combined = combined.sort_values("date").reset_index(drop=True)

    # Recalcular rolling y flags sobre dataset completo
    combined["fr_7d_mean"]       = combined["fr_mean"].rolling(7, min_periods=1).mean()
    combined["fr_extreme_long"]  = (combined["fr_mean"] > 0.05).astype(float)
    combined["fr_extreme_short"] = (combined["fr_mean"] < -0.01).astype(float)
    combined["fr_change"]        = combined["fr_mean"].diff()

    FUNDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(FUNDING_FILE, index=False)

    print("\n" + "=" * 60)
    print("FUNDING RATE COMPLETADO")
    print("=" * 60)
    print(f"Total días: {len(combined)}")
    print(f"Rango: {combined['date'].min()} → {combined['date'].max()}")
    print(f"\nFunding rate promedio histórico : {combined['fr_mean'].mean():.4f}%")
    print(f"Días con extreme long (>0.05%)  : {int(combined['fr_extreme_long'].sum())}")
    print(f"Días con extreme short (<-0.01%): {int(combined['fr_extreme_short'].sum())}")
    print(f"\nFin: {datetime.now():%Y-%m-%d %H:%M:%S}")


def main():
    run_funding_collector()


if __name__ == "__main__":
    main()
