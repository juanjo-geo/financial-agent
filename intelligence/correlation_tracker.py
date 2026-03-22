"""
Rastreador de correlaciones dinamicas entre pares de activos.

Calcula la correlacion de Pearson entre pares clave usando una ventana
movil de WINDOW_DAYS dias sobre market_history.csv.

Detecta "correlaciones rotas": casos donde la correlacion historica
(baseline de 60 dias) difiere significativamente de la actual (30 dias).

Pares monitoreados (con su correlacion esperada):
  DXY  <-> BTC      : normalmente negativa  (dolar fuerte = BTC baja)
  DXY  <-> Gold     : normalmente negativa  (dolar fuerte = oro baja)
  Brent<-> USDCOP   : normalmente positiva  (petroleo sube = COP se fortalece)
  BTC  <-> Gold     : variable              (refugio vs especulacion)
  Brent<-> DXY      : normalmente positiva  (petroleo en USD)

Salida: data/signals/correlations.json
  pares[{a, b, corr_actual, corr_baseline, delta, rota, alerta}]
  generado_en, n_dias_ventana
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT         = Path(__file__).parent.parent
HISTORY_FILE = ROOT / "data/historical/market_history.csv"
OUTPUT_FILE  = ROOT / "data/signals/correlations.json"

WINDOW_DAYS   = 30   # ventana actual
BASELINE_DAYS = 60   # ventana de referencia (mas antigua)
MIN_POINTS    = 10   # minimo de pares de fechas para calcular

BREAK_DELTA   = 0.40  # diferencia |actual - baseline| para declarar ruptura
ALERT_DELTA   = 0.55  # diferencia para alerta de alta intensidad

# (indicador_a, indicador_b, descripcion_relacion, correlacion_esperada)
_PAIRS: list[tuple[str, str, str, str]] = [
    ("dxy", "btc",    "DXY vs BTC",         "negativa"),
    ("dxy", "gold",   "DXY vs Oro",          "negativa"),
    ("brent", "usdcop","Brent vs USDCOP",    "positiva"),
    ("btc", "gold",   "BTC vs Oro",          "variable"),
    ("brent", "dxy",  "Brent vs DXY",        "positiva"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pearson(x: list[float], y: list[float]) -> float | None:
    """Correlacion de Pearson manual. Retorna None si no calculable."""
    n = len(x)
    if n < MIN_POINTS:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx  = sum((xi - mx) ** 2 for xi in x) ** 0.5
    dy  = sum((yi - my) ** 2 for yi in y) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 4)


def _load_pivot() -> pd.DataFrame:
    """
    Carga market_history y devuelve pivot: index=date_str, cols=indicadores,
    valores=change_pct.
    """
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(HISTORY_FILE)
        df["timestamp"]  = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")
        df = df.dropna(subset=["timestamp", "change_pct"])
        df["date_str"] = df["timestamp"].dt.strftime("%Y-%m-%d")

        pivot = df.pivot_table(
            index="date_str",
            columns="indicator",
            values="change_pct",
            aggfunc="last",
        )
        pivot.sort_index(inplace=True)
        return pivot
    except Exception:
        return pd.DataFrame()


# ── Motor principal ───────────────────────────────────────────────────────────

def run_correlation_tracker() -> dict:
    pivot = _load_pivot()

    if pivot.empty or len(pivot) < MIN_POINTS:
        return {
            "fecha":        datetime.now().strftime("%Y-%m-%d"),
            "generado_en":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "n_dias_ventana": WINDOW_DAYS,
            "n_dias_total":  len(pivot),
            "pares":        [],
            "alertas":      [],
        }

    # Ventanas
    all_dates    = pivot.index.tolist()
    window_dates = all_dates[-WINDOW_DAYS:]
    # Baseline: las BASELINE_DAYS anteriores a la ventana actual
    base_end   = max(0, len(all_dates) - WINDOW_DAYS)
    base_start = max(0, base_end - BASELINE_DAYS)
    baseline_dates = all_dates[base_start:base_end]

    current_pivot  = pivot.loc[window_dates]
    baseline_pivot = pivot.loc[baseline_dates] if baseline_dates else pd.DataFrame()

    pares: list[dict] = []
    alertas: list[str] = []

    for a, b, desc, expected in _PAIRS:
        if a not in pivot.columns or b not in pivot.columns:
            pares.append({
                "par": desc, "a": a, "b": b,
                "corr_actual": None, "corr_baseline": None,
                "delta": None, "rota": False, "alerta": False,
                "esperada": expected, "n_actual": 0,
            })
            continue

        # Correlacion actual (ultimos 30 dias)
        cur = current_pivot[[a, b]].dropna()
        corr_actual = _pearson(cur[a].tolist(), cur[b].tolist())

        # Correlacion baseline (dias 31-90 anteriores)
        corr_baseline = None
        if not baseline_pivot.empty and a in baseline_pivot.columns and b in baseline_pivot.columns:
            bas = baseline_pivot[[a, b]].dropna()
            corr_baseline = _pearson(bas[a].tolist(), bas[b].tolist())

        # Ruptura
        delta = None
        rota  = False
        alerta_flag = False
        if corr_actual is not None and corr_baseline is not None:
            delta = round(abs(corr_actual - corr_baseline), 4)
            rota  = delta >= BREAK_DELTA
            alerta_flag = delta >= ALERT_DELTA

        par_dict = {
            "par":            desc,
            "a":              a,
            "b":              b,
            "corr_actual":    corr_actual,
            "corr_baseline":  corr_baseline,
            "delta":          delta,
            "rota":           rota,
            "alerta":         alerta_flag,
            "esperada":       expected,
            "n_actual":       len(cur),
            "n_baseline":     len(baseline_pivot[[a, b]].dropna()) if not baseline_pivot.empty else 0,
        }
        pares.append(par_dict)

        if rota:
            dir_actual   = "positiva" if (corr_actual or 0) > 0 else "negativa"
            dir_baseline = "positiva" if (corr_baseline or 0) > 0 else "negativa"
            if dir_actual != dir_baseline:
                alertas.append(
                    f"Correlacion rota: {desc} cambio de {dir_baseline} "
                    f"({corr_baseline:.2f}) a {dir_actual} ({corr_actual:.2f})"
                )
            else:
                alertas.append(
                    f"Correlacion debilitada: {desc} "
                    f"baseline={corr_baseline:.2f} -> actual={corr_actual:.2f}"
                )

    return {
        "fecha":           datetime.now().strftime("%Y-%m-%d"),
        "generado_en":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_dias_ventana":  WINDOW_DAYS,
        "n_dias_baseline": len(baseline_dates),
        "n_dias_total":    len(all_dates),
        "pares":           pares,
        "alertas":         alertas,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Calculando correlaciones dinamicas entre activos...")
    result = run_correlation_tracker()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    pares = result.get("pares", [])
    print(f"  Ventana actual   : {result['n_dias_ventana']} dias")
    print(f"  Baseline         : {result.get('n_dias_baseline', 0)} dias")
    print(f"  Total disponible : {result['n_dias_total']} dias")
    print()
    print(f"  {'Par':<22} {'Actual':>8} {'Baseline':>10} {'Delta':>7}  Estado")
    print("  " + "-" * 60)
    for p in pares:
        cur  = f"{p['corr_actual']:+.2f}"  if p["corr_actual"]  is not None else "  N/A"
        base = f"{p['corr_baseline']:+.2f}" if p["corr_baseline"] is not None else "  N/A"
        dlt  = f"{p['delta']:.2f}"          if p["delta"]         is not None else " N/A"
        estado = "ALERTA" if p["alerta"] else ("Rota" if p["rota"] else "Normal")
        print(f"  {p['par']:<22} {cur:>8} {base:>10} {dlt:>7}  {estado}")

    if result["alertas"]:
        print(f"\n  ALERTAS DE CORRELACION:")
        for a in result["alertas"]:
            print(f"    - {a}")

    print(f"\n  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
