"""
Backfill walk-forward de evaluaciones historicas (90 dias de mercado).

Para cada par de dias consecutivos (D-1, D) disponibles en market_history.csv:
  1. Simula la prediccion que el sistema habria generado en D-1
     usando solo datos disponibles hasta ese dia (sin look-ahead).
  2. Evalua la prediccion contra el cambio real registrado en D.
  3. Registra el resultado en data/signals/evaluation_log.csv.

Objetivo: ~90 dias de mercado x 5 indicadores = ~450 evaluaciones.
Salida  : data/signals/evaluation_log.csv (columnas estandar del evaluador).

Uso:
  python -m scripts.backfill_predictions           # agrega solo filas nuevas
  python -m scripts.backfill_predictions --reset   # borra el log y regenera desde cero
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT                 = Path(__file__).parent.parent
HISTORY_FILE         = ROOT / "data/historical/market_history.csv"
SIGNALS_HISTORY_FILE = ROOT / "data/signals/signals_history.csv"
EVAL_LOG_FILE        = ROOT / "data/signals/evaluation_log.csv"
CONFIG_FILE          = ROOT / "config.json"

BACKFILL_DAYS    = 92          # pares de fechas a procesar
MIN_INDICATORS   = 2           # dias con menos activos que esto se saltan
LATERAL_THRESHOLD = 1.0        # abs(chg) < 1% = correcto para "Lateral"

EVAL_LOG_COLS = ["fecha", "indicador", "direccion_predicha",
                 "cambio_real", "acerto", "confianza_predicha"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_active() -> list[str]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f).get("active_indicators", [])
        except Exception:
            pass
    return ["brent", "btc", "dxy", "usdcop", "gold"]


def _match(predicted: str, actual_pct: float) -> int:
    if predicted == "Alcista":
        return 1 if actual_pct > 0 else 0
    if predicted == "Bajista":
        return 1 if actual_pct < 0 else 0
    if predicted == "Lateral":
        return 1 if abs(actual_pct) < LATERAL_THRESHOLD else 0
    return 0


def _signals_for_date(signals_hist: pd.DataFrame, fecha_str: str) -> dict:
    """Reconstruye contexto de senales para una fecha desde signals_history."""
    if signals_hist.empty:
        return {}
    row = signals_hist[signals_hist["fecha_str"] == fecha_str]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "senales": {
            "riesgo_macro":          str(r.get("riesgo_macro",          "")),
            "sesgo_mercado":         str(r.get("sesgo_mercado",         "")),
            "presion_inflacionaria": str(r.get("presion_inflacionaria", "")),
            "presion_cop":           str(r.get("presion_cop",           "")),
            "conviccion":            int(r.get("conviccion", 5)),
        }
    }


# ── Motor principal ───────────────────────────────────────────────────────────

def run_backfill_predictions(reset: bool = False) -> None:
    from intelligence.predictor_24h import predict_indicator

    if not HISTORY_FILE.exists():
        print("  market_history.csv no encontrado. Backfill omitido.")
        return

    # Cargar historico
    df_hist = pd.read_csv(HISTORY_FILE)
    df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"],
                                          errors="coerce", format="mixed")
    df_hist["value"]   = pd.to_numeric(df_hist["value"],      errors="coerce")
    df_hist["chg_pct"] = pd.to_numeric(df_hist["change_pct"], errors="coerce")
    df_hist = df_hist.dropna(subset=["timestamp", "value"])
    df_hist["date_str"] = df_hist["timestamp"].dt.strftime("%Y-%m-%d")

    # Cargar historial de senales
    signals_hist = pd.DataFrame()
    if SIGNALS_HISTORY_FILE.exists():
        sh = pd.read_csv(SIGNALS_HISTORY_FILE)
        sh["fecha_str"] = pd.to_datetime(sh["fecha"],
                                         errors="coerce").dt.strftime("%Y-%m-%d")
        signals_hist = sh

    active = _load_active()

    # Fechas validas con >= MIN_INDICATORS activos con datos
    date_counts = df_hist[df_hist["indicator"].isin(active)].groupby(
        "date_str"
    )["indicator"].nunique()
    valid_dates = (
        date_counts[date_counts >= MIN_INDICATORS]
        .sort_index()
        .tail(BACKFILL_DAYS + 1)
        .index.tolist()
    )

    if len(valid_dates) < 2:
        print("  Fechas insuficientes. Backfill omitido.")
        return

    # Claves ya existentes (si no reset)
    existing_keys: set[str] = set()
    if not reset and EVAL_LOG_FILE.exists():
        ex = pd.read_csv(EVAL_LOG_FILE)
        existing_keys = set(
            ex["fecha"].astype(str) + "_" + ex["indicador"].astype(str)
        )

    print(f"  Procesando {len(valid_dates) - 1} pares de fechas "
          f"({valid_dates[0]} -> {valid_dates[-1]})...")

    rows_all: list[dict] = []
    skipped = 0

    for i in range(1, len(valid_dates)):
        date_pred_str = valid_dates[i - 1]  # dia en que se "hizo" la prediccion
        date_eval_str = valid_dates[i]       # dia cuyos actuals evaluamos

        # Actuals del dia D
        day_actuals: dict[str, float] = {}
        for ind in active:
            sub = df_hist[
                (df_hist["indicator"] == ind) & (df_hist["date_str"] == date_eval_str)
            ]
            if not sub.empty and pd.notna(sub["chg_pct"].iloc[-1]):
                day_actuals[ind] = float(sub["chg_pct"].iloc[-1])

        if not day_actuals:
            continue

        # Historia hasta D-1 (inclusive) — sin look-ahead
        pred_ts    = pd.Timestamp(date_pred_str)
        hist_until = df_hist[df_hist["timestamp"].dt.normalize() <= pred_ts].copy()
        signals    = _signals_for_date(signals_hist, date_pred_str)

        for ind in active:
            actual_pct = day_actuals.get(ind)
            if actual_pct is None:
                continue

            key = f"{date_eval_str}_{ind}"
            if key in existing_keys:
                skipped += 1
                continue

            # Momentum de D-1: change_pct segun historico
            ind_prev = df_hist[
                (df_hist["indicator"] == ind) & (df_hist["date_str"] == date_pred_str)
            ]
            momentum_pct = (
                float(ind_prev["chg_pct"].iloc[-1])
                if not ind_prev.empty and pd.notna(ind_prev["chg_pct"].iloc[-1])
                else 0.0
            )

            try:
                pred = predict_indicator(ind, hist_until, momentum_pct, signals)
            except Exception:
                continue

            rows_all.append({
                "fecha":              date_eval_str,
                "indicador":          ind,
                "direccion_predicha": pred["direccion_24h"],
                "cambio_real":        round(actual_pct, 4),
                "acerto":             _match(pred["direccion_24h"], actual_pct),
                "confianza_predicha": pred["confianza"],
            })

    if skipped:
        print(f"  {skipped} filas ya existentes (omitidas).")

    if not rows_all:
        print("  Sin evaluaciones nuevas para guardar.")
        return

    # Guardar
    new_df = pd.DataFrame(rows_all, columns=EVAL_LOG_COLS)
    EVAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    if reset or not EVAL_LOG_FILE.exists():
        new_df.to_csv(EVAL_LOG_FILE, index=False)
        total = len(new_df)
    else:
        existing = pd.read_csv(EVAL_LOG_FILE)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined.sort_values(["fecha", "indicador"], inplace=True)
        combined.to_csv(EVAL_LOG_FILE, index=False)
        total = len(combined)

    print(f"  Guardadas {len(rows_all)} evaluaciones nuevas. "
          f"Total en log: {total} filas.")


# ── Resumen ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    if not EVAL_LOG_FILE.exists():
        print("  evaluation_log.csv no encontrado.")
        return

    df = pd.read_csv(EVAL_LOG_FILE)
    df["acerto"]            = pd.to_numeric(df["acerto"],            errors="coerce").fillna(0)
    df["confianza_predicha"]= pd.to_numeric(df["confianza_predicha"],errors="coerce").fillna(5)

    total = len(df)
    acc   = df["acerto"].mean() * 100

    print(f"\n  Total evaluaciones : {total}")
    print(f"  Acierto global     : {acc:.1f}%")

    print(f"\n  {'Indicador':<14} {'N':>5}  {'Acierto':>8}")
    print("  " + "-" * 32)
    for ind, grp in df.groupby("indicador"):
        n   = len(grp)
        acc_i = grp["acerto"].mean() * 100
        print(f"  {ind:<14} {n:>5}  {acc_i:>7.1f}%")

    _BANDS = [("1-3", 1, 3, 0.45), ("4-6", 4, 6, 0.55),
              ("7-8", 7, 8, 0.70), ("9-10", 9, 10, 0.87)]
    print(f"\n  {'Banda':<8} {'N':>5}  {'Real':>8}  {'Esperado':>9}  Estado")
    print("  " + "-" * 42)
    for name, lo, hi, exp in _BANDS:
        sub = df[(df["confianza_predicha"] >= lo) & (df["confianza_predicha"] <= hi)]
        n   = len(sub)
        real = sub["acerto"].mean() * 100 if n > 0 else 0.0
        if n < 10:
            status = "Sin datos"
        elif real / (exp * 100) < 0.80:
            status = "Sobreconfiado"
        elif real / (exp * 100) > 1.20:
            status = "Subconfiado"
        else:
            status = "Bien calibrado"
        print(f"  {name:<8} {n:>5}  {real:>7.1f}%  {exp*100:>8.1f}%  {status}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    reset = "--reset" in sys.argv
    if reset:
        print("Backfill walk-forward (modo RESET — regenerando desde cero)...")
    else:
        print("Backfill walk-forward de evaluaciones historicas (90 dias)...")

    run_backfill_predictions(reset=reset)
    print_summary()


if __name__ == "__main__":
    main()
