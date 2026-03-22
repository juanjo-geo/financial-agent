"""
Genera predicciones de direccion para las proximas 24h por indicador activo.

Metodo determinístico (sin ML):
  1. Tendencia lineal simple sobre los ultimos TREND_DAYS dias
  2. Momentum actual (change_pct de hoy)
  3. Alineacion con senales del dia (daily_signals.json)

Por indicador:
  direccion_24h     : Alcista / Bajista / Lateral
  magnitud_esperada : Leve (<1%) / Moderada (1-3%) / Significativa (>3%)
  confianza         : 1-10
  razon             : frase corta con lenguaje prudente

Salida: data/signals/predictions_24h.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT          = Path(__file__).parent.parent
HISTORY_FILE  = ROOT / "data/historical/market_history.csv"
SNAPSHOT_FILE = ROOT / "data/processed/latest_snapshot.csv"
SIGNALS_FILE  = ROOT / "data/signals/daily_signals.json"
CONFIG_FILE   = ROOT / "config.json"
OUTPUT_FILE   = ROOT / "data/signals/predictions_24h.json"

TREND_DAYS = 7

# ── Alineacion de senales por indicador ──────────────────────────────────────
# Key = f"{signal_field}_{signal_value}", Value = score aditivo
_ALIGNMENT: dict[str, dict[str, float]] = {
    "brent": {
        "presion_inflacionaria_Alcista": +1.2,
        "presion_inflacionaria_Bajista": -1.2,
        "sesgo_mercado_Risk-on":  +0.5,
        "sesgo_mercado_Risk-off": -0.5,
        "riesgo_macro_Alto":  -0.4,   # recession fear = less demand
        "riesgo_macro_Bajo":  +0.3,
    },
    "wti": {
        "presion_inflacionaria_Alcista": +1.2,
        "presion_inflacionaria_Bajista": -1.2,
        "sesgo_mercado_Risk-on":  +0.5,
        "sesgo_mercado_Risk-off": -0.5,
        "riesgo_macro_Alto": -0.4,
    },
    "gold": {
        "riesgo_macro_Alto":  +1.5,
        "riesgo_macro_Bajo":  -0.5,
        "sesgo_mercado_Risk-off": +1.0,
        "sesgo_mercado_Risk-on":  -0.5,
        "presion_inflacionaria_Alcista": +0.5,  # inflation hedge
        "presion_inflacionaria_Bajista": -0.3,
    },
    "silver": {
        "presion_inflacionaria_Alcista": +0.6,
        "presion_inflacionaria_Bajista": -0.6,
        "sesgo_mercado_Risk-on":  +0.4,
        "sesgo_mercado_Risk-off": -0.4,
        "riesgo_macro_Alto": -0.3,
    },
    "copper": {
        "sesgo_mercado_Risk-on":  +0.8,
        "sesgo_mercado_Risk-off": -0.8,
        "riesgo_macro_Alto": -0.6,
        "presion_inflacionaria_Alcista": +0.4,
    },
    "natgas": {
        "presion_inflacionaria_Alcista": +0.8,
        "presion_inflacionaria_Bajista": -0.8,
        "riesgo_macro_Alto": -0.2,
    },
    "btc": {
        "sesgo_mercado_Risk-on":  +1.8,
        "sesgo_mercado_Risk-off": -1.8,
        "riesgo_macro_Alto": -1.0,
        "riesgo_macro_Bajo": +0.8,
        "presion_inflacionaria_Alcista": -0.3,  # high inflation = tighter policy
    },
    "dxy": {
        "sesgo_mercado_Risk-off": +1.0,
        "sesgo_mercado_Risk-on":  -0.6,
        "riesgo_macro_Alto": +0.5,
        "presion_inflacionaria_Alcista": +0.3,
    },
    "usdcop": {
        "presion_cop_Alcista USD/COP":  +1.8,
        "presion_cop_Favorable COP":    -1.8,
        "sesgo_mercado_Risk-off": +0.8,
        "sesgo_mercado_Risk-on":  -0.5,
        "riesgo_macro_Alto": +0.5,
        "riesgo_macro_Bajo": -0.3,
    },
    "eurusd": {
        "sesgo_mercado_Risk-on":  +0.5,
        "sesgo_mercado_Risk-off": -0.5,
        "riesgo_macro_Alto": -0.4,
    },
    "sp500": {
        "sesgo_mercado_Risk-on":  +1.8,
        "sesgo_mercado_Risk-off": -2.0,
        "riesgo_macro_Bajo": +1.0,
        "riesgo_macro_Alto": -1.5,
        "presion_inflacionaria_Alcista": -0.5,
    },
    "nasdaq": {
        "sesgo_mercado_Risk-on":  +1.8,
        "sesgo_mercado_Risk-off": -2.0,
        "riesgo_macro_Alto": -2.0,
        "presion_inflacionaria_Alcista": -0.6,
    },
    # Acciones individuales: similar a sp500
    "aapl":  {"sesgo_mercado_Risk-on": +1.5, "sesgo_mercado_Risk-off": -1.5, "riesgo_macro_Alto": -1.0},
    "msft":  {"sesgo_mercado_Risk-on": +1.5, "sesgo_mercado_Risk-off": -1.5, "riesgo_macro_Alto": -1.0},
    "nvda":  {"sesgo_mercado_Risk-on": +2.0, "sesgo_mercado_Risk-off": -2.0, "riesgo_macro_Alto": -1.5},
    "amzn":  {"sesgo_mercado_Risk-on": +1.5, "sesgo_mercado_Risk-off": -1.5, "riesgo_macro_Alto": -1.0},
    "googl": {"sesgo_mercado_Risk-on": +1.5, "sesgo_mercado_Risk-off": -1.5, "riesgo_macro_Alto": -1.0},
    "meta":  {"sesgo_mercado_Risk-on": +1.5, "sesgo_mercado_Risk-off": -1.5, "riesgo_macro_Alto": -1.0},
    "tsla":  {"sesgo_mercado_Risk-on": +2.0, "sesgo_mercado_Risk-off": -2.0, "riesgo_macro_Alto": -1.5},
}
_DEFAULT_ALIGNMENT: dict[str, float] = {
    "sesgo_mercado_Risk-on": +0.5,
    "sesgo_mercado_Risk-off": -0.5,
}


# ── Utilidades ────────────────────────────────────────────────────────────────

def _linear_slope_pct(values: list[float]) -> float:
    """Pendiente lineal diaria como % del valor medio. Implementacion manual sin numpy."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_v = sum(values) / n
    if mean_v == 0:
        return 0.0
    x_mean = (n - 1) / 2.0
    num = sum((i - x_mean) * (v - mean_v) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    slope = num / den
    return (slope / mean_v) * 100.0  # % por dia


def _dir_from_score(score: float, threshold: float = 0.30) -> str:
    if score > threshold:
        return "alcista"
    elif score < -threshold:
        return "bajista"
    return "lateral"


def _magnitude(total_score: float, indicator: str) -> str:
    """Magnitude based on absolute composite score, calibrated per asset class."""
    abs_s = abs(total_score)
    # High-vol assets need larger score for same label
    high_vol = {"btc", "tsla", "nvda"}
    low_vol  = {"dxy", "usdcop", "eurusd", "global_inflation_proxy"}

    if indicator in high_vol:
        if abs_s >= 1.8: return "Significativa"
        if abs_s >= 0.6: return "Moderada"
        return "Leve"
    elif indicator in low_vol:
        if abs_s >= 1.2: return "Significativa"
        if abs_s >= 0.4: return "Moderada"
        return "Leve"
    else:
        if abs_s >= 1.4: return "Significativa"
        if abs_s >= 0.5: return "Moderada"
        return "Leve"


def _confidence(trend_dir: str, momentum_dir: str, signal_dir: str,
                n_points: int, total_score: float) -> int:
    dirs = [trend_dir, momentum_dir, signal_dir]
    non_neutral = [d for d in dirs if d != "lateral"]

    if not non_neutral:
        return 3

    dominant = max(set(non_neutral), key=non_neutral.count)
    agreements    = sum(1 for d in dirs if d == dominant)
    contradictions = sum(1 for d in dirs if d not in ("lateral", dominant))

    base = 2 + agreements * 2 - contradictions

    # Bonus: more data = more reliable trend
    if n_points >= 6:
        base += 1
    elif n_points < 3:
        base -= 1

    # Bonus: strong score = more conviction
    if abs(total_score) >= 1.5:
        base += 1

    return max(1, min(9, int(base)))


def _reason(indicator: str, direction: str, trend_score: float, momentum_score: float,
            signal_score: float, slope_pct: float, momentum_pct: float,
            signals: dict) -> str:
    """Genera frase explicativa con lenguaje prudente segun factor dominante."""
    dir_phrase = {
        "Alcista": "continuacion alcista",
        "Bajista": "presion bajista",
        "Lateral": "movimiento lateral o consolidacion",
    }.get(direction, direction.lower())

    # Pesos efectivos de cada componente
    t_w = abs(trend_score * 0.5)
    m_w = abs(momentum_score * 0.3)
    s_w = abs(signal_score * 0.2)

    sesgo    = signals.get("sesgo_mercado",         "Mixto")
    riesgo   = signals.get("riesgo_macro",          "Medio")
    inflacion = signals.get("presion_inflacionaria", "Neutral")

    if t_w >= m_w and t_w >= s_w and abs(slope_pct) >= 0.10:
        trend_qual = "positiva" if slope_pct > 0 else "negativa"
        return (f"La tendencia de {TREND_DAYS}d ({slope_pct:+.2f}%/dia) es {trend_qual} "
                f"y apunta a {dir_phrase}.")

    elif m_w >= s_w and abs(momentum_pct) >= 0.25:
        if direction == "Lateral":
            return (f"El movimiento de hoy ({momentum_pct:+.1f}%) no sugiere una "
                    f"ruptura de rango clara en las proximas 24h.")
        return (f"El momentum actual ({momentum_pct:+.1f}% hoy) podria sostener "
                f"la {dir_phrase} en el corto plazo.")

    else:
        # Signals dominan
        asset_group = {
            "btc": "activos especulativos",
            "sp500": "renta variable",
            "nasdaq": "tecnologicas",
            "aapl": "acciones",
            "msft": "acciones",
            "nvda": "acciones",
            "amzn": "acciones",
            "googl": "acciones",
            "meta": "acciones",
            "tsla": "acciones",
            "gold": "metales preciosos",
            "silver": "metales preciosos",
            "copper": "metales industriales",
            "brent": "el petroleo",
            "wti":   "el petroleo",
            "dxy":   "el dolar global",
            "usdcop":"el tipo de cambio",
            "natgas":"el gas natural",
        }.get(indicator, "el activo")

        if indicator in ("btc", "sp500", "nasdaq", "aapl", "msft", "nvda",
                         "amzn", "googl", "meta", "tsla"):
            return (f"El sesgo de mercado ({sesgo}) y el riesgo macro ({riesgo}) "
                    f"sugieren {dir_phrase} para {asset_group}.")
        elif indicator in ("gold", "silver"):
            return (f"Las condiciones macro (riesgo {riesgo}, inflacion {inflacion}) "
                    f"podrian respaldar {dir_phrase} en {asset_group}.")
        elif indicator in ("brent", "wti", "natgas"):
            return (f"La presion inflacionaria ({inflacion}) y el sesgo ({sesgo}) "
                    f"apuntan a {dir_phrase} para {asset_group}.")
        elif indicator == "usdcop":
            cop = signals.get("presion_cop", "Neutral")
            return (f"La presion COP ({cop}) junto al sesgo ({sesgo}) "
                    f"sugieren {dir_phrase} en el par.")
        else:
            return (f"Las senales del dia (sesgo {sesgo}, riesgo {riesgo}) "
                    f"podrian reflejar {dir_phrase}.")


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_active_indicators() -> list[str]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f).get("active_indicators", [])
        except Exception:
            pass
    return ["brent", "btc", "dxy", "usdcop", "gold"]


def _load_history() -> pd.DataFrame:
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    df = pd.read_csv(HISTORY_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    df["value"]     = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["timestamp", "value"])


def _load_snapshot() -> dict[str, float]:
    if not SNAPSHOT_FILE.exists():
        return {}
    df = pd.read_csv(SNAPSHOT_FILE)
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        pct = pd.to_numeric(row.get("change_pct"), errors="coerce")
        if pd.notna(pct):
            out[str(row["indicator"]).lower()] = float(pct)
    return out


def _load_signals() -> dict:
    if SIGNALS_FILE.exists():
        try:
            with open(SIGNALS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ── Core predictor ────────────────────────────────────────────────────────────

def predict_indicator(
    indicator: str,
    hist_df: pd.DataFrame,
    momentum_pct: float,
    signals: dict,
) -> dict:
    """Genera prediccion para un indicador usando tendencia + momentum + senales."""

    # ── 1. Tendencia lineal (últimos TREND_DAYS dias) ──────────────────────────
    today   = hist_df["timestamp"].max().normalize()
    cutoff  = today - pd.Timedelta(days=TREND_DAYS)
    ind_df  = hist_df[
        (hist_df["indicator"] == indicator)
        & (hist_df["timestamp"].dt.normalize() >= cutoff)
    ].sort_values("timestamp")

    values   = ind_df["value"].dropna().tolist()
    n_points = len(values)
    slope_pct = _linear_slope_pct(values) if n_points >= 2 else 0.0

    # Normalize slope to score: 1%/day slope -> score ±2
    trend_score = max(-3.0, min(3.0, slope_pct * 2.0))

    # ── 2. Momentum ────────────────────────────────────────────────────────────
    # Momentum has shorter-horizon signal; dampen for 24h prediction
    momentum_score = max(-3.0, min(3.0, momentum_pct * 0.5))

    # ── 3. Señales de mercado ──────────────────────────────────────────────────
    s = signals.get("senales", {})
    alignment = _ALIGNMENT.get(indicator, _DEFAULT_ALIGNMENT)
    signal_score = 0.0
    for field, value in s.items():
        if not isinstance(value, str):
            continue
        key = f"{field}_{value}"
        signal_score += alignment.get(key, 0.0)
    signal_score = max(-3.0, min(3.0, signal_score))

    # ── 4. Score compuesto ────────────────────────────────────────────────────
    total = 0.5 * trend_score + 0.3 * momentum_score + 0.2 * signal_score

    # ── 5. Clasificacion ──────────────────────────────────────────────────────
    # Threshold reduced for proxy indicators (always 0 change)
    threshold = 0.15 if indicator == "global_inflation_proxy" else 0.30
    direction_str = _dir_from_score(total, threshold)
    direction = {"alcista": "Alcista", "bajista": "Bajista", "lateral": "Lateral"}[direction_str]

    magnitude = "Leve" if direction == "Lateral" else _magnitude(total, indicator)

    # Confidence
    trend_dir    = _dir_from_score(trend_score)
    momentum_dir = _dir_from_score(momentum_score * 0.6)  # dampened momentum direction
    signal_dir   = _dir_from_score(signal_score)
    confidence   = _confidence(trend_dir, momentum_dir, signal_dir, n_points, total)

    reason = _reason(indicator, direction, trend_score, momentum_score,
                     signal_score, slope_pct, momentum_pct, s)

    return {
        "direccion_24h":     direction,
        "magnitud_esperada": magnitude,
        "confianza":         confidence,
        "razon":             reason,
        # Debug / transparency fields
        "_slope_pct_dia":    round(slope_pct, 4),
        "_momentum_pct":     round(momentum_pct, 4),
        "_trend_score":      round(trend_score, 3),
        "_momentum_score":   round(momentum_score, 3),
        "_signal_score":     round(signal_score, 3),
        "_total_score":      round(total, 3),
        "_n_puntos_7d":      n_points,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run_predictor() -> dict:
    active   = _load_active_indicators()
    hist_df  = _load_history()
    snapshot = _load_snapshot()
    signals  = _load_signals()

    predictions: dict[str, dict] = {}
    for ind in active:
        momentum_pct = snapshot.get(ind, 0.0)
        predictions[ind] = predict_indicator(ind, hist_df, momentum_pct, signals)

    result = {
        "fecha":        datetime.now().strftime("%Y-%m-%d"),
        "generado_en":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "predicciones": predictions,
    }
    return result


def main():
    print("Generando predicciones 24h...")
    result = run_predictor()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Copia fechada para evaluacion ex-post del dia siguiente
    dated_file = OUTPUT_FILE.parent / f"predictions_24h_{result['fecha']}.json"
    with open(dated_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Copia fechada: {dated_file.name}")

    print(f"\n{'Indicador':<28} {'Dir':^10} {'Magnitud':^14} {'Conf':^6}  Razon")
    print("-" * 90)
    for ind, p in result["predicciones"].items():
        arrow = {"Alcista": "^", "Bajista": "v", "Lateral": "-"}.get(p["direccion_24h"], "?")
        print(
            f"  {ind:<26} {arrow} {p['direccion_24h']:<8}  {p['magnitud_esperada']:<12}  "
            f"{p['confianza']}/10   {p['razon']}"
        )

    print(f"\n  Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
