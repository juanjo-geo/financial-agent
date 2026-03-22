"""
Clasificador de regimen de mercado (v2).

Analiza los ultimos WINDOW_DAYS dias de market_history.csv y clasifica
el mercado en uno de 4 regimenes usando reglas deterministicas:

  INFLACIONARIO : Brent fuerte, Gold al alza, DXY apreciandose
  RISK-ON       : BTC subiendo, DXY debil, activos de riesgo positivos
  CRISIS        : Multiples activos cayendo, volatilidad elevada
  LATERAL       : Sin direccion clara, movimientos promedio < 0.3%/dia

Salida: data/signals/market_regime_v2.json
  regime       : nombre del regimen dominante
  scores       : puntuacion 0-100 de cada regimen
  confianza    : diferencia entre el 1er y 2do score (certeza relativa)
  drivers      : factores que contribuyen al regimen dominante
  descripcion  : narrativa en espanol
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT         = Path(__file__).parent.parent
HISTORY_FILE = ROOT / "data/historical/market_history.csv"
CONFIG_FILE  = ROOT / "config.json"
OUTPUT_FILE  = ROOT / "data/signals/market_regime_v2.json"

WINDOW_DAYS = 14
MIN_DAYS    = 4

_REGIMES = ("INFLACIONARIO", "RISK-ON", "CRISIS", "LATERAL")

_DESCRIPTIONS = {
    "INFLACIONARIO": (
        "El mercado muestra señales de presion inflacionaria. "
        "El petroleo y los metales preciosos registran tendencias alcistas "
        "que suelen preceder incrementos en expectativas de inflacion."
    ),
    "RISK-ON": (
        "El mercado se encuentra en modo risk-on. "
        "Los activos especulativos lideran el alza mientras el dolar "
        "cede terreno, indicando apetito por riesgo en los mercados globales."
    ),
    "CRISIS": (
        "El mercado exhibe comportamiento de aversion al riesgo generalizada. "
        "Multiples activos registran caidas simultaneas, lo que sugiere "
        "un episodio de desapalancamiento o shock de liquidez."
    ),
    "LATERAL": (
        "El mercado no muestra una direccion clara. "
        "Los movimientos de precio son contenidos y sin tendencia definida, "
        "lo que indica consolidacion o espera de un catalizador."
    ),
}


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_history_window() -> pd.DataFrame:
    """Carga los ultimos WINDOW_DAYS dias de market_history."""
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(HISTORY_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")
        df = df.dropna(subset=["timestamp", "change_pct"])
        df["date_str"] = df["timestamp"].dt.strftime("%Y-%m-%d")
        all_dates = sorted(df["date_str"].unique())
        cutoff_dates = all_dates[-WINDOW_DAYS:]
        return df[df["date_str"].isin(cutoff_dates)].copy()
    except Exception:
        return pd.DataFrame()


def _load_active() -> list[str]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f).get("active_indicators", [])
        except Exception:
            pass
    return ["brent", "btc", "dxy", "usdcop", "gold"]


# ── Metricas por indicador ────────────────────────────────────────────────────

def _metrics(df: pd.DataFrame) -> dict[str, dict]:
    """
    Para cada indicador retorna:
      avg  : cambio medio diario (%)
      vol  : desviacion estandar de cambios diarios (%)
      n    : numero de dias con datos
    """
    result: dict[str, dict] = {}
    for ind, grp in df.groupby("indicator"):
        vals = grp["change_pct"].dropna().tolist()
        n = len(vals)
        if n < 1:
            continue
        avg = sum(vals) / n
        vol = (sum((v - avg) ** 2 for v in vals) / n) ** 0.5 if n > 1 else 0.0
        result[str(ind)] = {"avg": avg, "vol": vol, "n": n}
    return result


# ── Scoring por regimen ───────────────────────────────────────────────────────

def _score_inflacionario(m: dict[str, dict]) -> tuple[int, list[str]]:
    s = 0
    drivers = []

    brent_avg = m.get("brent", {}).get("avg", 0.0)
    gold_avg  = m.get("gold",  {}).get("avg", 0.0)
    dxy_avg   = m.get("dxy",   {}).get("avg", 0.0)
    cop_avg   = m.get("usdcop",{}).get("avg", 0.0)

    if brent_avg > 0.30:
        s += 30
        drivers.append(f"Brent +{brent_avg:.2f}%/dia")
    if brent_avg > 0.60:
        s += 20
    if gold_avg > 0.10:
        s += 25
        drivers.append(f"Oro +{gold_avg:.2f}%/dia")
    if dxy_avg > 0.05:
        s += 15
        drivers.append(f"DXY +{dxy_avg:.2f}%/dia")
    if cop_avg > 0.10:
        s += 10
        drivers.append(f"USDCOP +{cop_avg:.2f}%/dia")

    return min(100, s), drivers


def _score_risk_on(m: dict[str, dict]) -> tuple[int, list[str]]:
    s = 0
    drivers = []

    btc_avg  = m.get("btc",   {}).get("avg", 0.0)
    dxy_avg  = m.get("dxy",   {}).get("avg", 0.0)
    sp5_avg  = m.get("sp500", {}).get("avg", 0.0)
    brent_avg= m.get("brent", {}).get("avg", 0.0)

    if btc_avg > 0.40:
        s += 30
        drivers.append(f"BTC +{btc_avg:.2f}%/dia")
    if btc_avg > 1.00:
        s += 20
    if dxy_avg < -0.10:
        s += 30
        drivers.append(f"DXY {dxy_avg:.2f}%/dia (debil)")
    if brent_avg > 0.10:
        s += 10
        drivers.append(f"Brent +{brent_avg:.2f}%/dia")
    if sp5_avg > 0.10:
        s += 10
        drivers.append(f"SP500 +{sp5_avg:.2f}%/dia")

    return min(100, s), drivers


def _score_crisis(m: dict[str, dict]) -> tuple[int, list[str]]:
    s = 0
    drivers = []

    crisis_assets = ["brent", "btc", "gold"]
    falling = []
    high_vol = []

    for ind in crisis_assets:
        avg = m.get(ind, {}).get("avg", 0.0)
        vol = m.get(ind, {}).get("vol", 0.0)
        if avg < -0.30:
            falling.append(ind)
        if vol > 1.5:
            high_vol.append(ind)

    if falling:
        s += len(falling) * 28
        drivers.append(f"{', '.join(falling).upper()} en caida")

    if high_vol:
        s += 16
        drivers.append(f"Volatilidad alta en {', '.join(high_vol).upper()}")

    # Bonus si DXY sube mientras todo cae (flight to safety)
    dxy_avg = m.get("dxy", {}).get("avg", 0.0)
    if len(falling) >= 2 and dxy_avg > 0.10:
        s += 12
        drivers.append("Fuga hacia el dolar (DXY al alza)")

    return min(100, s), drivers


def _score_lateral(m: dict[str, dict]) -> tuple[int, list[str]]:
    s = 0
    drivers = []

    check_assets = ["brent", "btc", "dxy", "gold", "usdcop"]
    lateral_count = 0

    for ind in check_assets:
        avg = m.get(ind, {}).get("avg", 0.0)
        if abs(avg) < 0.30:
            lateral_count += 1

    s = lateral_count * 20
    if lateral_count >= 4:
        drivers.append(f"{lateral_count}/5 activos sin tendencia definida")
    elif lateral_count >= 2:
        drivers.append(f"{lateral_count} activos laterales")

    return min(100, s), drivers


# ── Motor principal ───────────────────────────────────────────────────────────

def run_regime_classifier() -> dict:
    df = _load_history_window()

    if df.empty:
        return _empty_result("Sin datos de mercado disponibles.")

    metrics = _metrics(df)
    n_indicators = len(metrics)

    if n_indicators < 2:
        return _empty_result(f"Solo {n_indicators} indicadores disponibles.")

    scores_raw: dict[str, int] = {}
    all_drivers: dict[str, list[str]] = {}

    scores_raw["INFLACIONARIO"], all_drivers["INFLACIONARIO"] = _score_inflacionario(metrics)
    scores_raw["RISK-ON"],       all_drivers["RISK-ON"]       = _score_risk_on(metrics)
    scores_raw["CRISIS"],        all_drivers["CRISIS"]         = _score_crisis(metrics)
    scores_raw["LATERAL"],       all_drivers["LATERAL"]        = _score_lateral(metrics)

    # Regimen dominante
    dominant = max(scores_raw, key=scores_raw.__getitem__)
    sorted_scores = sorted(scores_raw.values(), reverse=True)
    confianza = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) >= 2 else sorted_scores[0]

    # Si el maximo es muy bajo, forzar LATERAL
    if scores_raw[dominant] < 25:
        dominant = "LATERAL"
        scores_raw["LATERAL"] = max(scores_raw["LATERAL"], 25)

    # Resumen de tendencias para el JSON
    trend_summary = {
        ind: {
            "avg_pct_dia": round(d["avg"], 3),
            "volatilidad": round(d["vol"], 3),
            "n_dias":      d["n"],
        }
        for ind, d in metrics.items()
    }

    return {
        "fecha":          datetime.now().strftime("%Y-%m-%d"),
        "generado_en":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime":         dominant,
        "scores":         scores_raw,
        "confianza":      int(confianza),
        "drivers":        all_drivers[dominant],
        "descripcion":    _DESCRIPTIONS[dominant],
        "trend_summary":  trend_summary,
        "window_dias":    WINDOW_DAYS,
        "n_indicadores":  n_indicators,
    }


def _empty_result(msg: str) -> dict:
    return {
        "fecha":       datetime.now().strftime("%Y-%m-%d"),
        "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime":      "LATERAL",
        "scores":      {r: 0 for r in _REGIMES},
        "confianza":   0,
        "drivers":     [],
        "descripcion": msg,
        "trend_summary": {},
        "window_dias": WINDOW_DAYS,
        "n_indicadores": 0,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Clasificando regimen de mercado...")
    result = run_regime_classifier()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    regime = result["regime"]
    conf   = result["confianza"]
    scores = result["scores"]

    _REGIME_ICONS = {
        "INFLACIONARIO": "[INF]",
        "RISK-ON":       "[RON]",
        "CRISIS":        "[CRI]",
        "LATERAL":       "[LAT]",
    }
    icon = _REGIME_ICONS.get(regime, "[ ? ]")

    print(f"  Regimen detectado : {icon} {regime}  (confianza +{conf}pts sobre 2do)")
    print(f"  Scores: " +
          "  ".join(f"{r}={scores[r]}" for r in _REGIMES))
    if result["drivers"]:
        print(f"  Drivers: {' | '.join(result['drivers'])}")
    print(f"  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
