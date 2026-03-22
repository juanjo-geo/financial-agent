"""
Rellena signals_history.csv con datos historicos simulados de los ultimos 30 dias.
Usa los valores reales de change_pct de market_history.csv para calcular senales
deterministicas mediante las mismas reglas de signals_engine.

Solo corre si signals_history.csv tiene menos de MIN_BACKFILL_ROWS filas.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from intelligence.signals_engine import (
    HISTORY_COLS,
    SIGNALS_HISTORY_FILE,
    append_signals_history,
    compute_conviccion,
    compute_presion_cop,
    compute_presion_inflacionaria,
    compute_riesgo_macro,
    compute_sesgo_mercado,
)

ROOT         = Path(__file__).parent.parent
HISTORY_FILE = ROOT / "data/historical/market_history.csv"

MIN_BACKFILL_ROWS = 7
BACKFILL_DAYS     = 30


def _build_changes(date_df: pd.DataFrame) -> dict[str, float]:
    """Construye {indicator: change_pct} para un subconjunto de filas del mismo dia."""
    out: dict[str, float] = {}
    for _, row in date_df.iterrows():
        pct = pd.to_numeric(row.get("change_pct"), errors="coerce")
        if pd.notna(pct):
            out[str(row["indicator"]).lower()] = float(pct)
    return out


def _top2_driver_strings(changes: dict[str, float]) -> tuple[str, str]:
    """Retorna los 2 indicadores de mayor movimiento como strings 'INDICATOR +X.XX%'."""
    sorted_chg = sorted(changes.items(), key=lambda x: abs(x[1]), reverse=True)
    def fmt(key: str, val: float) -> str:
        return f"{key.upper()} {val:+.2f}%"
    d1 = fmt(*sorted_chg[0]) if len(sorted_chg) > 0 else ""
    d2 = fmt(*sorted_chg[1]) if len(sorted_chg) > 1 else ""
    return d1, d2


def main():
    # Verificar si ya hay suficientes filas
    if SIGNALS_HISTORY_FILE.exists():
        existing = pd.read_csv(SIGNALS_HISTORY_FILE)
        if len(existing) >= MIN_BACKFILL_ROWS:
            print(
                f"signals_history.csv ya tiene {len(existing)} filas "
                f"(>= {MIN_BACKFILL_ROWS}). Backfill omitido."
            )
            return
        existing_dates = set(existing["fecha"].astype(str))
    else:
        existing_dates = set()

    if not HISTORY_FILE.exists():
        print(f"No existe {HISTORY_FILE}. Backfill omitido.")
        return

    df = pd.read_csv(HISTORY_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    df = df.dropna(subset=["timestamp"])
    df["date_str"] = df["timestamp"].dt.strftime("%Y-%m-%d")

    # Ultimas BACKFILL_DAYS fechas con >= 3 indicadores
    date_counts = df.groupby("date_str")["indicator"].nunique()
    valid_dates = (
        date_counts[date_counts >= 3]
        .sort_index()
        .tail(BACKFILL_DAYS)
        .index.tolist()
    )

    if not valid_dates:
        print("No se encontraron fechas validas en market_history.csv. Backfill omitido.")
        return

    print(f"Backfill de senales historicas: {len(valid_dates)} fechas...")
    backfilled = 0

    for fecha in valid_dates:
        if fecha in existing_dates:
            continue

        day_df  = df[df["date_str"] == fecha]
        changes = _build_changes(day_df)
        nw: dict[str, int] = {}  # sin pesos de noticias para historico

        riesgo,    riesgo_score,    _ = compute_riesgo_macro(changes, nw)
        sesgo,     _                  = compute_sesgo_mercado(changes, nw)
        inflacion, inflacion_score, _ = compute_presion_inflacionaria(changes, nw)
        cop,       cop_score,       _ = compute_presion_cop(changes, nw)

        scores = {
            "riesgo_score":    riesgo_score,
            "inflacion_score": inflacion_score,
            "cop_score":       cop_score,
        }
        conviccion, _ = compute_conviccion(riesgo, sesgo, inflacion, cop, changes, nw, scores)

        senales = {
            "riesgo_macro":           riesgo,
            "sesgo_mercado":          sesgo,
            "presion_inflacionaria":  inflacion,
            "presion_cop":            cop,
            "conviccion":             conviccion,
        }
        d1, d2 = _top2_driver_strings(changes)

        # append_signals_history usa datetime.now() para la fecha;
        # inyectamos directamente para fechas historicas
        import pandas as _pd
        new_row = {
            "fecha":                 fecha,
            "riesgo_macro":          riesgo,
            "sesgo_mercado":         sesgo,
            "presion_inflacionaria": inflacion,
            "presion_cop":           cop,
            "conviccion":            conviccion,
            "driver_principal":      d1,
            "driver_secundario":     d2,
        }
        SIGNALS_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if SIGNALS_HISTORY_FILE.exists():
            hist_df = _pd.read_csv(SIGNALS_HISTORY_FILE)
            hist_df = hist_df[hist_df["fecha"] != fecha]
            hist_df = _pd.concat([hist_df, _pd.DataFrame([new_row])], ignore_index=True)
        else:
            hist_df = _pd.DataFrame([new_row], columns=HISTORY_COLS)
        hist_df.to_csv(SIGNALS_HISTORY_FILE, index=False)
        existing_dates.add(fecha)
        backfilled += 1

    total = len(pd.read_csv(SIGNALS_HISTORY_FILE)) if SIGNALS_HISTORY_FILE.exists() else 0
    print(f"  Backfill completado: {backfilled} fechas nuevas. Total: {total} filas.")
    print(f"  Guardado en: {SIGNALS_HISTORY_FILE}")


if __name__ == "__main__":
    main()
