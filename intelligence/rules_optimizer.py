"""
Optimizador de pesos del predictor 24h.

Para cada evaluacion historica (fecha, indicador, cambio_real) re-computa
los scores individuales de los 3 componentes (tendencia, momentum, senales)
y calcula la tasa de acierto real de cada componente de forma independiente.

Los nuevos pesos son proporcionales a la tasa de acierto de cada componente,
mezclados con los pesos actuales (suavizado: alpha=0.3).

Salida: data/signals/optimized_weights.json
  weights.trend    : nuevo peso para tendencia    (default 0.50)
  weights.momentum : nuevo peso para momentum     (default 0.30)
  weights.signals  : nuevo peso para senales      (default 0.20)

predictor_24h.py lee estos pesos si el archivo existe.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from intelligence.predictor_24h import (
    TREND_DAYS,
    _ALIGNMENT,
    _DEFAULT_ALIGNMENT,
    _dir_from_score,
    _linear_slope_pct,
)

ROOT                 = Path(__file__).parent.parent
EVAL_LOG_FILE        = ROOT / "data/signals/evaluation_log.csv"
HISTORY_FILE         = ROOT / "data/historical/market_history.csv"
SIGNALS_HISTORY_FILE = ROOT / "data/signals/signals_history.csv"
OUTPUT_FILE          = ROOT / "data/signals/optimized_weights.json"

MIN_EVALUATIONS  = 20     # minimo para optimizar pesos
ALPHA            = 0.30   # tasa de aprendizaje (mezcla con pesos anteriores)
WEIGHT_MIN       = 0.10   # peso minimo por componente
WEIGHT_MAX       = 0.70   # peso maximo por componente

_DEFAULT_WEIGHTS = {"trend": 0.50, "momentum": 0.30, "signals": 0.20}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _actual_dir(change_pct: float) -> str:
    if change_pct > 0:    return "alcista"
    if change_pct < 0:    return "bajista"
    return "lateral"


def _hit(predicted_dir: str, actual_dir: str) -> int:
    if predicted_dir == "lateral":
        return 1 if actual_dir == "lateral" else 0
    return 1 if predicted_dir == actual_dir else 0


def _load_prior_weights() -> dict[str, float]:
    """Lee pesos actuales del archivo si existe, si no usa defaults."""
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                d = json.load(f)
            w = d.get("weights", {})
            if all(k in w for k in ("trend", "momentum", "signals")):
                return {k: float(w[k]) for k in ("trend", "momentum", "signals")}
        except Exception:
            pass
    return dict(_DEFAULT_WEIGHTS)


def _signal_score_for(indicator: str, signals_dict: dict) -> float:
    """Computa signal_score para un indicador dado un dict de senales."""
    s         = signals_dict.get("senales", {})
    alignment = _ALIGNMENT.get(indicator, _DEFAULT_ALIGNMENT)
    score     = sum(alignment.get(f"{field}_{val}", 0.0)
                    for field, val in s.items() if isinstance(val, str))
    return max(-3.0, min(3.0, score))


# ── Motor principal ───────────────────────────────────────────────────────────

def run_rules_optimizer() -> dict:
    # ── Cargar datos ──────────────────────────────────────────────────────────
    if not EVAL_LOG_FILE.exists():
        print("  evaluation_log.csv no encontrado. Optimizacion omitida.")
        return {}
    if not HISTORY_FILE.exists():
        print("  market_history.csv no encontrado. Optimizacion omitida.")
        return {}

    eval_df = pd.read_csv(EVAL_LOG_FILE)
    eval_df["fecha"]      = pd.to_datetime(eval_df["fecha"], errors="coerce")
    eval_df["cambio_real"]= pd.to_numeric(eval_df["cambio_real"], errors="coerce")
    eval_df = eval_df.dropna(subset=["fecha", "cambio_real"])

    if len(eval_df) < MIN_EVALUATIONS:
        print(f"  Insuficientes evaluaciones ({len(eval_df)} < {MIN_EVALUATIONS}). "
              "Guardando pesos por defecto.")
        _save_defaults()
        return {}

    hist_df = pd.read_csv(HISTORY_FILE)
    hist_df["timestamp"] = pd.to_datetime(hist_df["timestamp"], errors="coerce", format="mixed")
    hist_df["value"]     = pd.to_numeric(hist_df["value"],      errors="coerce")
    hist_df["chg_pct"]   = pd.to_numeric(hist_df["change_pct"], errors="coerce")
    hist_df = hist_df.dropna(subset=["timestamp", "value"])
    hist_df["date_str"]  = hist_df["timestamp"].dt.strftime("%Y-%m-%d")

    # Indice de fechas de mercado disponibles por indicador
    all_market_dates = sorted(hist_df["date_str"].unique())

    # Historial de senales (para signal_score retroactivo)
    sig_hist: dict[str, dict] = {}   # date_str -> signals_dict
    if SIGNALS_HISTORY_FILE.exists():
        sh = pd.read_csv(SIGNALS_HISTORY_FILE)
        for _, row in sh.iterrows():
            fecha_s = str(row.get("fecha", ""))[:10]
            sig_hist[fecha_s] = {
                "senales": {
                    "riesgo_macro":          str(row.get("riesgo_macro",          "")),
                    "sesgo_mercado":         str(row.get("sesgo_mercado",         "")),
                    "presion_inflacionaria": str(row.get("presion_inflacionaria", "")),
                    "presion_cop":           str(row.get("presion_cop",           "")),
                    "conviccion":            int(row.get("conviccion", 5)),
                }
            }

    # ── Iterar evaluaciones ───────────────────────────────────────────────────
    trend_hits, momentum_hits, signal_hits, total_valid = 0, 0, 0, 0

    for _, row in eval_df.iterrows():
        fecha_eval = row["fecha"]
        ind        = str(row["indicador"]).lower()
        actual_pct = float(row["cambio_real"])

        # Encontrar la fecha de prediccion = ultimo dia de mercado ANTES de fecha_eval
        fecha_eval_s = fecha_eval.strftime("%Y-%m-%d")
        prev_dates   = [d for d in all_market_dates if d < fecha_eval_s]
        if not prev_dates:
            continue
        fecha_pred_s = prev_dates[-1]

        # Historia hasta fecha_pred (inclusive)
        hist_until = hist_df[hist_df["timestamp"].dt.normalize() <=
                              pd.Timestamp(fecha_pred_s)]

        # ── Tendencia ─────────────────────────────────────────────────────────
        today_ts = hist_until["timestamp"].max().normalize() if not hist_until.empty else None
        if today_ts is not None:
            cutoff  = today_ts - pd.Timedelta(days=TREND_DAYS)
            ind_sub = hist_until[
                (hist_until["indicator"] == ind) &
                (hist_until["timestamp"].dt.normalize() >= cutoff)
            ].sort_values("timestamp")
            vals        = ind_sub["value"].dropna().tolist()
            slope_pct   = _linear_slope_pct(vals) if len(vals) >= 2 else 0.0
            trend_score = max(-3.0, min(3.0, slope_pct * 2.0))
        else:
            trend_score = 0.0

        # ── Momentum ─────────────────────────────────────────────────────────
        mom_sub = hist_df[
            (hist_df["indicator"] == ind) & (hist_df["date_str"] == fecha_pred_s)
        ]
        mom_pct       = float(mom_sub["chg_pct"].iloc[-1]) if not mom_sub.empty else 0.0
        momentum_score= max(-3.0, min(3.0, mom_pct * 0.5))

        # ── Señales ───────────────────────────────────────────────────────────
        signals_prev  = sig_hist.get(fecha_pred_s, {})
        signal_score  = _signal_score_for(ind, signals_prev)

        # ── Direcciones ───────────────────────────────────────────────────────
        trend_dir    = _dir_from_score(trend_score)
        momentum_dir = _dir_from_score(momentum_score * 0.6)  # dampened (mismo que predictor)
        signal_dir   = _dir_from_score(signal_score)
        actual       = _actual_dir(actual_pct)

        # Excluir actuals con movimiento insignificante (< 0.1%) para evitar ruido
        if abs(actual_pct) < 0.1:
            continue

        trend_hits    += _hit(trend_dir,    actual)
        momentum_hits += _hit(momentum_dir, actual)
        signal_hits   += _hit(signal_dir,   actual)
        total_valid   += 1

    if total_valid == 0:
        print("  Sin evaluaciones validas para optimizacion. Guardando pesos por defecto.")
        _save_defaults()
        return {}

    # ── Calcular tasas de acierto ─────────────────────────────────────────────
    trend_rate    = trend_hits    / total_valid
    momentum_rate = momentum_hits / total_valid
    signal_rate   = signal_hits   / total_valid

    total_rate = trend_rate + momentum_rate + signal_rate
    if total_rate == 0:
        trend_rate = momentum_rate = signal_rate = 1 / 3

    # ── Nuevos pesos proporcionales a tasa de acierto ─────────────────────────
    new_trend    = trend_rate    / total_rate
    new_momentum = momentum_rate / total_rate
    new_signals  = signal_rate   / total_rate

    # ── Suavizado con pesos anteriores (alpha blend) ──────────────────────────
    prior = _load_prior_weights()
    blend_trend    = (1 - ALPHA) * prior["trend"]    + ALPHA * new_trend
    blend_momentum = (1 - ALPHA) * prior["momentum"] + ALPHA * new_momentum
    blend_signals  = (1 - ALPHA) * prior["signals"]  + ALPHA * new_signals

    # ── Clamp y renormalizar ──────────────────────────────────────────────────
    def _clamp(v: float) -> float:
        return max(WEIGHT_MIN, min(WEIGHT_MAX, v))

    ct = _clamp(blend_trend)
    cm = _clamp(blend_momentum)
    cs = _clamp(blend_signals)
    total_clamped = ct + cm + cs

    final_trend    = round(ct / total_clamped, 4)
    final_momentum = round(cm / total_clamped, 4)
    final_signals  = round(1.0 - final_trend - final_momentum, 4)  # ensure sum=1

    result = {
        "fecha":        datetime.now().strftime("%Y-%m-%d"),
        "generado_en":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_evaluaciones": total_valid,
        "weights": {
            "trend":    final_trend,
            "momentum": final_momentum,
            "signals":  final_signals,
        },
        "hit_rates": {
            "trend":    round(trend_rate,    4),
            "momentum": round(momentum_rate, 4),
            "signals":  round(signal_rate,   4),
        },
        "pesos_anteriores": prior,
    }
    return result


def _save_defaults() -> None:
    result = {
        "fecha":        datetime.now().strftime("%Y-%m-%d"),
        "generado_en":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_evaluaciones": 0,
        "weights":      _DEFAULT_WEIGHTS,
        "hit_rates":    {"trend": 0.0, "momentum": 0.0, "signals": 0.0},
        "pesos_anteriores": _DEFAULT_WEIGHTS,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


def main():
    print("Optimizando pesos del predictor...")
    result = run_rules_optimizer()
    if not result:
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    w  = result["weights"]
    hr = result["hit_rates"]
    n  = result["n_evaluaciones"]
    print(f"  Evaluaciones analizadas : {n}")
    print(f"  {'Componente':<12}  {'Hit Rate':>9}  {'Peso nuevo':>10}  {'Peso anterior':>13}")
    print("  " + "-" * 52)
    prior = result["pesos_anteriores"]
    for comp in ("trend", "momentum", "signals"):
        print(f"  {comp:<12}  {hr[comp]:>8.1%}  {w[comp]:>10.4f}  {prior[comp]:>13.4f}")
    print(f"\n  Pesos finales: trend={w['trend']:.3f}  "
          f"momentum={w['momentum']:.3f}  signals={w['signals']:.3f}")
    print(f"  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
