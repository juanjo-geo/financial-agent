"""
backtester.py
-------------
Evalúa históricamente si las señales del agente (sesgo_mercado, riesgo_macro)
tienen poder predictivo sobre el movimiento de BTC al día siguiente.

Estrategia simulada:
  - Risk-on  → LONG BTC (invertir 100% del capital en BTC overnight)
  - Risk-off → CASH    (salir de BTC ese día)
  - Mixto    → HOLD    (mantener posición anterior)

Benchmarks:
  - Buy & Hold BTC
  - Estrategia aleatoria (promedio de 1000 simulaciones)

Salida:
  - data/signals/backtest_results.json  (resultados estructurados)
  - reports/backtest_report.txt         (reporte narrativo)

Uso:
  python -m intelligence.backtester
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT              = Path(__file__).parent.parent
SIGNALS_FILE      = ROOT / "data/signals/signals_history.csv"
MARKET_FILE       = ROOT / "data/historical/market_history.csv"
EVAL_LOG_FILE     = ROOT / "data/signals/evaluation_log.csv"
RESULTS_FILE      = ROOT / "data/signals/backtest_results.json"
REPORT_FILE       = ROOT / "reports/backtest_report.txt"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_btc_prices() -> pd.DataFrame:
    """Retorna DataFrame con fecha → precio de cierre de BTC."""
    df = pd.read_csv(MARKET_FILE, parse_dates=["timestamp"])
    btc = df[df["indicator"] == "btc"].copy()
    btc["date"] = btc["timestamp"].dt.normalize()
    btc = btc.sort_values("date").drop_duplicates("date", keep="last")
    btc = btc[["date", "value"]].rename(columns={"value": "btc_close"})
    return btc.reset_index(drop=True)


def load_signals() -> pd.DataFrame:
    df = pd.read_csv(SIGNALS_FILE, parse_dates=["fecha"])
    df = df.rename(columns={"fecha": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.sort_values("date").reset_index(drop=True)


def load_eval_log() -> pd.DataFrame:
    df = pd.read_csv(EVAL_LOG_FILE)
    return df


# ── Estrategia principal ──────────────────────────────────────────────────────

def run_strategy(merged: pd.DataFrame) -> dict:
    """
    Simula la estrategia señal-driven vs buy&hold.
    merged debe tener: date, sesgo_mercado, btc_return_next (retorno BTC día t+1).
    """
    capital_strategy  = 1.0
    capital_bah       = 1.0
    in_position       = True  # buy&hold empieza invertido

    equity_strategy: list[float] = [1.0]
    equity_bah:      list[float] = [1.0]

    trades: list[dict] = []
    wins = 0
    losses = 0
    neutral = 0
    prev_position = None  # None, "LONG", "CASH"

    for _, row in merged.iterrows():
        sesgo  = row["sesgo_mercado"]
        ret    = row["btc_return_next"]   # retorno del siguiente día

        # Decidir posición hoy basada en la señal de hoy
        if sesgo == "Risk-on":
            position = "LONG"
        elif sesgo == "Risk-off":
            position = "CASH"
        else:  # Mixto → mantener posición anterior
            position = prev_position if prev_position else "LONG"

        # Calcular P&L de la estrategia
        if position == "LONG":
            pnl = ret
            capital_strategy *= (1 + ret)
            if ret > 0:
                wins += 1
            elif ret < 0:
                losses += 1
            else:
                neutral += 1
        else:
            pnl = 0.0  # en cash, no hay retorno

        # Buy & Hold siempre en posición
        capital_bah *= (1 + ret)

        equity_strategy.append(capital_strategy)
        equity_bah.append(capital_bah)

        trades.append({
            "date":     str(row["date"].date()),
            "sesgo":    sesgo,
            "position": position,
            "ret_btc":  round(ret * 100, 3),
            "ret_strat": round(pnl * 100, 3),
        })

        prev_position = position

    return {
        "capital_strategy": capital_strategy,
        "capital_bah":      capital_bah,
        "equity_strategy":  equity_strategy,
        "equity_bah":       equity_bah,
        "trades":           trades,
        "wins":             wins,
        "losses":           losses,
        "neutral":          neutral,
    }


def max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def sharpe_ratio(returns: list[float], rf: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    import statistics
    mean = statistics.mean(returns) - rf
    std  = statistics.stdev(returns)
    if std == 0:
        return 0.0
    return round((mean / std) * (252 ** 0.5), 2)  # anualizado


def random_benchmark(merged: pd.DataFrame, n_sims: int = 1000) -> float:
    """Promedio de capital final de estrategias aleatorias (Long/Cash al azar)."""
    returns = merged["btc_return_next"].tolist()
    totals = []
    for _ in range(n_sims):
        cap = 1.0
        for r in returns:
            if random.random() > 0.5:  # long
                cap *= (1 + r)
        totals.append(cap)
    return sum(totals) / len(totals)


# ── Análisis de predicciones por indicador ────────────────────────────────────

def analyze_predictions(df_eval: pd.DataFrame) -> dict:
    results = {}
    for indicator, grp in df_eval.groupby("indicador"):
        acc = grp["acerto"].mean()
        n   = len(grp)
        # Por dirección
        by_dir = grp.groupby("direccion_predicha")["acerto"].agg(["mean", "count"])
        by_dir = {k: {"accuracy": round(v["mean"]*100, 1), "n": int(v["count"])}
                  for k, v in by_dir.iterrows()}
        results[indicator] = {
            "accuracy_global": round(acc * 100, 1),
            "n": n,
            "por_direccion": by_dir,
        }
    return results


# ── Correlación señal → retorno BTC ──────────────────────────────────────────

def signal_btc_correlation(merged: pd.DataFrame) -> dict:
    """Para cada tipo de señal, calcula el retorno promedio de BTC al día siguiente."""
    result = {}
    for sesgo, grp in merged.groupby("sesgo_mercado"):
        rets = grp["btc_return_next"] * 100
        result[sesgo] = {
            "n":            len(grp),
            "btc_ret_mean": round(rets.mean(), 3),
            "btc_ret_std":  round(rets.std(), 3),
            "pct_positive": round((rets > 0).mean() * 100, 1),
            "pct_negative": round((rets < 0).mean() * 100, 1),
        }
    # Convicción alta vs baja
    high_conv = merged[merged["conviccion"] >= 7]
    low_conv  = merged[merged["conviccion"] < 7]
    result["alta_conviccion"]  = {
        "n":            len(high_conv),
        "btc_ret_mean": round((high_conv["btc_return_next"]*100).mean(), 3) if len(high_conv) else None,
        "pct_positive": round((high_conv["btc_return_next"] > 0).mean()*100, 1) if len(high_conv) else None,
    }
    result["baja_conviccion"]  = {
        "n":            len(low_conv),
        "btc_ret_mean": round((low_conv["btc_return_next"]*100).mean(), 3) if len(low_conv) else None,
        "pct_positive": round((low_conv["btc_return_next"] > 0).mean()*100, 1) if len(low_conv) else None,
    }
    return result


# ── Reporte narrativo ─────────────────────────────────────────────────────────

def build_report(results: dict) -> str:
    s      = results["strategy"]
    corr   = results["signal_btc_correlation"]
    preds  = results["prediction_accuracy"]
    meta   = results["meta"]

    ret_strat = (s["capital_strategy"] - 1) * 100
    ret_bah   = (s["capital_bah"] - 1) * 100
    ret_rand  = (s["random_benchmark"] - 1) * 100
    n_trades  = s["n_trades"]
    win_rate  = round(s["wins"] / max(s["wins"] + s["losses"], 1) * 100, 1)

    lines = [
        "BACKTEST — AGENTE FINANCIERO AUTÓNOMO",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Período evaluado: {meta['fecha_inicio']} → {meta['fecha_fin']}  ({meta['n_dias']} días con señal y precio BTC)",
        "=" * 60,
        "",
        "SECCIÓN 1 — RENDIMIENTO ESTRATEGIA vs BENCHMARKS",
        "-" * 60,
        f"  Estrategia señal-driven : {ret_strat:+.2f}%",
        f"  Buy & Hold BTC          : {ret_bah:+.2f}%",
        f"  Benchmark aleatorio     : {ret_rand:+.2f}%",
        f"  Alpha vs B&H            : {ret_strat - ret_bah:+.2f}%",
        f"  Alpha vs aleatorio      : {ret_strat - ret_rand:+.2f}%",
        "",
        "SECCIÓN 2 — MÉTRICAS DE RIESGO",
        "-" * 60,
        f"  Max Drawdown estrategia : {s['max_drawdown_strategy']*100:.2f}%",
        f"  Max Drawdown B&H        : {s['max_drawdown_bah']*100:.2f}%",
        f"  Sharpe ratio estrategia : {s['sharpe_strategy']}",
        f"  Sharpe ratio B&H        : {s['sharpe_bah']}",
        "",
        "SECCIÓN 3 — ESTADÍSTICAS DE OPERACIONES",
        "-" * 60,
        f"  Días con señal (n)      : {n_trades}",
        f"  Días LONG (Risk-on)     : {s['n_long']}",
        f"  Días CASH (Risk-off)    : {s['n_cash']}",
        f"  Días HOLD (Mixto)       : {s['n_hold']}",
        f"  Win rate (días en LONG) : {win_rate}%",
        f"  Victorias / Derrotas    : {s['wins']} / {s['losses']}",
        "",
        "SECCIÓN 4 — CORRELACIÓN SEÑAL → RETORNO BTC (DÍA SIGUIENTE)",
        "-" * 60,
    ]

    for sesgo in ["Risk-on", "Risk-off", "Mixto"]:
        if sesgo in corr:
            c = corr[sesgo]
            lines.append(
                f"  {sesgo:<12}: n={c['n']:>3}  BTC_ret_med={c['btc_ret_mean']:>+7.3f}%  "
                f"% positivos={c['pct_positive']:>5.1f}%"
            )

    lines += [
        "",
        "  Convicción ≥7            :",
        f"    n={corr['alta_conviccion']['n']}  BTC_ret_med={corr['alta_conviccion']['btc_ret_mean']:>+7.3f}%  "
        f"% positivos={corr['alta_conviccion']['pct_positive']:>5.1f}%",
        "  Convicción <7            :",
        f"    n={corr['baja_conviccion']['n']}  BTC_ret_med={corr['baja_conviccion']['btc_ret_mean']:>+7.3f}%  "
        f"% positivos={corr['baja_conviccion']['pct_positive']:>5.1f}%",
        "",
        "SECCIÓN 5 — PRECISIÓN DE PREDICCIONES 24H",
        "-" * 60,
    ]

    for ind, p in sorted(preds.items()):
        lines.append(f"  {ind:<10}: {p['accuracy_global']:>5.1f}% accuracy  (n={p['n']})")

    lines += [
        "",
        "SECCIÓN 6 — INTERPRETACIÓN",
        "-" * 60,
    ]

    # Interpretación dinámica
    if ret_strat > ret_bah:
        lines.append(
            f"  La estrategia señal-driven SUPERA al buy & hold en {ret_strat - ret_bah:+.2f}%,"
        )
        lines.append("  sugiriendo que las señales de sesgo tienen poder predictivo real.")
    else:
        lines.append(
            f"  La estrategia señal-driven queda por debajo del buy & hold en {ret_strat - ret_bah:.2f}%."
        )
        lines.append("  Esto sugiere que la política de salirse en Risk-off perdió más upside del que protegió.")

    ri_corr = corr.get("Risk-on", {})
    ro_corr = corr.get("Risk-off", {})
    if ri_corr and ro_corr:
        diff = ri_corr["btc_ret_mean"] - ro_corr["btc_ret_mean"]
        lines.append(
            f"  El diferencial de retorno BTC entre Risk-on y Risk-off es {diff:+.3f}%,"
        )
        if abs(diff) > 0.3:
            lines.append("  lo que indica una separación estadísticamente relevante entre ambos regímenes.")
        else:
            lines.append("  diferencial pequeño — las señales aún no discriminan fuertemente entre regímenes.")

    ac = corr.get("alta_conviccion", {})
    if ac.get("n", 0) > 3:
        lines.append(
            f"  Con convicción ≥7 (n={ac['n']}), el retorno medio de BTC es {ac['btc_ret_mean']:+.3f}% "
            f"con {ac['pct_positive']:.0f}% de días positivos."
        )

    lines += [
        "",
        "SECCIÓN 7 — OPERACIONES DETALLE",
        "-" * 60,
        f"  {'Fecha':<12} {'Señal':<10} {'Posición':<8} {'BTC%':>7} {'Strat%':>8}",
        f"  {'-'*12} {'-'*10} {'-'*8} {'-'*7} {'-'*8}",
    ]
    for t in results["trades"]:
        lines.append(
            f"  {t['date']:<12} {t['sesgo']:<10} {t['position']:<8} "
            f"{t['ret_btc']:>+7.3f} {t['ret_strat']:>+8.3f}"
        )

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Cargando datos...")
    btc    = load_btc_prices()
    signals = load_signals()
    df_eval = load_eval_log()

    print(f"  BTC: {len(btc)} días  |  Señales: {len(signals)} días  |  Eval log: {len(df_eval)} registros")

    # Merge: señal del día t con precio de cierre de t
    merged = signals.merge(btc, on="date", how="inner")

    # Para cada fila, buscar el siguiente precio BTC disponible (t+1 o siguiente día hábil)
    def find_next_btc(signal_date):
        future = btc[btc["date"] > signal_date]
        if future.empty:
            return None
        return future.iloc[0]["btc_close"]

    merged["btc_close_next"] = merged["date"].apply(find_next_btc)

    # Eliminar filas sin precio del día siguiente
    merged = merged.dropna(subset=["btc_close", "btc_close_next"]).copy()
    merged["btc_return_next"] = (merged["btc_close_next"] - merged["btc_close"]) / merged["btc_close"]

    print(f"  Días con señal Y precio BTC t+1: {len(merged)}")

    # Correr estrategia
    strat = run_strategy(merged)

    # Calcular métricas adicionales
    strat_returns = [t["ret_strat"] / 100 for t in strat["trades"]]
    bah_returns   = [t["ret_btc"] / 100 for t in strat["trades"]]

    n_long = sum(1 for t in strat["trades"] if t["position"] == "LONG")
    n_cash = sum(1 for t in strat["trades"] if t["position"] == "CASH")
    n_hold = sum(1 for t in strat["trades"] if t["position"] == "HOLD")

    print("Corriendo benchmark aleatorio (1000 simulaciones)...")
    rand_cap = random_benchmark(merged)

    # Correlación señal → BTC
    signal_corr = signal_btc_correlation(merged)

    # Predicciones
    pred_acc = analyze_predictions(df_eval)

    results = {
        "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "meta": {
            "fecha_inicio": str(merged["date"].min().date()),
            "fecha_fin":    str(merged["date"].max().date()),
            "n_dias":       len(merged),
        },
        "strategy": {
            "capital_strategy":       round(strat["capital_strategy"], 6),
            "capital_bah":            round(strat["capital_bah"], 6),
            "random_benchmark":       round(rand_cap, 6),
            "return_strategy_pct":    round((strat["capital_strategy"] - 1) * 100, 3),
            "return_bah_pct":         round((strat["capital_bah"] - 1) * 100, 3),
            "return_random_pct":      round((rand_cap - 1) * 100, 3),
            "alpha_vs_bah":           round((strat["capital_strategy"] - strat["capital_bah"]) * 100, 3),
            "max_drawdown_strategy":  round(max_drawdown(strat["equity_strategy"]), 6),
            "max_drawdown_bah":       round(max_drawdown(strat["equity_bah"]), 6),
            "sharpe_strategy":        sharpe_ratio(strat_returns),
            "sharpe_bah":             sharpe_ratio(bah_returns),
            "n_trades":               len(merged),
            "n_long":                 n_long,
            "n_cash":                 n_cash,
            "n_hold":                 n_hold,
            "wins":                   strat["wins"],
            "losses":                 strat["losses"],
            "neutral":                strat["neutral"],
        },
        "signal_btc_correlation": signal_corr,
        "prediction_accuracy":    pred_acc,
        "trades":                 strat["trades"],
    }

    # Guardar JSON
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = RESULTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, RESULTS_FILE)
    print(f"  Resultados guardados en: {RESULTS_FILE}")

    # Generar reporte
    report_text = build_report(results)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_r = REPORT_FILE.with_suffix(".tmp")
    tmp_r.write_text(report_text, encoding="utf-8")
    os.replace(tmp_r, REPORT_FILE)
    print(f"  Reporte guardado en: {REPORT_FILE}")

    # Imprimir resumen
    s = results["strategy"]
    print()
    print("=" * 50)
    print("RESUMEN BACKTEST")
    print("=" * 50)
    print(f"  Estrategia : {s['return_strategy_pct']:+.2f}%")
    print(f"  Buy & Hold : {s['return_bah_pct']:+.2f}%")
    print(f"  Aleatorio  : {s['return_random_pct']:+.2f}%")
    print(f"  Sharpe     : {s['sharpe_strategy']}")
    print(f"  Max DD     : {s['max_drawdown_strategy']*100:.2f}%")


if __name__ == "__main__":
    main()
