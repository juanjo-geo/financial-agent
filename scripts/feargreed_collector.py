"""
feargreed_collector.py
----------------------
Descarga el Fear & Greed Index de Bitcoin desde la API pública de alternative.me.
No requiere API key. Guarda los datos en data/historical/feargreed_history.csv.

Historia disponible: desde 2018-02-01 hasta hoy.

Columnas de salida:
  - date          : fecha (YYYY-MM-DD)
  - fg_value      : valor del índice (0-100)
  - fg_class      : clasificación textual (Extreme Fear, Fear, Neutral, Greed, Extreme Greed)
  - fg_change     : cambio absoluto respecto al día anterior
  - fg_change_pct : cambio porcentual respecto al día anterior

Uso:
  python -m scripts.feargreed_collector
"""

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT    = Path(__file__).parent.parent
FG_FILE = ROOT / "data/historical/feargreed_history.csv"


def fetch_feargreed() -> pd.DataFrame | None:
    """Descarga todo el historial del Fear & Greed Index desde alternative.me."""
    url = "https://api.alternative.me/fng/?limit=0&format=json&date_format=world"
    print(f"  Descargando Fear & Greed Index (alternative.me)...", end=" ", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "financial-agent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode())

        entries = raw.get("data", [])
        if not entries:
            print("sin datos")
            return None

        rows = []
        for e in entries:
            # date_format=world devuelve DD-MM-YYYY
            try:
                date = datetime.strptime(e["timestamp"], "%d-%m-%Y").strftime("%Y-%m-%d")
            except Exception:
                continue
            rows.append({
                "date":     date,
                "fg_value": int(e["value"]),
                "fg_class": e["value_classification"],
            })

        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

        # Calcular cambios día a día
        df["fg_change"]     = df["fg_value"].diff()
        df["fg_change_pct"] = df["fg_value"].pct_change() * 100

        print(f"{len(df)} filas  ({df['date'].min()} → {df['date'].max()})")
        return df

    except Exception as e:
        print(f"ERROR: {e}")
        return None


def run_feargreed_collector() -> None:
    """Descarga y fusiona el Fear & Greed Index con el archivo histórico existente."""
    print("=" * 60)
    print("FEAR & GREED COLLECTOR")
    print(f"Inicio: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    df_new = fetch_feargreed()
    if df_new is None:
        print("\nNo se pudo descargar el Fear & Greed Index.")
        return

    # Fusionar con historia existente
    if FG_FILE.exists():
        df_old = pd.read_csv(FG_FILE)
        print(f"  Historia existente: {len(df_old)} filas")
        combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        print("  Creando feargreed_history.csv desde cero...")
        combined = df_new

    combined = combined.drop_duplicates(subset=["date"], keep="last")
    combined = combined.sort_values("date").reset_index(drop=True)

    # Recalcular cambios sobre el dataset combinado y ordenado
    combined["fg_change"]     = combined["fg_value"].diff()
    combined["fg_change_pct"] = combined["fg_value"].pct_change() * 100

    FG_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(FG_FILE, index=False)

    print("\n" + "=" * 60)
    print("FEAR & GREED COMPLETADO")
    print("=" * 60)
    print(f"Total filas: {len(combined)}")
    print(f"Rango: {combined['date'].min()} → {combined['date'].max()}")
    print("\nDistribución de clasificaciones:")
    print(combined["fg_class"].value_counts().to_string())
    print(f"\nFin: {datetime.now():%Y-%m-%d %H:%M:%S}")


def main():
    run_feargreed_collector()


if __name__ == "__main__":
    main()
