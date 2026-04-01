"""
adaptive_weights.py
-------------------
Calcula multiplicadores adaptativos para cada indicador basándose en
la precisión real de sus predicciones en los últimos N días.

Lógica:
  - Lee evaluation_log.csv
  - Para cada indicador, calcula accuracy rolling (últimos WINDOW_DAYS)
  - Mapea accuracy → multiplicador usando función sigmoide centrada en 55%
      · accuracy = 55% → multiplicador = 1.0 (sin cambio)
      · accuracy = 70% → multiplicador ≈ 1.30 (aumenta peso)
      · accuracy = 40% → multiplicador ≈ 0.70 (reduce peso)
      · límites: [MIN_MULT, MAX_MULT]
  - Guarda en data/signals/adaptive_weights.json

El signals_engine.py lee estos multiplicadores y los aplica a los
scores de cada indicador antes de calcular las señales finales.

Uso: python -m intelligence.adaptive_weights
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT            = Path(__file__).parent.parent
EVAL_LOG_FILE   = ROOT / "data/signals/evaluation_log.csv"
OUTPUT_FILE     = ROOT / "data/signals/adaptive_weights.json"

WINDOW_DAYS = 30     # ventana rolling para calcular accuracy
MIN_N       = 10     # mínimo de predicciones para ajustar (si no, mult=1.0)
MIN_MULT    = 0.60   # multiplicador mínimo (indicador muy malo)
MAX_MULT    = 1.50   # multiplicador máximo (indicador muy bueno)
CENTER_ACC  = 0.55   # accuracy "neutral" → multiplicador = 1.0
STEEPNESS   = 6.0    # qué tan agresivo es el ajuste


def _sigmoid_mult(accuracy: float) -> float:
    """
    Mapea accuracy [0,1] → multiplicador [MIN_MULT, MAX_MULT].
    Centrado en CENTER_ACC → mult = 1.0.
    """
    x = accuracy - CENTER_ACC          # desviación del centro
    raw = 1.0 / (1.0 + math.exp(-STEEPNESS * x))  # sigmoide [0,1]
    # Escalar al rango [MIN_MULT, MAX_MULT]
    mult = MIN_MULT + raw * (MAX_MULT - MIN_MULT)
    return round(mult, 4)


def compute_adaptive_weights(window_days: int = WINDOW_DAYS) -> dict:
    if not EVAL_LOG_FILE.exists():
        print("  evaluation_log.csv no encontrado.")
        return {}

    df = pd.read_csv(EVAL_LOG_FILE, parse_dates=["fecha"])
    df["acerto"] = pd.to_numeric(df["acerto"], errors="coerce").fillna(0)

    cutoff = datetime.now() - timedelta(days=window_days)
    recent = df[df["fecha"] >= cutoff]

    weights: dict[str, dict] = {}
    all_indicators = df["indicador"].unique().tolist()

    for indicator in all_indicators:
        # Datos recientes
        subset_recent = recent[recent["indicador"] == indicator]
        n_recent = len(subset_recent)

        # Datos históricos totales (para referencia)
        subset_all = df[df["indicador"] == indicator]
        acc_all    = float(subset_all["acerto"].mean()) if len(subset_all) > 0 else 0.5

        if n_recent >= MIN_N:
            acc_recent = float(subset_recent["acerto"].mean())
            mult = _sigmoid_mult(acc_recent)
            source = f"rolling_{window_days}d"
        elif len(subset_all) >= MIN_N:
            # No hay suficientes datos recientes → usar histórico completo con menor confianza
            acc_recent = acc_all
            raw_mult = _sigmoid_mult(acc_all)
            # Suavizar hacia 1.0 (menos agresivo con datos viejos)
            mult = round(0.5 * raw_mult + 0.5 * 1.0, 4)
            source = "historico_total_suavizado"
            n_recent = len(subset_all)
        else:
            acc_recent = 0.5
            mult = 1.0
            source = "sin_datos"

        weights[indicator] = {
            "multiplicador":    mult,
            "accuracy_reciente": round(acc_recent, 4),
            "accuracy_global":   round(acc_all,    4),
            "n_reciente":        n_recent,
            "n_total":           len(subset_all),
            "fuente":            source,
            "estado":            _classify(mult),
        }

    return weights


def _classify(mult: float) -> str:
    if mult >= 1.20:   return "Confiable — peso aumentado"
    if mult >= 0.90:   return "Neutro"
    if mult >= 0.75:   return "Débil — peso reducido"
    return "Poco confiable — peso muy reducido"


def main():
    print(f"Calculando pesos adaptativos (ventana: {WINDOW_DAYS} días)...")
    weights = compute_adaptive_weights()

    if not weights:
        return

    result = {
        "generado_en":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "window_days":  WINDOW_DAYS,
        "center_acc":   CENTER_ACC,
        "pesos":        weights,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUTPUT_FILE)

    print(f"\n  {'Indicador':<12} {'Mult':>6}  {'Acc Reciente':>13}  {'Acc Global':>11}  Estado")
    print("  " + "-" * 68)
    for ind, w in sorted(weights.items()):
        print(
            f"  {ind:<12} {w['multiplicador']:>6.3f}  "
            f"{w['accuracy_reciente']:>12.1%}  "
            f"{w['accuracy_global']:>10.1%}  {w['estado']}"
        )
    print(f"\n  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
