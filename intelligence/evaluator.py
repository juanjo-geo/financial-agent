"""
Evaluacion ex-post de predicciones 24h.

Por cada dia, compara la prediccion generada ayer (predictions_24h_YYYY-MM-DD.json)
contra el cambio real registrado en el snapshot del dia (latest_snapshot.csv).

Acierto:
  Alcista  -> acerto si change_pct > 0
  Bajista  -> acerto si change_pct < 0
  Lateral  -> acerto si abs(change_pct) < LATERAL_THRESHOLD (1.0%)

Salida: data/signals/evaluation_log.csv
Columnas: fecha, indicador, direccion_predicha, cambio_real, acerto, confianza_predicha
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from intelligence.predictor_24h import predict_indicator

ROOT                 = Path(__file__).parent.parent
SNAPSHOT_FILE        = ROOT / "data/processed/latest_snapshot.csv"
HISTORY_FILE         = ROOT / "data/historical/market_history.csv"
SIGNALS_HISTORY_FILE = ROOT / "data/signals/signals_history.csv"
PREDICTIONS_DIR      = ROOT / "data/signals"
EVAL_LOG_FILE        = ROOT / "data/signals/evaluation_log.csv"
CONFIG_FILE          = ROOT / "config.json"

EVAL_LOG_COLS     = ["fecha", "indicador", "direccion_predicha", "cambio_real",
                     "acerto", "confianza_predicha"]
MIN_BACKFILL_ROWS = 7
BACKFILL_DAYS     = 30
LATERAL_THRESHOLD = 1.0   # abs(change_pct) < 1.0% = correcto para "Lateral"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _match(predicted: str, actual_pct: float) -> int:
    """1 si la direccion predicha coincide con el cambio real, 0 si no."""
    if predicted == "Alcista":
        return 1 if actual_pct > 0 else 0
    if predicted == "Bajista":
        return 1 if actual_pct < 0 else 0
    if predicted == "Lateral":
        return 1 if abs(actual_pct) < LATERAL_THRESHOLD else 0
    return 0


def _load_snapshot_changes() -> dict[str, float]:
    if not SNAPSHOT_FILE.exists():
        return {}
    df = pd.read_csv(SNAPSHOT_FILE)
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        pct = pd.to_numeric(row.get("change_pct"), errors="coerce")
        if pd.notna(pct):
            out[str(row["indicator"]).lower()] = float(pct)
    return out


def _load_active_indicators() -> list[str]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f).get("active_indicators", [])
        except Exception:
            pass
    return ["brent", "btc", "dxy", "usdcop", "gold"]


def _append_rows(rows: list[dict]) -> None:
    """Agrega filas al CSV evitando duplicados por (fecha, indicador)."""
    if not rows:
        return
    EVAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(rows, columns=EVAL_LOG_COLS)
    if EVAL_LOG_FILE.exists():
        existing = pd.read_csv(EVAL_LOG_FILE)
        ex_keys  = existing["fecha"].astype(str) + "_" + existing["indicador"].astype(str)
        nw_keys  = new_df["fecha"].astype(str)   + "_" + new_df["indicador"].astype(str)
        new_df   = new_df[~nw_keys.isin(ex_keys)]
        df       = pd.concat([existing, new_df], ignore_index=True)
    else:
        df = new_df
    df.to_csv(EVAL_LOG_FILE, index=False)


# ── Evaluacion del dia ────────────────────────────────────────────────────────

def evaluate_yesterday() -> list[dict]:
    """
    Lee predictions_24h_{ayer}.json y compara contra el snapshot actual.
    El snapshot antes de market_collector contiene los datos del dia anterior,
    que son exactamente los actuals que corresponde evaluar.
    """
    yesterday     = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    pred_file     = PREDICTIONS_DIR / f"predictions_24h_{yesterday}.json"

    if not pred_file.exists():
        print(f"  Sin archivo de predicciones para {yesterday}. "
              f"El archivo se crea en el primer pipeline completo.")
        return []

    with open(pred_file, encoding="utf-8") as f:
        pred_data = json.load(f)

    actuals = _load_snapshot_changes()
    if not actuals:
        print("  Snapshot vacio — sin datos para evaluar.")
        return []

    fecha_eval   = date.today().strftime("%Y-%m-%d")
    predicciones = pred_data.get("predicciones", {})
    rows: list[dict] = []

    for ind, p in predicciones.items():
        actual_pct = actuals.get(ind)
        if actual_pct is None:
            continue
        rows.append({
            "fecha":              fecha_eval,
            "indicador":          ind,
            "direccion_predicha": p.get("direccion_24h", "Lateral"),
            "cambio_real":        round(actual_pct, 4),
            "acerto":             _match(p.get("direccion_24h", "Lateral"), actual_pct),
            "confianza_predicha": p.get("confianza", 5),
        })

    return rows


# ── Backfill retroactivo ──────────────────────────────────────────────────────

def _signals_for_date(signals_hist: pd.DataFrame, fecha_str: str) -> dict:
    """Reconstruye el dict de senales desde signals_history.csv para una fecha."""
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


def backfill_evaluations() -> None:
    """
    Genera evaluaciones retroactivas para los ultimos BACKFILL_DAYS dias
    solo si evaluation_log.csv tiene menos de MIN_BACKFILL_ROWS filas.
    Usa predict_indicator() con datos historicos reales para simular la prediccion.
    """
    if EVAL_LOG_FILE.exists():
        existing = pd.read_csv(EVAL_LOG_FILE)
        if len(existing) >= MIN_BACKFILL_ROWS:
            print(f"  evaluation_log.csv ya tiene {len(existing)} filas. Backfill omitido.")
            return
        existing_keys = set(
            existing["fecha"].astype(str) + "_" + existing["indicador"].astype(str)
        )
    else:
        existing_keys = set()

    if not HISTORY_FILE.exists():
        print("  Sin market_history.csv. Backfill omitido.")
        return

    df_hist = pd.read_csv(HISTORY_FILE)
    df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"], errors="coerce", format="mixed")
    df_hist["value"]     = pd.to_numeric(df_hist["value"],      errors="coerce")
    df_hist["chg_pct"]   = pd.to_numeric(df_hist["change_pct"], errors="coerce")
    df_hist = df_hist.dropna(subset=["timestamp", "value"])
    df_hist["date_str"] = df_hist["timestamp"].dt.strftime("%Y-%m-%d")

    # Cargar historial de senales para contexto retroactivo
    signals_hist = pd.DataFrame()
    if SIGNALS_HISTORY_FILE.exists():
        sh = pd.read_csv(SIGNALS_HISTORY_FILE)
        sh["fecha_str"] = pd.to_datetime(sh["fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        signals_hist = sh

    active = _load_active_indicators()

    # Fechas validas con >= 3 indicadores
    date_counts = df_hist.groupby("date_str")["indicator"].nunique()
    valid_dates = (
        date_counts[date_counts >= 3]
        .sort_index()
        .tail(BACKFILL_DAYS + 1)
        .index.tolist()
    )

    if len(valid_dates) < 2:
        print("  Fechas insuficientes en historial para backfill.")
        return

    print(f"  Backfill evaluaciones retroactivas: {len(valid_dates) - 1} pares de fechas...")
    rows_all: list[dict] = []

    for i in range(1, len(valid_dates)):
        date_pred_str = valid_dates[i - 1]   # D-1: cuando se "habria hecho" la prediccion
        date_eval_str = valid_dates[i]        # D: fecha de los actuals

        # Actuals: change_pct real del dia D
        day_actuals: dict[str, float] = {}
        for ind in active:
            subset = df_hist[
                (df_hist["indicator"] == ind) & (df_hist["date_str"] == date_eval_str)
            ]
            if not subset.empty:
                chg = subset["chg_pct"].iloc[-1]
                if pd.notna(chg):
                    day_actuals[ind] = float(chg)

        if not day_actuals:
            continue

        # Historia hasta D-1 (inclusive) para calcular tendencia
        pred_ts      = pd.Timestamp(date_pred_str)
        hist_until   = df_hist[df_hist["timestamp"].dt.normalize() <= pred_ts].copy()
        signals_prev = _signals_for_date(signals_hist, date_pred_str)

        for ind in active:
            actual_pct = day_actuals.get(ind)
            if actual_pct is None:
                continue

            key = f"{date_eval_str}_{ind}"
            if key in existing_keys:
                continue

            # Momentum para D-1: change_pct de ese dia segun historial
            ind_prev = df_hist[
                (df_hist["indicator"] == ind) & (df_hist["date_str"] == date_pred_str)
            ]
            momentum_pct = (
                float(ind_prev["chg_pct"].iloc[-1])
                if not ind_prev.empty and pd.notna(ind_prev["chg_pct"].iloc[-1])
                else 0.0
            )

            try:
                pred = predict_indicator(ind, hist_until, momentum_pct, signals_prev)
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

    if rows_all:
        _append_rows(rows_all)
        total = len(pd.read_csv(EVAL_LOG_FILE)) if EVAL_LOG_FILE.exists() else len(rows_all)
        print(f"  Backfill completado: {len(rows_all)} evaluaciones. Total: {total} filas.")
    else:
        print("  Sin evaluaciones nuevas para backfill.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Evaluando predicciones del dia anterior...")
    backfill_evaluations()

    rows = evaluate_yesterday()
    if rows:
        _append_rows(rows)
        hits = sum(r["acerto"] for r in rows)
        pct  = hits / len(rows) * 100
        print(f"  Hoy: {len(rows)} indicadores evaluados | "
              f"Aciertos: {hits}/{len(rows)} ({pct:.0f}%)")
        total = len(pd.read_csv(EVAL_LOG_FILE))
        print(f"  Total en log: {total} filas | {EVAL_LOG_FILE.name}")
    else:
        print("  Sin evaluaciones nuevas para guardar.")


if __name__ == "__main__":
    main()
