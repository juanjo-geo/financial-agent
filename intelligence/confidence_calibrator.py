"""
Calibrador de confianza para predicciones 24h.

Lee evaluation_log.csv, agrupa por banda de confianza y calcula:
  - tasa de acierto real por grupo
  - factor de calibracion = acierto_real / acierto_esperado
  - estado: Bien calibrado / Sobreconfiado / Subconfiado

Bandas y precisiones esperadas:
  1-3  -> 0.45  (baja confianza, cercano al azar)
  4-6  -> 0.55  (confianza media)
  7-8  -> 0.70  (confianza alta)
  9-10 -> 0.87  (muy alta confianza)

Salida: data/signals/calibration_factors.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT           = Path(__file__).parent.parent
EVAL_LOG_FILE  = ROOT / "data/signals/evaluation_log.csv"
OUTPUT_FILE    = ROOT / "data/signals/calibration_factors.json"

MIN_N_BAND = 10   # minimo de predicciones para calcular factor real

# (nombre, min_conf, max_conf, precision_esperada)
_BANDS: list[tuple[str, int, int, float]] = [
    ("1-3",   1,  3, 0.45),
    ("4-6",   4,  6, 0.55),
    ("7-8",   7,  8, 0.70),
    ("9-10",  9, 10, 0.87),
]

# factor < OVER → Sobreconfiado  |  factor > UNDER → Subconfiado
_OVER_THRESHOLD  = 0.80
_UNDER_THRESHOLD = 1.20


def _status(factor: float, n: int) -> str:
    if n < MIN_N_BAND:
        return "Sin datos suficientes"
    if factor < _OVER_THRESHOLD:
        return "Sobreconfiado"
    if factor > _UNDER_THRESHOLD:
        return "Subconfiado"
    return "Bien calibrado"


def run_confidence_calibrator() -> dict:
    if not EVAL_LOG_FILE.exists():
        print("  evaluation_log.csv no encontrado. Calibracion omitida.")
        return {}

    df = pd.read_csv(EVAL_LOG_FILE)
    df["acerto"]            = pd.to_numeric(df["acerto"],            errors="coerce").fillna(0)
    df["confianza_predicha"]= pd.to_numeric(df["confianza_predicha"],errors="coerce").fillna(5)

    total = len(df)
    bandas: dict[str, dict] = {}

    for name, lo, hi, expected in _BANDS:
        mask    = (df["confianza_predicha"] >= lo) & (df["confianza_predicha"] <= hi)
        subset  = df[mask]
        n       = len(subset)
        acc_r   = float(subset["acerto"].mean()) if n > 0 else 0.0
        factor  = round(acc_r / expected, 4) if (n >= MIN_N_BAND and expected > 0) else 1.0
        status  = _status(factor, n)

        bandas[name] = {
            "n":                n,
            "acierto_real":     round(acc_r, 4),
            "acierto_esperado": expected,
            "factor":           factor,
            "status":           status,
            "suficientes_datos": n >= MIN_N_BAND,
        }

    result = {
        "fecha":        datetime.now().strftime("%Y-%m-%d"),
        "generado_en":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_predicciones": total,
        "bandas": bandas,
    }
    return result


def main():
    print("Calculando factores de calibracion de confianza...")
    result = run_confidence_calibrator()
    if not result:
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"  Total predicciones analizadas: {result['total_predicciones']}")
    print(f"  {'Banda':<8}  {'N':>5}  {'Real':>8}  {'Esperado':>9}  {'Factor':>7}  Estado")
    print("  " + "-" * 60)
    for name, b in result["bandas"].items():
        print(
            f"  {name:<8}  {b['n']:>5}  "
            f"{b['acierto_real']:>7.1%}  {b['acierto_esperado']:>8.1%}  "
            f"{b['factor']:>7.2f}  {b['status']}"
        )
    print(f"\n  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
